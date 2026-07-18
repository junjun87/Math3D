"""
代数 SymPy 精确计算内核。

使用 sympy 求解各类代数问题：
方程、方程组、不等式、数列、因式分解、函数性质。
"""

from __future__ import annotations
import re
import sympy as sp
from dataclasses import dataclass, field


@dataclass
class AlgebraResult:
    subject: str = "algebra"
    problem_type: str = ""
    answer: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)


class AlgebraKernel:

    def __init__(self):
        self.x = sp.Symbol("x", real=True)
        self.y = sp.Symbol("y", real=True)
        self.z = sp.Symbol("z", real=True)
        self.n = sp.Symbol("n", integer=True, positive=True)

    def compute(self, problem: dict) -> dict:
        target = problem.get("target", {})
        ptype = target.get("type", "quadratic_equation")

        handler = getattr(self, f"_handle_{ptype}", None)
        if handler:
            result = handler(problem)
        else:
            result = AlgebraResult(problem_type=ptype)
            result.steps = [{
                "step_number": 1,
                "title": "暂不支持",
                "description": f"代数题型 '{ptype}' 开发中",
                "formula": "",
                "result": "",
            }]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        return {
            "subject": result.subject,
            "problem_type": result.problem_type,
            "answer": result.answer,
            "steps": result.steps,
        }

    # ========== 一元一次方程 ==========

    def _handle_linear_equation(self, problem: dict) -> AlgebraResult:
        """解一元一次方程 ax + b = c。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="linear_equation")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            if "=" in expr_str:
                left_str, right_str = expr_str.split("=", 1)
                eq = sp.Eq(sp.sympify(left_str), sp.sympify(right_str))
            else:
                eq = sp.Eq(sp.sympify(expr_str), 0)

            solution = sp.solve(eq, self.x)

            steps = [
                {"step_number": 1, "title": "原方程",
                 "description": "",
                 "formula": sp.latex(eq),
                 "result": ""},
                {"step_number": 2, "title": "移项合并",
                 "description": "将所有含 x 的项移到左边，常数移到右边",
                 "formula": sp.latex(sp.Eq(sp.expand(eq.lhs - eq.rhs), 0)),
                 "result": ""},
                {"step_number": 3, "title": "求解 x",
                 "description": "",
                 "formula": "",
                 "result": f"x = {sp.latex(solution[0])}" if solution else "无解"},
            ]

            result.answer = {
                "latex": sp.latex(solution[0]) if solution else "N/A",
                "exact": str(solution[0]) if solution else "N/A",
                "numeric": float(solution[0].evalf()) if solution else 0,
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法解析表达式: {expr_str}", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 一元二次方程 ==========

    def _handle_quadratic_equation(self, problem: dict) -> AlgebraResult:
        """解一元二次方程 ax² + bx + c = 0。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="quadratic_equation")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            if "=" in expr_str:
                left_str, right_str = expr_str.split("=", 1)
                eq = sp.Eq(sp.sympify(left_str), sp.sympify(right_str))
            else:
                eq = sp.Eq(sp.sympify(expr_str), 0)

            expr = sp.expand(eq.lhs - eq.rhs)
            # 整理为标准形式
            a = sp.simplify(expr.coeff(self.x, 2))
            b = sp.simplify(expr.coeff(self.x, 1))
            c = sp.simplify(expr.coeff(self.x, 0)) if self.x not in expr.free_symbols or expr != sp.simplify(expr.subs(self.x, 0)) else sp.sympify(0)

            discriminant = b**2 - 4*a*c

            solutions = sp.solve(eq, self.x)

            steps = [
                {"step_number": 1, "title": "化为标准形式",
                 "description": "ax² + bx + c = 0",
                 "formula": sp.latex(sp.Eq(a*self.x**2 + b*self.x + c, 0)),
                 "result": ""},
                {"step_number": 2, "title": "确定系数",
                 "description": "",
                 "formula": rf"a = {sp.latex(a)},\; b = {sp.latex(b)},\; c = {sp.latex(c)}",
                 "result": ""},
                {"step_number": 3, "title": "求判别式",
                 "description": "Δ = b² - 4ac",
                 "formula": rf"\Delta = {sp.latex(b)}^2 - 4 \times {sp.latex(a)} \times {sp.latex(c)} = {sp.latex(discriminant)}",
                 "result": ""},
                {"step_number": 4, "title": "求根公式",
                 "description": "x = (-b ± √Δ) / (2a)",
                 "formula": rf"x = \frac{{-{sp.latex(b)} \pm \sqrt{{{sp.latex(discriminant)}}}}}{{2 \times {sp.latex(a)}}}",
                 "result": " 或 ".join(sp.latex(s) for s in solutions) if solutions else "无实数根"},
            ]

            ans_str = " 或 ".join(sp.latex(s) for s in solutions) if solutions else "无实数根"
            result.answer = {
                "latex": ans_str,
                "exact": str(solutions),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法解析表达式: {expr_str}", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 方程组 ==========

    def _handle_system_of_equations(self, problem: dict) -> AlgebraResult:
        """解方程组。"""
        target = problem.get("target", {})
        equations = target.get("equations", [])

        result = AlgebraResult(problem_type="system_of_equations")
        steps = []

        if not equations:
            desc = problem.get("description", "")
            equations = re.findall(r'[\w\^\+\-\*\/\(\)=]+', desc)
            equations = [e for e in equations if "=" in e and len(e) > 3]

        try:
            eqs = []
            for eq_str in equations[:3]:  # 最多 3 个方程
                eq_str = eq_str.replace(" ", "")
                if "=" in eq_str:
                    left, right = eq_str.split("=", 1)
                    eqs.append(sp.Eq(sp.sympify(left), sp.sympify(right)))
                else:
                    eqs.append(sp.Eq(sp.sympify(eq_str), 0))

            if not eqs:
                eqs = [sp.Eq(self.x + self.y, 1), sp.Eq(self.x - self.y, 3)]

            # 确定变量
            all_symbols = set()
            for eq in eqs:
                all_symbols.update(eq.free_symbols)
            syms = sorted(all_symbols, key=lambda s: str(s))

            solutions = sp.solve(eqs, syms, dict=True)

            steps = [
                {"step_number": 1, "title": "方程组",
                 "description": "",
                 "formula": " \\\\ ".join(sp.latex(eq) for eq in eqs),
                 "result": ""},
                {"step_number": 2, "title": "消元求解",
                 "description": "使用代入法或加减消元法",
                 "formula": "",
                 "result": "  ".join(
                     ", ".join(f"{sp.latex(s)} = {sp.latex(v)}" for s, v in sol.items())
                     for sol in solutions
                 ) if solutions else "无解"},
            ]

            ans_str = "  ".join(sp.latex(sol) for sol in solutions) if solutions else "无解"
            result.answer = {
                "latex": ans_str,
                "exact": str(solutions),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法解方程组", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 不等式 ==========

    def _handle_inequality(self, problem: dict) -> AlgebraResult:
        """解不等式。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="inequality")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            # 转换为不等式
            if ">=" in expr_str:
                left, right = expr_str.rsplit(">=", 1)
                rel = ">="
            elif "<=" in expr_str:
                left, right = expr_str.rsplit("<=", 1)
                rel = "<="
            elif ">" in expr_str:
                left, right = expr_str.rsplit(">", 1)
                rel = ">"
            elif "<" in expr_str:
                left, right = expr_str.rsplit("<", 1)
                rel = "<"
            else:
                left, right = expr_str, "0"
                rel = ">"

            expr = sp.sympify(f"({left})-({right})")
            solution = sp.solve_univariate_inequality(expr, self.x, relational=False)

            steps = [
                {"step_number": 1, "title": "原不等式",
                 "description": "",
                 "formula": sp.latex(sp.sympify(f"{left} {rel} {right}")),
                 "result": ""},
                {"step_number": 2, "title": "移项整理",
                 "description": "将所有项移到左边",
                 "formula": sp.latex(sp.Eq(expr, 0)),
                 "result": ""},
                {"step_number": 3, "title": "求解",
                 "description": "",
                 "formula": "",
                 "result": sp.latex(solution)},
            ]

            result.answer = {
                "latex": sp.latex(solution),
                "exact": str(solution),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": "不等式求解失败", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 数列 ==========

    def _handle_sequence(self, problem: dict) -> AlgebraResult:
        """等差/等比数列求通项、求和。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = AlgebraResult(problem_type="sequence")
        steps = []

        seq_type = target.get("sequence_type") or given.get("sequence_type") or "arithmetic"

        # 是否是等比数列
        if "等比" in desc or seq_type == "geometric":
            return self._handle_geometric_sequence(problem)

        # 等差数列
        a1 = sp.sympify(given.get("a1", given.get("first_term", 1)))
        d = sp.sympify(given.get("d", given.get("common_difference", 1)))
        n_val = sp.sympify(given.get("n", self.n))

        an = a1 + (n_val - 1) * d
        sn = n_val * (a1 + an) / 2

        steps = [
            {"step_number": 1, "title": "确定首项和公差",
             "description": "",
             "formula": rf"a_1 = {sp.latex(a1)},\; d = {sp.latex(d)}",
             "result": ""},
            {"step_number": 2, "title": "通项公式",
             "description": "aₙ = a₁ + (n-1)d",
             "formula": rf"a_n = {sp.latex(a1)} + (n-1) \times {sp.latex(d)} = {sp.latex(sp.simplify(an))}",
             "result": ""},
            {"step_number": 3, "title": "前 n 项和公式",
             "description": "Sₙ = n(a₁+aₙ)/2",
             "formula": rf"S_n = \frac{{n({sp.latex(a1)} + {sp.latex(sp.simplify(an))})}}{{2}} = {sp.latex(sp.simplify(sn))}",
             "result": ""},
        ]

        result.steps = steps
        result.answer = {
            "latex": sp.latex(sp.simplify(an)),
            "exact": str(sp.simplify(an)),
        }

        return result

    def _handle_geometric_sequence(self, problem: dict) -> AlgebraResult:
        """等比数列。"""
        given = problem.get("given", {})
        a1 = sp.sympify(given.get("a1", given.get("first_term", 1)))
        q = sp.sympify(given.get("q", given.get("common_ratio", 2)))
        n_val = sp.sympify(given.get("n", self.n))

        result = AlgebraResult(problem_type="sequence")
        an = a1 * q**(n_val - 1)
        sn = a1 * (1 - q**n_val) / (1 - q) if q != 1 else a1 * n_val

        result.steps = [
            {"step_number": 1, "title": "确定首项和公比",
             "description": "",
             "formula": rf"a_1 = {sp.latex(a1)},\; q = {sp.latex(q)}",
             "result": ""},
            {"step_number": 2, "title": "通项公式",
             "description": "aₙ = a₁·qⁿ⁻¹",
             "formula": rf"a_n = {sp.latex(a1)} \times {sp.latex(q)}^{{n-1}} = {sp.latex(sp.simplify(an))}",
             "result": ""},
            {"step_number": 3, "title": "前 n 项和",
             "description": "Sₙ = a₁(1-qⁿ)/(1-q)" if q != 1 else "Sₙ = na₁",
             "formula": sp.latex(sp.simplify(sn)),
             "result": ""},
        ]

        result.answer = {
            "latex": sp.latex(sp.simplify(an)),
            "exact": str(sp.simplify(an)),
        }
        return result

    # ========== 因式分解 ==========

    def _handle_polynomial(self, problem: dict) -> AlgebraResult:
        """因式分解。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="polynomial")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            expr = sp.sympify(expr_str)
            factored = sp.factor(expr)

            steps = [
                {"step_number": 1, "title": "原多项式",
                 "description": "",
                 "formula": sp.latex(expr),
                 "result": ""},
                {"step_number": 2, "title": "因式分解",
                 "description": "",
                 "formula": sp.latex(factored),
                 "result": f"分解结果为 {sp.latex(factored)}"},
            ]

            result.answer = {
                "latex": sp.latex(factored),
                "exact": str(factored),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法因式分解", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 函数性质 ==========

    def _handle_function_properties(self, problem: dict) -> AlgebraResult:
        """分析函数性质（定义域、值域、单调性等）。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="function_properties")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            expr = sp.sympify(expr_str)
            f = sp.Lambda(self.x, expr)

            # 定义域（实数范围内）
            singularities = sp.singularities(expr, self.x)
            domain = sp.simplify(sp.Interval(-sp.oo, sp.oo) - singularities)

            # 导数和极值点
            deriv = sp.diff(expr, self.x)
            critical_pts = sp.solve(deriv, self.x)

            steps = [
                {"step_number": 1, "title": "函数表达式",
                 "description": "",
                 "formula": rf"f(x) = {sp.latex(expr)}",
                 "result": ""},
                {"step_number": 2, "title": "定义域",
                 "description": "函数有定义的 x 的取值范围",
                 "formula": sp.latex(singularities) if singularities != sp.EmptySet else r"\mathbb{R}",
                 "result": f"定义域为 {sp.latex(singularities) if singularities != sp.EmptySet else '全体实数'}"},
                {"step_number": 3, "title": "求导",
                 "description": "",
                 "formula": rf"f'(x) = {sp.latex(deriv)}",
                 "result": ""},
                {"step_number": 4, "title": "驻点",
                 "description": "令 f'(x) = 0",
                 "formula": "",
                 "result": ", ".join(sp.latex(pt) for pt in critical_pts) if critical_pts else "无驻点"},
            ]

            result.answer = {
                "latex": sp.latex(expr),
                "exact": str(expr),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法分析函数", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 化简 ==========

    def _handle_simplification(self, problem: dict) -> AlgebraResult:
        """代数式化简。"""
        target = problem.get("target", {})
        expr_str = target.get("expression", "")

        result = AlgebraResult(problem_type="simplification")
        steps = []

        if not expr_str:
            desc = problem.get("description", "")
            expr_str = self._extract_expression(desc)

        try:
            expr = sp.sympify(expr_str)
            simplified = sp.simplify(expr)

            steps = [
                {"step_number": 1, "title": "原式",
                 "description": "",
                 "formula": sp.latex(expr),
                 "result": ""},
                {"step_number": 2, "title": "化简",
                 "description": "使用代数运算法则化简",
                 "formula": sp.latex(simplified),
                 "result": f"化简结果为 {sp.latex(simplified)}"},
            ]

            result.answer = {
                "latex": sp.latex(simplified),
                "exact": str(simplified),
            }
        except Exception as e:
            steps = [{"step_number": 1, "title": "解析失败",
                      "description": f"无法化简", "formula": "", "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 辅助方法 ==========

    def _extract_expression(self, text: str) -> str:
        """从文本中提取代数表达式。"""
        # 去掉中文描述，保留数学表达式
        # 匹配 x^2 - 5x + 6 = 0 这类表达式
        match = re.search(r'([xyzn]\^?\d*\s*[\+\-\*\/]\s*[\d\w\^\+\-\*\/\(\)\s]*)(?:$|\。|\；|，)', text)
        if match:
            return match.group(1).strip()
        # 简单匹配
        match = re.search(r'([\w\^\+\-\*\/\(\)\=]+(?:[\+\-\*\/][\w\^\+\-\*\/\(\)\=]+)+)', text)
        if match:
            return match.group(1).strip()
        return text.strip()
