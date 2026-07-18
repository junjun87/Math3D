"""
解析几何 SymPy 精确计算内核。

使用 sympy.geometry 解决平面解析几何问题：
直线/圆/椭圆/双曲线/抛物线方程、距离、交点、切线。
"""

from __future__ import annotations
import re
import sympy as sp
from dataclasses import dataclass, field


@dataclass
class AnalyticResult:
    """解析几何计算结果。"""
    subject: str = "analytic_geometry"
    problem_type: str = ""
    answer: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    model_2d: dict = field(default_factory=dict)


class AnalyticGeometryKernel:

    def __init__(self):
        self.x, self.y = sp.symbols("x y", real=True)

    def compute(self, problem: dict) -> dict:
        target = problem.get("target", {})
        ptype = target.get("type", "line_equation")

        handler = getattr(self, f"_handle_{ptype}", None)
        if handler:
            result = handler(problem)
        else:
            result = AnalyticResult(problem_type=ptype)
            result.steps = [{
                "step_number": 1,
                "title": "暂不支持",
                "description": f"解析几何题型 '{ptype}' 开发中",
                "formula": "",
                "result": "",
            }]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        return {
            "subject": result.subject,
            "problem_type": result.problem_type,
            "answer": result.answer,
            "steps": result.steps,
            "model_2d": result.model_2d,
        }

    # ========== 直线方程 ==========

    def _handle_line_equation(self, problem: dict) -> AnalyticResult:
        """求直线方程。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AnalyticResult(problem_type="line_equation")
        steps = []

        point = target.get("point") or given.get("point")
        relation = target.get("relation") or ""  # perpendicular, parallel
        line_str = target.get("line") or given.get("line", "")

        # 从文本中提取已知直线
        known_line = None
        if line_str:
            known_line = self._parse_line_from_str(line_str)

        # 从文本中提取点
        pts = self._extract_points(desc)
        if point:
            pt = sp.Point(point[0], point[1])
        elif pts:
            pt = sp.Point(pts[0][0], pts[0][1])
        else:
            pt = sp.Point(0, 0)

        # 场景1：过一点且垂直于已知直线
        if known_line and relation == "perpendicular":
            slope = -1 / known_line.slope
            result_line = sp.Line(pt, pt + sp.Point(1, slope))

            steps = [
                {"step_number": 1, "title": "已知条件",
                 "description": f"已知直线 {sp.latex(known_line)}，求过点{sp.latex(pt)}且垂直于该直线的直线",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "求已知直线的斜率",
                 "description": f"将直线化为斜截式",
                 "formula": rf"k_1 = {sp.latex(known_line.slope)}",
                 "result": ""},
                {"step_number": 3, "title": "求垂直直线的斜率",
                 "description": "垂直直线斜率乘积为 -1",
                 "formula": rf"k_2 = -\frac{{1}}{{k_1}} = {sp.latex(-1/known_line.slope)}",
                 "result": ""},
                {"step_number": 4, "title": "点斜式写出直线方程",
                 "description": f"过点{sp.latex(pt)}，斜率为{sp.latex(-1/known_line.slope)}",
                 "formula": sp.latex(result_line.equation(x=self.x, y=self.y)),
                 "result": f"直线方程为 {sp.latex(result_line)}"},
            ]

        # 场景2：过一点且平行于已知直线
        elif known_line and relation == "parallel":
            slope = known_line.slope
            result_line = sp.Line(pt, pt + sp.Point(1, slope))

            steps = [
                {"step_number": 1, "title": "已知条件",
                 "description": f"已知直线 {sp.latex(known_line)}，求过点{sp.latex(pt)}且平行于该直线的直线",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "求已知直线的斜率",
                 "description": f"平行直线斜率相等",
                 "formula": rf"k = {sp.latex(slope)}",
                 "result": ""},
                {"step_number": 3, "title": "点斜式写出直线方程",
                 "description": f"过点{sp.latex(pt)}，斜率为{sp.latex(slope)}",
                 "formula": sp.latex(result_line.equation(x=self.x, y=self.y)),
                 "result": f"直线方程为 {sp.latex(result_line)}"},
            ]

        # 场景3：两点式
        elif len(pts) >= 2:
            p1 = sp.Point(pts[0][0], pts[0][1])
            p2 = sp.Point(pts[1][0], pts[1][1])
            result_line = sp.Line(p1, p2)

            steps = [
                {"step_number": 1, "title": "已知两点",
                 "description": f"点 A{sp.latex(p1)}，点 B{sp.latex(p2)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "求斜率",
                 "description": "两点间斜率公式",
                 "formula": rf"k = \frac{{y_2 - y_1}}{{x_2 - x_1}} = {sp.latex(result_line.slope)}",
                 "result": ""},
                {"step_number": 3, "title": "两点式写出直线方程",
                 "description": "",
                 "formula": sp.latex(result_line.equation(x=self.x, y=self.y)),
                 "result": f"直线方程为 {sp.latex(result_line)}"},
            ]

        # 场景4：已知斜率和一点
        else:
            result_line = sp.Line(pt, pt + sp.Point(1, 1))

            steps = [
                {"step_number": 1, "title": "点斜式",
                 "description": f"过点{sp.latex(pt)}的直线",
                 "formula": sp.latex(result_line.equation(x=self.x, y=self.y)),
                 "result": f"直线方程为 {sp.latex(result_line)}"},
            ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(result_line.equation(x=self.x, y=self.y)),
            "exact": str(result_line.equation(x=self.x, y=self.y)),
        }

        # 2D 渲染数据
        result.model_2d = self._line_2d_model(result_line)

        return result

    # ========== 圆的方程 ==========

    def _handle_circle_equation(self, problem: dict) -> AnalyticResult:
        """求圆的方程。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AnalyticResult(problem_type="circle_equation")
        steps = []

        center = target.get("center") or given.get("center")
        radius = target.get("radius") or given.get("radius")
        diameter_pts = target.get("diameter_endpoints") or given.get("diameter_endpoints")
        points_on_circle = given.get("points_on_circle") or []

        # 场景1：已知圆心和半径
        if center and radius:
            c = sp.Point(center[0], center[1])
            r = sp.sympify(radius)
            eq = (self.x - c.x)**2 + (self.y - c.y)**2 - r**2

            steps = [
                {"step_number": 1, "title": "圆心和半径",
                 "description": f"圆心 {sp.latex(c)}，半径 r = {sp.latex(r)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "圆的标准方程",
                 "description": "(x - a)² + (y - b)² = r²",
                 "formula": sp.latex(sp.Eq((self.x - c.x)**2 + (self.y - c.y)**2, r**2)),
                 "result": f"圆的方程为 {sp.latex(sp.Eq(sp.simplify(eq + r**2), r**2))}"},
            ]

        # 场景2：已知直径两端点
        elif diameter_pts and len(diameter_pts) >= 2:
            p1 = sp.Point(diameter_pts[0][0], diameter_pts[0][1])
            p2 = sp.Point(diameter_pts[1][0], diameter_pts[1][1])
            center_pt = sp.Point((p1.x + p2.x)/2, (p1.y + p2.y)/2)
            r = p1.distance(p2) / 2

            steps = [
                {"step_number": 1, "title": "直径端点",
                 "description": f"A{sp.latex(p1)}，B{sp.latex(p2)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "求圆心（中点）",
                 "description": "圆心为直径中点",
                 "formula": rf"O = \left(\frac{{{sp.latex(p1.x)}+{sp.latex(p2.x)}}}{{2}}, \frac{{{sp.latex(p1.y)}+{sp.latex(p2.y)}}}{{2}}\right) = {sp.latex(center_pt)}",
                 "result": ""},
                {"step_number": 3, "title": "求半径",
                 "description": "半径为直径的一半",
                 "formula": rf"r = \frac{{|AB|}}{{2}} = {sp.latex(r)}",
                 "result": ""},
                {"step_number": 4, "title": "圆的标准方程",
                 "description": "",
                 "formula": sp.latex(sp.Eq((self.x - center_pt.x)**2 + (self.y - center_pt.y)**2, r**2)),
                 "result": f"圆的方程为 {sp.latex(sp.Eq((self.x - center_pt.x)**2 + (self.y - center_pt.y)**2, r**2))}"},
            ]
            c = center_pt

        # 场景3：从文本提取
        else:
            pts = self._extract_points(desc)
            if len(pts) >= 2:
                c = sp.Point(pts[0][0], pts[0][1])
                r = sp.sqrt((pts[1][0] - pts[0][0])**2 + (pts[1][1] - pts[0][1])**2)
            else:
                c = sp.Point(0, 0)
                r = sp.sympify(1)

            steps = [
                {"step_number": 1, "title": "圆的标准方程",
                 "description": f"圆心 {sp.latex(c)}，半径 r = {sp.latex(r)}",
                 "formula": sp.latex(sp.Eq((self.x - c.x)**2 + (self.y - c.y)**2, r**2)),
                 "result": ""},
            ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(sp.Eq((self.x - c.x)**2 + (self.y - c.y)**2, r**2)),
            "exact": str(sp.Eq((self.x - c.x)**2 + (self.y - c.y)**2, r**2)),
        }
        result.model_2d = self._circle_2d_model(c, r)

        return result

    # ========== 椭圆 ==========

    def _handle_ellipse_equation(self, problem: dict) -> AnalyticResult:
        """求椭圆方程/性质。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AnalyticResult(problem_type="ellipse_equation")
        steps = []

        a_val = given.get("a") or given.get("semi_major")
        b_val = given.get("b") or given.get("semi_minor")
        c_val = given.get("c") or given.get("focal_distance")

        # 从表达式 x²/a² + y²/b² = 1 提取
        a, b = self._extract_ellipse_params(desc)
        if a_val:
            a = sp.sympify(a_val)
        if b_val:
            b = sp.sympify(b_val)
        if a is None:
            a = sp.sympify(4)
        if b is None:
            b = sp.sympify(3)

        c = sp.sqrt(sp.Abs(a**2 - b**2))  # 半焦距
        e = c / a if a != 0 else sp.sympify(0)  # 离心率

        steps = [
            {"step_number": 1, "title": "椭圆标准方程",
             "description": "",
             "formula": sp.latex(sp.Eq(self.x**2/a**2 + self.y**2/b**2, 1)),
             "result": f"椭圆方程为 {sp.latex(sp.Eq(self.x**2/a**2 + self.y**2/b**2, 1))}"},
            {"step_number": 2, "title": "求半焦距",
             "description": "c² = |a² - b²|",
             "formula": rf"c = \sqrt{{|{sp.latex(a)}^2 - {sp.latex(b)}^2|}} = {sp.latex(c)}",
             "result": ""},
            {"step_number": 3, "title": "焦点坐标",
             "description": "焦点在长轴上 (±c, 0)",
             "formula": rf"F_1({sp.latex(-c)}, 0),\; F_2({sp.latex(c)}, 0)",
             "result": ""},
            {"step_number": 4, "title": "离心率",
             "description": "e = c/a",
             "formula": rf"e = \frac{{{sp.latex(c)}}}{{{sp.latex(a)}}} = {sp.latex(e)}",
             "result": ""},
        ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(sp.Eq(self.x**2/a**2 + self.y**2/b**2, 1)),
            "exact": f"x^2/{a}^2 + y^2/{b}^2 = 1",
        }

        return result

    # ========== 双曲线 ==========

    def _handle_hyperbola_equation(self, problem: dict) -> AnalyticResult:
        """求双曲线方程/性质。"""
        desc = problem.get("description", "")
        given = problem.get("given", {})

        result = AnalyticResult(problem_type="hyperbola_equation")
        steps = []

        a, b = self._extract_ellipse_params(desc)
        if a is None:
            a = sp.sympify(3)
        if b is None:
            b = sp.sympify(4)

        c = sp.sqrt(a**2 + b**2)
        e = c / a
        asymptote = b / a  # 渐近线斜率

        steps = [
            {"step_number": 1, "title": "双曲线标准方程",
             "description": "",
             "formula": sp.latex(sp.Eq(self.x**2/a**2 - self.y**2/b**2, 1)),
             "result": f"双曲线方程为 {sp.latex(sp.Eq(self.x**2/a**2 - self.y**2/b**2, 1))}"},
            {"step_number": 2, "title": "求半焦距",
             "description": "c² = a² + b²",
             "formula": rf"c = \sqrt{{{sp.latex(a)}^2 + {sp.latex(b)}^2}} = {sp.latex(sp.simplify(c))}",
             "result": ""},
            {"step_number": 3, "title": "焦点坐标",
             "description": "焦点在 x 轴上 (±c, 0)",
             "formula": rf"F_1({sp.latex(-c)}, 0),\; F_2({sp.latex(c)}, 0)",
             "result": ""},
            {"step_number": 4, "title": "渐近线",
             "description": "y = ±(b/a)x",
             "formula": rf"y = \pm\frac{{{sp.latex(b)}}}{{{sp.latex(a)}}}x = \pm{sp.latex(sp.simplify(asymptote))}x",
             "result": ""},
            {"step_number": 5, "title": "离心率",
             "description": "e = c/a > 1",
             "formula": rf"e = \frac{{{sp.latex(c)}}}{{{sp.latex(a)}}} = {sp.latex(sp.simplify(e))}",
             "result": ""},
        ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(sp.Eq(self.x**2/a**2 - self.y**2/b**2, 1)),
            "exact": f"x^2/{a}^2 - y^2/{b}^2 = 1",
        }

        return result

    # ========== 抛物线 ==========

    def _handle_parabola_equation(self, problem: dict) -> AnalyticResult:
        """求抛物线方程/性质。"""
        desc = problem.get("description", "")
        given = problem.get("given", {})

        result = AnalyticResult(problem_type="parabola_equation")
        steps = []

        p_val = given.get("p") or given.get("focal_parameter")
        if p_val:
            p = sp.sympify(p_val)
        else:
            # 从文本提取
            match = re.search(r'[yY]\^?2\s*=\s*(\d+)\s*[xX]', desc)
            if match:
                p = sp.sympify(int(match.group(1))) / 2
            else:
                p = sp.sympify(2)

        steps = [
            {"step_number": 1, "title": "抛物线标准方程",
             "description": "y² = 2px（开口向右）",
             "formula": sp.latex(sp.Eq(self.y**2, 2*p*self.x)),
             "result": f"抛物线方程为 {sp.latex(sp.Eq(self.y**2, 2*p*self.x))}"},
            {"step_number": 2, "title": "焦点坐标",
             "description": "焦点 F(p/2, 0)",
             "formula": rf"F\left(\frac{{{sp.latex(p)}}}{{2}}, 0\right) = ({sp.latex(p/2)}, 0)",
             "result": ""},
            {"step_number": 3, "title": "准线方程",
             "description": "准线 x = -p/2",
             "formula": rf"x = -\frac{{{sp.latex(p)}}}{{2}} = {sp.latex(-p/2)}",
             "result": ""},
        ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(sp.Eq(self.y**2, 2*p*self.x)),
            "exact": f"y^2 = {2*float(p)}x",
        }

        return result

    # ========== 距离 ==========

    def _handle_distance(self, problem: dict) -> AnalyticResult:
        """计算距离：两点间距离 / 点到直线距离。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AnalyticResult(problem_type="distance")
        steps = []

        pts = self._extract_points(desc)
        line_str = target.get("line") or given.get("line", "")

        # 点到直线距离
        if line_str and len(pts) >= 1:
            line = self._parse_line_from_str(line_str)
            pt = sp.Point(pts[0][0], pts[0][1])
            dist = sp.simplify(line.distance(pt))

            steps = [
                {"step_number": 1, "title": "已知条件",
                 "description": f"点 P{sp.latex(pt)}，直线 l: {sp.latex(line)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "点到直线距离公式",
                 "description": r"d = \frac{|Ax_0 + By_0 + C|}{\sqrt{A^2 + B^2}}",
                 "formula": sp.latex(dist),
                 "result": f"距离为 {sp.latex(dist)}"},
            ]

        # 两点间距离
        elif len(pts) >= 2:
            p1 = sp.Point(pts[0][0], pts[0][1])
            p2 = sp.Point(pts[1][0], pts[1][1])
            dist = sp.simplify(p1.distance(p2))

            steps = [
                {"step_number": 1, "title": "已知两点",
                 "description": f"A{sp.latex(p1)}，B{sp.latex(p2)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "两点间距离公式",
                 "description": r"d = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}",
                 "formula": sp.latex(dist),
                 "result": f"距离为 {sp.latex(dist)}"},
            ]
        else:
            steps = [
                {"step_number": 1, "title": "信息不足",
                 "description": "请提供两个点的坐标或一个点加一条直线",
                 "formula": "", "result": ""},
            ]
            dist = sp.sympify(0)

        result.steps = steps
        result.answer = {
            "latex": sp.latex(dist),
            "exact": str(dist),
            "numeric": float(dist.evalf()) if dist != 0 else 0,
        }

        return result

    # ========== 交点 ==========

    def _handle_intersection(self, problem: dict) -> AnalyticResult:
        """求交点：直线与直线、直线与圆的交点。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AnalyticResult(problem_type="intersection")
        steps = []

        # 尝试从文本解析两个几何对象
        line_strs = re.findall(r'[\d\-]*x\s*[+\-]\s*[\d\-]*y\s*[+\-]\s*[\d\-]+\s*=\s*0', desc)
        # 提取圆
        circle_match = re.search(r'[xX]\^?2\s*\+\s*[yY]\^?2\s*[=\-+].*', desc)

        intersection_pts = []
        if len(line_strs) >= 2:
            l1 = self._parse_line_from_str(line_strs[0])
            l2 = self._parse_line_from_str(line_strs[1])
            intersection_pts = l1.intersection(l2)

            steps = [
                {"step_number": 1, "title": "已知直线",
                 "description": f"l₁: {sp.latex(l1)}, l₂: {sp.latex(l2)}",
                 "formula": "", "result": ""},
                {"step_number": 2, "title": "联立求解",
                 "description": "解方程组求交点",
                 "formula": rf"\begin{{cases}} {sp.latex(l1.equation(x=self.x, y=self.y))} \\ {sp.latex(l2.equation(x=self.x, y=self.y))} \end{{cases}}",
                 "result": f"交点为 {sp.latex(intersection_pts[0])}" if intersection_pts else "无交点（平行）",
                },
            ]
        elif circle_match and len(pts := self._extract_points(desc)) >= 1:
            steps = [
                {"step_number": 1, "title": "暂不支持",
                 "description": "直线与圆的交点求解待实现",
                 "formula": "", "result": ""},
            ]
        else:
            steps = [
                {"step_number": 1, "title": "联立方程",
                 "description": "将两个几何对象的方程联立求解",
                 "formula": "", "result": "请提供两个几何对象的方程"},
            ]

        result.steps = steps
        ans_str = ", ".join(sp.latex(p) for p in intersection_pts) if intersection_pts else "无交点"
        result.answer = {
            "latex": ans_str if intersection_pts else "N/A",
            "exact": str(intersection_pts) if intersection_pts else "N/A",
        }

        return result

    # ========== 切线 ==========

    def _handle_tangent_line(self, problem: dict) -> AnalyticResult:
        """求切线方程。"""
        desc = problem.get("description", "")
        given = problem.get("given", {})

        result = AnalyticResult(problem_type="tangent_line")
        steps = []

        pts = self._extract_points(desc)
        circle_data = given.get("circle") or {}
        center = circle_data.get("center", [0, 0])
        radius = circle_data.get("radius", 1)

        c = sp.Point(center[0], center[1])
        r = sp.sympify(radius)

        if pts:
            pt = sp.Point(pts[0][0], pts[0][1])

            # 点到圆心的向量
            vec = sp.Matrix([pt.x - c.x, pt.y - c.y])
            vec_len = sp.sqrt(vec.dot(vec))

            if sp.simplify(vec_len - r) == 0:
                # 点在圆上：切线垂直于半径
                normal = sp.Matrix([pt.x - c.x, pt.y - c.y])
                # 切线方向为法向量旋转 90°
                dir_vec = sp.Matrix([-normal[1], normal[0]])
                tangent_line = sp.Line(pt, pt + sp.Point(dir_vec[0], dir_vec[1]))

                steps = [
                    {"step_number": 1, "title": "点在圆上",
                     "description": f"点 P{sp.latex(pt)} 在圆上",
                     "formula": "", "result": ""},
                    {"step_number": 2, "title": "切线垂直于半径",
                     "description": "过切点的半径与切线垂直",
                     "formula": sp.latex(tangent_line.equation(x=self.x, y=self.y)),
                     "result": f"切线方程为 {sp.latex(tangent_line.equation(x=self.x, y=self.y))}"},
                ]
            else:
                # 点在圆外，求切线方程（一般式）
                steps = [
                    {"step_number": 1, "title": "点在圆外",
                     "description": "圆外一点有两条切线",
                     "formula": "",
                     "result": "过圆外一点的切线方程需解二次方程，即将支持"},
                ]
                tangent_line = sp.Line(pt, pt + sp.Point(1, 0))

            result.answer = {
                "latex": sp.latex(tangent_line.equation(x=self.x, y=self.y)),
                "exact": str(tangent_line.equation(x=self.x, y=self.y)),
            }
        else:
            steps = [
                {"step_number": 1, "title": "信息不足",
                 "description": "请提供切点坐标或圆外一点坐标",
                 "formula": "", "result": ""},
            ]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 辅助方法 ==========

    def _parse_line_from_str(self, line_str: str) -> sp.Line | None:
        """从字符串解析直线。支持 3x-4y+5=0 或 3x-4y=-5 等格式。"""
        if not line_str:
            return None

        line_str = line_str.replace(" ", "")
        # 标准化为 =0 形式
        if "=" in line_str:
            left, right = line_str.split("=", 1)
            expr_str = f"({left})-({right})"
        else:
            expr_str = line_str

        try:
            expr = sp.sympify(expr_str)
            # 找两个点
            x0, y0 = 0, 0
            # 解出 y 截距
            y0_expr = sp.solve(expr.subs(self.x, 0), self.y)
            if y0_expr:
                y0 = float(y0_expr[0].evalf())
            # 解出 x 截距
            x0_expr = sp.solve(expr.subs(self.y, 0), self.x)
            if x0_expr:
                x0 = float(x0_expr[0].evalf())

            if x0 == 0 and y0 == 0:
                return sp.Line(sp.Point(0, 0), sp.Point(1, 1))

            p1 = sp.Point(0, float(sp.N(sp.solve(expr.subs(self.x, 0), self.y)[0])))
            p2 = sp.Point(float(sp.N(sp.solve(expr.subs(self.y, 0), self.x)[0])), 0)

            # 处理退化情况
            if sp.simplify(p1.distance(p2)) == 0:
                p2 = sp.Point(1, p1.y + 1)

            return sp.Line(p1, p2)
        except Exception:
            return None

    def _extract_points(self, text: str) -> list:
        """从文本中提取坐标点。"""
        pts = []
        for match in re.finditer(r'[\(（]\s*(-?\d+\.?\d*)\s*[,，]\s*(-?\d+\.?\d*)\s*[\)）]', text):
            pts.append([float(match.group(1)), float(match.group(2))])
        return pts

    def _extract_ellipse_params(self, text: str) -> tuple:
        """从椭圆/双曲线方程文本提取参数。"""
        a, b = None, None
        # x²/a² + y²/b² = 1
        m = re.search(r'[xX]\^?2\s*/\s*(\d+)', text)
        if m:
            a = sp.sqrt(sp.sympify(int(m.group(1))))
        m = re.search(r'[yY]\^?2\s*/\s*(\d+)', text)
        if m:
            b = sp.sqrt(sp.sympify(int(m.group(1))))
        return a, b

    def _line_2d_model(self, line: sp.Line) -> dict:
        """生成 2D 渲染数据。"""
        x_int = sp.solve(line.equation(x=self.x, y=self.y).subs(self.y, 0), self.x)
        y_int = sp.solve(line.equation(x=self.x, y=self.y).subs(self.x, 0), self.y)
        return {
            "type": "line",
            "x_intercept": float(x_int[0].evalf()) if x_int else 0,
            "y_intercept": float(y_int[0].evalf()) if y_int else 0,
            "slope": float(line.slope.evalf()) if hasattr(line.slope, 'evalf') else float(line.slope),
        }

    def _circle_2d_model(self, center: sp.Point, radius) -> dict:
        """生成圆的 2D 渲染数据。"""
        return {
            "type": "circle",
            "center": [float(center.x.evalf()) if hasattr(center.x, 'evalf') else float(center.x),
                       float(center.y.evalf()) if hasattr(center.y, 'evalf') else float(center.y)],
            "radius": float(radius.evalf()) if hasattr(radius, 'evalf') else float(radius),
        }
