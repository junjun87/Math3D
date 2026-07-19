"""题目识别服务。优先 DeepSeek V4 视觉识图，失败回退阿里云 OCR。"""

import base64
import json
import logging
import os

import httpx
from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()

VISION_PROMPT = (
    "提取图中题目的完整文字，保留所有数学符号和公式。"
    "只输出题目原文，不要任何解释或额外文字。"
)


class OCRServiceError(RuntimeError):
    """题目识别失败。"""


async def recognize_text(image_path: str) -> dict:
    """识别图片中的题目文字。优先 LLM 视觉，失败回退阿里云 OCR。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as error:
        raise OCRServiceError(f"Failed to read image: {error}") from error

    # 1) 优先 DeepSeek V4 视觉识图（数学符号识别更准）
    if settings.LLM_API_KEY:
        try:
            return await _recognize_via_llm_vision(image_bytes, image_path)
        except Exception as vision_error:
            logger.warning("LLM Vision failed: %s; falling back to Alibaba OCR", vision_error)

    # 2) 回退阿里云 OCR
    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("No OCR method available: configure LLM_API_KEY or Alibaba Cloud credentials")

    ocr_bytes = _preprocess_for_ocr(image_bytes)
    try:
        return _call_aliyun_edu_ocr(ocr_bytes)
    except Exception as edu_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", edu_error)
        try:
            return _call_aliyun_general_ocr(ocr_bytes)
        except Exception as gen_error:
            raise OCRServiceError("All OCR methods failed") from gen_error


# ─── LLM 视觉识图 ───────────────────────────────────────────────

async def _recognize_via_llm_vision(image_bytes: bytes, image_path: str) -> dict:
    """DeepSeek V4 多模态识图：直接看图片提取题目文字。"""
    logger.info("Calling LLM Vision for image recognition")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    ext = os.path.splitext(image_path)[1].lower()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/jpeg")
    data_url = f"data:{media_type};base64,{b64}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 使用 OpenAI 兼容格式（DeepSeek vision 需要此格式而非 Anthropic image block）
        response = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "max_tokens": 512,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }],
            },
        )
        response.raise_for_status()
        data = response.json()

    raw_text = _extract_text_from_response(data)
    logger.info("LLM Vision result: %s", raw_text[:200])
    return {
        "raw_text": raw_text,
        "text_blocks": [{"text": raw_text, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }


def _extract_text_from_response(data: dict) -> str:
    """兼容 Anthropic / OpenAI / DeepSeek 多种响应格式。"""
    # Anthropic: content[0].text
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass
    # OpenAI: choices[0].message.content
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass
    # DeepSeek 兼容
    try:
        items = data.get("content", [])
        if items and isinstance(items[0], dict):
            if "text" in items[0]:
                return items[0]["text"]
    except (IndexError, TypeError):
        pass
    raise OCRServiceError(f"Unknown vision response: {json.dumps(data, ensure_ascii=False)[:300]}")


# ─── 阿里云 OCR（fallback）────────────────────────────────────

def _preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """OCR 预处理：自动对比度 + 锐化。"""
    from PIL import Image, ImageOps, ImageFilter
    import io as pil_io

    img = Image.open(pil_io.BytesIO(image_bytes))
    if img.mode != "L":
        img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.SHARPEN)
    buf = pil_io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    result = buf.getvalue()
    logger.info("OCR preprocess: L %dx%d -> %d bytes", img.size[0], img.size[1], len(result))
    return result


def _create_aliyun_client():
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    config = OcrConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
        read_timeout=30000,
        connect_timeout=10000,
    )
    return Client(config)


def _get_result_data(response) -> dict:
    raw = response.body.data
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise OCRServiceError(f"Unexpected response data type: {type(raw).__name__}")


def _call_aliyun_edu_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeEduQuestionOcr")
    request = RecognizeEduQuestionOcrRequest(body=image_bytes, need_rotate=True)
    runtime = RuntimeOptions()
    response = _create_aliyun_client().recognize_edu_question_ocr_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("content", "").strip()
    words_info = data.get("prism_wordsInfo", []) or []
    text_blocks = []
    for item in words_info:
        word = item.get("word", "").strip()
        if not word:
            continue
        prob = item.get("prob", 95)
        text_blocks.append({
            "text": word,
            "confidence": float(prob) / 100.0,
            "is_formula": item.get("recClassify", 0) == 51,
            "bbox": item.get("pos", []),
        })

    # 合并相邻同类块，避免公式被切成碎片（如 C_1 = 6 切成 $$C_1$$$$=$$$$6$$）
    merged = []
    for b in text_blocks:
        if merged and merged[-1]["is_formula"] == b["is_formula"]:
            merged[-1]["text"] += " " + b["text"]
        else:
            merged.append(dict(b))
    raw_text = "".join(
        f"$${b['text']}$$" if b["is_formula"] else b["text"]
        for b in merged
    ) if merged else content

    if not raw_text:
        raise OCRServiceError("Alibaba Edu OCR returned no text")

    confidence = sum(b["confidence"] for b in text_blocks) / len(text_blocks) if text_blocks else 0.99
    logger.info("Edu OCR: %d blocks, conf=%.3f, text=%s", len(text_blocks), confidence, raw_text[:200])
    return {"raw_text": raw_text, "text_blocks": text_blocks, "confidence": round(confidence, 4)}


def _call_aliyun_general_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeGeneral (fallback)")
    request = RecognizeGeneralRequest(body=image_bytes)
    runtime = RuntimeOptions()
    response = _create_aliyun_client().recognize_general_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("Content", "").strip()
    if not content:
        raise OCRServiceError("Alibaba General OCR returned no text")

    logger.info("General OCR: %s", content[:200])
    return {"raw_text": content, "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}], "confidence": 0.99}
