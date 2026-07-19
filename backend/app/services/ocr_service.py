"""阿里云 OCR 服务。图片以 Base64 直传，不依赖本地 OCR 模型。"""

import base64
import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """云端 OCR 服务未能返回可用识别结果。"""


async def recognize_text(image_path: str) -> dict:
    """调用阿里云 OCR；本地服务器只负责读取和编码图片。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))
    try:
        with open(image_path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
    except OSError as error:
        raise OCRServiceError(f"Failed to read/encode image: {error}") from error

    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials are not configured")

    try:
        return _call_aliyun_edu_ocr(image_base64)
    except Exception as education_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", education_error)
        try:
            return _call_aliyun_general_ocr(image_base64)
        except Exception as general_error:
            raise OCRServiceError("Alibaba Cloud OCR failed") from general_error


def _create_aliyun_client():
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    config = OcrConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
    )
    return Client(config)


def _call_aliyun_edu_ocr(image_base64: str) -> dict:
    """调用教育题目 OCR，优先保留公式识别信息。"""
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest

    logger.info("Calling Alibaba RecognizeEduQuestionOcr")
    request = RecognizeEduQuestionOcrRequest(
        body=json.dumps({"ImageData": image_base64}),
    )
    response = _create_aliyun_client().recognize_edu_question_ocr(request)
    return _parse_aliyun_edu_response(response.body.to_map())


def _parse_aliyun_edu_response(data: dict) -> dict:
    """将阿里云教育题目 OCR 的响应转换为应用统一格式。"""
    response_data = data.get("Data", {})
    if not isinstance(response_data, dict):
        raise OCRServiceError("Alibaba Edu OCR response has invalid Data")

    content = (response_data.get("content") or response_data.get("Content") or "").strip()
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
    logger.info("Alibaba Edu OCR: %d blocks, conf=%.3f", len(text_blocks), confidence)
    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "confidence": round(confidence, 4),
    }


def _call_aliyun_general_ocr(image_base64: str) -> dict:
    """教育题目 OCR 无法识别时，使用阿里云通用 OCR 作为云端回退。"""
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest

    logger.info("Calling Alibaba RecognizeGeneral")
    request = RecognizeGeneralRequest(
        body=json.dumps({"ImageData": image_base64}),
    )
    response = _create_aliyun_client().recognize_general(request)
    response_data = response.body.to_map().get("Data", {})
    content = (response_data.get("Content") or response_data.get("content") or "").strip()
    if not content:
        raise OCRServiceError("Alibaba General OCR returned no text")

    logger.info("Alibaba General OCR: %s", content[:120])
    return {
        "raw_text": content,
        "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }
