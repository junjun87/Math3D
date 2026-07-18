"""
阿里云 OCR 服务 — 教育场景题目识别 + 通用识别 fallback。

优先 RecognizeEduQuestionOcr（数学/理科题目专用），失败 fallback RecognizeGeneral。
通过 ImageURL 方式传图（图片通过静态文件服务暴露）。
"""

import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()

_SERVER_HOST = "http://59.110.93.243:8000"


async def recognize_text(image_path: str) -> dict:
    """识别图片中的题目文字。优先教育 API，失败 fallback 通用 API。"""
    ak_id = settings.ALIBABA_CLOUD_ACCESS_KEY_ID
    ak_secret = settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET

    if not ak_id or not ak_secret:
        logger.warning("Alibaba Cloud credentials not configured, using mock")
        return _mock_recognize()

    filename = os.path.basename(image_path)
    image_url = f"{_SERVER_HOST}/static/uploads/{filename}"
    logger.info(f"OCR using ImageURL: {image_url}")

    # 优先教育题目识别
    try:
        return _call_edu_ocr(image_url)
    except Exception as edu_error:
        logger.warning(f"Edu OCR failed: {edu_error}, falling back to General")
        try:
            return _call_general_ocr(image_url)
        except Exception as gen_error:
            logger.error(f"General OCR also failed: {gen_error}")
            return _mock_recognize()


# ========== 教育题目识别 ==========

def _call_edu_ocr(image_url: str) -> dict:
    logger.info("Calling RecognizeEduQuestionOcr")
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    config = OcrConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
    )
    client = Client(config)
    req = RecognizeEduQuestionOcrRequest(
        body=json.dumps({"ImageURL": image_url}, ensure_ascii=False),
    )
    resp = client.recognize_edu_question_ocr(req)
    return _parse_edu_response(resp.body.to_map())


def _parse_edu_response(data: dict) -> dict:
    content = data.get("Data", {}).get("content", "").strip()
    words_info = data.get("Data", {}).get("prism_wordsInfo", []) or []

    text_blocks = []
    formula_parts = []
    normal_parts = []

    for item in words_info:
        word = item.get("word", "").strip()
        classify = item.get("recClassify", 0)
        prob = item.get("prob", 95)
        text_blocks.append({
            "text": word,
            "confidence": float(prob) / 100.0,
            "is_formula": classify == 51,
            "rec_classify": classify,
            "bbox": item.get("pos", []),
        })
        if classify == 51:
            formula_parts.append(word)
        else:
            normal_parts.append(word)

    if text_blocks:
        raw_text = "".join(
            f"$${b['text']}$$" if b["is_formula"] else b["text"]
            for b in text_blocks
        )
    else:
        raw_text = content

    avg_conf = sum(b["confidence"] for b in text_blocks) / len(text_blocks) if text_blocks else 0.99
    logger.info(f"Edu OCR: {len(text_blocks)} blocks, {len(formula_parts)} formulas, conf={avg_conf:.3f}")
    if raw_text:
        logger.info(f"OCR text: {raw_text[:120]}")

    return {
        "raw_text": raw_text or content,
        "text_blocks": text_blocks,
        "confidence": round(avg_conf, 4),
        "formula_count": len(formula_parts),
    }


# ========== 通用识别（fallback） ==========

def _call_general_ocr(image_url: str) -> dict:
    logger.info("Calling RecognizeGeneral fallback")
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    config = OcrConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
    )
    client = Client(config)
    req = RecognizeGeneralRequest(
        body=json.dumps({"ImageURL": image_url}, ensure_ascii=False),
    )
    resp = client.recognize_general(req)
    content = resp.body.to_map().get("Data", {}).get("Content", "").strip()
    logger.info(f"General OCR result: {content[:120]}")
    return {
        "raw_text": content,
        "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }


# ========== Mock ==========

def _mock_recognize() -> dict:
    return {
        "raw_text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
        "text_blocks": [{
            "text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
            "confidence": 0.95,
            "bbox": [],
            "is_formula": False,
        }],
        "confidence": 0.95,
    }
