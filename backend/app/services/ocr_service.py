"""阿里云 OCR 服务。通过图片 URL 调用（阿里云推荐方式，响应更快且自动增强图片）。"""

import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """云端 OCR 服务未能返回可用识别结果。"""


async def recognize_text(image_path: str) -> dict:
    """调用阿里云 OCR；通过 URL 方式传图。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))

    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials are not configured")

    filename = os.path.basename(image_path)
    image_url = f"{settings.SERVER_HOST}/static/uploads/{filename}"
    logger.info("OCR using URL: %s", image_url)

    try:
        return _call_aliyun_edu_ocr(image_url)
    except Exception as education_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", education_error)
        try:
            return _call_aliyun_general_ocr(image_url)
        except Exception as general_error:
            raise OCRServiceError("Alibaba Cloud OCR failed") from general_error


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


def _parse_data_field(raw_response: dict) -> dict:
    """SDK 返回的 Data 字段可能是 JSON 字符串，需要解析。"""
    data = raw_response.get("Data", {})
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise OCRServiceError(f"Alibaba OCR response Data is not dict: {type(data).__name__}")
    return data


def _call_aliyun_edu_ocr(image_url: str) -> dict:
    """调用教育题目 OCR，通过 URL 传图（阿里云推荐）。"""
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest

    logger.info("Calling Alibaba RecognizeEduQuestionOcr via URL")
    request = RecognizeEduQuestionOcrRequest(
        url=image_url,
        need_rotate=True,
    )
    response = _create_aliyun_client().recognize_edu_question_ocr(request)
    response_data = _parse_data_field(response.body.to_map())

    content = response_data.get("content", "").strip()
    words_info = response_data.get("prism_wordsInfo", []) or []
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
    logger.info("Alibaba Edu OCR: %d blocks, conf=%.3f, text=%s", len(text_blocks), confidence, raw_text[:120])
    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "confidence": round(confidence, 4),
    }


def _call_aliyun_general_ocr(image_url: str) -> dict:
    """教育题目 OCR 无法识别时，使用阿里云通用 OCR 作为云端回退。通过 URL 传图。"""
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest

    logger.info("Calling Alibaba RecognizeGeneral via URL")
    request = RecognizeGeneralRequest(
        url=image_url,
    )
    response = _create_aliyun_client().recognize_general(request)
    response_data = _parse_data_field(response.body.to_map())

    content = response_data.get("Content", "").strip()
    if not content:
        raise OCRServiceError("Alibaba General OCR returned no text")

    logger.info("Alibaba General OCR: %s", content[:120])
    return {
        "raw_text": content,
        "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }
