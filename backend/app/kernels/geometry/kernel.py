"""
立体几何 SymPy 精确计算内核 (参照 edulab geometry_kernel.py)。

核心设计原则：所有数值（最终答案、分步中间值、3D 坐标、高亮标注）
全部来自同一次 sympy 计算调用，确保数据一致性。

支持的问题类型：
- line_plane_angle: 线面角
- dihedral_angle: 二面角
- skew_line_angle: 异面直线夹角
- point_plane_distance: 点面距离
- volume: 体积
- surface_area: 表面积
"""

from __future__ import annotations
import sympy as sp
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComputationResult:
    """计算内核的完整输出。"""
    subject: str = "solid_geometry"
    body_type: str = "cube"
    problem_type: str = ""
    answer: dict = field(default_factory=dict)       # { latex, exact, numeric_approx }
    steps: list[dict] = field(default_factory=list)  # 分步解析
    model_3d: dict = field(default_factory=dict)     # 3D 渲染数据


class SolidGeometryKernel:
    """
    立体几何计算内核。

    使用坐标法 + 向量法统一求解各类立体几何问题。
    所有计算使用 sympy 符号数学，确保精确值。
    """

    def __init__(self):
        self.x, self.y, self.z = sp.symbols("x y z", real=True)

    def compute(self, problem: dict) -> ComputationResult:
        """根据结构化题目执行计算。"""
        body_type = problem.get("body_type", "cube")
        problem_type = problem.get("target", {}).get("type", "line_plane_angle")
        params = problem.get("given", {})

        result = ComputationResult(
            body_type=body_type,
            problem_type=problem_type,
        )

        if body_type == "cube":
            return self._compute_cube(problem, result)
        elif body_type == "cuboid":
            return self._compute_cuboid(problem, result)
        elif body_type == "pyramid":
            return self._compute_pyramid(problem, result)
        elif body_type == "prism":
            return self._compute_prism(problem, result)
        elif body_type == "tetrahedron":
            return self._compute_tetrahedron(problem, result)
        elif body_type == "cylinder":
            return self._compute_cylinder(problem, result)
        elif body_type == "cone":
            return self._compute_cone(problem, result)

        result.steps = [{
            "step_number": 1,
            "title": "暂不支持",
            "description": f"几何体类型 '{body_type}' 暂未实现",
            "formula": "",
            "result": "",
        }]
        result.answer = {"latex": "N/A", "exact": "N/A"}
        return result

    # ========== 正方体 ==========

    def _compute_cube(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """正方体相关问题计算。"""
        a = problem.get("given", {}).get("edge_length", 2)
        a = sp.sympify(a)
        vertices = self._cube_coordinates(a)
        result.model_3d = self._build_3d_model("cube", vertices, a)
        return self._solve_with_vertices(problem, vertices, result)

    def _cube_coordinates(self, a) -> dict[str, sp.Matrix]:
        """正方体标准坐标系：A 为原点，AB 为 x 轴，AD 为 y 轴，AA1 为 z 轴。"""
        return {
            "A":  sp.Matrix([0, 0, 0]),
            "B":  sp.Matrix([a, 0, 0]),
            "C":  sp.Matrix([a, a, 0]),
            "D":  sp.Matrix([0, a, 0]),
            "A1": sp.Matrix([0, 0, a]),
            "B1": sp.Matrix([a, 0, a]),
            "C1": sp.Matrix([a, a, a]),
            "D1": sp.Matrix([0, a, a]),
        }

    # ========== 长方体 (Cuboid) ==========

    def _compute_cuboid(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """长方体相关问题计算。支持长(a)/宽(b)/高(c) 三个独立参数。"""
        given = problem.get("given", {})
        a = sp.sympify(given.get("length", given.get("edge_length", 2)))
        b = sp.sympify(given.get("width", given.get("edge_length", 2)))
        c = sp.sympify(given.get("height", given.get("edge_length", 2)))

        vertices = self._cuboid_coordinates(a, b, c)
        result.model_3d = self._build_3d_model("cuboid", vertices, max(float(a), float(b), float(c)))

        return self._solve_with_vertices(problem, vertices, result)

    def _cuboid_coordinates(self, a, b, c) -> dict[str, sp.Matrix]:
        """长方体坐标系：长沿 x 轴，宽沿 y 轴，高沿 z 轴。"""
        return {
            "A":  sp.Matrix([0, 0, 0]),
            "B":  sp.Matrix([a, 0, 0]),
            "C":  sp.Matrix([a, b, 0]),
            "D":  sp.Matrix([0, b, 0]),
            "A1": sp.Matrix([0, 0, c]),
            "B1": sp.Matrix([a, 0, c]),
            "C1": sp.Matrix([a, b, c]),
            "D1": sp.Matrix([0, b, c]),
        }

    # ========== 正四棱锥 (Pyramid) ==========

    def _compute_pyramid(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """正四棱锥相关问题计算。"""
        given = problem.get("given", {})
        base_edge = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
        height = sp.sympify(given.get("height", 2))

        vertices = self._pyramid_coordinates(base_edge, height)
        result.model_3d = self._build_3d_model("pyramid", vertices, max(float(base_edge), float(height)))

        return self._solve_with_vertices(problem, vertices, result)

    def _pyramid_coordinates(self, base_edge, height) -> dict[str, sp.Matrix]:
        """正四棱锥：底面正方形中心为原点，P 在 z 轴正上方。"""
        half = base_edge / 2
        return {
            "P": sp.Matrix([0, 0, height]),
            "A": sp.Matrix([-half, -half, 0]),
            "B": sp.Matrix([half, -half, 0]),
            "C": sp.Matrix([half, half, 0]),
            "D": sp.Matrix([-half, half, 0]),
        }

    # ========== 正三棱柱 (Triangular Prism) ==========

    def _compute_prism(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """正三棱柱相关问题计算。"""
        given = problem.get("given", {})
        base_edge = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
        height = sp.sympify(given.get("height", 2))

        vertices = self._prism_coordinates(base_edge, height)
        result.model_3d = self._build_3d_model("prism", vertices, max(float(base_edge), float(height)))

        return self._solve_with_vertices(problem, vertices, result)

    def _prism_coordinates(self, base_edge, height) -> dict[str, sp.Matrix]:
        """正三棱柱：底面等边三角形在 xy 平面，侧棱沿 z 轴。"""
        r = base_edge / sp.sqrt(3)  # 外接圆半径
        return {
            "A":  sp.Matrix([0, r, 0]),
            "B":  sp.Matrix([-base_edge/2, -r/2, 0]),
            "C":  sp.Matrix([base_edge/2, -r/2, 0]),
            "A1": sp.Matrix([0, r, height]),
            "B1": sp.Matrix([-base_edge/2, -r/2, height]),
            "C1": sp.Matrix([base_edge/2, -r/2, height]),
        }

    # ========== 正四面体 (Tetrahedron) ==========

    def _compute_tetrahedron(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """正四面体相关问题计算。"""
        given = problem.get("given", {})
        edge = sp.sympify(given.get("edge_length", 2))

        vertices = self._tetrahedron_coordinates(edge)
        result.model_3d = self._build_3d_model("tetrahedron", vertices, float(edge))

        return self._solve_with_vertices(problem, vertices, result)

    def _tetrahedron_coordinates(self, edge) -> dict[str, sp.Matrix]:
        """正四面体：底面 ABC 在 xy 平面，D 在 z 轴上方。"""
        r = edge / sp.sqrt(3)  # 底面外接圆半径
        h = edge * sp.sqrt(6) / 3  # 高
        return {
            "A": sp.Matrix([0, r, 0]),
            "B": sp.Matrix([-edge/2, -r/2, 0]),
            "C": sp.Matrix([edge/2, -r/2, 0]),
            "D": sp.Matrix([0, 0, h]),
        }

    # ========== 圆柱 (Cylinder) ==========

    def _compute_cylinder(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """圆柱相关问题计算。"""
        given = problem.get("given", {})
        radius = sp.sympify(given.get("radius", given.get("edge_length", 1)))
        height = sp.sympify(given.get("height", 2))

        vertices = self._cylinder_coordinates(radius, height)
        result.model_3d = self._build_3d_model("cylinder", vertices, max(float(radius), float(height)))

        return self._solve_with_vertices(problem, vertices, result)

    def _cylinder_coordinates(self, radius, height, segments: int = 8) -> dict[str, sp.Matrix]:
        """圆柱：底面圆心在原点，用正 N 边形近似圆。"""
        import math
        labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        pts = {}
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = radius * sp.cos(angle)
            y = radius * sp.sin(angle)
            pts[labels[i]] = sp.Matrix([x, y, 0])
            pts[labels[i] + "1"] = sp.Matrix([x, y, height])
        return pts

    # ========== 圆锥 (Cone) ==========

    def _compute_cone(self, problem: dict, result: ComputationResult) -> ComputationResult:
        """圆锥相关问题计算。"""
        given = problem.get("given", {})
        radius = sp.sympify(given.get("radius", given.get("edge_length", 1)))
        height = sp.sympify(given.get("height", 2))

        vertices = self._cone_coordinates(radius, height)
        result.model_3d = self._build_3d_model("cone", vertices, max(float(radius), float(height)))

        return self._solve_with_vertices(problem, vertices, result)

    def _cone_coordinates(self, radius, height, segments: int = 8) -> dict[str, sp.Matrix]:
        """圆锥：底面圆心在原点，顶点 P 在 z 轴正上方。"""
        import math
        labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        pts = {"P": sp.Matrix([0, 0, height])}
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            pts[labels[i]] = sp.Matrix([radius * sp.cos(angle), radius * sp.sin(angle), 0])
        return pts

    # ========== 通用求解分发 ==========

    def _solve_with_vertices(
        self, problem: dict, V: dict, result: ComputationResult
    ) -> ComputationResult:
        """给定顶点坐标，按题型分发到对应计算方法。"""
        target = problem.get("target", {})
        problem_type = target.get("type", "line_plane_angle")

        if problem_type == "line_plane_angle":
            return self._compute_line_plane_angle(V, target, result)
        elif problem_type == "dihedral_angle":
            return self._compute_dihedral_angle(V, target, result)
        elif problem_type == "skew_line_angle":
            return self._compute_skew_line_angle(V, target, result)
        elif problem_type == "point_plane_distance":
            return self._compute_point_plane_distance(V, target, result)
        elif problem_type == "volume":
            return self._compute_volume(result, problem)
        elif problem_type == "surface_area":
            return self._compute_surface_area(result, problem)
        else:
            return self._unknown_type(result, problem_type)

    # ========== 通用计算方法（向量法，不依赖几何体类型） ==========

    def _compute_line_plane_angle(
        self, V: dict, target: dict, result: ComputationResult
    ) -> ComputationResult:
        """求直线与平面所成角。"""
        line_str = target.get("line", "AB1")
        plane_str = target.get("plane", "A1C1D")

        v_from, v_to = self._parse_line(line_str)
        line_dir = V[v_to] - V[v_from]

        plane_pts = self._parse_plane_label(plane_str)
        p1, p2, p3 = V[plane_pts[0]], V[plane_pts[1]], V[plane_pts[2]]
        normal = (p2 - p1).cross(p3 - p1)

        dot_val = sp.Abs(line_dir.dot(normal))
        mag_line = sp.sqrt(line_dir.dot(line_dir))
        mag_normal = sp.sqrt(normal.dot(normal))
        sin_theta = sp.simplify(dot_val / (mag_line * mag_normal))
        theta = sp.asin(sin_theta)

        result.steps = [
            {
                "step_number": 1,
                "title": "建立坐标系",
                "description": "建立空间直角坐标系，确定各点坐标",
                "formula": self._format_coords(V),
                "result": "",
            },
            {
                "step_number": 2,
                "title": "求直线的方向向量",
                "description": f"直线 {line_str} 的方向向量",
                "formula": (rf"\overrightarrow{{{line_str}}} = "
                           rf"{sp.latex(V[v_to])} - {sp.latex(V[v_from])} "
                           rf"= {sp.latex(line_dir)}"),
                "result": "",
            },
            {
                "step_number": 3,
                "title": "求平面的法向量",
                "description": f"平面 {plane_str} 的法向量",
                "formula": (rf"\vec{{n}} = ({sp.latex(p2 - p1)}) \times "
                           rf"({sp.latex(p3 - p1)}) = {sp.latex(normal)}"),
                "result": "",
            },
            {
                "step_number": 4,
                "title": "计算线面角",
                "description": f"直线 {line_str} 与平面 {plane_str} 所成角的正弦值",
                "formula": (rf"\sin\theta = \frac{{|\overrightarrow{{{line_str}}}\cdot\vec{{n}}|}}"
                           rf"{{|\overrightarrow{{{line_str}}}|\cdot|\vec{{n}}|}} "
                           rf"= {sp.latex(sin_theta)}"),
                "result": rf"\theta = \arcsin({sp.latex(sin_theta)}) = {sp.latex(theta)}",
            },
        ]

        result.answer = {
            "latex": sp.latex(sin_theta),
            "exact": str(sin_theta),
            "numeric": float(sin_theta.evalf()),
            "angle_latex": sp.latex(theta),
        }
        return result

    def _compute_dihedral_angle(
        self, V: dict, target: dict, result: ComputationResult
    ) -> ComputationResult:
        """求二面角。"""
        plane1_str = target.get("plane1", "A1BD")
        plane2_str = target.get("plane2", "C1BD")

        pts1 = self._parse_plane_label(plane1_str)
        pts2 = self._parse_plane_label(plane2_str)

        n1 = (V[pts1[1]] - V[pts1[0]]).cross(V[pts1[2]] - V[pts1[0]])
        n2 = (V[pts2[1]] - V[pts2[0]]).cross(V[pts2[2]] - V[pts2[0]])

        cos_angle = sp.Abs(n1.dot(n2)) / (sp.sqrt(n1.dot(n1)) * sp.sqrt(n2.dot(n2)))
        cos_angle = sp.simplify(cos_angle)

        result.steps = [
            {
                "step_number": 1,
                "title": "建立坐标系",
                "description": "建立空间直角坐标系，确定各点坐标",
                "formula": self._format_coords(V),
                "result": "",
            },
            {
                "step_number": 2,
                "title": "求平面法向量",
                "description": f"分别求平面 {plane1_str} 和 {plane2_str} 的法向量",
                "formula": (rf"\vec{{n}}_1 = {sp.latex(n1)}, \quad "
                           rf"\vec{{n}}_2 = {sp.latex(n2)}"),
                "result": "",
            },
            {
                "step_number": 3,
                "title": "计算二面角",
                "description": f"平面 {plane1_str} 与 {plane2_str} 的二面角",
                "formula": (rf"\cos\theta = \frac{{|\vec{{n}}_1 \cdot \vec{{n}}_2|}}"
                           rf"{{|\vec{{n}}_1| \cdot |\vec{{n}}_2|}} = "
                           rf"{sp.latex(cos_angle)}"),
                "result": rf"\theta = \arccos({sp.latex(cos_angle)})",
            },
        ]

        result.answer = {
            "latex": sp.latex(cos_angle),
            "exact": str(cos_angle),
            "numeric": float(cos_angle.evalf()),
        }
        return result

    def _compute_skew_line_angle(
        self, V: dict, target: dict, result: ComputationResult
    ) -> ComputationResult:
        """求异面直线夹角。"""
        line1_str = target.get("line1", "A1B")
        line2_str = target.get("line2", "C1D")

        v1 = V[self._parse_line(line1_str)[1]] - V[self._parse_line(line1_str)[0]]
        v2 = V[self._parse_line(line2_str)[1]] - V[self._parse_line(line2_str)[0]]

        cos_angle = sp.Abs(v1.dot(v2)) / (sp.sqrt(v1.dot(v1)) * sp.sqrt(v2.dot(v2)))
        cos_angle = sp.simplify(cos_angle)

        result.steps = [
            {
                "step_number": 1,
                "title": "建立坐标系",
                "description": "建立空间直角坐标系，确定各点坐标",
                "formula": self._format_coords(V),
                "result": "",
            },
            {
                "step_number": 2,
                "title": "求方向向量",
                "description": f"分别求 {line1_str} 和 {line2_str} 的方向向量",
                "formula": (rf"\overrightarrow{{{line1_str}}} = {sp.latex(v1)}, \quad "
                           rf"\overrightarrow{{{line2_str}}} = {sp.latex(v2)}"),
                "result": "",
            },
            {
                "step_number": 3,
                "title": "计算夹角",
                "description": f"异面直线 {line1_str} 与 {line2_str} 的夹角",
                "formula": (rf"\cos\theta = \frac{{|\overrightarrow{{{line1_str}}}"
                           rf"\cdot\overrightarrow{{{line2_str}}}|}}"
                           rf"{{|\overrightarrow{{{line1_str}}}|\cdot"
                           rf"|\overrightarrow{{{line2_str}}}|}} = "
                           rf"{sp.latex(cos_angle)}"),
                "result": rf"\theta = \arccos({sp.latex(cos_angle)})",
            },
        ]

        result.answer = {
            "latex": sp.latex(cos_angle),
            "exact": str(cos_angle),
            "numeric": float(cos_angle.evalf()),
        }
        return result

    def _compute_point_plane_distance(
        self, V: dict, target: dict, result: ComputationResult
    ) -> ComputationResult:
        """求点到平面的距离。"""
        point_str = target.get("point", "B1")
        plane_str = target.get("plane", "A1C1D")

        P = V[point_str]
        pts = self._parse_plane_label(plane_str)
        p0, p1, p2 = V[pts[0]], V[pts[1]], V[pts[2]]

        normal = (p1 - p0).cross(p2 - p0)
        distance = sp.Abs((P - p0).dot(normal)) / sp.sqrt(normal.dot(normal))
        distance = sp.simplify(distance)

        result.steps = [
            {
                "step_number": 1,
                "title": "建立坐标系",
                "description": "建立空间直角坐标系，确定各点坐标",
                "formula": self._format_coords(V),
                "result": "",
            },
            {
                "step_number": 2,
                "title": "求平面法向量",
                "description": f"平面 {plane_str} 的法向量",
                "formula": rf"\vec{{n}} = {sp.latex(normal)}",
                "result": "",
            },
            {
                "step_number": 3,
                "title": "代入点面距离公式",
                "description": f"点 {point_str} 到平面 {plane_str} 的距离",
                "formula": (rf"d = \frac{{|\overrightarrow{{{point_str}{pts[0]}}}"
                           rf"\cdot\vec{{n}}|}}{{|\vec{{n}}|}} = "
                           rf"{sp.latex(distance)}"),
                "result": f"距离为 {sp.latex(distance)}",
            },
        ]

        result.answer = {
            "latex": sp.latex(distance),
            "exact": str(distance),
            "numeric": float(distance.evalf()),
        }
        return result

    def _compute_volume(self, result: ComputationResult, problem: dict) -> ComputationResult:
        """计算体积（根据几何体类型选择公式）。"""
        body_type = result.body_type
        given = problem.get("given", {})

        if body_type == "cube":
            a = sp.sympify(given.get("edge_length", 2))
            v = a ** 3
            formula = rf"V = a^3 = {sp.latex(a)}^3 = {sp.latex(v)}"
            desc = "正方体体积 = 棱长的立方"
        elif body_type == "cuboid":
            a = sp.sympify(given.get("length", given.get("edge_length", 2)))
            b = sp.sympify(given.get("width", given.get("edge_length", 2)))
            c = sp.sympify(given.get("height", given.get("edge_length", 2)))
            v = a * b * c
            formula = rf"V = abc = {sp.latex(a)} \times {sp.latex(b)} \times {sp.latex(c)} = {sp.latex(v)}"
            desc = "长方体体积 = 长 × 宽 × 高"
        elif body_type == "pyramid":
            base = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
            h = sp.sympify(given.get("height", 2))
            v = base ** 2 * h / 3
            formula = rf"V = \frac{{1}}{{3}}a^2 h = \frac{{1}}{{3}} \times {sp.latex(base)}^2 \times {sp.latex(h)} = {sp.latex(v)}"
            desc = "四棱锥体积 = 1/3 × 底面积 × 高"
        elif body_type == "prism":
            base = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
            h = sp.sympify(given.get("height", 2))
            base_area = sp.sqrt(3) * base ** 2 / 4
            v = base_area * h
            formula = rf"V = \frac{{\sqrt{{3}}}}{{4}}a^2 h = {sp.latex(v)}"
            desc = "三棱柱体积 = 底面积 × 高"
        elif body_type == "tetrahedron":
            edge = sp.sympify(given.get("edge_length", 2))
            v = sp.sqrt(2) * edge ** 3 / 12
            formula = rf"V = \frac{{\sqrt{{2}}}}{{12}}a^3 = {sp.latex(v)}"
            desc = "正四面体体积 = √2/12 × 棱长³"
        elif body_type == "cylinder":
            r = sp.sympify(given.get("radius", given.get("edge_length", 1)))
            h = sp.sympify(given.get("height", 2))
            v = sp.pi * r ** 2 * h
            formula = rf"V = \pi r^2 h = {sp.latex(v)}"
            desc = "圆柱体积 = πr²h"
        elif body_type == "cone":
            r = sp.sympify(given.get("radius", given.get("edge_length", 1)))
            h = sp.sympify(given.get("height", 2))
            v = sp.pi * r ** 2 * h / 3
            formula = rf"V = \frac{{1}}{{3}}\pi r^2 h = {sp.latex(v)}"
            desc = "圆锥体积 = 1/3 × πr²h"
        else:
            v = sp.sympify(0)
            formula = "N/A"
            desc = "未知几何体"

        result.steps = [
            {
                "step_number": 1,
                "title": f"{body_type} 体积公式",
                "description": desc,
                "formula": formula,
                "result": f"体积为 {sp.latex(v)}",
            },
        ]
        result.answer = {
            "latex": sp.latex(v),
            "exact": str(v),
            "numeric": float(v.evalf()),
        }
        return result

    def _compute_surface_area(self, result: ComputationResult, problem: dict) -> ComputationResult:
        """计算表面积（根据几何体类型选择公式）。"""
        body_type = result.body_type
        given = problem.get("given", {})

        if body_type == "cube":
            a = sp.sympify(given.get("edge_length", 2))
            s = 6 * a ** 2
            formula = rf"S = 6a^2 = 6 \times {sp.latex(a)}^2 = {sp.latex(s)}"
            desc = "正方体表面积 = 6 × 棱长²"
        elif body_type == "cuboid":
            a = sp.sympify(given.get("length", given.get("edge_length", 2)))
            b = sp.sympify(given.get("width", given.get("edge_length", 2)))
            c = sp.sympify(given.get("height", given.get("edge_length", 2)))
            s = 2 * (a*b + b*c + a*c)
            formula = rf"S = 2(ab+bc+ac) = {sp.latex(s)}"
            desc = "长方体表面积 = 2(长×宽 + 宽×高 + 长×高)"
        elif body_type == "pyramid":
            base = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
            h = sp.sympify(given.get("height", 2))
            slant = sp.sqrt(h**2 + (base/2)**2)
            s = base**2 + 2 * base * slant
            formula = rf"S = a^2 + 2a\sqrt{{h^2+(a/2)^2}} = {sp.latex(s)}"
            desc = "四棱锥表面积 = 底面积 + 侧面积"
        elif body_type == "prism":
            base = sp.sympify(given.get("base_edge", given.get("edge_length", 2)))
            h = sp.sympify(given.get("height", 2))
            base_area = sp.sqrt(3) * base**2 / 4
            s = 2 * base_area + 3 * base * h
            formula = rf"S = \frac{{\sqrt{{3}}}}{{2}}a^2 + 3ah = {sp.latex(s)}"
            desc = "三棱柱表面积 = 2×底面积 + 侧面积"
        elif body_type == "tetrahedron":
            edge = sp.sympify(given.get("edge_length", 2))
            s = sp.sqrt(3) * edge**2
            formula = rf"S = \sqrt{{3}}a^2 = {sp.latex(s)}"
            desc = "正四面体表面积 = √3 × 棱长²"
        elif body_type == "cylinder":
            r = sp.sympify(given.get("radius", given.get("edge_length", 1)))
            h = sp.sympify(given.get("height", 2))
            s = 2 * sp.pi * r**2 + 2 * sp.pi * r * h
            formula = rf"S = 2\pi r^2 + 2\pi rh = {sp.latex(s)}"
            desc = "圆柱表面积 = 2πr² + 2πrh"
        elif body_type == "cone":
            r = sp.sympify(given.get("radius", given.get("edge_length", 1)))
            h = sp.sympify(given.get("height", 2))
            slant = sp.sqrt(r**2 + h**2)
            s = sp.pi * r**2 + sp.pi * r * slant
            formula = rf"S = \pi r^2 + \pi rl = {sp.latex(s)}"
            desc = "圆锥表面积 = πr² + πrl"
        else:
            s = sp.sympify(0)
            formula = "N/A"
            desc = "未知几何体"

        result.steps = [
            {
                "step_number": 1,
                "title": f"{body_type} 表面积公式",
                "description": desc,
                "formula": formula,
                "result": f"表面积为 {sp.latex(s)}",
            },
        ]
        result.answer = {
            "latex": sp.latex(s),
            "exact": str(s),
            "numeric": float(s.evalf()),
        }
        return result

    def _format_coords(self, V: dict) -> str:
        """格式化顶点坐标为 LaTeX 字符串。"""
        parts = []
        for label, vec in V.items():
            coords = ", ".join(sp.latex(c) for c in vec)
            parts.append(f"{label}({coords})")
        return "; ".join(parts)

    def _unknown_type(self, result: ComputationResult, problem_type: str) -> ComputationResult:
        result.steps = [{
            "step_number": 1,
            "title": "未知题型",
            "description": f"暂不支持的问题类型: '{problem_type}'",
            "formula": "",
            "result": "",
        }]
        result.answer = {"latex": "N/A", "exact": "N/A"}
        return result

    # ========== 辅助方法 ==========

    def _parse_line(self, line_str: str) -> tuple[str, str]:
        """解析直线标签，如 'AB1' → ('A', 'B1')"""
        if len(line_str) == 2:
            return (line_str[0], line_str[1])
        elif len(line_str) == 3:
            # 可能是 "AB1" (A→B1) 或 "A1B" (A1→B)
            if line_str[1].isdigit():
                return (line_str[:2], line_str[2])
            else:
                return (line_str[0], line_str[1:])
        elif len(line_str) == 4:
            return (line_str[:2], line_str[2:])
        return (line_str[0], line_str[-1])

    def _parse_plane_label(self, plane_str: str) -> list[str]:
        """解析平面标签，如 'A1C1D' → ['A1', 'C1', 'D']"""
        # 按数字后缀分割
        import re
        parts = re.findall(r'[A-Z]\d?', plane_str)
        return parts[:3] if len(parts) >= 3 else parts

    def _build_3d_model(
        self, body_type: str, vertices: dict[str, sp.Matrix], a
    ) -> dict:
        """构建 3D 渲染模型数据。"""
        # 将 sympy 矩阵转为 Python float 列表
        points = {}
        for label, vec in vertices.items():
            pt = [float(c.evalf()) if hasattr(c, 'evalf') else float(c) for c in vec]
            points[label] = pt

        from app.kernels.geometry.bodies import get_body_edges, get_body_faces

        edges = get_body_edges(body_type)
        faces = get_body_faces(body_type)

        return {
            "points": points,
            "edges": edges,
            "faces": faces,
            "scale": float(a),
        }

    def to_three_coords(
        self, sympy_points: dict[str, sp.Matrix], scale: float = 1.0
    ) -> dict[str, list[float]]:
        """将 sympy 坐标转换为 Three.js 可用的浮点坐标。"""
        result = {}
        for label, vec in sympy_points.items():
            result[label] = [
                float(vec[0].evalf()) / scale,
                float(vec[2].evalf()) / scale,  # y/z 交换适配 Three.js
                float(vec[1].evalf()) / scale,
            ]
        return result
