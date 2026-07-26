"""
LLM 题面解析器：将自然语言题面解析为结构化几何问题 spec。

通过 OpenAI 兼容 API 调用 LLM，提取 (shape_type, query_type, parameters)。
配置通过环境变量读取，支持任意 OpenAI 兼容提供商。
"""

from __future__ import annotations

import base64 as _b64
import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote as _url_quote

import httpx

from solver_registry import list_supported_types

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class LLMNotConfiguredError(Exception):
    """LLM 未配置（缺少 API key 或 base URL）。"""


class LLMParseError(Exception):
    """LLM 返回内容无法解析为有效的几何 spec。"""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout: int = 60

    @classmethod
    def from_env(cls) -> "LLMConfig":
        try:
            timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        except (TypeError, ValueError):
            logger.warning("LLM_TIMEOUT is not a valid integer, using default 30")
            timeout = 30
        return cls(
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("LLM_API_KEY", ""),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            timeout=timeout,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    """从求解器注册表动态生成中文 system prompt。"""
    supported = list_supported_types()

    type_descriptions = {
        "cube": "正方体",
        "cuboid": "长方体",
        "regular_tetrahedron": "正四面体",
        "regular_quad_pyramid": "正四棱锥",
        "regular_triangular_prism": "正三棱柱",
    }
    query_descriptions = {
        "line_plane_angle": "线面角（直线与平面所成角的正弦值）",
        "line_line_angle": "异面直线夹角（余弦值）",
        "point_plane_distance": "点到平面距离",
        "point_range": "动点取值范围（动点在侧面上满足某条件时，线段长度的取值范围）",
        "volume": "体积",
        "dihedral_angle": "二面角（余弦值）",
    }

    # 生成支持的题型列表
    type_lines = []
    for shape, queries in supported.items():
        shape_cn = type_descriptions.get(shape, shape)
        for q in queries:
            q_cn = query_descriptions.get(q, q)
            type_lines.append(f"- {shape} + {q}：{shape_cn}{q_cn}")

    type_list = "\n".join(type_lines) if type_lines else "（暂未注册任何题型）"

    return f"""你是一个立体几何题面解析专家。将用户输入的中文题面解析为结构化 JSON。

## 当前支持的几何体类型与问题类型

{type_list}

## 输出 JSON 格式

{{
  "shape_type": "<几何体类型>",
  "query_type": "<问题类型>",
  "parameters": {{ "edge": <棱长数值> }}
}}

## 参数说明

- edge：正方体的棱长 / 正四面体的棱长（数值）。如果题面给出了具体数值则提取；如果出现字母变量（如 "棱长为 a"）则默认为 2。
- base_edge：正四棱锥的底面边长（数值）。默认为 2。
- height：正四棱锥的高（数值）。默认为 1。
- 其他参数按题面实际含义提取，使用数字键名。

## 规则

1. 只输出 JSON，不要包含其他文字或 markdown 代码块标记。
2. 如果题面涉及当前不支持的几何体或问题类型，输出 {{"error": "不支持的问题类型：<简要原因>"}}。
3. 如果题面信息不完整，用默认值补充（棱长默认为 2）。
4. 不要编造题面中没有的数值。

## OCR 容错提示

题面文字可能由 OCR 自动识别生成，可能存在以下识别错误，请根据上下文自动修正：
- 数学下标可能缺失（如 A1 应为 A₁、C1 应为 C₁）
- 角度符号 ∠ 可能被识别为 Z 或丢失
- 根号 √ 可能被识别为 V 或 J
- 度数符号 ° 可能被识别为句号 。或字母 o
- 三角形符号 △ 可能被识别为其他字符

遇到明显是数学符号但 OCR 识别异常的情况，按数学语境理解即可，
不要将 OCR 错误当作题面本意。

## 示例

用户：正方体 ABCD-A1B1C1D1 棱长为 2，求直线 AC1 与平面 BDD1B1 所成角的正弦值。
输出：{{"shape_type": "cube", "query_type": "line_plane_angle", "parameters": {{"edge": 2}}}}

用户：一个边长为3的正方体，求体对角线AC1与对角面BDD1B1的夹角正弦
输出：{{"shape_type": "cube", "query_type": "line_plane_angle", "parameters": {{"edge": 3}}}}

用户：正方体ABCD-A1B1C1D1棱长为2，E,F分别是棱BC,CC1的中点，P是侧面BCC1B1内一点，若A1P∥平面AEF，求线段A1P长度的取值范围。
输出：{{"shape_type": "cube", "query_type": "point_range", "parameters": {{"edge": 2}}}}

用户：正方体棱长为2，求点A1到平面AB1C的距离。
输出：{{"shape_type": "cube", "query_type": "point_plane_distance", "parameters": {{"edge": 2}}}}

用户：正方体棱长为2，求异面直线A1C与AB所成角的余弦值。
输出：{{"shape_type": "cube", "query_type": "line_line_angle", "parameters": {{"edge": 2}}}}

用户：正方体棱长为2，求二面角A-BD-C1的余弦值。
输出：{{"shape_type": "cube", "query_type": "dihedral_angle", "parameters": {{"edge": 2}}}}

用户：正方体棱长为3，求该正方体的体积。
输出：{{"shape_type": "cube", "query_type": "volume", "parameters": {{"edge": 3}}}}

用户：正四面体ABCD棱长为2，求该正四面体的体积。
输出：{{"shape_type": "regular_tetrahedron", "query_type": "volume", "parameters": {{"edge": 2}}}}

用户：正四面体棱长为3，求直线AB与平面BCD所成角的正弦值。
输出：{{"shape_type": "regular_tetrahedron", "query_type": "line_plane_angle", "parameters": {{"edge": 3}}}}

用户：正四面体棱长为2，求异面直线AB与CD所成角的余弦值。
输出：{{"shape_type": "regular_tetrahedron", "query_type": "line_line_angle", "parameters": {{"edge": 2}}}}

用户：正四面体棱长为2，求二面角A-BC-D的余弦值。
输出：{{"shape_type": "regular_tetrahedron", "query_type": "dihedral_angle", "parameters": {{"edge": 2}}}}

用户：正四棱锥P-ABCD底面边长2高1，求侧面PAB与底面ABCD所成二面角的余弦值。
输出：{{"shape_type": "regular_quad_pyramid", "query_type": "dihedral_angle", "parameters": {{"base_edge": 2, "height": 1}}}}

用户：正四棱锥底面边长2高1，求该正四棱锥的体积。
输出：{{"shape_type": "regular_quad_pyramid", "query_type": "volume", "parameters": {{"base_edge": 2, "height": 1}}}}

用户：正三棱柱ABC-A1B1C1底面边长2高3，求该正三棱柱的体积。
输出：{{"shape_type": "regular_triangular_prism", "query_type": "volume", "parameters": {{"base_edge": 2, "height": 3}}}}

用户：正三棱柱底面等边三角形边长2高3，求直线AB1与底面ABC所成角的正弦值。
输出：{{"shape_type": "regular_triangular_prism", "query_type": "line_plane_angle", "parameters": {{"base_edge": 2, "height": 3}}}}

用户：正三棱柱底面边长2高3，求点C1到侧面ABB1A1的距离。
输出：{{"shape_type": "regular_triangular_prism", "query_type": "point_plane_distance", "parameters": {{"base_edge": 2, "height": 3}}}}"""


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------

_JSON_MARKER_START = "```json"
_JSON_MARKER_END = "```"


def _extract_content(data: dict) -> str:
    """Safely extract message content from a chat completions response."""
    try:
        choices = data.get("choices", [])
        if not choices:
            raise LLMParseError("LLM returned empty choices")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise LLMParseError("LLM response has no content")
        return content.strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMParseError(f"Unexpected LLM response structure: {e}") from e


def _call_llm(system_prompt: str, user_message: str, config: LLMConfig,
              use_json: bool = True, max_tokens: int = 4096) -> str:
    """调用 OpenAI 兼容的 /v1/chat/completions，返回响应文本。"""
    url = config.base_url.rstrip("/") + "/v1/chat/completions"

    payload: dict = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    # DeepSeek 思考模式会增加响应时间，OCR/解析场景必须关闭；
    # 只对 DeepSeek 模型注入该参数，避免其他 OpenAI 兼容服务 400。
    if "deepseek" in config.model.lower() or "deepseek" in config.base_url.lower():
        payload["thinking"] = {"type": "disabled"}
    if use_json:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Calling LLM: model=%s url=%s", config.model, url)

    with httpx.Client(timeout=config.timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # Debug: log raw response structure
    choices = data.get("choices", [])
    finish_reason = ""
    if choices:
        msg = choices[0].get("message", {})
        finish_reason = choices[0].get("finish_reason", "")
        raw_content = msg.get("content", "")
        logger.info("LLM raw response: finish_reason=%s content_len=%d content=%s",
                    finish_reason, len(raw_content or ""), (raw_content or "")[:200])

    content = _extract_content(data)
    logger.info("LLM response: %s", content[:200])
    return content


def _parse_response(raw: str) -> dict:
    """解析 LLM 返回的 JSON，处理可能的 markdown 代码块包裹。"""
    text = raw.strip()

    # 去掉可能的 ```json ... ``` 包裹
    if text.startswith(_JSON_MARKER_START):
        text = text[len(_JSON_MARKER_START):]
        if text.endswith(_JSON_MARKER_END):
            text = text[:-len(_JSON_MARKER_END)]
        text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON 解析失败: {e}\n原始内容: {raw[:300]}")

    if not isinstance(result, dict):
        raise LLMParseError(f"期望 JSON 对象，实际收到: {type(result).__name__}")

    # 检查 LLM 自身返回的错误
    if "error" in result:
        raise LLMParseError(result["error"])

    # 验证必填字段
    required = ["shape_type", "query_type"]
    missing = [k for k in required if k not in result]
    if missing:
        raise LLMParseError(f"LLM 响应缺少必填字段: {missing}")

    return result


# ---------------------------------------------------------------------------
# 阿里云文字识别 OCR（按次计费，不走 token）
# ---------------------------------------------------------------------------


def _percent_encode(s: str) -> str:
    """URL 百分号编码（阿里云 POP API 专用）。"""
    return _url_quote(str(s), safe='-_.~')


def _call_aliyun_ocr_api(action: str, image_bytes: bytes, extra_params: dict | None = None) -> str:
    """
    调用阿里云 OCR POP API，返回识别文本 content。
    共享签名 + HTTP 调用逻辑，供不同 Action 复用。
    """
    ak_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    ak_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

    if not ak_id or not ak_secret:
        raise RuntimeError("ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 未设置")

    params = {
        "AccessKeyId": ak_id,
        "Action": action,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2021-07-07",
    }
    if extra_params:
        params.update(extra_params)

    # HMAC-SHA1 签名
    sorted_keys = sorted(params.keys())
    canon_query = "&".join(
        f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted_keys
    )
    string_to_sign = f'POST&{_percent_encode("/")}&{_percent_encode(canon_query)}'
    signing_key = (ak_secret + "&").encode("utf-8")
    signature = _b64.b64encode(
        hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    url = (
        "https://ocr-api.cn-hangzhou.aliyuncs.com/?"
        + canon_query
        + "&Signature="
        + _percent_encode(signature)
    )

    logger.info("Calling Aliyun OCR: action=%s image_size=%dKB", action, len(image_bytes) // 1024)

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, content=image_bytes,
                           headers={"Content-Type": "application/octet-stream"})
        resp.raise_for_status()
        data = resp.json()

    # 解析 Data 字段（可能是 JSON 字符串或字典）
    raw_data = data.get("Data", "")
    if isinstance(raw_data, str) and raw_data:
        try:
            parsed = json.loads(raw_data)
            content = parsed.get("content", "")
        except json.JSONDecodeError:
            content = raw_data
    elif isinstance(raw_data, dict):
        content = raw_data.get("content", "")
    else:
        content = ""

    logger.info("Aliyun OCR [%s]: %s", action, content[:200] if content else "(empty)")
    return content.strip()


def _call_aliyun_ocr(image_base64: str) -> str:
    """
    识别图片中的题目文字。
    策略：先试教育场景题目识别（RecognizeEduQuestionOcr），
    返回空则降级到通用文字识别（RecognizeAdvanced）。
    """
    image_bytes = _b64.b64decode(image_base64)

    # ---- 路径 A：教育场景题目识别 ----
    content = _call_aliyun_ocr_api(
        "RecognizeEduQuestionOcr", image_bytes,
        extra_params={"NeedRotate": "true"},
    )
    if content:
        return content

    # ---- 路径 B：降级到通用文字识别 ----
    logger.info("EduQuestionOcr returned empty, falling back to RecognizeAdvanced")
    content = _call_aliyun_ocr_api("RecognizeAdvanced", image_bytes)
    return content


# ---------------------------------------------------------------------------
# 视觉 LLM 调用（fallback：当阿里云 OCR 未配置时使用）
# ---------------------------------------------------------------------------

VISION_SYSTEM_PROMPT = """你是一个立体几何题面 OCR 专家。你的任务是从用户上传的图片中提取立体几何题目原文。

## 规则

1. 忠实还原图片中的题目文字，不要添加解释或额外内容。
2. 保留题目中的所有数学符号、字母、下标（如下标用 _ 表示，如 A_1、C_1）。
3. 如果是中文题目，用简体中文输出。
4. 如果图片中没有几何题目，输出空字符串。
5. 只输出题目原文，不要包含任何前缀、后缀或说明。"""


def _call_vision_llm(image_base64: str, media_type: str, config: LLMConfig) -> str:
    """调用 OpenAI 兼容 vision API，传入图片，返回识别文本（fallback）。"""
    url = config.base_url.rstrip("/") + "/v1/chat/completions"

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": VISION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请识别并提取这张图片中的立体几何题目原文。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_base64}",
                        },
                    },
                ],
            },
        ],
        "max_tokens": 512,
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Calling vision LLM: model=%s url=%s image_size=%dKB",
                config.model, url, len(image_base64) // 1024)

    # Vision calls need more time — large images take longer to process
    vision_timeout = max(config.timeout, 60)

    try:
        with httpx.Client(timeout=vision_timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Vision LLM HTTP error: %s %s", e.response.status_code, e.response.text[:500])
        raise
    except httpx.TimeoutException:
        logger.error("Vision LLM timed out after %ds", vision_timeout)
        raise

    content = _extract_content(data)
    logger.info("Vision LLM response: %s", content[:200])
    return content


# ---------------------------------------------------------------------------
# OCR 文字规范化
# ---------------------------------------------------------------------------

def _normalize_ocr_text(text: str) -> str:
    """对 OCR 输出做安全的规范化。

    只处理零歧义的 OCR 错误模式（根号、角度、度数等）。
    有上下文依赖的修正（如 A1→A₁）交给 LLM 判断。
    """
    import re

    # 全角字符 → 半角
    text = text.translate(str.maketrans(
        '０１２３４５６７８９．，；：？！（）【】＋－×÷＝＜＞％',
        '0123456789.,;:?!()[]+-×÷=<>%'
    ))

    # ── 根号 ──
    # OCR 常把 √ 识别为 V / J / v（如 V3→√3, J2→√2）
    # 只在独立出现（前无字母）时替换，避免误伤变量名
    text = re.sub(r'(?<![a-zA-Z])[VJv](?=\d)', r'√', text)

    # ── 度数 ──
    # 30。→30° / 30o→30° / 30O→30° / 30°→30°（已正确的不动）
    text = re.sub(r'(\d)[。.oO]', r'\1°', text)

    # ── 角度符号 ──
    # OCR 常把 ∠ 识别为 Z / L / 么 / 乙
    # ZABC→∠ABC, LABC→∠ABC, 么ABC→∠ABC
    text = re.sub(r'(?<![a-zA-Z])[ZL](?=[A-Z]{3})', r'∠', text)
    text = re.sub(r'[么乙](?=[A-Z]{3})', r'∠', text)

    # ── 三角形符号 ──
    # OCR 常把 △ 识别为空或 A
    # "AABC" 在几何上下文中应是 "△ABC"
    # 安全策略：只替换已知的三角形顶点命名模式
    text = re.sub(r'(?<![a-zA-Z])A(?=ABC)', r'△', text)

    # ── 平行符号 ──
    # OCR 可能丢失 ∥
    text = re.sub(r'(?<![a-zA-Z])\\|\\|(?![a-zA-Z])', r'∥', text)

    # ── 垂直符号 ──
    text = re.sub(r'(?<![a-zA-Z])_\\|_(?![a-zA-Z])', r'⊥', text)

    # ── 空白清理 ──
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _normalize_with_llm(raw_text: str) -> str:
    """
    用 LLM 清洗 OCR 原始输出：
    1. 修复数学符号（下标、根号、度数、角度等）
    2. 过滤立体图形上的标注文字，只保留题目正文

    如果 LLM 未配置或调用失败，返回原始文本（不阻塞流程）。
    """
    config = LLMConfig.from_env()
    if not config.is_configured:
        return raw_text

    prompt = """你是一个数学题面 OCR 清洗专家。请对以下 OCR 识别结果进行处理，输出清洗后的题目原文。

## 任务

### 1. 修复下标
OCR 经常丢失数学下标。在立体几何中，数字跟在字母后面通常表示下标：
- A1 → A₁、C1 → C₁、B1 → B₁
- A1C1 → A₁C₁（注意：两个字母都可能带下标）
- AA1 → AA₁（前面的 A 没有下标）
- 平面 BDD1B1 → 平面 BDD₁B₁
- 保留格式：A_{1}、C_{1}

### 2. 修复根号
OCR 经常把 √ 识别为 V 或 J：
- V3 → √3
- V2 → √2
- V6 → √6
- 2V3 → 2√3

### 3. 修复角度符号
OCR 经常把 ∠ 识别为 Z、L 或其他字符：
- ZABC → ∠ABC
- LABC → ∠ABC
- 如果角度符号完全丢失（如只写 ABC），根据"所成角""夹角"等上下文补回 ∠

### 4. 修复度数符号
OCR 经常把 ° 识别为句号或字母 o：
- 30。→ 30°
- 45o → 45°
- 90° 保持

### 5. 修复三角形符号
OCR 可能丢失 △：
- AABC → △ABC

### 6. 修复平行/垂直符号
- ∥ 可能被识别为 // 或 ||
- ⊥ 可能被识别为 _|_

### 7. 过滤图形标注
立体几何照片中的图形上有零散的顶点标签（如单独的 A、B、C、D 等），这些不属于题目正文。请将它们移除，只保留完整的题目句子。

## 输出规则
- 只输出清洗后的题目原文，一行或两行即可
- 不要加任何解释、前缀（如"清洗后："）或后缀
- 用简体中文输出，保持原题的数学符号
- 如果某处无法确定，保留原文"""

    try:
        content = _call_llm(prompt, raw_text, config, use_json=False, max_tokens=4096)
        logger.info("LLM normalized OCR (%d chars): %s", len(content), content[:300])
        return content.strip() if content.strip() else raw_text
    except Exception as e:
        logger.warning("LLM normalization failed: %s, using raw text", e)
        return raw_text


# ---------------------------------------------------------------------------
# LLM 纯文字解题（不匹配已注册题型时的降级方案）
# ---------------------------------------------------------------------------

def solve_text_only(problem_text: str) -> dict:
    """
    对无法匹配已注册题型的题目，调用 LLM 给出纯文字逐步解答。

    返回:
        {"steps": [...], "answer_latex": str}

    异常:
        LLMNotConfiguredError — API key 未配置
        LLMParseError — LLM 返回不可解析
    """
    config = LLMConfig.from_env()
    if not config.is_configured:
        raise LLMNotConfiguredError("LLM not configured for text-only solving")

    supported = list_supported_types()
    supported_str = "\n".join(
        f"- {s} + {q}" for s, qs in supported.items() for q in qs
    )

    prompt = f"""你是一个立体几何解题专家。请对以下题目给出详细的逐步解答。

## 已注册题型参考（本题不属于以下任一，请自由发挥）

{supported_str}

## 输出格式

严格输出以下 JSON（不要包含 markdown 代码块标记）：

{{
  "answer_latex": "最终答案的 LaTeX 表达式（纯 LaTeX，不含 $ 符号）",
  "steps": [
    {{"title": "步骤标题", "content": "步骤内容。可使用 <p> 段落、$...$ 行内公式、$$...$$ 独立公式。"}}
  ]
}}

## 要求
- 每个步骤的 content 为 HTML，数学公式用 $...$（行内）或 $$...$$（独立行）
- 解答要完整、准确，展示关键推理过程和中间结果
- 最终答案放在 answer_latex 中，使用纯 LaTeX 格式（如 \\frac{{a}}{{b}}、\\sqrt{{2}}）
- 如果题目信息不完整，在第一步指出并给出合理假设
- 如果题目不属于立体几何，返回 error 字段

## 示例

题目：正方体棱长为1，求其外接球的表面积。
输出：
{{
  "answer_latex": "3\\pi",
  "steps": [
    {{"title": "分析题意", "content": "<p>正方体棱长 $a=1$，外接球直径等于体对角线。</p>"}},
    {{"title": "计算体对角线", "content": "<p>体对角线 $d = \\sqrt{{a^2 + a^2 + a^2}} = \\sqrt{{3}}a = \\sqrt{{3}}$</p>"}},
    {{"title": "计算外接球表面积", "content": "<p>球半径 $R = d/2 = \\sqrt{{3}}/2$</p><p>表面积 $S = 4\\pi R^2 = 4\\pi \\cdot \\frac{{3}}{{4}} = 3\\pi$</p>"}}
  ]
}}"""

    # Use plain text mode — JSON mode can truncate long structured responses
    try:
        content = _call_llm(prompt, problem_text, config, use_json=False, max_tokens=4096)
    except Exception as e:
        logger.warning("LLM text-only call failed: %s", e)
        raise LLMParseError(f"LLM API 调用失败: {e}")

    # Parse the response — try to extract JSON from possible markdown wrapping
    import json as _json_mod
    text = content.strip()
    if text.startswith(_JSON_MARKER_START):
        text = text[len(_JSON_MARKER_START):]
        if text.endswith(_JSON_MARKER_END):
            text = text[:-len(_JSON_MARKER_END)]
        text = text.strip()

    try:
        result = _json_mod.loads(text)
    except _json_mod.JSONDecodeError as e:
        logger.warning("LLM text-only JSON parse failed. Raw: %s", content[:500])
        raise LLMParseError(f"LLM 返回内容无法解析为 JSON: {e}")

    if not isinstance(result, dict):
        raise LLMParseError(f"Expected JSON object, got {type(result).__name__}")

    if "error" in result:
        raise LLMParseError(result["error"])

    if "steps" not in result:
        raise LLMParseError("LLM response missing 'steps' field")

    return result


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def parse_problem(problem_text: str) -> dict:
    """
    将中文题面解析为结构化 spec。

    返回:
        {"shape_type": str, "query_type": str, "parameters": dict}

    异常:
        LLMNotConfiguredError — API key 未配置
        LLMParseError — LLM 返回内容无法解析
        httpx.HTTPError — 网络或 API 错误
    """
    problem_text = _normalize_ocr_text(problem_text)
    config = LLMConfig.from_env()

    if not config.is_configured:
        raise LLMNotConfiguredError("LLM_API_KEY 未设置，跳过 LLM 解析")

    system_prompt = _build_system_prompt()
    raw = _call_llm(system_prompt, problem_text, config, use_json=True, max_tokens=4096)
    return _parse_response(raw)


def ocr_image(image_base64: str, media_type: str = "image/jpeg") -> str:
    """
    识别图片中的几何题目文字。

    优先使用阿里云文字识别 OCR（按次计费，便宜）。
    未配置阿里云 AccessKey 时降级为视觉 LLM（需支持 vision 的模型）。
    """
    text = ""

    # ---- 路径 1：阿里云文字识别 OCR ----
    ak_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    if ak_id:
        logger.info("OCR: using Aliyun RecognizeEduQuestionOcr")
        try:
            text = _call_aliyun_ocr(image_base64)
        except Exception as e:
            logger.warning("Aliyun OCR failed: %s, falling back to vision LLM", e)

    # ---- 路径 2：视觉 LLM（fallback） ----
    if not text:
        config = LLMConfig.from_env()

        if not config.is_configured:
            raise LLMNotConfiguredError(
                "未配置 OCR 服务。请设置 ALIBABA_CLOUD_ACCESS_KEY_ID + "
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET（阿里云 OCR），"
                "或 LLM_API_KEY + LLM_BASE_URL + LLM_MODEL（视觉 LLM）。"
            )

        text = _call_vision_llm(image_base64, media_type, config)

    # 轻量正则规范化
    text = _normalize_ocr_text(text)
    # LLM 清洗：修复数学符号 + 过滤图形标注文字（可通过 OCR_LLM_NORMALIZE=0 关闭以节省费用）
    if text and os.getenv("OCR_LLM_NORMALIZE", "1") not in ("0", "false", "no", "off"):
        text = _normalize_with_llm(text)
    return text
