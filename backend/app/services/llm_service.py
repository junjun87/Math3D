"""
LLM 题目结构化服务。

调用 Claude API 将 OCR 识别出的自然语言文本转换为结构化 JSON，
作为 SymPy 计算内核的输入。
"""

from __future__ import annotations
import json
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger("llm_service")
settings = get_settings()

SYSTEM_PROMPT = """你是一个数理化题目结构化解析器。将题目文本转换为严格的结构化 JSON。

## 学科一：立体几何 (subject: "solid_geometry")
- body_type: cube | cuboid | pyramid | prism | tetrahedron | cylinder | cone
- target.type: line_plane_angle | dihedral_angle | skew_line_angle | point_plane_distance | volume | surface_area

```json
{
  "subject": "solid_geometry",
  "body_type": "cube",
  "description": "题目的完整描述",
  "question": "具体的求解目标",
  "given": {"edge_length": 2},
  "target": {
    "type": "line_plane_angle",
    "line": "AB1",
    "plane": "A1C1D"
  },
  "language": "zh"
}
```
target 字段：
- line_plane_angle → line (直线), plane (平面)
- dihedral_angle → plane1, plane2 (两个平面)
- skew_line_angle → line1, line2 (两条异面直线)
- point_plane_distance → point, plane
- volume / surface_area → 无需额外字段

## 学科二：解析几何 (subject: "analytic_geometry")
- target.type: line_equation | circle_equation | ellipse_equation | hyperbola_equation | parabola_equation | distance | intersection | tangent_line

```json
{
  "subject": "analytic_geometry",
  "description": "求经过点(2,1)且与直线3x-4y+5=0垂直的直线方程",
  "question": "求直线方程",
  "given": {"point": [2, 1], "line": "3x-4y+5=0"},
  "target": {
    "type": "line_equation",
    "relation": "perpendicular",
    "line": "3x-4y+5=0",
    "point": [2, 1]
  },
  "language": "zh"
}
```
target 字段按题目实际内容填写。

## 学科三：代数 (subject: "algebra")
- target.type: linear_equation | quadratic_equation | system_of_equations | inequality | function_properties | sequence | polynomial | simplification

```json
{
  "subject": "algebra",
  "description": "解方程 x² - 5x + 6 = 0",
  "question": "求方程的解",
  "given": {"expression": "x^2 - 5x + 6 = 0"},
  "target": {
    "type": "quadratic_equation",
    "expression": "x^2 - 5x + 6 = 0"
  },
  "language": "zh"
}
```
- quadratic_equation → expression (含变量的表达式)
- system_of_equations → equations (方程数组)
- inequality → expression (不等式), variable (变量)
- sequence → sequence_type (arithmetic/geometric), terms
- 其他题型按题目内容填写

## 学科四：化学 (subject: "chemistry")
- target.type: equation_balance | mole_calculation | concentration | gas_law | ph_calculation | stoichiometry

```json
{
  "subject": "chemistry",
  "description": "配平化学方程式 Fe + O₂ → Fe₃O₄",
  "question": "配平化学方程式",
  "given": {"reactants": ["Fe", "O2"], "products": ["Fe3O4"]},
  "target": {
    "type": "equation_balance",
    "reactants": ["Fe", "O2"],
    "products": ["Fe3O4"]
  },
  "language": "zh"
}
```
- equation_balance → reactants (反应物数组), products (生成物数组)
- mole_calculation → substance (物质), mass (质量), molar_mass (摩尔质量)
- concentration → solute, volume, molarity
- 化学式中的数字下标写成普通数字即可，如 H2O, Fe3O4

## 全局规则
1. 顶点标签使用标准记号：底面 A,B,C,D，顶面 A1,B1,C1,D1，顶点 P 等
2. 从题目文本中提取所有已知条件放入 given
3. 只输出 JSON，不要任何额外文字、注释或 markdown
4. 无法确定学科时 subject 设为 "unknown"
5. 学科和题型尽可能推断最匹配的，不要轻易判 unknown"""


