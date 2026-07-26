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
    if e.is_Float or e.has(sp.Float):
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
    text_only: bool = False


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


def build_regular_triangular_prism(base_edge, height):
    """正三棱柱 ABC-A1B1C1：底面为等边三角形，A 在原点，AB 沿 x 轴，C 在上方。

    坐标约定（数学坐标，z 轴向上）：
      - A=(0,0,0), B=(a,0,0), C=(a/2, a√3/2, 0)
      - A1=(0,0,h), B1=(a,0,h), C1=(a/2, a√3/2, h)
    """
    a = sp.sympify(base_edge)
    h = sp.sympify(height)
    return {
        "A": V(0, 0, 0),
        "B": V(a, 0, 0),
        "C": V(a / 2, a * sqrt(3) / 2, 0),
        "A1": V(0, 0, h),
        "B1": V(a, 0, h),
        "C1": V(a / 2, a * sqrt(3) / 2, h),
    }


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
    """组装模板所需的完整 lesson data。

    ⚠️ 与 app.py 中 _build_lesson_data(solution) 对应 —— 修改 dict 结构时两边需同步。
    """
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


# --- 正方体 · 动点取值范围 (A₁P∥平面AEF，P在侧面上) ---

@register_solver("cube", "point_range")
def solve_cube_point_range(edge=2) -> Solution:
    """正方体 ABCD-A₁B₁C₁D₁，E=BC中点, F=CC₁中点, P在侧面BCC₁B₁上,
    A₁P∥平面AEF，求|A₁P|取值范围。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_cube(edge)

    # E = BC中点, F = CC₁中点
    E_vec = midpoint(pts["B"], pts["C"])
    F_vec = midpoint(pts["C"], pts["C1"])
    pts["E"] = E_vec
    pts["F"] = F_vec
    A1 = pts["A1"]

    # 平面 AEF 过 A，法向量 n = AE × AF
    AE = E_vec - pts["A"]
    AF = F_vec - pts["A"]
    n = AE.cross(AF)

    # A₁P ∥ 平面 AEF → P 满足 n·P = n·A₁
    # P 在侧面 BCC₁B₁ 上: x = a, y∈(0,a), z∈(0,a)
    # 代入得 z - y = a/2 → z = y + a/2
    rhs = n.dot(A1)

    # 用 sympy 验证：P=(a, y, z), n·P = rhs → z = y + a/2
    y_sym = sp.symbols('y', real=True)
    # n[0]*a + n[1]*y + n[2]*(y + a/2) == rhs 应该恒成立

    # y 的范围：0 < y < a 且 0 < z = y + a/2 < a → 0 < y < a/2
    y_low = sp.Integer(0)
    y_high = a / 2

    # |A₁P|² = (a-0)² + (y-0)² + (z-a)²
    # z = y + a/2, 所以 z - a = y - a/2
    # = a² + y² + (y - a/2)² = 2y² - a·y + 5a²/4
    dist_sq = a**2 + y_sym**2 + (y_sym + a/2 - a)**2
    dist_sq = sp.simplify(dist_sq)  # 2*y**2 - a*y + 5*a**2/4

    # 二次函数最小值在 y = a/4
    d_dist = sp.diff(dist_sq, y_sym)
    y_crit = sp.solve(d_dist, y_sym)[0]  # a/4
    min_dist_sq = sp.simplify(dist_sq.subs(y_sym, y_crit))
    min_dist = sp.sqrt(min_dist_sq)  # 3a√2/4

    # 端点值（开区间，取 sup）
    max_dist_sq = sp.simplify(dist_sq.subs(y_sym, 0))  # 5a²/4
    max_dist = sp.sqrt(max_dist_sq)  # a√5/2

    ans_latex = rf"\left[{tex(min_dist)},\ {tex(max_dist)}\right)"
    ans_val = float(min_dist)  # 以最小值作为数值答案

    problem_text = (
        f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 {edge}，"
        f"$E,F$ 分别是棱 $BC,CC_1$ 的中点，"
        f"$P$ 是侧面 $BCC_1B_1$ 内（不含边界）一点。"
        rf"若 $A_1P \parallel$ 平面 $AEF$，则线段 $A_1P$ 长度的取值范围是_____。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    # P 轨迹线段端点（在面 BCC₁B₁ 上）
    P_low = V(a, y_low, y_low + a/2)    # (a, 0, a/2) — 边界，不含
    P_high = V(a, y_high, y_high + a/2)  # (a, a/2, a) — 边界，不含
    pts["P_low"] = P_low
    pts["P_high"] = P_high
    # P 的中点（实际可取到的点，用于展示）
    pts["P_mid"] = V(a, a/4, 3*a/4)

    answer_label = f"线段 A₁P 长度的取值范围"

    # 重新生成 three_points（新增了 E, F, P 系列点）
    tp2 = to_three(pts, scale=2)
    names2 = list(tp2)
    center2 = [sum(tp2[k][i] for k in names2) / len(names2) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, answer_label,
        scale=2,
        spheres=topo["spheres"] + ["E", "F", "A1", "P_mid"],
        edges=topo["edges"],
        elements={
            "Point_E": {"type": "sphere", "pt": "E", "color": "emphasis", "radius": 0.15},
            "Point_F": {"type": "sphere", "pt": "F", "color": "emphasis", "radius": 0.15},
            "Point_A1": {"type": "sphere", "pt": "A1", "color": "emphasis", "radius": 0.18},
            "Point_P_mid": {"type": "sphere", "pt": "P_mid", "color": "highlight", "radius": 0.16},
            "Plane_AEF": {"type": "plane", "pts": ["A", "E", "F"]},
            "Line_P_track": {"type": "line", "a": "P_low", "b": "P_high", "color": "emphasis", "depthTest": False},
            "Line_A1P": {"type": "line", "a": "A1", "b": "P_mid", "color": "highlight", "dashed": True, "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center2, initial_camera=[6, 5, 4],
        lesson_meta="交互解题 · 动点取值范围", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，正方体棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, A_1{mp['A1']}, B_1{mp['B1']}, C_1{mp['C1']}$</p>"
                f"<p>$E$ 为 $BC$ 中点：$E{mp['E']}$</p>"
                f"<p>$F$ 为 $CC_1$ 中点：$F{mp['F']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 6, "y": 5, "z": 4},
        },
        {
            "title": "求平面 AEF 的法向量",
            "content": (
                f"<p>$\\overrightarrow{{AE}} = {tex_vec(AE)}, \\quad \\overrightarrow{{AF}} = {tex_vec(AF)}$</p>"
                f"<p>法向量 $\\vec n = \\overrightarrow{{AE}} \\times \\overrightarrow{{AF}} = {tex_vec(n)}$</p>"
                f"<p>平面 $AEF$ 过原点，方程为 ${tex(n[0])}x {'+' if n[1]>=0 else ''}{tex(n[1])}y {'+' if n[2]>=0 else ''}{tex(n[2])}z = 0$</p>"
            ),
            "highlight": ["Plane_AEF", "Point_E", "Point_F"],
            "cameraPos": {"x": 5, "y": 6, "z": 5},
        },
        {
            "title": "由平行条件求 P 的轨迹",
            "content": (
                rf"<p>$A_1P \parallel$ 平面 $AEF$，即 $P$ 在过 $A_1$ 且平行于平面 $AEF$ 的平面上：</p>"
                f"<p>$\\vec n \\cdot (P - A_1) = 0$，即 $\\vec n \\cdot P = \\vec n \\cdot A_1 = {tex(rhs)}$</p>"
                f"<p>$P$ 在侧面 $BCC_1B_1$ 上，设 $P(a, y, z)$，代入得：</p>"
                f"<p>$z - y = \\frac{{a}}{{2}}$，即 $z = y + \\frac{{a}}{{2}}$</p>"
                f"<p>又 $0 < y < a,\\ 0 < z < a$，得 $0 < y < \\frac{{a}}{{2}}$</p>"
            ),
            "highlight": ["Line_P_track", "Point_A1", "Plane_AEF"],
            "cameraPos": {"x": 0, "y": 8, "z": 2},
        },
        {
            "title": "求 |A₁P| 的取值范围",
            "content": (
                f"<p>$|A_1P|^2 = (a-0)^2 + (y-0)^2 + (z-a)^2$</p>"
                f"<p>$= a^2 + y^2 + (y - \\frac{{a}}{{2}})^2$</p>"
                f"<p>$= 2y^2 - ay + \\frac{{5a^2}}{{4}}$</p>"
                f"<p>$= 2(y - \\frac{{a}}{{4}})^2 + \\frac{{9a^2}}{{8}}$</p>"
                f"<p>当 $y = \\frac{{a}}{{4}}$ 时，$|A_1P|_{{min}} = {tex(min_dist)} = {tex(min_dist.evalf(4))}$</p>"
                f"<p>当 $y \\to 0$ 或 $y \\to \\frac{{a}}{{2}}$ 时（不含边界），$|A_1P| \\to {tex(max_dist)} = {tex(max_dist.evalf(4))}$</p>"
                f"<p>$\\therefore |A_1P| \\in {ans_latex}$</p>"
            ),
            "highlight": ["Line_P_track", "Line_A1P", "Point_A1", "Point_P_mid"],
            "cameraPos": {"x": 6, "y": 5, "z": 4},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=answer_label,
        three_points=tp2, spheres=topo["spheres"] + ["E", "F", "A1", "P_mid"],
        edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center2, initial_camera=[6, 5, 4], scale=2,
    )


# --- 正方体 · 体积 ---

@register_solver("cube", "volume")
def solve_cube_volume(edge=2) -> Solution:
    """正方体 ABCD-A1B1C1D1 棱长为 a，求体积。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_cube(edge)

    V_expr = volume_box(a, a, a)
    ans_latex = tex(V_expr)
    ans_val = float(V_expr)

    problem_text = f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 ${tex(a)}$，求该正方体的体积。"

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "正方体 ABCD-A₁B₁C₁D₁ 的体积",
        scale=2, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 正方体体积", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点，$AB$、$AD$、$AA_1$ 分别为 $x$、$y$、$z$ 轴，"
                f"正方体棱长为 ${tex(a)}$。</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "计算体积",
            "content": (
                f"<p>正方体体积公式：$V = a^3$</p>"
                f"<p>代入 $a = {tex(a)}$：</p>"
                f"$$V = {tex(a)}^3 = {ans_latex}$$"
            ),
            "highlight": [],
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


