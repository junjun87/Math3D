"""阿里云 OCR 服务。调用阿里云 2021-07-07 OCR API。"""

import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """云端 OCR 服务未能返回可用识别结果。"""


async def recognize_text(image_path: str) -> dict:
    """调用阿里云 OCR；二进制 body 直传，带图像预处理提升准确率。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))

    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials are not configured")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as error:
        raise OCRServiceError(f"Failed to read image: {error}") from error

    # OCR 预处理：灰度化 + 对比度增强 + 锐化，提升数学符号识别率
    image_bytes = _preprocess_for_ocr(image_bytes)

    try:
        return _call_aliyun_edu_ocr(image_bytes)
    except Exception as education_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", education_error)
        try:
            return _call_aliyun_general_ocr(image_bytes)
        except Exception as general_error:
            raise OCRServiceError("Alibaba Cloud OCR failed") from general_error


def _preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """OCR 预处理：灰度化、增强对比度、锐化，输出高质量 JPEG。"""
    from PIL import Image, ImageEnhance, ImageFilter
    import io as pil_io

    img = Image.open(pil_io.BytesIO(image_bytes))
    img = img.convert("L")  # 灰度化
    # 增强对比度 1.5x
    img = ImageEnhance.Contrast(img).enhance(1.5)
    # 锐化
    img = img.filter(ImageFilter.SHARPEN)
    buf = pil_io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    result = buf.getvalue()
    logger.info("OCR preprocess: %s %dx%d -> %d bytes grayscale", img.mode, img.size[0], img.size[1], len(result))
    return result


def _create_client():
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
    """从 SDK 响应中提取 Data 字段。response.body.data 是 JSON 字符串。"""
    raw = response.body.data
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise OCRServiceError(f"Unexpected response data type: {type(raw).__name__}")


def _call_aliyun_edu_ocr(image_bytes: bytes) -> dict:
    """教育题目 OCR（RecognizeEduQuestionOcr）。二进制 body + 自动旋转。"""
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeEduQuestionOcr")
    request = RecognizeEduQuestionOcrRequest(
        body=image_bytes,
        need_rotate=True,
    )
    runtime = RuntimeOptions()
    response = _create_client().recognize_edu_question_ocr_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("content", "").strip()
    words_info = data.get("prism_wordsInfo", []) or []
    text_blocks = []

    for item in words_info:
        word = item.get("word", "").strip()
        if not word:
            continue
        probability = item.get("prob", 95)
        text_blocks.append({
            "text": word,
            "confidence": float(probability) / 100.0,
            "is_formula": item.get("recClassify", 0) == 51,
            "bbox": item.get("pos", []),
        })

    if text_blocks:
        raw_text = "".join(
            f"$${block['text']}$$" if block["is_formula"] else block["text"]
            for block in text_blocks
        )
    else:
        raw_text = content

    if not raw_text:
        raise OCRServiceError("Alibaba Edu OCR returned no text")

    confidence = (
        sum(block["confidence"] for block in text_blocks) / len(text_blocks)
        if text_blocks else 0.99
    )
    logger.info("Edu OCR: %d blocks, conf=%.3f, text=%s", len(text_blocks), confidence, raw_text[:200])
    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "confidence": round(confidence, 4),
    }


def _call_aliyun_general_ocr(image_bytes: bytes) -> dict:
    """通用 OCR（RecognizeGeneral）。二进制 body 回退。"""
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeGeneral (fallback)")
    request = RecognizeGeneralRequest(body=image_bytes)
    runtime = RuntimeOptions()
    response = _create_client().recognize_general_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("Content", "").strip()
    if not content:
        raise OCRServiceError("Alibaba General OCR returned no text")

    logger.info("General OCR: %s", content[:200])
    return {
        "raw_text": content,
        "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }
