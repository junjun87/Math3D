"""
立体几何计算核心（基于 sympy 精确符号运算）

设计目标：坐标、向量、最终答案全部由本模块精确算出，
杜绝心算误差。同一套坐标既喂给解题文案，也喂给 3D 渲染，
保证"图、解、答"严格一致。

坐标约定（数学坐标，z 轴向上）：
  - 题面/公式里展示数学坐标。
  - 3D 渲染坐标采用 three.js 约定（y 轴向上）：three = (x, z, y) * scale。
"""
from __future__ import annotations

import hashlib
import logging
import random as _random
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import sympy as sp

import llm_parser
from solver_registry import get_solver, list_supported_types, register_solver

logger = logging.getLogger(__name__)

sqrt = sp.sqrt


# ══════════════════════════════════════════════════════════════════════════════
# 基础工具
# ══════════════════════════════════════════════════════════════════════════════

def V(*comps):
    """构造列向量（sympy.Matrix）。"""
    if len(comps) == 1 and isinstance(comps[0], (list, tuple)):
        comps = comps[0]
    return sp.Matrix([sp.sympify(c) for c in comps])


def midpoint(a, b):
    """两点中点。"""
    return (a + b) / 2


def normal_from_points(p, q, r):
    """由平面上三点求法向量（叉积）。"""
    return (q - p).cross(r - p)


def simplify_vec(v):
    """把向量按公因子约简到最简整系数方向（仅用于展示"简化取 n=…"）。"""
    v = sp.Matrix([sp.simplify(c) for c in v])
    nonzero = [c for c in v if c != 0]
    if not nonzero:
        return v
    g = nonzero[0]
    for c in nonzero[1:]:
        g = sp.gcd(g, c)
    if g != 0:
        cand = sp.simplify(v / g)
        if all(c.is_rational for c in cand):
            return cand
    return v


def line_plane_angle_sin(line_dir, normal):
    """线面角正弦：sinθ = |v·n| / (|v||n|)。"""
    v, n = line_dir, normal
    return sp.simplify(sp.Abs(v.dot(n)) / (v.norm() * n.norm()))


def line_line_angle_cos(d1, d2):
    """异面直线夹角余弦：cosθ = |d1·d2| / (|d1||d2|)。"""
    return sp.simplify(sp.Abs(d1.dot(d2)) / (d1.norm() * d2.norm()))


def point_plane_distance(point, plane_point, normal):
    """点到平面距离：|(P-P0)·n| / |n|。"""
    return sp.simplify(sp.Abs((point - plane_point).dot(normal)) / normal.norm())


def dihedral_cos(A, B, C, D):
    """二面角 C-AB-D 的余弦：在两个半平面内各取垂直于棱 AB 的向量再求夹角。"""
    u = B - A
    def _perp(P):
        w = P - A
        return w - (w.dot(u) / u.dot(u)) * u
    v1, v2 = _perp(C), _perp(D)
    return sp.simplify(v1.dot(v2) / (v1.norm() * v2.norm()))


def dihedral_cos_from_normals(n1, n2):
    """由两半平面法向量求二面角余弦。"""
    return sp.simplify(n1.dot(n2) / (n1.norm() * n2.norm()))


# --- 体积 ---

def volume_box(lx, ly, lz):
    return sp.simplify(sp.sympify(lx) * sp.sympify(ly) * sp.sympify(lz))


def volume_prism(base_area, height):
    return sp.simplify(sp.sympify(base_area) * sp.sympify(height))


def volume_pyramid(base_area, height):
    return sp.simplify(sp.Rational(1, 3) * sp.sympify(base_area) * sp.sympify(height))


def volume_tetra(A, B, C, D):
    """四面体体积 = |(AB×AC)·AD| / 6。"""
    return sp.simplify(sp.Abs((B - A).cross(C - A).dot(D - A)) / 6)


# --- LaTeX 输出 ---

def tex(expr):
    return sp.latex(sp.simplify(expr))


def tex_vec(v):
    return "(" + ", ".join(sp.latex(sp.simplify(c)) for c in v) + ")"


