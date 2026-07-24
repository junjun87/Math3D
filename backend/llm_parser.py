"""
LLM 题面解析器：将自然语言题面解析为结构化几何问题 spec。

通过 OpenAI 兼容 API 调用 LLM，提取 (shape_type, query_type, parameters)。
配置通过环境变量读取，支持任意 OpenAI 兼容提供商。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

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
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("LLM_API_KEY", ""),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            timeout=int(os.getenv("LLM_TIMEOUT", "30")),
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
    }
    query_descriptions = {
        "line_plane_angle": "线面角（直线与平面所成角的正弦值）",
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

- edge：正方体的棱长（数值）。如果题面给出了具体数值则提取；如果出现字母变量（如 "棱长为 a"）则默认为 2。
- 其他参数按题面实际含义提取，使用数字键名。

## 规则

1. 只输出 JSON，不要包含其他文字或 markdown 代码块标记。
2. 如果题面涉及当前不支持的几何体或问题类型，输出 {{"error": "不支持的问题类型：<简要原因>"}}。
3. 如果题面信息不完整，用默认值补充（棱长默认为 2）。
4. 不要编造题面中没有的数值。

## 示例

用户：正方体 ABCD-A1B1C1D1 棱长为 2，求直线 AC1 与平面 BDD1B1 所成角的正弦值。
输出：{{"shape_type": "cube", "query_type": "line_plane_angle", "parameters": {{"edge": 2}}}}

用户：一个边长为3的正方体，求体对角线AC1与对角面BDD1B1的夹角正弦
输出：{{"shape_type": "cube", "query_type": "line_plane_angle", "parameters": {{"edge": 3}}}}"""


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------

_JSON_MARKER_START = "```json"
_JSON_MARKER_END = "```"


def _call_llm(system_prompt: str, user_message: str, config: LLMConfig) -> str:
    """调用 OpenAI 兼容的 /v1/chat/completions，返回响应文本。"""
    url = config.base_url.rstrip("/") + "/v1/chat/completions"

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Calling LLM: model=%s url=%s", config.model, url)

    with httpx.Client(timeout=config.timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    logger.info("LLM response: %s", content[:200])
    return content.strip()


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
    config = LLMConfig.from_env()

    if not config.is_configured:
        raise LLMNotConfiguredError("LLM_API_KEY 未设置，跳过 LLM 解析")

    system_prompt = _build_system_prompt()
    raw = _call_llm(system_prompt, problem_text, config)
    return _parse_response(raw)
