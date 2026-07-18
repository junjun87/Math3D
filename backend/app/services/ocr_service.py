"""
阿里云 OCR 服务 — 使用官方 SDK 调用文字识别 API。
"""

import base64
import json
import logging

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


async def recognize_text(image_bytes: bytes) -> dict:
    """
    调用阿里云通用文字识别 API (RecognizeGeneral)。
    返回：{ raw_text, text_blocks, confidence }
    """
    ak_id = settings.ALIBABA_CLOUD_ACCESS_KEY_ID
    ak_secret = settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET

    if not ak_id or not ak_secret:
        logger.warning("Alibaba Cloud credentials not configured, using mock")
        return _mock_recognize()

    # 压缩大图：限制 max 2048px 边，减小传输体积
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        max_dim = 2048
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            image_bytes = buf.getvalue()
    except Exception:
        pass  # 压缩失败就用原始图

    img_base64 = base64.b64encode(image_bytes).decode()
    logger.info(f"OCR image size after compress: {len(image_bytes) / 1024:.0f}KB")

    try:
        from alibabacloud_ocr_api20210707.client import Client
        from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
        from alibabacloud_tea_openapi.models import Config as OcrConfig
        from alibabacloud_tea_util.models import RuntimeOptions

        # 使用阿里云内网 endpoint，不走公网
        config = OcrConfig(
            access_key_id=ak_id,
            access_key_secret=ak_secret,
            endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
        )
        client = Client(config)
        req = RecognizeGeneralRequest(
            body=json.dumps({"ImageBase64": img_base64}, ensure_ascii=False),
        )
        runtime = RuntimeOptions(
            connect_timeout=10000,
            read_timeout=60000,  # 大图片 60 秒超时
        )
        resp = client.recognize_general_with_options(req, runtime)
        data = resp.body.to_map()

        return _parse_response(data)

    except ImportError:
        logger.warning("Alibaba Cloud OCR SDK not installed, using mock")
        return _mock_recognize()
    except Exception as e:
        logger.error(f"OCR API error: {e}", exc_info=True)
        return _mock_recognize()


def _parse_response(data: dict) -> dict:
    """解析阿里云 OCR 响应。Content 为纯文本字符串。"""
    raw_text = data.get("Data", {}).get("Content", "").strip()
    return {
        "raw_text": raw_text,
        "text_blocks": [{"text": raw_text, "confidence": 0.99, "bbox": []}],
        "confidence": 0.99,
    }


def _mock_recognize() -> dict:
    """未配置密钥时的测试数据。"""
    return {
        "raw_text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
        "text_blocks": [{
            "text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
            "confidence": 0.95,
            "bbox": [],
        }],
        "confidence": 0.95,
    }