def is_clean(expr, max_ops=7, max_radicand=60):
    """判断答案是否"规整"：化简后复杂度低、无嵌套根式。

    用于随机出题：参数随机求解后，答案不规整就重抽。
    """
    e = sp.radsimp(sp.nsimplify(sp.simplify(expr)))
    if e.has(sp.zoo, sp.nan, sp.oo) or e.free_symbols:
        return False
    if sp.count_ops(e) > max_ops:
        return False
    for p in e.atoms(sp.Pow):
        if p.exp == sp.Rational(1, 2):
            rad = p.base
            if not (rad.is_Integer and 0 <= int(rad) <= max_radicand):
                return False
            if rad.atoms(sp.Pow):
                return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 坐标映射：数学坐标 (z 向上) → three.js 坐标 (y 向上)
# ══════════════════════════════════════════════════════════════════════════════

def to_three(points: dict, scale=1.5) -> dict:
    """{name: 数学向量} → {name: [x, y, z] 浮点（three.js: y 向上）}。

    three = (x, z, y) * scale
    """
    s = sp.Float(scale)
    out = {}
    for name, p in points.items():
        mx, my, mz = p[0], p[1], p[2]
        three = (mx * s, mz * s, my * s)
        out[name] = [float(c) for c in three]
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 数据类
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Point:
    name: str
    coords: tuple

    def __post_init__(self):
        self.x, self.y, self.z = [sp.Rational(c) for c in self.coords]

    def vec(self) -> sp.Matrix:
        return sp.Matrix([self.x, self.y, self.z])

    def three_json(self) -> dict:
        return {"name": self.name, "x": float(self.x), "y": float(self.y), "z": float(self.z)}


@dataclass
class Segment:
    name: str
    p1: Point
    p2: Point

    def three_json(self) -> dict:
        return {"name": self.name, "from": self.p1.name, "to": self.p2.name}


@dataclass
class SolidModel:
    points: List[Point] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    highlight_segments: List[Segment] = field(default_factory=list)
    highlight_plane_points: List[str] = field(default_factory=list)

    def to_three(self) -> dict:
        return {
            "points": [p.three_json() for p in self.points],
            "segments": [s.three_json() for s in self.segments],
            "highlightSegments": [s.three_json() for s in self.highlight_segments],
            "highlightPlanePoints": self.highlight_plane_points,
        }


@dataclass
class Solution:
    problem: str
    steps: List[dict]
    answer_latex: str
    answer_value: float
    model: SolidModel
    # 扩展字段：支持 lesson data 格式
    lesson_meta: str = ""
    answer_label: str = ""
    three_points: dict = field(default_factory=dict)
    spheres: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    elements: dict = field(default_factory=dict)
    target: list = field(default_factory=list)
    initial_camera: list = field(default_factory=list)
    scale: float = 1.5


# ══════════════════════════════════════════════════════════════════════════════
# 几何体构建库（数学坐标，z 轴向上）
# ══════════════════════════════════════════════════════════════════════════════

def build_cuboid(lx, ly, lz) -> Dict[str, sp.Matrix]:
    """长方体 ABCD-A1B1C1D1：A 在原点，AB 沿 x，AD 沿 y，AA1 沿 z。"""
    lx, ly, lz = sp.sympify(lx), sp.sympify(ly), sp.sympify(lz)
    return {
        "A": V(0, 0, 0), "B": V(lx, 0, 0), "C": V(lx, ly, 0), "D": V(0, ly, 0),
        "A1": V(0, 0, lz), "B1": V(lx, 0, lz), "C1": V(lx, ly, lz), "D1": V(0, ly, lz),
    }


def build_cube(edge=2) -> Dict[str, sp.Matrix]:
    """正方体（长方体特例）。"""
    return build_cuboid(edge, edge, edge)


def build_regular_quad_pyramid(base_edge, height) -> Dict[str, sp.Matrix]:
    """正四棱锥 P-ABCD：底面中心 O 为原点，对角线 AC 在 x 轴、BD 在 y 轴，顶点 P 在 z 轴。"""
    a = sp.sympify(base_edge)
    h = sp.sympify(height)
    d = sp.simplify(a / sqrt(2))  # 半对角线 = a√2/2
    return {
        "O": V(0, 0, 0),
        "A": V(d, 0, 0),
        "C": V(-d, 0, 0),
        "B": V(0, d, 0),
        "D": V(0, -d, 0),
        "P": V(0, 0, h),
    }


