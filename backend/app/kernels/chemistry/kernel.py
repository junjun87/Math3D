"""
化学 SymPy 计算内核。

使用 sympy + 线性代数解决：
化学方程式配平、物质的量计算、浓度、pH、气体定律。
"""

from __future__ import annotations
import re
import sympy as sp
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChemistryResult:
    subject: str = "chemistry"
    problem_type: str = ""
    answer: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)


# 元素周期表常用元素
ATOMIC_MASSES = {
    "H": 1.008, "He": 4.003, "Li": 6.941, "Be": 9.012, "B": 10.811,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.086, "P": 30.974,
    "S": 32.065, "Cl": 35.453, "K": 39.098, "Ca": 40.078, "Mn": 54.938,
    "Fe": 55.845, "Cu": 63.546, "Zn": 65.380, "Ag": 107.868, "Ba": 137.327,
    "Au": 196.967, "Hg": 200.590, "Pb": 207.200,
}


class ChemistryKernel:

    def __init__(self):
        pass

    def compute(self, problem: dict) -> dict:
        target = problem.get("target", {})
        ptype = target.get("type", "equation_balance")

        handler = getattr(self, f"_handle_{ptype}", None)
        if handler:
            result = handler(problem)
        else:
            result = ChemistryResult(problem_type=ptype)
            result.steps = [{
                "step_number": 1,
                "title": "暂不支持",
                "description": f"化学题型 '{ptype}' 开发中",
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

    # ========== 化学方程式配平（线性代数法） ==========

    def _handle_equation_balance(self, problem: dict) -> ChemistryResult:
        """
        化学方程式配平。使用元素守恒 + 线性代数求解系数。
        """
        target = problem.get("target", {})
        reactants = target.get("reactants", [])
        products = target.get("products", [])

        result = ChemistryResult(problem_type="equation_balance")
        steps = []

        if not reactants or not products:
            desc = problem.get("description", "")
            reactants, products = self._parse_reaction(desc)

        try:
            # 解析化学式中的元素组成
            rxn_formulas = [self._parse_formula(f) for f in reactants]
            prod_formulas = [self._parse_formula(f) for f in products]

            # 收集所有元素
            all_elements = set()
            for f_dict in rxn_formulas + prod_formulas:
                all_elements.update(f_dict.keys())

            # 构建系数矩阵：对于每种元素 i 和每种物质 j
            # Σ(系数_j × 物质中元素_i的原子数) = 0 (反应物为负，生成物为正)
            n_react = len(reactants)
            n_prod = len(products)
            n_total = n_react + n_prod

            elements = sorted(all_elements)
            coeffs = []

            for elem in elements:
                row = []
                for f_dict in rxn_formulas:
                    row.append(-f_dict.get(elem, 0))  # 反应物为负
                for f_dict in prod_formulas:
                    row.append(f_dict.get(elem, 0))  # 生成物为正
                coeffs.append(row)

            # 用 sympy 解齐次线性方程组：Ax = 0，求最小正整数解
            A = sp.Matrix(coeffs)
            nullspace = A.nullspace()

            if nullspace:
                # 取 nullspace 中第一个向量，化为最小正整数比
                v = nullspace[0]
                # 归一化：除以最大公约数，乘以分母的公倍数得到整数
                denom_lcm = 1
                for val in v:
                    denom = sp.denom(val)
                    denom_lcm = sp.lcm(denom_lcm, denom)
                v_int = [sp.Abs(val * denom_lcm) for val in v]

                # 除以最大公约数
                g = sp.gcd_list(v_int)
                v_final = [sp.simplify(val / g) for val in v_int]
            else:
                v_final = [1] * n_total

            # 构建配平后的方程式
            balanced_parts = []
            for i, f in enumerate(reactants):
                coef = v_final[i]
                if coef == 1:
                    balanced_parts.append(f)
                else:
                    balanced_parts.append(f"{coef}{f}")
            balanced_parts.append("→")
            for i, f in enumerate(products):
                coef = v_final[n_react + i]
                if coef == 1:
                    balanced_parts.append(f)
                else:
                    balanced_parts.append(f"{coef}{f}")

            balanced_eq = " ".join(balanced_parts)

            steps = [
                {"step_number": 1, "title": "原方程式",
                 "description": "",
                 "formula": f"{' + '.join(reactants)} → {' + '.join(products)}",
                 "result": ""},
                {"step_number": 2, "title": "列出元素守恒方程",
                 "description": "每种元素的原子数在反应前后相等",
                 "formula": r"\begin{cases}" + " \\\\ ".join(
                     f"\\text{{{elem}}}: " + " + ".join(
                         f"{c} \\times {coef}_{{{i+1}}}" for i, c in enumerate(row)
                     ) + " = 0" for elem, row in zip(elements, coeffs)
                 ) + r"\end{cases}",
                 "result": ""},
                {"step_number": 3, "title": "求解系数（最小正整数）",
                 "description": "解齐次线性方程组 Ax=0，取最小正整数解",
                 "formula": f"({', '.join(str(v) for v in v_final)})",
                 "result": ""},
                {"step_number": 4, "title": "配平结果",
                 "description": "",
                 "formula": rf"\text{{{balanced_eq}}}",
                 "result": f"配平后: {balanced_eq}"},
            ]

            result.steps = steps
            result.answer = {
                "latex": rf"\text{{{balanced_eq}}}",
                "exact": balanced_eq,
                "coefficients": [int(sp.N(v)) for v in v_final],
            }

        except Exception as e:
            steps = [{"step_number": 1, "title": "配平失败",
                      "description": f"方程式配平出错",
                      "formula": "",
                      "result": str(e)}]
            result.answer = {"latex": "N/A", "exact": "N/A"}
            result.steps = steps

        return result

    # ========== 物质的量计算 ==========

    def _handle_mole_calculation(self, problem: dict) -> ChemistryResult:
        """物质的量 n = m / M 相关计算。"""
        target = problem.get("target", {})
        given = problem.get("given", {})
        desc = problem.get("description", "")

        result = ChemistryResult(problem_type="mole_calculation")
        steps = []

        mass = given.get("mass")
        substance = given.get("substance") or target.get("substance", "")
        molar_mass_val = given.get("molar_mass")

        # 如果没给摩尔质量，从化学式计算
        if not molar_mass_val and substance:
            formula_dict = self._parse_formula(substance)
            molar_mass_val = 0
            for elem, count in formula_dict.items():
                molar_mass_val += ATOMIC_MASSES.get(elem, 0) * count

        if mass and molar_mass_val:
            m = sp.sympify(mass)
            M = sp.sympify(molar_mass_val)
            n = m / M

            steps = [
                {"step_number": 1, "title": "物质的量公式",
                 "description": "n = m / M",
                 "formula": rf"n = \frac{{m}}{{M}}",
                 "result": ""},
                {"step_number": 2, "title": "代入数值",
                 "description": f"质量 m = {m} g，摩尔质量 M = {M} g/mol",
                 "formula": rf"n = \frac{{{sp.latex(m)}}}{{{sp.latex(sp.N(M, 4))}}}",
                 "result": f"n = {sp.latex(sp.N(n, 4))} mol"},
            ]

            result.answer = {
                "latex": sp.latex(sp.N(n, 4)),
                "exact": str(sp.N(n, 4)),
                "numeric": float(sp.N(n, 4)),
                "unit": "mol",
            }
        else:
            steps = [{"step_number": 1, "title": "信息不足",
                      "description": "需要提供质量和摩尔质量（或化学式）",
                      "formula": "", "result": ""}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 浓度计算 ==========

    def _handle_concentration(self, problem: dict) -> ChemistryResult:
        """溶液浓度 c = n / V 相关计算。"""
        given = problem.get("given", {})
        target = problem.get("target", {})

        result = ChemistryResult(problem_type="concentration")
        steps = []

        n_val = given.get("n") or given.get("amount")
        V_val = given.get("volume") or given.get("V")
        c_val = given.get("concentration") or given.get("c")

        try:
            if n_val and V_val:
                n = sp.sympify(n_val)
                V = sp.sympify(V_val)
                c = n / V
                steps = [
                    {"step_number": 1, "title": "浓度公式",
                     "description": "c = n / V",
                     "formula": rf"c = \frac{{n}}{{V}}",
                     "result": ""},
                    {"step_number": 2, "title": "代入数值",
                     "description": f"n = {n} mol, V = {V} L",
                     "formula": rf"c = \frac{{{sp.latex(n)}}}{{{sp.latex(V)}}}",
                     "result": f"c = {sp.latex(sp.N(c, 4))} mol/L"},
                ]
                answer_val = sp.N(c, 4)
            elif c_val and V_val:
                c = sp.sympify(c_val)
                V = sp.sympify(V_val)
                n = c * V
                steps = [
                    {"step_number": 1, "title": "求物质的量",
                     "description": "n = c × V",
                     "formula": rf"n = {sp.latex(c)} \times {sp.latex(V)}",
                     "result": f"n = {sp.latex(sp.N(n, 4))} mol"},
                ]
                answer_val = sp.N(n, 4)
            else:
                steps = [{"step_number": 1, "title": "信息不足",
                          "description": "需提供 n 和 V，或 c 和 V", "formula": "", "result": ""}]
                answer_val = sp.sympify(0)

            result.steps = steps
            result.answer = {
                "latex": sp.latex(answer_val),
                "exact": str(answer_val),
                "numeric": float(answer_val),
                "unit": "mol/L",
            }
        except Exception as e:
            result.steps = [{"step_number": 1, "title": "计算失败",
                             "description": str(e), "formula": "", "result": ""}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        return result

    # ========== pH 计算 ==========

    def _handle_ph_calculation(self, problem: dict) -> ChemistryResult:
        """pH = -log[H⁺] 计算。"""
        given = problem.get("given", {})
        target = problem.get("target", {})
        desc = problem.get("description", "")

        result = ChemistryResult(problem_type="ph_calculation")
        steps = []

        H_conc = given.get("h_concentration") or given.get("H_plus") or target.get("H_plus")
        pH_val = given.get("pH") or target.get("pH")

        try:
            if H_conc:
                H = sp.sympify(H_conc)
                pH = -sp.log(H, 10)
                # 处理特殊值
                pH_simplified = sp.simplify(pH)
                steps = [
                    {"step_number": 1, "title": "pH 定义",
                     "description": "pH = -lg[H⁺]",
                     "formula": rf"pH = -\lg[H^+]",
                     "result": ""},
                    {"step_number": 2, "title": "代入计算",
                     "description": f"[H⁺] = {H} mol/L",
                     "formula": rf"pH = -\lg({sp.latex(H)})",
                     "result": f"pH = {sp.latex(sp.N(pH_simplified, 4))}"},
                ]
                result.answer = {
                    "latex": sp.latex(sp.N(pH_simplified, 4)),
                    "exact": str(sp.N(pH_simplified, 4)),
                    "numeric": float(sp.N(pH_simplified, 4)),
                }
            elif pH_val:
                pH = sp.sympify(pH_val)
                H = 10**(-pH)
                steps = [
                    {"step_number": 1, "title": "求 [H⁺]",
                     "description": "[H⁺] = 10^(-pH)",
                     "formula": rf"[H^+] = 10^{{-{sp.latex(pH)}}}",
                     "result": rf"[H^+] = {sp.latex(sp.N(H, 4))} mol/L"},
                ]
                result.answer = {
                    "latex": sp.latex(sp.N(H, 4)),
                    "exact": str(sp.N(H, 4)),
                    "numeric": float(sp.N(H, 4)),
                    "unit": "mol/L",
                }
            else:
                steps = [{"step_number": 1, "title": "信息不足",
                          "description": "需提供 [H⁺] 或 pH 值", "formula": "", "result": ""}]
                result.answer = {"latex": "N/A", "exact": "N/A"}

        except Exception as e:
            result.steps = [{"step_number": 1, "title": "计算失败",
                             "description": str(e), "formula": "", "result": ""}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 气体定律 ==========

    def _handle_gas_law(self, problem: dict) -> ChemistryResult:
        """理想气体状态方程 PV = nRT。"""
        given = problem.get("given", {})
        target = problem.get("target", {})

        result = ChemistryResult(problem_type="gas_law")
        steps = []

        R = sp.sympify(8.314)  # J/(mol·K)

        P = given.get("P") or given.get("pressure")
        V = given.get("V") or given.get("volume")
        n = given.get("n") or given.get("amount")
        T = given.get("T") or given.get("temperature")

        # 计算缺失的未知量
        known = sum(1 for v in [P, V, n, T] if v is not None)

        try:
            if P and V and n and T:
                # 验证
                P_s = sp.sympify(P)
                V_s = sp.sympify(V)
                n_s = sp.sympify(n)
                T_s = sp.sympify(T)
                PV = P_s * V_s
                nRT = n_s * R * T_s
                steps = [
                    {"step_number": 1, "title": "理想气体状态方程",
                     "description": "PV = nRT",
                     "formula": rf"PV = {sp.latex(PV)},\; nRT = {sp.latex(sp.N(nRT, 4))}",
                     "result": f"{'符合' if abs(float(PV) - float(nRT)) < 1 else '不符合'}理想气体状态方程"},
                ]
                result.answer = {"latex": sp.latex(sp.N(PV, 4)), "exact": str(sp.N(PV, 4))}
            elif P and V and T:
                P_s, V_s, T_s = sp.sympify(P), sp.sympify(V), sp.sympify(T)
                n_calc = P_s * V_s / (R * T_s)
                steps = [
                    {"step_number": 1, "title": "求物质的量",
                     "description": "n = PV / RT",
                     "formula": rf"n = \frac{{{sp.latex(P_s)} \times {sp.latex(V_s)}}}{{{sp.latex(sp.N(R, 3))} \times {sp.latex(T_s)}}}",
                     "result": f"n = {sp.latex(sp.N(n_calc, 4))} mol"},
                ]
                result.answer = {"latex": sp.latex(sp.N(n_calc, 4)), "exact": str(sp.N(n_calc, 4))}
            elif P and V and n:
                P_s, V_s, n_s = sp.sympify(P), sp.sympify(V), sp.sympify(n)
                T_calc = P_s * V_s / (n_s * R)
                steps = [
                    {"step_number": 1, "title": "求温度",
                     "description": "T = PV / nR",
                     "formula": rf"T = \frac{{{sp.latex(P_s)} \times {sp.latex(V_s)}}}{{{sp.latex(n_s)} \times {sp.latex(sp.N(R, 3))}}}",
                     "result": f"T = {sp.latex(sp.N(T_calc, 4))} K"},
                ]
                result.answer = {"latex": sp.latex(sp.N(T_calc, 4)), "exact": str(sp.N(T_calc, 4))}
            else:
                steps = [{"step_number": 1, "title": "信息不足",
                          "description": "理想气体方程 PV=nRT 需要提供 4 个量中的 3 个",
                          "formula": "", "result": ""}]
                result.answer = {"latex": "N/A", "exact": "N/A"}

        except Exception as e:
            result.steps = [{"step_number": 1, "title": "计算失败",
                             "description": str(e), "formula": "", "result": ""}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 化学计量 ==========

    def _handle_stoichiometry(self, problem: dict) -> ChemistryResult:
        """化学计量计算。"""
        given = problem.get("given", {})
        target = problem.get("target", {})

        result = ChemistryResult(problem_type="stoichiometry")
        steps = []

        mass = given.get("mass")
        substance = given.get("substance") or target.get("substance", "")

        if mass and substance:
            formula_dict = self._parse_formula(substance)
            M = sum(ATOMIC_MASSES.get(elem, 0) * count for elem, count in formula_dict.items())
            m = sp.sympify(mass)
            n = m / M

            steps = [
                {"step_number": 1, "title": "计算摩尔质量",
                 "description": f"计算 {substance} 的摩尔质量",
                 "formula": " + ".join(f"{count}×{ATOMIC_MASSES.get(elem, '?')}" for elem, count in formula_dict.items()),
                 "result": f"M = {sp.latex(sp.N(M, 4))} g/mol"},
                {"step_number": 2, "title": "求物质的量",
                 "description": "n = m / M",
                 "formula": rf"n = \frac{{{sp.latex(m)}}}{{{sp.latex(sp.N(M, 4))}}}",
                 "result": f"n = {sp.latex(sp.N(n, 4))} mol"},
            ]

            result.answer = {
                "latex": sp.latex(sp.N(n, 4)),
                "exact": str(sp.N(n, 4)),
                "numeric": float(sp.N(n, 4)),
                "unit": "mol",
            }
        else:
            steps = [{"step_number": 1, "title": "信息不足",
                      "description": "需提供物质质量", "formula": "", "result": ""}]
            result.answer = {"latex": "N/A", "exact": "N/A"}

        result.steps = steps
        return result

    # ========== 辅助方法 ==========

    def _parse_formula(self, formula: str) -> dict[str, int]:
        """解析化学式，返回元素-原子数映射。如 H2O → {'H': 2, 'O': 1}"""
        elements = {}
        # 匹配大写字母开头 + 可选小写字母 + 可选数字的片段
        for match in re.finditer(r'([A-Z][a-z]?)(\d*)', formula):
            elem = match.group(1)
            count = int(match.group(2)) if match.group(2) else 1
            elements[elem] = elements.get(elem, 0) + count
        return elements

    def _parse_reaction(self, text: str) -> tuple[list[str], list[str]]:
        """从文本解析化学反应方程式。"""
        # 找箭头
        arrow = "→" if "→" in text else "=" if "=" in text else "->"
        parts = text.split(arrow, 1)
        if len(parts) != 2:
            return (["H2", "O2"], ["H2O"])

        before = parts[0]
        after = parts[1].lstrip(">")

        # 用 + 分割
        reactants = [s.strip() for s in before.split("+")]
        products = [s.strip() for s in after.split("+")]

        # 清理数字系数前缀
        reactants = [re.sub(r'^\d+\s*', '', r).strip() for r in reactants]
        products = [re.sub(r'^\d+\s*', '', p).strip() for p in products]

        # 过滤非化学式文本
        reactants = [r for r in reactants if re.match(r'^[A-Z][A-Za-z0-9]*$', r)]
        products = [p for p in products if re.match(r'^[A-Z][A-Za-z0-9]*$', p)]

        if not reactants or not products:
            return (["H2", "O2"], ["H2O"])

        return (reactants, products)
