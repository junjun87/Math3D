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

SYSTEM_PROMPT = """你是一个数学题目结构化解析器。你的任务是将用户提供的数学题目文本转换为严格的结构化 JSON。

## 支持的题目类型

### 立体几何 (solid_geometry)
- body_type: cube | cuboid | pyramid | prism | tetrahedron | cylinder | cone
- problem_type: line_plane_angle | dihedral_angle | skew_line_angle | point_plane_distance | volume | surface_area

输出格式：
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

### target 字段说明
- line_plane_angle: 需要 line (直线) 和 plane (平面)
- dihedral_angle: 需要 plane1 和 plane2 (两个平面)
- skew_line_angle: 需要 line1 和 line2 (两条异面直线)
- point_plane_distance: 需要 point 和 plane
- volume / surface_area: 不需要额外字段

## 规则
1. 顶点标签使用标准记号：底面 A,B,C,D，顶面 A1,B1,C1,D1，顶点 P 等
2. 从题目中提取棱长等已知条件放入 given
3. 只输出 JSON，不要输出任何其他内容
4. 如果题目不属于立体几何，subject 设为 "unknown"
5. 如果无法确定具体类型，尽可能推断最匹配的类型"""


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


async def structure_problem(ocr_text: str) -> dict:
    """
    使用 LLM 将 OCR 文本结构化为题目 JSON。

    Args:
        ocr_text: OCR 识别出的原始文本

    Returns:
        结构化题目 dict，可直接传给计算内核
    """
    # 如果没有配置 API key，使用 mock 模式
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, using mock mode")
        return _mock_structure(ocr_text)

    raw_data = None
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

            # 提取 LLM 返回的文本（兼容多种响应格式）
            content = _extract_text_from_response(raw_data)

            # 尝试从响应中提取 JSON（可能包裹在 ```json ``` 中）
            json_str = _extract_json(content)
            structured = json.loads(json_str)
            logger.info(f"LLM structured problem: {structured.get('body_type')} / {structured.get('target', {}).get('type')}")
            return structured

    except httpx.HTTPError as e:
        logger.error(f"LLM API request failed: {e}")
        return _mock_structure(ocr_text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(
            f"Failed to parse LLM response: {e}, "
            f"raw_sample: {json.dumps(raw_data, ensure_ascii=False)[:400] if raw_data else 'N/A'}"
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
    Mock 模式：尝试简单关键词匹配，否则返回默认正方体线面角题目。
    用于没有 API key 时的开发和测试。
    """
    text = ocr_text.lower()

    # 尝试关键词匹配
    body_type = "cube"
    if "长方体" in text or "cuboid" in text:
        body_type = "cuboid"
    elif "棱锥" in text or "pyramid" in text or "四棱锥" in text:
        body_type = "pyramid"
    elif "棱柱" in text or "prism" in text or "三棱柱" in text:
        body_type = "prism"
    elif "四面体" in text or "tetrahedron" in text:
        body_type = "tetrahedron"
    elif "圆柱" in text or "cylinder" in text:
        body_type = "cylinder"
    elif "圆锥" in text or "cone" in text:
        body_type = "cone"

    problem_type = "line_plane_angle"
    if "二面角" in text or "dihedral" in text:
        problem_type = "dihedral_angle"
    elif "异面" in text or "skew" in text:
        problem_type = "skew_line_angle"
    elif "距离" in text or "distance" in text:
        problem_type = "point_plane_distance"
    elif "体积" in text or "volume" in text:
        problem_type = "volume"
    elif "面积" in text or "表面积" in text or "surface" in text:
        problem_type = "surface_area"

    # 提取棱长
    import re
    edge_length = 2  # 默认
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

    # 根据题型补充 target 字段
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

    logger.info(f"Mock structured: {body_type}/{problem_type}")
    return result