def build_regular_tetrahedron(edge=None):
    """正四面体 ABCD（默认棱长 2√2 时坐标为整数）。"""
    if edge is None:
        edge = 2 * sqrt(2)
    base = {
        "A": V(1, 1, 1),
        "B": V(1, -1, -1),
        "C": V(-1, 1, -1),
        "D": V(-1, -1, 1),
    }
    k = sp.simplify(sp.sympify(edge) / (2 * sqrt(2)))
    return {name: sp.simplify(k * v) for name, v in base.items()}


# ══════════════════════════════════════════════════════════════════════════════
# 题型求解器
# ══════════════════════════════════════════════════════════════════════════════

def _build_lesson_data(
    pts: Dict[str, sp.Matrix],
    steps: list,
    answer_latex: str,
    answer_value: float,
    answer_label: str,
    *,
    scale: float = 1.5,
    spheres: list = None,
    edges: list = None,
    elements: dict = None,
    target: list = None,
    initial_camera: list = None,
    lesson_meta: str = "交互解题",
    problem: str = "",
) -> dict:
    """组装模板所需的完整 lesson data。"""
    tp = to_three(pts, scale=scale)
    if target is None:
        names = list(tp)
        n = len(names)
        target = [sum(tp[k][i] for k in names) / n for i in range(3)]
    if initial_camera is None:
        initial_camera = [4, 3, 5]
    return {
        "lesson": {
            "language": "zh-CN",
            "meta": lesson_meta,
            "title": problem,
            "answerLabel": answer_label,
            "answerValue": f"${answer_latex}$",
        },
        "steps": steps,
        "model": {
            "points": tp,
            "spheres": spheres or list(pts.keys()),
            "edges": edges or [],
            "elements": elements or {},
            "target": target,
            "initialCamera": initial_camera,
        },
        "_answer_latex": answer_latex,
        "_answer_value": answer_value,
    }


# --- 正方体 · 线面角 (AC1 + BDD1B1) ---