def _extract_text_from_response(data: dict) -> str:
    """
    从 LLM API 响应中提取文本内容。
    兼容 Anthropic、OpenAI、DeepSeek 等多种响应格式。

    Raises:
        KeyError: 无法从响应中提取文本
    """
    # 1. Anthropic 标准格式: {"content": [{"type": "text", "text": "..."}]}
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass

    # 2. OpenAI 标准格式: {"choices": [{"message": {"content": "..."}}]}
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass

    # 3. DeepSeek Anthropic 兼容格式（可能缺少外层 type）:
    #    {"content": [{"text": "...", "type": "text"}]}
    try:
        items = data.get("content", [])
        if items and isinstance(items[0], dict):
            # 尝试 text 字段，再尝试 delta.text（流式）
            item = items[0]
            if "text" in item:
                return item["text"]
            if "delta" in item and "text" in item["delta"]:
                return item["delta"]["text"]
    except (IndexError, TypeError):
        pass

    # 4. 尝试直接拼合 content 数组中的字符串片段
    try:
        items = data.get("content", [])
        texts = []
        for item in items:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.append(item.get("text", "") or item.get("delta", {}).get("text", ""))
        result = "".join(texts)
        if result.strip():
            return result
    except Exception:
        pass

    raise KeyError(f"Unknown LLM response format: {json.dumps(data, ensure_ascii=False)[:300]}")


OCR_CLEANUP_PROMPT = """你是一个数学 OCR 后期修正专家。请修正下面 OCR 识别的数学题文字中的错误，但保留原始语义。

修正规则：
1. LaTeX 公式使用 $$...$$ 包裹
2. 修复公式内的 OCR 错误：中文标点（，。；）→ 删除或替换为空格
3. 修正粘连的 LaTeX 命令：\\angleABC → \\angle ABC、\\sqrt2 → \\sqrt{2}
4. 上下标加花括号：A_1 → A_{1}、x^2 → x^{2}（但如果已有花括号则不动）
5. 删除公式块内的中文文字（如 "其中"、"则" 等连词如果在 $$ 内则移到外面）
6. 分数用 \\frac{分子}{分母} 格式
7. 不要添加或删除题目信息，只修正格式
8. 直接输出修正后的文本，不要加任何解释、markdown 代码块、JSON 包裹"""


async def clean_ocr_with_llm(ocr_text: str) -> str:
    """使用 LLM 清理 OCR 文本中的 LaTeX/数学符号错误。

    当 LLM API 不可用时，返回原文（不做修改）。
    """
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, skipping OCR cleanup")
        return ocr_text

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.LLM_API_BASE}/v1/messages",
                headers={
                    "x-api-key": settings.LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "max_tokens": 2048,
                    "system": OCR_CLEANUP_PROMPT,
                    "messages": [
                        {"role": "user", "content": ocr_text}
                    ],
                },
            )
            response.raise_for_status()
            raw_data = response.json()

        content = _extract_text_from_response(raw_data)
        if content and len(content.strip()) >= len(ocr_text) * 0.3:
            logger.info("LLM OCR cleanup: %d → %d chars", len(ocr_text), len(content.strip()))
            # 如果 LLM 返回了 markdown 代码块包裹，去包裹
            content = _extract_json(content)
            # _extract_json 去掉了 ```json 标记，如果内容看起来不像 JSON 则直接返回
            if content.startswith("{") and content.endswith("}"):
                # LLM 可能误返回 JSON，用原文
                logger.warning("LLM returned JSON instead of text, using original")
                return ocr_text
            return content.strip()
        else:
            logger.warning("LLM OCR cleanup returned too-short result (%d chars)", len(content or ""))
            return ocr_text

    except Exception as exc:
        logger.warning("LLM OCR cleanup failed: %s", exc)
        return ocr_text


async def structure_problem(ocr_text: str) -> dict:
    """
    使用 LLM 将 OCR 文本结构化为题目 JSON。

    Args:
        ocr_text: OCR 识别出的原始文本

    Returns:
        结构化题目 dict，可直接传给计算内核
    """
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, using mock mode")
        return _mock_structure(ocr_text)

    raw_data = None
    content = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.LLM_API_BASE}/v1/messages",
                    headers={
                        "x-api-key": settings.LLM_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.LLM_MODEL,
                        "max_tokens": 1024,
                        "system": SYSTEM_PROMPT,
                        "messages": [
                            {"role": "user", "content": ocr_text}
                        ],
                    },
                )
                response.raise_for_status()
                raw_data = response.json()

            content = _extract_text_from_response(raw_data)
            logger.info("LLM raw response (attempt %d): %s", attempt + 1, content[:300])

            json_str = _extract_json(content)
            structured = json.loads(json_str)
            logger.info("LLM structured: subject=%s body=%s type=%s",
                        structured.get("subject"), structured.get("body_type"),
                        structured.get("target", {}).get("type"))
            return structured

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("LLM parse failed (attempt %d): %s", attempt + 1, e)
            if attempt == 0:
                # 重试，prompt 加强调
                ocr_text = f"请严格按JSON格式输出，不要markdown包裹：\n\n{ocr_text}"
                continue
        except httpx.HTTPError as e:
            logger.error("LLM API request failed (attempt %d): %s", attempt + 1, e)
            break

    # 两次都失败，记录详细信息后回退 mock
    logger.error(
        "LLM structure failed after 2 attempts. "
        "OCR text preview: %s... | "
        "Raw response: %s",
        ocr_text[:200],
        json.dumps(raw_data, ensure_ascii=False)[:500] if raw_data else "N/A"
    )
    return _mock_structure(ocr_text)


