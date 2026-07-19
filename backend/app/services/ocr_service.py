"""阿里云 OCR 题目识别服务。"""

import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """题目识别失败。"""


async def recognize_text(image_path: str) -> dict:
    """识别图片中的题目文字（阿里云 OCR）。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))

    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials not configured")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as error:
        raise OCRServiceError(f"Failed to read image: {error}") from error

    ocr_bytes = _preprocess_for_ocr(image_bytes)
    try:
        return _call_aliyun_edu_ocr(ocr_bytes)
    except Exception as edu_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", edu_error)
        try:
            return _call_aliyun_general_ocr(ocr_bytes)
        except Exception as gen_error:
            raise OCRServiceError("All OCR methods failed") from gen_error


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

    raw_text = _clean_ocr_text(raw_text)
    confidence = sum(b["confidence"] for b in text_blocks) / len(text_blocks) if text_blocks else 0.99
    logger.info("Edu OCR: %d blocks, conf=%.3f, text=%s", len(text_blocks), confidence, raw_text[:200])
    return {"raw_text": raw_text, "text_blocks": text_blocks, "confidence": round(confidence, 4)}


def _clean_ocr_text(text: str) -> str:
    """清理 OCR 文本杂质：公式内多余空格、分离的 LaTeX 块合并。"""
    import re

    # 1. 修复公式块内多余空格：$$a b c$$ → $$abc$$（但保留中文和标点前后的空格）
    def _fix_formula_spaces(m):
        content = m.group(1)
        # 去掉操作符周围的空格：A B C → ABC，但保留语义空格
        content = re.sub(r'(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9_{}\\])', '', content)
        content = re.sub(r'(?<=[A-Za-z0-9_{}])\s+(?=[+\-=×÷<>])', '', content)
        content = re.sub(r'(?<=[+\-=×÷<>])\s+(?=[A-Za-z0-9])', '', content)
        return f'$${content}$$'

    text = re.sub(r'\$\$(.+?)\$\$', _fix_formula_spaces, text)

    # 2. 合并相邻的 $$...$$ 块：$$A$$$$B$$ → $$AB$$
    text = re.sub(r'\$\$\s*\$\$', '', text)

    # 3. 修复常见 OCR 错误
    text = text.replace('$$$', '$$')  # 三个 $ → 两个 $

    return text


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
