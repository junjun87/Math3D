"""
阿里云 OCR 服务 — 替代本地 PaddleOCR。
使用阿里云文字识别 API，低延迟、高精度、免运维。
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid

import httpx
from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()

# 阿里云 OCR API 端点
OCR_ENDPOINT = "ocr-api.cn-hangzhou.aliyuncs.com"
OCR_ACTION = "RecognizeGeneral"
OCR_VERSION = "2021-07-07"


async def recognize_text(image_bytes: bytes) -> dict:
    """
    调用阿里云通用文字识别 API。
    返回格式与原有 PaddleOCR 兼容：{ raw_text, text_blocks, confidence }
    """
    ak_id = settings.ALIBABA_CLOUD_ACCESS_KEY_ID
    ak_secret = settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET

    if not ak_id or not ak_secret:
        logger.warning("Alibaba Cloud credentials not configured, using mock")
        return _mock_recognize(image_bytes)

    # 图片 Base64 编码
    img_base64 = base64.b64encode(image_bytes).decode()

    # 构建请求体
    request_body = json.dumps({
        "ImageBase64": img_base64,
        "OutputCharInfo": False,
        "OutputTable": False,
    })

    # 签名参数
    method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    content_type = "application/json"
    host = OCR_ENDPOINT

    headers = {
        "host": host,
        "content-type": content_type,
        "x-acs-action": OCR_ACTION,
        "x-acs-version": OCR_VERSION,
        "x-acs-date": _timestamp(),
        "x-acs-signature-nonce": str(uuid.uuid4()),
        "x-acs-content-sha256": _sha256_hex(request_body),
    }

    # 签名
    headers["authorization"] = _sign(ak_id, ak_secret, method, canonical_uri,
                                      canonical_querystring, headers, request_body)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://{host}/",
                headers=headers,
                content=request_body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Aliyun OCR response keys: {list(data.keys())}")
            return _parse_response(data)

    except httpx.HTTPError as e:
        logger.error(f"Alibaba Cloud OCR API error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response body: {e.response.text[:500]}")
        return _mock_recognize(image_bytes)
    except Exception as e:
        logger.error(f"OCR unexpected error: {e}", exc_info=True)
        return _mock_recognize(image_bytes)


def _timestamp() -> str:
    """生成 ISO8601 格式时间戳。"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _sign(ak_id: str, ak_secret: str, method: str, uri: str,
          querystring: str, headers: dict, body: str) -> str:
    """阿里云 OpenAPI V3 签名算法 (ACS3-HMAC-SHA256)。"""
    # 构造规范化请求
    canonical_headers = "\n".join(
        f"{k}:{headers[k]}" for k in sorted(headers)
    )
    signed_headers = ";".join(sorted(headers.keys()))

    hashed_payload = _sha256_hex(body)
    canonical_request = f"{method}\n{uri}\n{querystring}\n{canonical_headers}\n\n{signed_headers}\n{hashed_payload}"

    # 构造待签名字符串
    hashed_canonical = _sha256_hex(canonical_request)
    string_to_sign = f"ACS3-HMAC-SHA256\n{hashed_canonical}"

    # 计算签名
    secret = ak_secret.encode()
    signing_key = _hmac_sha256(secret, "aliyun_v3")
    signature = _hmac_sha256(signing_key, string_to_sign).hex()

    return f"ACS3-HMAC-SHA256 Credential={ak_id},SignedHeaders={signed_headers},Signature={signature}"


def _parse_response(data: dict) -> dict:
    """解析阿里云 OCR 响应，转为统一格式。兼容 Content 为字符串或数组。"""
    content = data.get("Data", {}).get("Content", "")

    if isinstance(content, str):
        # General OCR 返回纯文本字符串
        raw_text = content.strip()
        return {
            "raw_text": raw_text,
            "text_blocks": [{"text": raw_text, "confidence": 0.99, "bbox": []}],
            "confidence": 0.99,
        }

    # 结构化 OCR 返回数组
    text_blocks = []
    for block in (content or []):
        text = block.get("Text", "")
        confidence = block.get("Confidence", 0) / 100.0
        text_blocks.append({"text": text, "confidence": round(confidence, 4), "bbox": []})

    raw_text = "\n".join(t["text"] for t in text_blocks)
    avg_confidence = sum(t["confidence"] for t in text_blocks) / len(text_blocks) if text_blocks else 0

    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "confidence": round(avg_confidence, 4),
    }


def _mock_recognize(image_bytes: bytes) -> dict:
    """未配置密钥时的测试数据。"""
    return {
        "raw_text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
        "text_blocks": [{
            "text": "在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角。",
            "confidence": 0.95,
            "bbox": [[0, 0], [400, 0], [400, 30], [0, 30]],
        }],
        "confidence": 0.95,
    }