def _extract_json(text: str) -> str:
    """从 LLM 响应中提取 JSON 字符串。处理被 ```json ``` 包裹的情况。"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _mock_structure(ocr_text: str) -> dict:
    """
    Mock 模式：关键词匹配识别学科和题型。
    用于没有 API key 或 API 解析失败时的 fallback。
    """
    import re
    text = ocr_text.lower()

    subject = _detect_subject(text)
    logger.info(f"Mock detected subject: {subject}")

    if subject == "solid_geometry":
        return _mock_solid_geometry(ocr_text)
    elif subject == "analytic_geometry":
        return _mock_analytic_geometry(ocr_text)
    elif subject == "algebra":
        return _mock_algebra(ocr_text)
    elif subject == "chemistry":
        return _mock_chemistry(ocr_text)
    else:
        return _mock_solid_geometry(ocr_text)  # 默认 fallback


def _detect_subject(text: str) -> str:
    """根据关键词识别学科。"""
    import re
    # 立体几何
    geo_keywords = [
        "正方体", "长方体", "棱柱", "棱锥", "四面体", "圆柱", "圆锥",
        "线面角", "二面角", "异面", "点面距离",
        "cube", "cuboid", "pyramid", "prism", "tetrahedron",
    ]
    if any(kw in text for kw in geo_keywords):
        return "solid_geometry"

    # 化学
    chem_keywords = [
        "化学方程", "配平", "物质的量", "摩尔", "浓度",
        "ph", "反应", "气体", "溶液", "电解质",
        "h2o", "co2", "fe", "naoh", "hcl", "h2so4",
    ]
    if any(kw in text for kw in chem_keywords):
        return "chemistry"

    # 解析几何
    analytic_keywords = [
        "直线方程", "圆的方程", "椭圆", "双曲线", "抛物线",
        "焦点", "准线", "离心率", "渐近线", "弦长",
        "切线", "法线", "交点", "距离公式",
    ]
    if any(kw in text for kw in analytic_keywords):
        return "analytic_geometry"

    # 代数（最宽泛，放最后）
    algebra_keywords = [
        "解方程", "方程组", "不等式", "函数", "数列",
        "求根", "因式分解", "多项式", "求导", "积分",
        "最大值", "最小值", "定义域", "值域",
    ]
    if any(kw in text for kw in algebra_keywords):
        return "algebra"

    # 如果有数字和字母表达式但没命中上面关键词，默认代数
    if re.search(r'[xy]\s*[=]', text) or re.search(r'[xy]\^?\d', text):
        return "algebra"

    return "solid_geometry"


def _mock_solid_geometry(ocr_text: str) -> dict:
    """立体几何 mock 结构化。"""
    import re
    text = ocr_text.lower()

    body_type = "cube"
    if "长方体" in text:
        body_type = "cuboid"
    elif "棱锥" in text or "四棱锥" in text:
        body_type = "pyramid"
    elif "棱柱" in text or "三棱柱" in text:
        body_type = "prism"
    elif "四面体" in text:
        body_type = "tetrahedron"
    elif "圆柱" in text:
        body_type = "cylinder"
    elif "圆锥" in text:
        body_type = "cone"

    problem_type = "line_plane_angle"
    if "二面角" in text:
        problem_type = "dihedral_angle"
    elif "异面" in text:
        problem_type = "skew_line_angle"
    elif "距离" in text:
        problem_type = "point_plane_distance"
    elif "体积" in text:
        problem_type = "volume"
    elif "面积" in text or "表面积" in text:
        problem_type = "surface_area"

    edge_length = 2
    match = re.search(r'棱长[为是]?\s*(\d+)', ocr_text)
    if match:
        edge_length = int(match.group(1))

    result = {
        "subject": "solid_geometry",
        "body_type": body_type,
        "description": ocr_text.strip(),
        "question": "",
        "given": {"edge_length": edge_length},
        "target": {"type": problem_type},
        "language": "zh",
    }

    if problem_type == "line_plane_angle":
        result["target"]["line"] = "AB1"
        result["target"]["plane"] = "A1C1D"
    elif problem_type == "dihedral_angle":
        result["target"]["plane1"] = "A1BD"
        result["target"]["plane2"] = "C1BD"
    elif problem_type == "skew_line_angle":
        result["target"]["line1"] = "A1B"
        result["target"]["line2"] = "C1D"
    elif problem_type == "point_plane_distance":
        result["target"]["point"] = "B1"
        result["target"]["plane"] = "A1C1D"

    logger.info(f"Mock structured: solid_geometry/{body_type}/{problem_type}")
    return result


def _mock_analytic_geometry(ocr_text: str) -> dict:
    """解析几何 mock 结构化。"""
    import re
    text = ocr_text.lower()

    problem_type = "line_equation"
    if "椭圆" in text:
        problem_type = "ellipse_equation"
    elif "双曲线" in text:
        problem_type = "hyperbola_equation"
    elif "抛物线" in text:
        problem_type = "parabola_equation"
    elif "圆的" in text or "圆方程" in text:
        problem_type = "circle_equation"
    elif "切线" in text:
        problem_type = "tangent_line"
    elif "距离" in text:
        problem_type = "distance"
    elif "交点" in text or "相交" in text:
        problem_type = "intersection"

    # 提取坐标点
    points = re.findall(r'[\(（]\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*[\)）]', ocr_text)

    result = {
        "subject": "analytic_geometry",
        "description": ocr_text.strip(),
        "question": "",
        "given": {},
        "target": {"type": problem_type},
        "language": "zh",
    }

    if points:
        result["given"]["points"] = [[int(x), int(y)] for x, y in points[:4]]

    if "垂直" in text:
        result["target"]["relation"] = "perpendicular"
    elif "平行" in text:
        result["target"]["relation"] = "parallel"

    # 提取直线方程
    line_match = re.search(r'([\d\-]*x\s*[+\-]\s*[\d\-]*y\s*[+\-]\s*[\d\-]+)\s*=\s*0', ocr_text)
    if line_match:
        result["given"]["line"] = line_match.group(1).replace(" ", "") + "=0"

    logger.info(f"Mock structured: analytic_geometry/{problem_type}")
    return result


def _mock_algebra(ocr_text: str) -> dict:
    """代数 mock 结构化。"""
    import re
    text = ocr_text.lower()

    problem_type = "quadratic_equation"
    if "方程组" in text:
        problem_type = "system_of_equations"
    elif "一次方程" in text or "一元一次" in text:
        problem_type = "linear_equation"
    elif "不等式" in text:
        problem_type = "inequality"
    elif "数列" in text or "等差" in text or "等比" in text:
        problem_type = "sequence"
    elif "因式分解" in text:
        problem_type = "polynomial"
    elif "函数" in text:
        problem_type = "function_properties"
    elif "化简" in text:
        problem_type = "simplification"

    # 提取表达式
    expr_match = re.search(
        r'([\d\w\^\+\-\*\/\=\(\)xXyYzZ\s]+(?:=\s*0)?)', ocr_text
    )
    expression = expr_match.group(1).strip() if expr_match else ""

    result = {
        "subject": "algebra",
        "description": ocr_text.strip(),
        "question": "",
        "given": {},
        "target": {"type": problem_type},
        "language": "zh",
    }

    if problem_type == "system_of_equations":
        result["target"]["equations"] = [expression] if expression else ["x+y=1", "x-y=3"]
    elif expression:
        result["target"]["expression"] = expression.replace(" ", "")

    logger.info(f"Mock structured: algebra/{problem_type}")
    return result


def _mock_chemistry(ocr_text: str) -> dict:
    """化学 mock 结构化。"""
    import re

    problem_type = "equation_balance"
    if "物质的量" in ocr_text or "摩尔" in ocr_text:
        problem_type = "mole_calculation"
    elif "浓度" in ocr_text:
        problem_type = "concentration"
    elif "ph" in ocr_text.lower():
        problem_type = "ph_calculation"
    elif "气体" in ocr_text:
        problem_type = "gas_law"

    # 提取化学式（大写字母开头 + 可选小写字母 + 可选数字）
    formulas = re.findall(r'[A-Z][a-z]?\d*', ocr_text)
    plus_idx = ocr_text.find("+")
    arrow_idx = ocr_text.find("→") if "→" in ocr_text else ocr_text.find("=")

    reactants, products = [], []
    if arrow_idx > 0:
        before_arrow = ocr_text[:arrow_idx]
        after_arrow = ocr_text[arrow_idx + 1:].lstrip(">")
        reactants = re.findall(r'[A-Z][a-z]?\d*', before_arrow)
        products = re.findall(r'[A-Z][a-z]?\d*', after_arrow)

    result = {
        "subject": "chemistry",
        "description": ocr_text.strip(),
        "question": "",
        "given": {"reactants": reactants, "products": products},
        "target": {
            "type": problem_type,
            "reactants": reactants,
            "products": products,
        },
        "language": "zh",
    }

    logger.info(f"Mock structured: chemistry/{problem_type}")
    return result