@register_solver("cube", "line_plane_angle")
def solve_line_plane_angle_cube(edge=2) -> Solution:
    """正方体 ABCD-A1B1C1D1，求直线 AC1 与平面 BDD1B1 所成角的正弦值。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_cube(edge)
    mp = {k: tex_vec(v) for k, v in pts.items()}

    AC1 = pts["C1"] - pts["A"]
    BD = pts["D"] - pts["B"]
    BB1 = pts["B1"] - pts["B"]
    n = BD.cross(BB1)
    n = sp.simplify(n)
    n_simpl = simplify_vec(n)

    sin_theta = line_plane_angle_sin(AC1, n)
    dot = AC1.dot(n_simpl)
    norm_ac1 = sqrt(sum(c**2 for c in AC1))
    ans_latex = tex(sin_theta)
    ans_val = float(sin_theta)

    problem_text = (
        f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 {edge}，"
        f"求直线 $AC_1$ 与平面 $BDD_1B_1$ 所成角的正弦值。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "直线 AC₁ 与平面 BDD₁B₁ 所成角的正弦值",
        scale=2, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AC1": {"type": "line", "a": "A", "b": "C1", "color": "emphasis", "depthTest": False},
            "Plane_BDD1B1": {"type": "plane", "pts": ["B", "D", "D1", "B1"]},
            "Normal_Vector": {"type": "arrow", "origin": "B", "dir": [0, 0.8, 1], "length": 1.6, "color": "normal"},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 6],
        lesson_meta="交互解题 · 线面角", problem=problem_text,
    )

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点，$AB$、$AD$、$AA_1$ 分别为 $x$、$y$、$z$ 轴，"
                f"正方体棱长为 ${tex(a)}$。</p>"
                f"<p>关键点坐标：$A{mp['A']}, C_1{mp['C1']}, B{mp['B']}, D{mp['D']}, B_1{mp['B1']}, D_1{mp['D1']}$</p>"
            ),
            "highlight": ["Axis"],
            "cameraPos": {"x": 5, "y": 4, "z": 6},
        },
        {
            "title": "求直线方向向量",
            "content": (
                f"<p>直线 $AC_1$ 的方向向量：</p>"
                f"$$\\overrightarrow{{AC_1}} = C_1 - A = {tex_vec(AC1)}$$"
            ),
            "highlight": ["Line_AC1"],
            "cameraPos": {"x": 3, "y": 5, "z": 7},
        },
        {
            "title": "求平面法向量",
            "content": (
                f"<p>在平面 $BDD_1B_1$ 内取两向量：</p>"
                f"$$\\overrightarrow{{BD}} = {tex_vec(BD)}, \\quad \\overrightarrow{{BB_1}} = {tex_vec(BB1)}$$"
                f"<p>法向量 $\\vec n = \\overrightarrow{{BD}} \\times \\overrightarrow{{BB_1}} = {tex_vec(n)}$</p>"
                f"<p>简化取 $\\vec n = {tex_vec(n_simpl)}$</p>"
            ),
            "highlight": ["Line_AC1", "Plane_BDD1B1", "Normal_Vector"],
            "cameraPos": {"x": 4, "y": 5, "z": 5},
        },
        {
            "title": "计算线面角的正弦值",
            "content": (
                f"<p>设直线 $AC_1$ 与平面 $BDD_1B_1$ 所成角为 $\\theta$。</p>"
                f"$$\\sin\\theta = \\frac{{|\\overrightarrow{{AC_1}} \\cdot \\vec n|}}"
                f"{{|\\overrightarrow{{AC_1}}| \\cdot |\\vec n|}}"
                f"= \\frac{{{tex(sp.Abs(dot))}}}{{{tex(norm_ac1)} \\cdot {tex(sp.sqrt(sum(c**2 for c in n)))}}}"
                f"= {ans_latex}$$"
            ),
            "highlight": ["Line_AC1", "Plane_BDD1B1", "Normal_Vector"],
            "cameraPos": {"x": 5, "y": 4, "z": 6},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text,
        steps=steps,
        answer_latex=ans_latex,
        answer_value=ans_val,
        model=SolidModel(
            points=[Point(name, (float(pts[name][0]), float(pts[name][1]), float(pts[name][2]))) for name in pts],
            segments=[Segment(e["a"] + e["b"], Point(e["a"], (0, 0, 0)), Point(e["b"], (0, 0, 0))) for e in topo["edges"]],
        ),
        lesson_meta=lesson["lesson"]["meta"],
        answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp,
        spheres=topo["spheres"],
        edges=topo["edges"],
        elements=lesson["model"]["elements"],
        target=center,
        initial_camera=[5, 4, 6],
        scale=2,
    )


# --- 正方体 · 异面直线夹角 ---

@register_solver("cube", "line_line_angle")
def solve_cube_line_line_angle(edge=2) -> Solution:
    """正方体中 A1C 与 AB 的异面直线夹角余弦。"""
    import bodies as _bodies
    pts = build_cube(edge)
    d1 = pts["C"] - pts["A1"]
    d2 = pts["B"] - pts["A"]
    cos_theta = line_line_angle_cos(d1, d2)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 {edge}，"
        f"求异面直线 $A_1C$ 与 $AB$ 所成角的余弦值。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "异面直线 A₁C 与 AB 所成角的余弦值",
        scale=2, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_A1C": {"type": "line", "a": "A1", "b": "C", "color": "emphasis", "depthTest": False},
            "Line_AB": {"type": "line", "a": "A", "b": "B", "color": "normal", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 异面直线夹角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，正方体棱长为 ${tex(sp.sympify(edge))}$。</p>"
                f"<p>$A_1{mp['A1']}, C{mp['C']}, A{mp['A']}, B{mp['B']}$</p>"
            ),
            "highlight": ["Axis"],
            "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "求两直线方向向量",
            "content": (
                f"$$\\overrightarrow{{A_1C}} = {tex_vec(d1)}, \\quad \\overrightarrow{{AB}} = {tex_vec(d2)}$$"
            ),
            "highlight": ["Line_A1C", "Line_AB"],
            "cameraPos": {"x": 3, "y": 5, "z": 6},
        },
        {
            "title": "计算夹角余弦",
            "content": (
                f"$$\\cos\\theta = \\frac{{|\\overrightarrow{{A_1C}} \\cdot \\overrightarrow{{AB}}|}}"
                f"{{|\\overrightarrow{{A_1C}}| \\cdot |\\overrightarrow{{AB}}|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_A1C", "Line_AB"],
            "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[5, 4, 5], scale=2,
    )


# --- 正方体 · 点到平面距离 ---

@register_solver("cube", "point_plane_distance")
def solve_cube_point_plane_distance(edge=2) -> Solution:
    """正方体中点 A1 到平面 AB1C 的距离。"""
    import bodies as _bodies
    pts = build_cube(edge)
    n = normal_from_points(pts["A"], pts["B1"], pts["C"])
    dist = point_plane_distance(pts["A1"], pts["A"], n)
    ans_latex = tex(dist)
    ans_val = float(dist)

    problem_text = (
        f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 {edge}，"
        f"求点 $A_1$ 到平面 $AB_1C$ 的距离。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "点 A₁ 到平面 AB₁C 的距离",
        scale=2, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Point_A1": {"type": "sphere", "pt": "A1", "color": "emphasis", "radius": 0.18},
            "Plane_AB1C": {"type": "plane", "pts": ["A", "B1", "C"]},
            "Normal_Vector": {"type": "arrow", "origin": "A", "dir": [0.5, 0.7, 0.5], "length": 1.4, "color": "normal"},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 5, 5],
        lesson_meta="交互解题 · 点面距离", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，正方体棱长为 ${tex(sp.sympify(edge))}$。</p>"
                f"<p>$A{mp['A']}, A_1{mp['A1']}, B_1{mp['B1']}, C{mp['C']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 5, "z": 5},
        },
        {
            "title": "求平面法向量",
            "content": (
                f"<p>平面 $AB_1C$ 过三点 $A, B_1, C$：</p>"
                f"$$\\overrightarrow{{AB_1}} = {tex_vec(pts['B1'] - pts['A'])}, \\quad"
                f"\\overrightarrow{{AC}} = {tex_vec(pts['C'] - pts['A'])}$$"
                f"<p>法向量 $\\vec n = \\overrightarrow{{AB_1}} \\times \\overrightarrow{{AC}} = {tex_vec(n)}$</p>"
            ),
            "highlight": ["Plane_AB1C", "Normal_Vector"], "cameraPos": {"x": 6, "y": 3, "z": 6},
        },
        {
            "title": "计算点面距离",
            "content": (
                f"$$d = \\frac{{|\\overrightarrow{{AA_1}} \\cdot \\vec n|}}{{|\\vec n|}}"
                f"= \\frac{{{tex(sp.Abs((pts['A1'] - pts['A']).dot(n)))}}}{{{tex(sp.sqrt(sum(c**2 for c in n)))}}}"
                f"= {ans_latex}$$"
            ),
            "highlight": ["Point_A1", "Plane_AB1C", "Normal_Vector"],
            "cameraPos": {"x": 5, "y": 5, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[5, 5, 5], scale=2,
    )


# --- 正四棱锥 · 线面角 ---

@register_solver("regular_quad_pyramid", "line_plane_angle")
def solve_pyramid_line_plane_angle(base_edge=2, height=1) -> Solution:
    """正四棱锥 P-ABCD，E 为 PC 中点，求直线 BE 与平面 PAC 所成角的正弦值。"""
    import bodies as _bodies
    pts = build_regular_quad_pyramid(base_edge, height)
    pts["E"] = midpoint(pts["P"], pts["C"])

    BE = pts["E"] - pts["B"]
    n = normal_from_points(pts["P"], pts["A"], pts["C"])
    n_simpl = simplify_vec(n)
    sin_theta = line_plane_angle_sin(BE, n)
    ans_latex = tex(sin_theta)
    ans_val = float(sin_theta)

    problem_text = (
        f"正四棱锥 $P-ABCD$，底面边长 ${base_edge}$，高 ${height}$，"
        f"$E$ 为 $PC$ 中点，求直线 $BE$ 与平面 $PAC$ 所成角的正弦值。"
    )

    topo = _bodies.quad_pyramid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "直线 BE 与平面 PAC 所成角的正弦值",
        scale=1.5, spheres=topo["spheres"] + ["E"], edges=topo["edges"],
        elements={
            "Line_BE": {"type": "line", "a": "B", "b": "E", "color": "emphasis", "depthTest": False},
            "Plane_PAC": {"type": "plane", "pts": ["P", "A", "C"]},
            "Line_PC": {"type": "line", "a": "P", "b": "C", "color": "aux", "dashed": True},
            "Normal_Vector": {"type": "arrow", "origin": "O", "dir": [0, 0.6, 1.2], "length": 1.0, "color": "normal"},
            "Axis": {"type": "axes", "size": 2.5},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 四棱锥线面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以底面中心 $O$ 为原点，$AC$ 在 $x$ 轴、$BD$ 在 $y$ 轴，$P$ 在 $z$ 轴。</p>"
                f"<p>底面边长 ${base_edge}$，高 ${height}$。</p>"
                f"<p>$B{mp['B']}, E{mp['E']}, P{mp['P']}, A{mp['A']}, C{mp['C']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求直线 BE 的方向向量",
            "content": (
                f"<p>$E$ 为 $PC$ 中点：$E = \\frac{{P+C}}{{2}} = {mp['E']}$</p>"
                f"$$\\overrightarrow{{BE}} = E - B = {tex_vec(BE)}$$"
            ),
            "highlight": ["Line_BE", "Line_PC"], "cameraPos": {"x": 2, "y": 4, "z": 5},
        },
        {
            "title": "求平面 PAC 的法向量",
            "content": (
                f"<p>平面 $PAC$ 中：</p>"
                f"$$\\overrightarrow{{PA}} = {tex_vec(pts['A'] - pts['P'])}, \\quad"
                f"\\overrightarrow{{PC}} = {tex_vec(pts['C'] - pts['P'])}$$"
                f"<p>法向量 $\\vec n = \\overrightarrow{{PA}} \\times \\overrightarrow{{PC}} = {tex_vec(n)}$</p>"
                f"<p>简化取 $\\vec n = {tex_vec(n_simpl)}$</p>"
            ),
            "highlight": ["Plane_PAC", "Normal_Vector"], "cameraPos": {"x": 4, "y": 3, "z": 4},
        },
        {
            "title": "计算线面角正弦值",
            "content": (
                f"$$\\sin\\theta = \\frac{{|\\overrightarrow{{BE}} \\cdot \\vec n|}}"
                f"{{|\\overrightarrow{{BE}}| \\cdot |\\vec n|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_BE", "Plane_PAC", "Normal_Vector"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"] + ["E"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 随机出题
# ══════════════════════════════════════════════════════════════════════════════

_RANDOM_TEMPLATES: List[Callable[..., Solution]] = [
    solve_line_plane_angle_cube,
    solve_cube_line_line_angle,
    solve_cube_point_plane_distance,
    solve_pyramid_line_plane_angle,
]


def generate_random(seed: int = None, max_retries: int = 30) -> Solution:
    """随机选题型 + 随机参数 → 求解 → 答案不规整则重抽。

    Args:
        seed: 随机种子（None 表示不固定）
        max_retries: 最大重试次数
    """
    rng = _random.Random(seed)
    for _ in range(max_retries):
        solver = rng.choice(_RANDOM_TEMPLATES)
        # 随机参数
        edge = rng.choice([1, 2, 3, 4])
        kwargs = {}
        sig_params = ["edge", "base_edge"]
        for p in sig_params:
            if p == "edge":
                kwargs["edge"] = edge
            elif p == "base_edge":
                kwargs["base_edge"] = edge
                kwargs["height"] = rng.choice([1, 2, 3])

        try:
            sol = solver(**{k: v for k, v in kwargs.items() if k in solver.__code__.co_varnames})
        except TypeError:
            sol = solver()

        # 检查答案是否规整
        if is_clean(sol.answer_value):
            return sol

    # 重试耗尽，返回最后一试
    return solver()


# ══════════════════════════════════════════════════════════════════════════════
# 题面路由
# ══════════════════════════════════════════════════════════════════════════════

def _sanitize_params(params: dict) -> dict:
    """将 LLM 返回的参数中的非数值转为默认值。"""
    cleaned = {}
    for k, v in params.items():
        try:
            cleaned[k] = float(v)
        except (TypeError, ValueError):
            logger.warning("Non-numeric parameter %s=%s, using default 2", k, v)
            cleaned[k] = 2
    return cleaned


def _keyword_fallback(problem_text: str) -> Solution:
    """原始关键词匹配逻辑，LLM 不可用时的降级方案。"""
    lowered = problem_text.lower()
    if "异面" in problem_text or "skew" in lowered:
        return solve_cube_line_line_angle()
    if "距离" in problem_text or "distance" in lowered:
        return solve_cube_point_plane_distance()
    if "四棱锥" in problem_text or "pyramid" in lowered:
        return solve_pyramid_line_plane_angle()
    if "随机" in problem_text or "random" in lowered:
        return generate_random()
    # 默认：正方体线面角
    if "正方体" in problem_text or "cube" in lowered:
        return solve_line_plane_angle_cube(edge=2)
    return solve_line_plane_angle_cube(edge=2)


def solve(problem_text: str) -> Solution:
    """解析题面并求解。

    优先尝试 LLM 结构化解析；LLM 不可用或解析失败时
    降级到关键词匹配。
    """
    # Phase 1: LLM 解析
    try:
        spec = llm_parser.parse_problem(problem_text)
        solver = get_solver(spec["shape_type"], spec["query_type"])
        if solver is None:
            supported = ", ".join(
                f"{s}+{q}" for s, qs in list_supported_types().items() for q in qs
            )
            raise ValueError(
                f"不支持的问题类型：shape={spec['shape_type']}, query={spec['query_type']}。"
                f"当前支持：{supported}"
            )
        params = _sanitize_params(spec.get("parameters", {}))
        logger.info("LLM parsed: shape=%s query=%s params=%s",
                     spec["shape_type"], spec["query_type"], params)
        return solver(**params)
    except llm_parser.LLMNotConfiguredError:
        logger.info("LLM not configured; falling back to keyword matching")
    except llm_parser.LLMParseError as e:
        logger.warning("LLM parse failed: %s; falling back to keyword matching", e)
    except Exception as e:
        logger.warning("LLM call failed (%s: %s); falling back to keyword matching",
                       type(e).__name__, e)

    # Phase 2: 降级 — 关键词匹配
    return _keyword_fallback(problem_text)


# ══════════════════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== 正方体 · 线面角 (AC1 + BDD1B1) ===")
    sol = solve_line_plane_angle_cube(2)
    expected = sqrt(6) / 3
    ok = abs(sol.answer_value - float(expected)) < 1e-12
    print(f"  sinθ = {sol.answer_latex} ≈ {sol.answer_value}")
    print(f"  expect sqrt(6)/3 = {float(expected):.6f}  {'PASS' if ok else 'FAIL'}")
    assert ok, "line-plane angle answer mismatch"

    print("\n=== cube: skew lines angle ===")
    sol2 = solve_cube_line_line_angle(2)
    exp2 = sqrt(3) / 3
    ok2 = abs(sol2.answer_value - float(exp2)) < 1e-12
    print(f"  cos = {sol2.answer_latex} = {sol2.answer_value}")
    print(f"  expect sqrt(3)/3 = {float(exp2):.6f}  {'PASS' if ok2 else 'FAIL'}")
    assert ok2

    print("\n=== cube: point-plane distance ===")
    sol3 = solve_cube_point_plane_distance(2)
    print(f"  d = {sol3.answer_latex} = {sol3.answer_value}")
    assert sol3.answer_value > 0
    print("  PASS")

    print("\n=== regular quad pyramid: line-plane angle ===")
    sol4 = solve_pyramid_line_plane_angle(2, 1)
    expected4 = 2 * sqrt(22) / 11
    ok4 = abs(sol4.answer_value - float(expected4)) < 1e-12
    print(f"  sin = {sol4.answer_latex} = {sol4.answer_value}")
    print(f"  expect 2*sqrt(22)/11 = {float(expected4):.6f}  {'PASS' if ok4 else 'FAIL'}")
    assert ok4

    print("\n=== random generation ===")
    for i in range(3):
        r = generate_random(seed=i)
        print(f"  seed={i}: {r.problem[:60]}... -> {r.answer_latex}")

    print("\n=== ALL SELF-TESTS PASSED ===")
