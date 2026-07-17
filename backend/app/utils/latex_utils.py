def escape_latex(text: str) -> str:
    """转义文本中的 LaTeX 特殊字符。"""
    special_chars = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
        "\\": r"\textbackslash{}",
    }
    for char, escaped in special_chars.items():
        text = text.replace(char, escaped)
    return text


def wrap_math(text: str) -> str:
    """将数学表达式包裹在 $...$ 中（行内）或 $$...$$ 中（块级）。"""
    # 简单实现：检测是否包含 LaTeX 命令
    latex_commands = [
        r"\frac", r"\sqrt", r"\int", r"\sum", r"\prod",
        r"\alpha", r"\beta", r"\gamma", r"\theta", r"\pi",
        r"\sin", r"\cos", r"\tan", r"\log", r"\ln",
        r"\vec", r"\overrightarrow", r"\angle",
        r"\mathbf", r"\mathrm", r"\mathbb",
    ]
    if any(cmd in text for cmd in latex_commands):
        if "\n" in text:
            return f"$${text}$$"
        return f"${text}$"
    return text


def format_angle(value_str: str) -> str:
    """格式化角度值，返回带单位的 LaTeX。"""
    return r"\theta = " + value_str


def format_distance(value_str: str) -> str:
    """格式化距离值。"""
    return r"d = " + value_str


def format_vector(label: str, components: list) -> str:
    """格式化向量 LaTeX。"""
    comp_str = ", ".join(str(c) for c in components)
    return rf"\overrightarrow{{{label}}} = ({comp_str})"