# --- 正方体 · 二面角 ---

@register_solver("cube", "dihedral_angle")
def solve_cube_dihedral_angle(edge=2) -> Solution:
    """正方体 ABCD-A1B1C1D1 中二面角 A-BD-C1 的余弦值。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_cube(edge)

    # 二面角 A-BD-C1：公共棱 BD，半平面 ABD 和 C1BD
    cos_theta = sp.simplify(sp.Abs(dihedral_cos(pts["B"], pts["D"], pts["A"], pts["C1"])))
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正方体 $ABCD-A_1B_1C_1D_1$ 棱长为 {edge}，"
        f"求二面角 $A-BD-C_1$ 的余弦值。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=2)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "二面角 A-BD-C₁ 的余弦值",
        scale=2, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Plane_ABD": {"type": "plane", "pts": ["A", "B", "D"]},
            "Plane_C1BD": {"type": "plane", "pts": ["C1", "B", "D"]},
            "Edge_BD": {"type": "line", "a": "B", "b": "D", "color": "emphasis", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 二面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    BD = pts["D"] - pts["B"]
    n1 = simplify_vec(normal_from_points(pts["A"], pts["B"], pts["D"]))
    n2 = simplify_vec(normal_from_points(pts["C1"], pts["B"], pts["D"]))

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，正方体棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, D{mp['D']}, C_1{mp['C1']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "分析二面角的构成",
            "content": (
                f"<p>二面角 $A-BD-C_1$：公共棱为 $BD$，两个半平面分别为 $ABD$ 和 $C_1BD$。</p>"
                f"<p>棱的方向向量：$\\overrightarrow{{BD}} = {tex_vec(BD)}$</p>"
                f"<p>平面 $ABD$ 即底面，法向量 $\\vec n_1 = {tex_vec(n1)}$</p>"
                f"<p>平面 $C_1BD$ 的法向量 $\\vec n_2 = {tex_vec(n2)}$</p>"
            ),
            "highlight": ["Plane_ABD", "Plane_C1BD", "Edge_BD"],
            "cameraPos": {"x": 4, "y": 5, "z": 6},
        },
        {
            "title": "计算二面角余弦",
            "content": (
                f"<p>二面角余弦公式：</p>"
                f"$$\\cos\\theta = \\frac{{|\\vec n_1 \\cdot \\vec n_2|}}"
                f"{{|\\vec n_1| \\cdot |\\vec n_2|}} = {ans_latex}$$"
            ),
            "highlight": ["Plane_ABD", "Plane_C1BD", "Edge_BD"],
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


# --- 正四面体 · 体积 ---

@register_solver("regular_tetrahedron", "volume")
def solve_tetra_volume(edge=2) -> Solution:
    """正四面体 ABCD 棱长为 a，求体积。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_regular_tetrahedron(edge)

    V_expr = volume_tetra(pts["A"], pts["B"], pts["C"], pts["D"])
    ans_latex = tex(V_expr)
    ans_val = float(V_expr)

    problem_text = f"正四面体 $ABCD$ 棱长为 ${tex(a)}$，求该正四面体的体积。"

    topo = _bodies.tri_pyramid(apex="D", base=("A", "B", "C"))
    tp = to_three(pts, scale=2.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]
    # 默认 spheres 包含 A,B,C,D

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "正四面体 ABCD 的体积",
        scale=2.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Plane_ABC": {"type": "plane", "pts": ["A", "B", "C"]},
            "Point_D": {"type": "sphere", "pt": "D", "color": "emphasis", "radius": 0.16},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 正四面体体积", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    AB = pts["B"] - pts["A"]
    AC = pts["C"] - pts["A"]
    AD = pts["D"] - pts["A"]

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以正四面体中心为原点建系，棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "利用向量法求体积",
            "content": (
                f"<p>计算向量：$\\overrightarrow{{AB}} = {tex_vec(AB)}, \\quad "
                f"\\overrightarrow{{AC}} = {tex_vec(AC)}, \\quad "
                f"\\overrightarrow{{AD}} = {tex_vec(AD)}$</p>"
                f"<p>四面体体积公式：$V = \\frac{{1}}{{6}}\\left|(\\overrightarrow{{AB}} \\times "
                f"\\overrightarrow{{AC}}) \\cdot \\overrightarrow{{AD}}\\right|$</p>"
                f"<p>正四面体体积公式也可记为：$V = \\frac{{\\sqrt{{2}}}}{{12}}a^3$</p>"
                f"$$V = \\frac{{\\sqrt{{2}}}}{{12}} \\cdot {tex(a)}^3 = {ans_latex}$$"
            ),
            "highlight": ["Plane_ABC", "Point_D"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=2.5,
    )


# --- 正四面体 · 异面直线夹角 ---

@register_solver("regular_tetrahedron", "line_line_angle")
def solve_tetra_line_line_angle(edge=2) -> Solution:
    """正四面体 ABCD 中对棱 AB 与 CD 的异面直线夹角余弦。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_regular_tetrahedron(edge)

    AB = pts["B"] - pts["A"]
    CD = pts["D"] - pts["C"]
    cos_theta = line_line_angle_cos(AB, CD)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正四面体 $ABCD$ 棱长为 ${tex(a)}$，"
        f"求异面直线 $AB$ 与 $CD$ 所成角的余弦值。"
    )

    topo = _bodies.tri_pyramid(apex="D", base=("A", "B", "C"))
    tp = to_three(pts, scale=2.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "异面直线 AB 与 CD 所成角的余弦值",
        scale=2.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AB": {"type": "line", "a": "A", "b": "B", "color": "emphasis", "depthTest": False},
            "Line_CD": {"type": "line", "a": "C", "b": "D", "color": "normal", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 正四面体对棱夹角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以正四面体中心为原点建系，棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求两直线的方向向量",
            "content": (
                f"$$\\overrightarrow{{AB}} = {tex_vec(AB)}, \\quad \\overrightarrow{{CD}} = {tex_vec(CD)}$$"
            ),
            "highlight": ["Line_AB", "Line_CD"],
            "cameraPos": {"x": 3, "y": 4, "z": 6},
        },
        {
            "title": "计算夹角余弦",
            "content": (
                f"$$\\cos\\theta = \\frac{{|\\overrightarrow{{AB}} \\cdot \\overrightarrow{{CD}}|}}"
                f"{{|\\overrightarrow{{AB}}| \\cdot |\\overrightarrow{{CD}}|}} = {ans_latex}$$"
                f"<p>正四面体的对棱相互垂直，夹角为 $90^\\circ$。</p>"
            ),
            "highlight": ["Line_AB", "Line_CD"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=2.5,
    )


# --- 正四面体 · 线面角 ---

@register_solver("regular_tetrahedron", "line_plane_angle")
def solve_tetra_line_plane_angle(edge=2) -> Solution:
    """正四面体 ABCD 中棱 AB 与平面 BCD 所成角的正弦值。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_regular_tetrahedron(edge)

    AB = pts["B"] - pts["A"]
    n = normal_from_points(pts["B"], pts["C"], pts["D"])
    n_simpl = simplify_vec(n)
    sin_theta = line_plane_angle_sin(AB, n)
    ans_latex = tex(sin_theta)
    ans_val = float(sin_theta)

    problem_text = (
        f"正四面体 $ABCD$ 棱长为 ${tex(a)}$，"
        f"求直线 $AB$ 与平面 $BCD$ 所成角的正弦值。"
    )

    topo = _bodies.tri_pyramid(apex="D", base=("A", "B", "C"))
    tp = to_three(pts, scale=2.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    # 法向量方向：math (1,1,1) → THREE (1,1,1) (当 x,y,z 分量相同时)
    # 对于非均匀情况，normal_from_points(B,C,D) 的方向需要在 THREE 中转换
    # 这里法向量是 (1,1,1) 方向（scale factor 影响），归一化后方向在 THREE 也是 (≈0.577, ≈0.577, ≈0.577)
    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "直线 AB 与平面 BCD 所成角的正弦值",
        scale=2.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AB": {"type": "line", "a": "A", "b": "B", "color": "emphasis", "depthTest": False},
            "Plane_BCD": {"type": "plane", "pts": ["B", "C", "D"]},
            "Normal_Vector": {"type": "arrow", "origin": "C", "dir": [0.6, 0.6, 0.6], "length": 1.2, "color": "normal"},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 正四面体线面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以正四面体中心为原点建系，棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求直线 AB 的方向向量",
            "content": (
                f"$$\\overrightarrow{{AB}} = B - A = {tex_vec(AB)}$$"
            ),
            "highlight": ["Line_AB"],
            "cameraPos": {"x": 3, "y": 4, "z": 6},
        },
        {
            "title": "求平面 BCD 的法向量",
            "content": (
                f"<p>$\\overrightarrow{{BC}} = {tex_vec(pts['C'] - pts['B'])}, \\quad"
                f"\\overrightarrow{{BD}} = {tex_vec(pts['D'] - pts['B'])}$</p>"
                f"<p>法向量 $\\vec n = \\overrightarrow{{BC}} \\times \\overrightarrow{{BD}} = {tex_vec(n)}$</p>"
                f"<p>简化取 $\\vec n = {tex_vec(n_simpl)}$</p>"
            ),
            "highlight": ["Plane_BCD", "Normal_Vector"],
            "cameraPos": {"x": 4, "y": 3, "z": 4},
        },
        {
            "title": "计算线面角正弦值",
            "content": (
                f"$$\\sin\\theta = \\frac{{|\\overrightarrow{{AB}} \\cdot \\vec n|}}"
                f"{{|\\overrightarrow{{AB}}| \\cdot |\\vec n|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_AB", "Plane_BCD", "Normal_Vector"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=2.5,
    )


# --- 正四面体 · 二面角 ---

@register_solver("regular_tetrahedron", "dihedral_angle")
def solve_tetra_dihedral_angle(edge=2) -> Solution:
    """正四面体 ABCD 中二面角 A-BC-D 的余弦值。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_regular_tetrahedron(edge)

    # dihedral_cos(B, C, A, D) = 二面角 A-BC-D 的余弦
    cos_theta = dihedral_cos(pts["B"], pts["C"], pts["A"], pts["D"])
    cos_theta = sp.simplify(cos_theta)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正四面体 $ABCD$ 棱长为 ${tex(a)}$，"
        f"求二面角 $A-BC-D$ 的余弦值。"
    )

    topo = _bodies.tri_pyramid(apex="D", base=("A", "B", "C"))
    tp = to_three(pts, scale=2.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "二面角 A-BC-D 的余弦值",
        scale=2.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Plane_ABC": {"type": "plane", "pts": ["A", "B", "C"]},
            "Plane_DBC": {"type": "plane", "pts": ["D", "B", "C"]},
            "Edge_BC": {"type": "line", "a": "B", "b": "C", "color": "emphasis", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 正四面体二面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    BC = pts["C"] - pts["B"]

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以正四面体中心为原点建系，棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "分析二面角的构成",
            "content": (
                f"<p>二面角 $A-BC-D$：公共棱为 $BC$，两个半平面分别为 $ABC$ 和 $DBC$。</p>"
                f"<p>棱的方向向量：$\\overrightarrow{{BC}} = {tex_vec(BC)}$</p>"
            ),
            "highlight": ["Plane_ABC", "Plane_DBC", "Edge_BC"],
            "cameraPos": {"x": 4, "y": 5, "z": 3},
        },
        {
            "title": "计算二面角余弦",
            "content": (
                f"<p>分别在两个半平面内作垂直于棱 $BC$ 的向量，计算其夹角余弦：</p>"
                f"$$\\cos\\theta = \\frac{{\\vec v_1 \\cdot \\vec v_2}}"
                f"{{|\\vec v_1| \\cdot |\\vec v_2|}} = {ans_latex}$$"
                f"<p>正四面体的所有二面角均相等，余弦值为 $\\frac{{1}}{{3}}$。</p>"
            ),
            "highlight": ["Plane_ABC", "Plane_DBC", "Edge_BC"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=2.5,
    )


# --- 正四棱锥 · 体积 ---

@register_solver("regular_quad_pyramid", "volume")
def solve_pyramid_volume(base_edge=2, height=1) -> Solution:
    """正四棱锥 P-ABCD，底面边长 base_edge，高 height，求体积。"""
    import bodies as _bodies
    a = sp.Rational(base_edge)
    h = sp.Rational(height)
    pts = build_regular_quad_pyramid(base_edge, height)

    V_expr = volume_pyramid(a**2, h)
    ans_latex = tex(V_expr)
    ans_val = float(V_expr)

    problem_text = (
        f"正四棱锥 $P-ABCD$，底面边长 ${tex(a)}$，高 ${tex(h)}$，"
        f"求该正四棱锥的体积。"
    )

    topo = _bodies.quad_pyramid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "正四棱锥 P-ABCD 的体积",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Axis": {"type": "axes", "size": 2.5},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 四棱锥体积", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以底面中心 $O$ 为原点，$AC$ 在 $x$ 轴、$BD$ 在 $y$ 轴，$P$ 在 $z$ 轴。</p>"
                f"<p>底面边长 ${tex(a)}$，高 ${tex(h)}$。</p>"
                f"<p>$O{mp['O']}, P{mp['P']}, A{mp['A']}, B{mp['B']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "计算体积",
            "content": (
                f"<p>底面积 $S = a^2 = {tex(a)}^2 = {tex(a**2)}$</p>"
                f"<p>棱锥体积公式：$V = \\frac{{1}}{{3}}Sh$</p>"
                f"$$V = \\frac{{1}}{{3}} \\cdot {tex(a**2)} \\cdot {tex(h)} = {ans_latex}$$"
            ),
            "highlight": [],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正四棱锥 · 二面角 ---

@register_solver("regular_quad_pyramid", "dihedral_angle")
def solve_pyramid_dihedral_angle(base_edge=2, height=1) -> Solution:
    """正四棱锥 P-ABCD 中侧面 PAB 与底面 ABCD 所成二面角的余弦值。"""
    import bodies as _bodies
    a = sp.Rational(base_edge)
    h = sp.Rational(height)
    pts = build_regular_quad_pyramid(base_edge, height)

    # 二面角：侧面 PAB 与底面，公共棱 AB
    # dihedral_cos(A, B, P, O) = 二面角 P-AB-O（侧面与底面）
    cos_theta = dihedral_cos(pts["A"], pts["B"], pts["P"], pts["O"])
    cos_theta = sp.simplify(cos_theta)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正四棱锥 $P-ABCD$，底面边长 ${tex(a)}$，高 ${tex(h)}$，"
        f"求侧面 $PAB$ 与底面 $ABCD$ 所成二面角的余弦值。"
    )

    topo = _bodies.quad_pyramid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "侧面 PAB 与底面 ABCD 所成二面角的余弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Plane_PAB": {"type": "plane", "pts": ["P", "A", "B"]},
            "Plane_Base": {"type": "plane", "pts": ["O", "A", "B"]},
            "Edge_AB": {"type": "line", "a": "A", "b": "B", "color": "emphasis", "depthTest": False},
            "Axis": {"type": "axes", "size": 2.5},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 四棱锥二面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    AB = pts["B"] - pts["A"]
    n1 = simplify_vec(normal_from_points(pts["P"], pts["A"], pts["B"]))
    n2 = simplify_vec(normal_from_points(pts["O"], pts["A"], pts["B"]))

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以底面中心 $O$ 为原点，$AC$ 在 $x$ 轴、$BD$ 在 $y$ 轴，$P$ 在 $z$ 轴。</p>"
                f"<p>底面边长 ${tex(a)}$，高 ${tex(h)}$。</p>"
                f"<p>$O{mp['O']}, P{mp['P']}, A{mp['A']}, B{mp['B']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "分析二面角的构成",
            "content": (
                f"<p>二面角：侧面 $PAB$ 与底面 $ABCD$，公共棱为 $AB$。</p>"
                f"<p>棱的方向向量：$\\overrightarrow{{AB}} = {tex_vec(AB)}$</p>"
                f"<p>侧面 $PAB$ 的法向量：$\\vec n_1 = \\overrightarrow{{PA}} \\times "
                f"\\overrightarrow{{PB}} = {tex_vec(n1)}$</p>"
                f"<p>底面（$z=0$ 平面）的法向量：$\\vec n_2 = {tex_vec(n2)}$</p>"
            ),
            "highlight": ["Plane_PAB", "Plane_Base", "Edge_AB"],
            "cameraPos": {"x": 4, "y": 5, "z": 3},
        },
        {
            "title": "计算二面角余弦",
            "content": (
                f"<p>二面角余弦公式：</p>"
                f"$$\\cos\\theta = \\frac{{|\\vec n_1 \\cdot \\vec n_2|}}"
                f"{{|\\vec n_1| \\cdot |\\vec n_2|}} = {ans_latex}$$"
            ),
            "highlight": ["Plane_PAB", "Plane_Base", "Edge_AB"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正三棱柱 · 体积 ---

@register_solver("regular_triangular_prism", "volume")
def solve_prism_volume(base_edge=2, height=3) -> Solution:
    """正三棱柱 ABC-A1B1C1，底面等边三角形边长为 base_edge，高为 height，求体积。"""
    import bodies as _bodies
    a = sp.Rational(base_edge)
    h = sp.Rational(height)
    pts = build_regular_triangular_prism(base_edge, height)

    base_area = a**2 * sqrt(3) / 4
    V_expr = sp.simplify(base_area * h)
    ans_latex = tex(V_expr)
    ans_val = float(V_expr)

    problem_text = (
        f"正三棱柱 $ABC-A_1B_1C_1$，底面等边三角形边长为 ${tex(a)}$，"
        f"高为 ${tex(h)}$，求该正三棱柱的体积。"
    )

    topo = _bodies.prism()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "正三棱柱 ABC-A₁B₁C₁ 的体积",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 三棱柱体积", problem=problem_text,
    )

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点，$AB$ 沿 $x$ 轴，$AA_1$ 沿 $z$ 轴建系。</p>"
                f"<p>底面等边三角形边长 ${tex(a)}$，高 ${tex(h)}$。</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "计算体积",
            "content": (
                f"<p>底面等边三角形面积：$S = \\frac{{\\sqrt{{3}}}}{{4}}a^2"
                f"= \\frac{{\\sqrt{{3}}}}{{4}} \\cdot {tex(a)}^2 = {tex(base_area)}$</p>"
                f"<p>柱体体积：$V = S \\cdot h = {tex(base_area)} \\cdot {tex(h)} = {ans_latex}$</p>"
            ),
            "highlight": [],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正三棱柱 · 线面角 ---

@register_solver("regular_triangular_prism", "line_plane_angle")
def solve_prism_line_plane_angle(base_edge=2, height=3) -> Solution:
    """正三棱柱 ABC-A1B1C1 中 AB₁ 与底面 ABC 所成角的正弦值。"""
    import bodies as _bodies
    a = sp.Rational(base_edge)
    h = sp.Rational(height)
    pts = build_regular_triangular_prism(base_edge, height)

    AB1 = pts["B1"] - pts["A"]
    # 底面 ABC 的法向量即 z 轴方向 (0,0,1)
    n = V(0, 0, 1)
    sin_theta = line_plane_angle_sin(AB1, n)
    ans_latex = tex(sin_theta)
    ans_val = float(sin_theta)

    problem_text = (
        f"正三棱柱 $ABC-A_1B_1C_1$，底面等边三角形边长为 ${tex(a)}$，"
        f"高为 ${tex(h)}$，求直线 $AB_1$ 与底面 $ABC$ 所成角的正弦值。"
    )

    topo = _bodies.prism()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "直线 AB₁ 与底面 ABC 所成角的正弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AB1": {"type": "line", "a": "A", "b": "B1", "color": "emphasis", "depthTest": False},
            "Plane_Base": {"type": "plane", "pts": ["A", "B", "C"]},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 三棱柱线面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点，$AB$ 沿 $x$ 轴，$AA_1$ 沿 $z$ 轴建系。</p>"
                f"<p>$A{mp['A']}, B_1{mp['B1']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求 AB₁ 的方向向量",
            "content": (
                f"$$\\overrightarrow{{AB_1}} = B_1 - A = {tex_vec(AB1)}$$"
            ),
            "highlight": ["Line_AB1"],
            "cameraPos": {"x": 3, "y": 5, "z": 4},
        },
        {
            "title": "计算线面角正弦",
            "content": (
                f"<p>底面 $ABC$ 在 $z=0$ 平面，法向量 $\\vec n = (0,0,1)$。</p>"
                f"$$\\sin\\theta = \\frac{{|\\overrightarrow{{AB_1}} \\cdot \\vec n|}}"
                f"{{|\\overrightarrow{{AB_1}}| \\cdot |\\vec n|}}"
                f"= \\frac{{{tex(sp.Abs(AB1.dot(n)))}}}"
                f"{{{tex(sp.sqrt(sum(c**2 for c in AB1)))}}} = {ans_latex}$$"
            ),
            "highlight": ["Line_AB1", "Plane_Base"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正三棱柱 · 点面距离 ---

@register_solver("regular_triangular_prism", "point_plane_distance")
def solve_prism_point_plane_distance(base_edge=2, height=3) -> Solution:
    """正三棱柱 ABC-A1B1C1 中 C₁ 到侧面 ABB₁A₁ 的距离。"""
    import bodies as _bodies
    a = sp.Rational(base_edge)
    h = sp.Rational(height)
    pts = build_regular_triangular_prism(base_edge, height)

    # 侧面 ABB₁A₁：平面 y=0（过 A, B, B₁）
    n = normal_from_points(pts["A"], pts["B"], pts["B1"])
    dist = point_plane_distance(pts["C1"], pts["A"], n)
    ans_latex = tex(dist)
    ans_val = float(dist)

    problem_text = (
        f"正三棱柱 $ABC-A_1B_1C_1$，底面等边三角形边长为 ${tex(a)}$，"
        f"高为 ${tex(h)}$，求点 $C_1$ 到侧面 $ABB_1A_1$ 的距离。"
    )

    topo = _bodies.prism()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "点 C₁ 到侧面 ABB₁A₁ 的距离",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Point_C1": {"type": "sphere", "pt": "C1", "color": "emphasis", "radius": 0.18},
            "Plane_Side": {"type": "plane", "pts": ["A", "B", "B1"]},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[2, 5, 3],
        lesson_meta="交互解题 · 三棱柱点面距离", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点，$AB$ 沿 $x$ 轴，$AA_1$ 沿 $z$ 轴建系。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, B_1{mp['B1']}, C_1{mp['C1']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 2, "y": 5, "z": 3},
        },
        {
            "title": "求侧面法向量",
            "content": (
                f"<p>侧面 $ABB_1A_1$ 由点 $A, B, B_1$ 确定。</p>"
                f"<p>$\\overrightarrow{{AB}} = {tex_vec(pts['B'] - pts['A'])}, \\quad"
                f"\\overrightarrow{{AB_1}} = {tex_vec(pts['B1'] - pts['A'])}$</p>"
                f"<p>法向量 $\\vec n = \\overrightarrow{{AB}} \\times "
                f"\\overrightarrow{{AB_1}} = {tex_vec(n)}$</p>"
                f"<p>即平面 $y=0$。</p>"
            ),
            "highlight": ["Plane_Side"],
            "cameraPos": {"x": 0, "y": 6, "z": 2},
        },
        {
            "title": "计算点到平面距离",
            "content": (
                f"<p>$C_1$ 到平面 $y=0$ 的距离即 $C_1$ 的 $y$ 坐标：</p>"
                f"$$d = |y_{{C_1}}| = \\frac{{\\sqrt{{3}}}}{{2}}a"
                f"= \\frac{{\\sqrt{{3}}}}{{2}} \\cdot {tex(a)} = {ans_latex}$$"
            ),
            "highlight": ["Point_C1", "Plane_Side"],
            "cameraPos": {"x": 2, "y": 5, "z": 3},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[2, 5, 3], scale=1.5,
    )


# --- 长方体 · 体积 ---

@register_solver("cuboid", "volume")
def solve_cuboid_volume(lx=3, ly=2, lz=2) -> Solution:
    """长方体 ABCD-A1B1C1D1，长宽高为 lx, ly, lz，求体积。"""
    import bodies as _bodies
    lx_s, ly_s, lz_s = sp.Rational(lx), sp.Rational(ly), sp.Rational(lz)
    pts = build_cuboid(lx, ly, lz)

    V_expr = volume_box(lx_s, ly_s, lz_s)
    ans_latex = tex(V_expr)
    ans_val = float(V_expr)

    problem_text = (
        f"长方体 $ABCD-A_1B_1C_1D_1$，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，"
        f"$AA_1={tex(lz_s)}$，求该长方体的体积。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "长方体 ABCD-A₁B₁C₁D₁ 的体积",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={"Axis": {"type": "axes", "size": 3}},
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 长方体体积", problem=problem_text,
    )

    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，$AA_1={tex(lz_s)}$。</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "计算体积",
            "content": (
                f"<p>长方体体积公式：$V = AB \\cdot AD \\cdot AA_1$</p>"
                f"$$V = {tex(lx_s)} \\cdot {tex(ly_s)} \\cdot {tex(lz_s)} = {ans_latex}$$"
            ),
            "highlight": [], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[5, 4, 5], scale=1.5,
    )


# --- 长方体 · 线面角 ---

@register_solver("cuboid", "line_plane_angle")
def solve_cuboid_line_plane_angle(lx=3, ly=2, lz=2) -> Solution:
    """长方体 ABCD-A1B1C1D1 中 AC₁ 与平面 BDD₁B₁ 所成角的正弦值。"""
    import bodies as _bodies
    lx_s, ly_s, lz_s = sp.Rational(lx), sp.Rational(ly), sp.Rational(lz)
    pts = build_cuboid(lx, ly, lz)

    AC1 = pts["C1"] - pts["A"]
    BD = pts["D"] - pts["B"]
    BB1 = pts["B1"] - pts["B"]
    n = BD.cross(BB1)
    n_simpl = simplify_vec(n)
    sin_theta = line_plane_angle_sin(AC1, n)
    ans_latex = tex(sin_theta)
    ans_val = float(sin_theta)

    problem_text = (
        f"长方体 $ABCD-A_1B_1C_1D_1$，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，"
        f"$AA_1={tex(lz_s)}$，求直线 $AC_1$ 与平面 $BDD_1B_1$ 所成角的正弦值。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "直线 AC₁ 与平面 BDD₁B₁ 所成角的正弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AC1": {"type": "line", "a": "A", "b": "C1", "color": "emphasis", "depthTest": False},
            "Plane_BDD1B1": {"type": "plane", "pts": ["B", "D", "D1", "B1"]},
            "Normal_Vector": {"type": "arrow", "origin": "B", "dir": [0, 0.8, 1], "length": 1.6, "color": "normal"},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 长方体线面角", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，$AA_1={tex(lz_s)}$。</p>"
                f"<p>$A{mp['A']}, C_1{mp['C1']}, B{mp['B']}, D{mp['D']}, B_1{mp['B1']}, D_1{mp['D1']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "求直线方向向量",
            "content": (
                f"$$\\overrightarrow{{AC_1}} = C_1 - A = {tex_vec(AC1)}$$"
            ),
            "highlight": ["Line_AC1"], "cameraPos": {"x": 3, "y": 5, "z": 7},
        },
        {
            "title": "求平面法向量",
            "content": (
                f"<p>平面 $BDD_1B_1$ 中：</p>"
                f"$$\\overrightarrow{{BD}} = {tex_vec(BD)}, \\quad \\overrightarrow{{BB_1}} = {tex_vec(BB1)}$$"
                f"<p>法向量 $\\vec n = \\overrightarrow{{BD}} \\times \\overrightarrow{{BB_1}} = {tex_vec(n)}$</p>"
                f"<p>简化取 $\\vec n = {tex_vec(n_simpl)}$</p>"
            ),
            "highlight": ["Line_AC1", "Plane_BDD1B1", "Normal_Vector"],
            "cameraPos": {"x": 4, "y": 5, "z": 5},
        },
        {
            "title": "计算线面角正弦值",
            "content": (
                f"$$\\sin\\theta = \\frac{{|\\overrightarrow{{AC_1}} \\cdot \\vec n|}}"
                f"{{|\\overrightarrow{{AC_1}}| \\cdot |\\vec n|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_AC1", "Plane_BDD1B1", "Normal_Vector"],
            "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[5, 4, 5], scale=1.5,
    )


# --- 长方体 · 异面直线夹角 ---

@register_solver("cuboid", "line_line_angle")
def solve_cuboid_line_line_angle(lx=3, ly=2, lz=2) -> Solution:
    """长方体 ABCD-A1B1C1D1 中异面直线 A₁C₁ 与 BD 所成角的余弦值。"""
    import bodies as _bodies
    lx_s, ly_s, lz_s = sp.Rational(lx), sp.Rational(ly), sp.Rational(lz)
    pts = build_cuboid(lx, ly, lz)

    A1C1 = pts["C1"] - pts["A1"]
    BD = pts["D"] - pts["B"]
    cos_theta = line_line_angle_cos(A1C1, BD)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"长方体 $ABCD-A_1B_1C_1D_1$，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，"
        f"$AA_1={tex(lz_s)}$，求异面直线 $A_1C_1$ 与 $BD$ 所成角的余弦值。"
    )

    topo = _bodies.cuboid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "异面直线 A₁C₁ 与 BD 所成角的余弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_A1C1": {"type": "line", "a": "A1", "b": "C1", "color": "emphasis", "depthTest": False},
            "Line_BD": {"type": "line", "a": "B", "b": "D", "color": "normal", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[5, 4, 5],
        lesson_meta="交互解题 · 长方体异面直线", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，$AB={tex(lx_s)}$，$AD={tex(ly_s)}$，$AA_1={tex(lz_s)}$。</p>"
                f"<p>$A_1{mp['A1']}, C_1{mp['C1']}, B{mp['B']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
        {
            "title": "求两直线方向向量",
            "content": (
                f"$$\\overrightarrow{{A_1C_1}} = {tex_vec(A1C1)}, \\quad \\overrightarrow{{BD}} = {tex_vec(BD)}$$"
            ),
            "highlight": ["Line_A1C1", "Line_BD"],
            "cameraPos": {"x": 3, "y": 5, "z": 6},
        },
        {
            "title": "计算夹角余弦",
            "content": (
                f"$$\\cos\\theta = \\frac{{|\\overrightarrow{{A_1C_1}} \\cdot \\overrightarrow{{BD}}|}}"
                f"{{|\\overrightarrow{{A_1C_1}}| \\cdot |\\overrightarrow{{BD}}|}} = {ans_latex}$$"
                f"<p>注意：此为长方体，长宽不等，夹角与正方体不同。</p>"
            ),
            "highlight": ["Line_A1C1", "Line_BD"],
            "cameraPos": {"x": 5, "y": 4, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[5, 4, 5], scale=1.5,
    )


# --- 正四面体 · 点面距离 ---

@register_solver("regular_tetrahedron", "point_plane_distance")
def solve_tetra_point_plane_distance(edge=2) -> Solution:
    """正四面体 ABCD 中点 A 到平面 BCD 的距离（即高）。"""
    import bodies as _bodies
    a = sp.Rational(edge)
    pts = build_regular_tetrahedron(edge)

    n = normal_from_points(pts["B"], pts["C"], pts["D"])
    dist = point_plane_distance(pts["A"], pts["B"], n)
    ans_latex = tex(dist)
    ans_val = float(dist)

    problem_text = (
        f"正四面体 $ABCD$ 棱长为 ${tex(a)}$，"
        f"求点 $A$ 到平面 $BCD$ 的距离。"
    )

    topo = _bodies.tri_pyramid(apex="D", base=("A", "B", "C"))
    tp = to_three(pts, scale=2.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "点 A 到平面 BCD 的距离（四面体的高）",
        scale=2.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Point_A": {"type": "sphere", "pt": "A", "color": "emphasis", "radius": 0.18},
            "Plane_BCD": {"type": "plane", "pts": ["B", "C", "D"]},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 正四面体点面距离", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    n_simpl = simplify_vec(n)
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以正四面体中心为原点建系，棱长为 ${tex(a)}$。</p>"
                f"<p>$A{mp['A']}, B{mp['B']}, C{mp['C']}, D{mp['D']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求平面 BCD 的法向量",
            "content": (
                f"<p>$\\overrightarrow{{BC}} = {tex_vec(pts['C'] - pts['B'])}, \\quad"
                f"\\overrightarrow{{BD}} = {tex_vec(pts['D'] - pts['B'])}$</p>"
                f"<p>法向量 $\\vec n = \\overrightarrow{{BC}} \\times \\overrightarrow{{BD}} = {tex_vec(n)}$</p>"
                f"<p>简化取 $\\vec n = {tex_vec(n_simpl)}$</p>"
            ),
            "highlight": ["Plane_BCD"],
            "cameraPos": {"x": 4, "y": 5, "z": 3},
        },
        {
            "title": "计算点面距离",
            "content": (
                f"<p>点 $A$ 到平面 $BCD$ 的距离即为正四面体的高：</p>"
                f"$$d = \\frac{{|\\overrightarrow{{BA}} \\cdot \\vec n|}}{{|\\vec n|}}"
                f"= {ans_latex} = \\frac{{\\sqrt{{6}}}}{{3}}a$$"
            ),
            "highlight": ["Point_A", "Plane_BCD"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=2.5,
    )


# --- 正四棱锥 · 异面直线夹角 ---

@register_solver("regular_quad_pyramid", "line_line_angle")
def solve_pyramid_line_line_angle(base_edge=2, height=1) -> Solution:
    """正四棱锥 P-ABCD 中异面直线 PC 与 AB 所成角的余弦值。"""
    import bodies as _bodies
    pts = build_regular_quad_pyramid(base_edge, height)

    PC = pts["C"] - pts["P"]
    AB = pts["B"] - pts["A"]
    cos_theta = line_line_angle_cos(PC, AB)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正四棱锥 $P-ABCD$，底面边长 ${base_edge}$，高 ${height}$，"
        f"求异面直线 $PC$ 与 $AB$ 所成角的余弦值。"
    )

    topo = _bodies.quad_pyramid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "异面直线 PC 与 AB 所成角的余弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_PC": {"type": "line", "a": "P", "b": "C", "color": "emphasis", "depthTest": False},
            "Line_AB": {"type": "line", "a": "A", "b": "B", "color": "normal", "depthTest": False},
            "Axis": {"type": "axes", "size": 2.5},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 四棱锥异面直线", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以底面中心 $O$ 为原点建系，底面边长 ${base_edge}$，高 ${height}$。</p>"
                f"<p>$P{mp['P']}, C{mp['C']}, A{mp['A']}, B{mp['B']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求方向向量",
            "content": (
                f"$$\\overrightarrow{{PC}} = {tex_vec(PC)}, \\quad \\overrightarrow{{AB}} = {tex_vec(AB)}$$"
            ),
            "highlight": ["Line_PC", "Line_AB"],
            "cameraPos": {"x": 3, "y": 5, "z": 4},
        },
        {
            "title": "计算夹角余弦",
            "content": (
                f"$$\\cos\\theta = \\frac{{|\\overrightarrow{{PC}} \\cdot \\overrightarrow{{AB}}|}}"
                f"{{|\\overrightarrow{{PC}}| \\cdot |\\overrightarrow{{AB}}|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_PC", "Line_AB"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正四棱锥 · 点面距离 ---

@register_solver("regular_quad_pyramid", "point_plane_distance")
def solve_pyramid_point_plane_distance(base_edge=2, height=1) -> Solution:
    """正四棱锥 P-ABCD 中点 B 到平面 PAC 的距离。"""
    import bodies as _bodies
    pts = build_regular_quad_pyramid(base_edge, height)

    n = normal_from_points(pts["P"], pts["A"], pts["C"])
    dist = point_plane_distance(pts["B"], pts["P"], n)
    ans_latex = tex(dist)
    ans_val = float(dist)

    problem_text = (
        f"正四棱锥 $P-ABCD$，底面边长 ${base_edge}$，高 ${height}$，"
        f"求点 $B$ 到平面 $PAC$ 的距离。"
    )

    topo = _bodies.quad_pyramid()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "点 B 到平面 PAC 的距离",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Point_B": {"type": "sphere", "pt": "B", "color": "emphasis", "radius": 0.18},
            "Plane_PAC": {"type": "plane", "pts": ["P", "A", "C"]},
            "Axis": {"type": "axes", "size": 2.5},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 四棱锥点面距离", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    n_simpl = simplify_vec(n)
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以底面中心 $O$ 为原点建系，底面边长 ${base_edge}$，高 ${height}$。</p>"
                f"<p>$P{mp['P']}, A{mp['A']}, C{mp['C']}, B{mp['B']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "分析平面 PAC",
            "content": (
                f"<p>$P, A, C$ 三点均在 $y=0$ 平面（$xOz$ 面）上。</p>"
                f"<p>故平面 $PAC$ 即 $y=0$ 平面，法向量 $\\vec n = (0, 1, 0)$。</p>"
            ),
            "highlight": ["Plane_PAC"],
            "cameraPos": {"x": 4, "y": 5, "z": 3},
        },
        {
            "title": "计算点 B 到平面的距离",
            "content": (
                f"<p>$B$ 的 $y$ 坐标为 $d = \\frac{{a}}{{\\sqrt{{2}}}}$（半对角线）。</p>"
                f"<p>故 $d = |y_B| = {ans_latex}$</p>"
            ),
            "highlight": ["Point_B", "Plane_PAC"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正三棱柱 · 二面角 ---

@register_solver("regular_triangular_prism", "dihedral_angle")
def solve_prism_dihedral_angle(base_edge=2, height=3) -> Solution:
    """正三棱柱 ABC-A1B1C1 中侧面 ABB₁A₁ 与 BCC₁B₁ 所成二面角的余弦值。"""
    import bodies as _bodies
    pts = build_regular_triangular_prism(base_edge, height)

    # 侧面 ABB₁A₁ → 点 A,B,B₁ 确定，法向量 n1
    n1 = normal_from_points(pts["A"], pts["B"], pts["B1"])
    # 侧面 BCC₁B₁ → 点 B,C,B₁ 确定，法向量 n2
    n2 = normal_from_points(pts["B"], pts["C"], pts["B1"])
    cos_theta = sp.simplify(sp.Abs(dihedral_cos_from_normals(n1, n2)))
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正三棱柱 $ABC-A_1B_1C_1$，底面等边三角形边长为 ${base_edge}$，"
        f"高为 ${height}$，求侧面 $ABB_1A_1$ 与 $BCC_1B_1$ 所成二面角的余弦值。"
    )

    topo = _bodies.prism()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "侧面 ABB₁A₁ 与 BCC₁B₁ 所成二面角的余弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Plane_ABB1A1": {"type": "plane", "pts": ["A", "B", "B1"]},
            "Plane_BCC1B1": {"type": "plane", "pts": ["B", "C", "B1"]},
            "Edge_BB1": {"type": "line", "a": "B", "b": "B1", "color": "emphasis", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 三棱柱二面角", problem=problem_text,
    )

    n1_simpl = simplify_vec(n1)
    n2_simpl = simplify_vec(n2)
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，底面等边三角形边长 ${base_edge}$，高 ${height}$。</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求两侧面的法向量",
            "content": (
                f"<p>侧面 $ABB_1A_1$：$\\vec n_1 = {tex_vec(n1_simpl)}$</p>"
                f"<p>侧面 $BCC_1B_1$：$\\vec n_2 = {tex_vec(n2_simpl)}$</p>"
            ),
            "highlight": ["Plane_ABB1A1", "Plane_BCC1B1", "Edge_BB1"],
            "cameraPos": {"x": 2, "y": 5, "z": 3},
        },
        {
            "title": "计算二面角余弦",
            "content": (
                f"<p>正三棱柱相邻侧面夹角为 $60^\\circ$：</p>"
                f"$$\\cos\\theta = \\frac{{|\\vec n_1 \\cdot \\vec n_2|}}"
                f"{{|\\vec n_1| \\cdot |\\vec n_2|}} = {ans_latex}$$"
            ),
            "highlight": ["Plane_ABB1A1", "Plane_BCC1B1", "Edge_BB1"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
        elements=lesson["model"]["elements"], target=center, initial_camera=[4, 3, 5], scale=1.5,
    )


# --- 正三棱柱 · 异面直线夹角 ---

@register_solver("regular_triangular_prism", "line_line_angle")
def solve_prism_line_line_angle(base_edge=2, height=3) -> Solution:
    """正三棱柱 ABC-A1B1C1 中异面直线 AC₁ 与 BC 所成角的余弦值。"""
    import bodies as _bodies
    pts = build_regular_triangular_prism(base_edge, height)

    AC1 = pts["C1"] - pts["A"]
    BC = pts["C"] - pts["B"]
    cos_theta = line_line_angle_cos(AC1, BC)
    ans_latex = tex(cos_theta)
    ans_val = float(cos_theta)

    problem_text = (
        f"正三棱柱 $ABC-A_1B_1C_1$，底面等边三角形边长为 ${base_edge}$，"
        f"高为 ${height}$，求异面直线 $AC_1$ 与 $BC$ 所成角的余弦值。"
    )

    topo = _bodies.prism()
    tp = to_three(pts, scale=1.5)
    names = list(tp)
    center = [sum(tp[k][i] for k in names) / len(names) for i in range(3)]

    lesson = _build_lesson_data(
        pts, [], ans_latex, ans_val, "异面直线 AC₁ 与 BC 所成角的余弦值",
        scale=1.5, spheres=topo["spheres"], edges=topo["edges"],
        elements={
            "Line_AC1": {"type": "line", "a": "A", "b": "C1", "color": "emphasis", "depthTest": False},
            "Line_BC": {"type": "line", "a": "B", "b": "C", "color": "normal", "depthTest": False},
            "Axis": {"type": "axes", "size": 3},
        },
        target=center, initial_camera=[4, 3, 5],
        lesson_meta="交互解题 · 三棱柱异面直线", problem=problem_text,
    )

    mp = {k: tex_vec(v) for k, v in pts.items()}
    steps = [
        {
            "title": "建立空间直角坐标系",
            "content": (
                f"<p>以 $A$ 为原点建系，底面等边三角形边长 ${base_edge}$，高 ${height}$。</p>"
                f"<p>$A{mp['A']}, C_1{mp['C1']}, B{mp['B']}, C{mp['C']}$</p>"
            ),
            "highlight": ["Axis"], "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
        {
            "title": "求方向向量",
            "content": (
                f"$$\\overrightarrow{{AC_1}} = {tex_vec(AC1)}, \\quad \\overrightarrow{{BC}} = {tex_vec(BC)}$$"
            ),
            "highlight": ["Line_AC1", "Line_BC"],
            "cameraPos": {"x": 3, "y": 5, "z": 5},
        },
        {
            "title": "计算夹角余弦",
            "content": (
                f"$$\\cos\\theta = \\frac{{|\\overrightarrow{{AC_1}} \\cdot \\overrightarrow{{BC}}|}}"
                f"{{|\\overrightarrow{{AC_1}}| \\cdot |\\overrightarrow{{BC}}|}} = {ans_latex}$$"
            ),
            "highlight": ["Line_AC1", "Line_BC"],
            "cameraPos": {"x": 4, "y": 3, "z": 5},
        },
    ]
    lesson["steps"] = steps

    return Solution(
        problem=problem_text, steps=steps, answer_latex=ans_latex, answer_value=ans_val,
        model=SolidModel(),
        lesson_meta=lesson["lesson"]["meta"], answer_label=lesson["lesson"]["answerLabel"],
        three_points=tp, spheres=topo["spheres"], edges=topo["edges"],
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
    solve_cube_point_range,
    # --- 新增题型 ---
    solve_cube_volume,
    solve_cube_dihedral_angle,
    solve_tetra_volume,
    solve_tetra_line_line_angle,
    solve_tetra_line_plane_angle,
    solve_tetra_dihedral_angle,
    solve_pyramid_volume,
    solve_pyramid_dihedral_angle,
    # --- 三棱柱 ---
    solve_prism_volume,
    solve_prism_line_plane_angle,
    solve_prism_point_plane_distance,
    # --- 长方体 ---
    solve_cuboid_volume,
    solve_cuboid_line_plane_angle,
    solve_cuboid_line_line_angle,
    # --- 缺口补全 ---
    solve_tetra_point_plane_distance,
    solve_pyramid_line_line_angle,
    solve_pyramid_point_plane_distance,
    solve_prism_dihedral_angle,
    solve_prism_line_line_angle,
]


def generate_random(seed: int = None, max_retries: int = 30) -> Solution:
    """随机选题型 + 随机参数 → 求解 → 答案不规整则重抽。

    Args:
        seed: 随机种子（None 表示不固定）
        max_retries: 最大重试次数
    """
    rng = _random.Random(seed)
    solver = _RANDOM_TEMPLATES[0]  # fallback if max_retries=0
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
            cleaned[k] = sp.Rational(v)
        except (TypeError, ValueError):
            logger.warning("Non-numeric parameter %s=%s, using default 2", k, v)
            cleaned[k] = 2
    return cleaned


def _keyword_fallback(problem_text: str) -> Solution:
    """原始关键词匹配逻辑，LLM 不可用时的降级方案。

    只对明确可匹配的题型做关键词匹配；
    无法判断时抛出 ValueError（让调用方返回错误而非瞎猜）。
    """
    problem_text = llm_parser._normalize_ocr_text(problem_text)
    lowered = problem_text.lower()

    # --- 正四面体（独立匹配，优先级高）---
    if "正四面体" in problem_text or "四面体" in problem_text:
        if "距离" in problem_text:
            return solve_tetra_point_plane_distance()
        if "体积" in problem_text:
            return solve_tetra_volume()
        if "二面角" in problem_text:
            return solve_tetra_dihedral_angle()
        if "异面" in problem_text:
            return solve_tetra_line_line_angle()
        if "线面角" in problem_text or ("所成角" in problem_text and "平面" in problem_text):
            return solve_tetra_line_plane_angle()
        return solve_tetra_volume()

    # --- 长方体（独立匹配）---
    if "长方体" in problem_text or "cuboid" in lowered:
        if "体积" in problem_text:
            return solve_cuboid_volume()
        if "异面" in problem_text:
            return solve_cuboid_line_line_angle()
        if "线面角" in problem_text or "所成角" in problem_text:
            return solve_cuboid_line_plane_angle()
        return solve_cuboid_volume()

    # --- 体积（跨几何体）---
    if "体积" in problem_text:
        if "正方体" in problem_text or "cube" in lowered:
            return solve_cube_volume()
        if "四棱锥" in problem_text or "pyramid" in lowered:
            return solve_pyramid_volume()

    # --- 二面角（跨几何体）---
    if "二面角" in problem_text:
        if "正方体" in problem_text or "cube" in lowered:
            return solve_cube_dihedral_angle()
        if "四棱锥" in problem_text or "pyramid" in lowered:
            return solve_pyramid_dihedral_angle()

    # 异面直线夹角（非长方体/非正四面体的回退）
    if "异面" in problem_text or "skew" in lowered:
        if "四棱锥" in problem_text:
            return solve_pyramid_line_line_angle()
        return solve_cube_line_line_angle()

    # 点到平面距离（非正四面体的回退）
    if ("距离" in problem_text or "distance" in lowered) and "平面" in problem_text:
        if "四棱锥" in problem_text:
            return solve_pyramid_point_plane_distance()
        return solve_cube_point_plane_distance()

    # 线面角（直线与平面所成角）
    if "线面角" in problem_text or ("所成角" in problem_text and "平面" in problem_text):
        return solve_line_plane_angle_cube(edge=2)

    # --- 三棱柱 ---
    if "三棱柱" in problem_text or "prism" in lowered:
        if "体积" in problem_text:
            return solve_prism_volume()
        if "二面角" in problem_text:
            return solve_prism_dihedral_angle()
        if "异面" in problem_text:
            return solve_prism_line_line_angle()
        if "距离" in problem_text:
            return solve_prism_point_plane_distance()
        if "线面角" in problem_text or "所成角" in problem_text:
            return solve_prism_line_plane_angle()
        return solve_prism_volume()

    # 正四棱锥（兜底）
    if "四棱锥" in problem_text or "pyramid" in lowered:
        if "异面" in problem_text:
            return solve_pyramid_line_line_angle()
        if "距离" in problem_text:
            return solve_pyramid_point_plane_distance()
        return solve_pyramid_line_plane_angle()

    # 动点取值范围（动点在侧面上满足条件，求线段长度范围）
    if "取值范围" in problem_text or "范围" in problem_text:
        if "正方体" in problem_text or "cube" in lowered:
            return solve_cube_point_range()

    # 随机出题
    if "随机" in problem_text or "random" in lowered:
        return generate_random()

    # 无法确定题型 → 抛出错误
    supported = ", ".join(
        f"{s}+{q}" for s, qs in list_supported_types().items() for q in qs
    )
    raise ValueError(
        f"无法自动判断题型，请手动选择题目类型。"
        f"当前支持：{supported}"
    )


def solve(problem_text: str) -> Solution:
    """解析题面并求解。

    优先尝试 LLM 结构化解析 → 关键词匹配 → LLM 纯文字解题。
    三层降级确保任何题目都有可用输出。
    """
    # Phase 1: LLM 解析
    parse_error_msg = None
    try:
        spec = llm_parser.parse_problem(problem_text)
        solver = get_solver(spec["shape_type"], spec["query_type"])
        if solver is None:
            supported = ", ".join(
                f"{s}+{q}" for s, qs in list_supported_types().items() for q in qs
            )
            msg = (
                f"不支持的问题类型：{spec['shape_type']} + {spec['query_type']}。"
                f"当前支持：{supported}"
            )
            raise ValueError(msg)
        params = _sanitize_params(spec.get("parameters", {}))
        logger.info("LLM parsed: shape=%s query=%s params=%s",
                     spec["shape_type"], spec["query_type"], params)
        return solver(**params)
    except llm_parser.LLMNotConfiguredError:
        logger.info("LLM not configured; falling back to keyword matching")
    except llm_parser.LLMParseError as e:
        error_str = str(e)
        if "不支持" in error_str:
            parse_error_msg = error_str
        logger.warning("LLM parse failed: %s; falling back to keyword matching", e)
    except Exception as e:
        logger.warning("LLM call failed (%s: %s); falling back to keyword matching",
                       type(e).__name__, e)

    # Phase 2: 降级 — 关键词匹配
    try:
        return _keyword_fallback(problem_text)
    except ValueError:
        pass  # 无法匹配题型，进入 Phase 3
    except Exception:
        logger.exception("Keyword fallback crashed unexpectedly — falling through to LLM text-only")
        pass  # 关键词匹配自身有 bug，降级到 Phase 3

    # Phase 3: 降级 — LLM 纯文字解题（无 3D 模型）
    try:
        logger.info("Falling back to LLM text-only solving")
        result = llm_parser.solve_text_only(problem_text)
        steps = result.get("steps", [])
        answer_latex = result.get("answer_latex", "")

        return Solution(
            problem=problem_text,
            steps=steps,
            answer_latex=answer_latex,
            answer_value=0.0,
            model=SolidModel(),
            lesson_meta="AI 解题",
            answer_label="答案",
            three_points={},
            spheres=[],
            edges=[],
            elements={},
            target=[0, 0, 0],
            initial_camera=[0, 0, 5],
            scale=1.0,
            text_only=True,
        )
    except Exception as e:
        logger.exception("LLM text-only solving failed")
        # Always show the actual failure reason, not a stale Phase 1 parse error
        raise ValueError(
            f"AI 解题失败：{e}。"
            f"请尝试更明确的题目描述，或输入「随机」尝试随机出题。"
        )


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

    # --- 新增题型自检 ---
    print("\n=== cube: volume ===")
    sol_cv = solve_cube_volume(2)
    expected_cv = 8
    ok_cv = abs(sol_cv.answer_value - expected_cv) < 1e-12
    print(f"  V = {sol_cv.answer_latex} = {sol_cv.answer_value}  {'PASS' if ok_cv else 'FAIL'}")
    assert ok_cv, "cube volume mismatch"

    print("\n=== cube: dihedral angle ===")
    sol_cd = solve_cube_dihedral_angle(2)
    expected_cd = float(sqrt(3) / 3)
    ok_cd = abs(sol_cd.answer_value - expected_cd) < 1e-12
    print(f"  cos = {sol_cd.answer_latex} = {sol_cd.answer_value}  {'PASS' if ok_cd else 'FAIL'}")
    assert ok_cd, "cube dihedral angle mismatch"

    print("\n=== regular tetrahedron: volume ===")
    sol_tv = solve_tetra_volume(2)
    expected_tv = float(2 * sqrt(2) / 3)
    ok_tv = abs(sol_tv.answer_value - expected_tv) < 1e-12
    print(f"  V = {sol_tv.answer_latex} = {sol_tv.answer_value}  {'PASS' if ok_tv else 'FAIL'}")
    assert ok_tv, "tetra volume mismatch"

    print("\n=== regular tetrahedron: skew line ===")
    sol_ts = solve_tetra_line_line_angle(2)
    expected_ts = 0.0
    ok_ts = abs(sol_ts.answer_value - expected_ts) < 1e-12
    print(f"  cos = {sol_ts.answer_latex} = {sol_ts.answer_value}  {'PASS' if ok_ts else 'FAIL'}")
    assert ok_ts, "tetra line-line angle mismatch"

    print("\n=== regular tetrahedron: line-plane angle ===")
    sol_tlp = solve_tetra_line_plane_angle(2)
    expected_tlp = float(sqrt(6) / 3)
    ok_tlp = abs(sol_tlp.answer_value - expected_tlp) < 1e-12
    print(f"  sin = {sol_tlp.answer_latex} = {sol_tlp.answer_value}  {'PASS' if ok_tlp else 'FAIL'}")
    assert ok_tlp, "tetra line-plane angle mismatch"

    print("\n=== regular tetrahedron: dihedral angle ===")
    sol_td = solve_tetra_dihedral_angle(2)
    expected_td = 1.0 / 3.0
    ok_td = abs(sol_td.answer_value - expected_td) < 1e-12
    print(f"  cos = {sol_td.answer_latex} = {sol_td.answer_value}  {'PASS' if ok_td else 'FAIL'}")
    assert ok_td, "tetra dihedral angle mismatch"

    print("\n=== regular quad pyramid: volume ===")
    sol_pv = solve_pyramid_volume(2, 1)
    expected_pv = float(sp.Rational(4, 3))
    ok_pv = abs(sol_pv.answer_value - expected_pv) < 1e-12
    print(f"  V = {sol_pv.answer_latex} = {sol_pv.answer_value}  {'PASS' if ok_pv else 'FAIL'}")
    assert ok_pv, "pyramid volume mismatch"

    print("\n=== regular quad pyramid: dihedral angle ===")
    sol_pd = solve_pyramid_dihedral_angle(2, 1)
    expected_pd = float(sqrt(2) / 2)
    ok_pd = abs(sol_pd.answer_value - expected_pd) < 1e-12
    print(f"  cos = {sol_pd.answer_latex} = {sol_pd.answer_value}  {'PASS' if ok_pd else 'FAIL'}")
    assert ok_pd, "pyramid dihedral angle mismatch"

    # --- 三棱柱自检 ---
    print("\n=== regular triangular prism: volume ===")
    sol_pv2 = solve_prism_volume(2, 3)
    # base area = 2²√3/4 = √3, V = 3√3
    expected_pv2 = float(3 * sqrt(3))
    ok_pv2 = abs(sol_pv2.answer_value - expected_pv2) < 1e-12
    print(f"  V = {sol_pv2.answer_latex} = {sol_pv2.answer_value}  {'PASS' if ok_pv2 else 'FAIL'}")
    assert ok_pv2, "prism volume mismatch"

    print("\n=== regular triangular prism: line-plane angle ===")
    sol_plp = solve_prism_line_plane_angle(2, 3)
    # AB1 = (2, 0, 3), n = (0,0,1), sin = 3/√13
    expected_plp = float(3 / sqrt(13))
    ok_plp = abs(sol_plp.answer_value - expected_plp) < 1e-12
    print(f"  sin = {sol_plp.answer_latex} = {sol_plp.answer_value}  {'PASS' if ok_plp else 'FAIL'}")
    assert ok_plp, "prism line-plane angle mismatch"

    print("\n=== regular triangular prism: point-plane distance ===")
    sol_ppd = solve_prism_point_plane_distance(2, 3)
    # distance from C1 to y=0 is C1's y coordinate = a√3/2 = √3
    expected_ppd = float(sqrt(3))
    ok_ppd = abs(sol_ppd.answer_value - expected_ppd) < 1e-12
    print(f"  d = {sol_ppd.answer_latex} = {sol_ppd.answer_value}  {'PASS' if ok_ppd else 'FAIL'}")
    assert ok_ppd, "prism point-plane distance mismatch"

    # --- 长方体自检 ---
    print("\n=== cuboid: volume ===")
    sol_cuv = solve_cuboid_volume(3, 2, 2)
    assert abs(sol_cuv.answer_value - 12) < 1e-12, "cuboid volume mismatch"
    print(f"  V = {sol_cuv.answer_latex} = {sol_cuv.answer_value}  PASS")

    print("\n=== cuboid: line-plane angle ===")
    sol_culp = solve_cuboid_line_plane_angle(3, 2, 2)
    assert sol_culp.answer_value > 0, "cuboid line-plane angle mismatch"
    print(f"  sin = {sol_culp.answer_latex} = {sol_culp.answer_value}  PASS")

    print("\n=== cuboid: line-line angle ===")
    sol_cull = solve_cuboid_line_line_angle(3, 2, 2)
    # cos = |ly²-lx²|/(lx²+ly²) = |4-9|/13 = 5/13
    assert abs(sol_cull.answer_value - 5/13) < 1e-12, "cuboid line-line angle mismatch"
    print(f"  cos = {sol_cull.answer_latex} = {sol_cull.answer_value}  PASS")

    # --- 缺口补全自检 ---
    print("\n=== tetrahedron: point-plane distance ===")
    sol_tppd = solve_tetra_point_plane_distance(2)
    expected_tppd = float(2 * sqrt(6) / 3)
    assert abs(sol_tppd.answer_value - expected_tppd) < 1e-12, "tetra point-plane distance mismatch"
    print(f"  d = {sol_tppd.answer_latex} = {sol_tppd.answer_value}  PASS")

    print("\n=== pyramid: line-line angle ===")
    sol_pll = solve_pyramid_line_line_angle(2, 1)
    expected_pll = float(sqrt(3) / 3)
    assert abs(sol_pll.answer_value - expected_pll) < 1e-12, "pyramid line-line angle mismatch"
    print(f"  cos = {sol_pll.answer_latex} = {sol_pll.answer_value}  PASS")

    print("\n=== pyramid: point-plane distance ===")
    sol_ppd2 = solve_pyramid_point_plane_distance(2, 1)
    expected_ppd2 = float(sqrt(2))
    assert abs(sol_ppd2.answer_value - expected_ppd2) < 1e-12, "pyramid point-plane distance mismatch"
    print(f"  d = {sol_ppd2.answer_latex} = {sol_ppd2.answer_value}  PASS")

    print("\n=== prism: dihedral angle ===")
    sol_pda = solve_prism_dihedral_angle(2, 3)
    assert abs(sol_pda.answer_value - 0.5) < 1e-12, "prism dihedral angle mismatch"
    print(f"  cos = {sol_pda.answer_latex} = {sol_pda.answer_value}  PASS")

    print("\n=== prism: line-line angle ===")
    sol_pll2 = solve_prism_line_line_angle(2, 3)
    expected_pll2 = float(sqrt(13) / 13)
    assert abs(sol_pll2.answer_value - expected_pll2) < 1e-12, "prism line-line angle mismatch"
    print(f"  cos = {sol_pll2.answer_latex} = {sol_pll2.answer_value}  PASS")

    print("\n=== ALL SELF-TESTS PASSED ===")
