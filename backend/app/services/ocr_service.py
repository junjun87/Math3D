"""Alibaba Cloud OCR integration with layout-aware math review metadata."""

from __future__ import annotations

import io
import json
import logging
import os
from statistics import median

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """Raised when all configured OCR calls fail."""


async def recognize_text(image_path: str) -> dict:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials not configured")

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    ocr_bytes = _preprocess_for_ocr(image_bytes)
    try:
        return _call_aliyun_edu_ocr(ocr_bytes)
    except Exception as edu_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", edu_error)
        try:
            return _call_aliyun_general_ocr(ocr_bytes)
        except Exception as general_error:
            raise OCRServiceError("All OCR methods failed") from general_error


def _preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """Normalize orientation and contrast without a lossy JPEG re-encode."""
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("L")
    image = ImageOps.autocontrast(image, cutoff=0)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


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


def _bbox_rect(pos: object) -> list[float] | None:
    """Return [left, top, right, bottom] from Alibaba's polygon coordinates."""
    if not isinstance(pos, list) or not pos:
        return None

    points: list[tuple[float, float]] = []
    if all(isinstance(point, dict) for point in pos):
        for point in pos:
            if "x" in point and "y" in point:
                points.append((float(point["x"]), float(point["y"])))
    elif len(pos) >= 4 and all(isinstance(value, (int, float)) for value in pos):
        points = [(float(pos[index]), float(pos[index + 1])) for index in range(0, len(pos) - 1, 2)]

    if not points:
        return None
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def _add_risk_flags(text: str, confidence: float, is_formula: bool) -> list[str]:
    flags: list[str] = []
    if confidence < 0.93:
        flags.append("low_confidence")
    if chr(0xFFFD) in text or "?" in text:
        flags.append("unrecognized_character")
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        flags.append("unbalanced_brackets")
    if is_formula and (text.count("{") != text.count("}") or text.count("$") % 2):
        flags.append("invalid_formula_delimiter")
    return flags


def _order_blocks(blocks: list[dict]) -> list[dict]:
    """Sort OCR blocks into reading order and assign a stable line number."""
    positioned = [block for block in blocks if block["bbox_rect"]]
    unpositioned = [block for block in blocks if not block["bbox_rect"]]
    if not positioned:
        for index, block in enumerate(blocks):
            block["line"] = index
        return blocks

    heights = [block["bbox_rect"][3] - block["bbox_rect"][1] for block in positioned]
    line_tolerance = max(8.0, median(heights) * 0.6)
    positioned.sort(key=lambda block: (block["bbox_rect"][1] + block["bbox_rect"][3]) / 2)

    lines: list[list[dict]] = []
    line_centers: list[float] = []
    for block in positioned:
        center_y = (block["bbox_rect"][1] + block["bbox_rect"][3]) / 2
        if lines and abs(center_y - line_centers[-1]) <= line_tolerance:
            lines[-1].append(block)
            line_centers[-1] = sum(
                (item["bbox_rect"][1] + item["bbox_rect"][3]) / 2 for item in lines[-1]
            ) / len(lines[-1])
        else:
            lines.append([block])
            line_centers.append(center_y)

    ordered: list[dict] = []
    for line_number, line in enumerate(lines):
        line.sort(key=lambda block: block["bbox_rect"][0])
        for block in line:
            block["line"] = line_number
            ordered.append(block)
    for block in unpositioned:
        block["line"] = len(lines)
        ordered.append(block)
    return ordered


def _build_raw_text(blocks: list[dict]) -> str:
    lines: dict[int, list[dict]] = {}
    for block in blocks:
        lines.setdefault(block["line"], []).append(block)

    output_lines = []
    for line_number in sorted(lines):
        parts = []
        formula_parts = []
        for block in lines[line_number]:
            text = block["text"].strip()
            if not text:
                continue
            if block["is_formula"]:
                formula_parts.append(text)
                continue
            if formula_parts:
                parts.append(f"$${''.join(formula_parts)}$$")
                formula_parts = []
            parts.append(text)
        if formula_parts:
            parts.append(f"$${''.join(formula_parts)}$$")
        if parts:
            output_lines.append(" ".join(parts))
    return "\n".join(output_lines).replace("$$$", "$$").strip()


def _build_blocks(words_info: list[dict]) -> list[dict]:
    blocks = []
    for item in words_info:
        text = str(item.get("word", "")).strip()
        if not text:
            continue
        confidence = float(item.get("prob", 95)) / 100.0
        is_formula = str(item.get("recClassify", 0)) == "51"
        blocks.append({
            "text": text,
            "confidence": round(confidence, 4),
            "is_formula": is_formula,
            "bbox": item.get("pos", []),
            "bbox_rect": _bbox_rect(item.get("pos", [])),
            "risk_flags": _add_risk_flags(text, confidence, is_formula),
        })
    return _order_blocks(blocks)


def _result_from_blocks(blocks: list[dict], fallback_text: str, source: str) -> dict:
    raw_text = _build_raw_text(blocks) or fallback_text.strip()
    if not raw_text:
        raise OCRServiceError("Alibaba OCR returned no text")
    weighted = sum(block["confidence"] * max(len(block["text"]), 1) for block in blocks)
    weight = sum(max(len(block["text"]), 1) for block in blocks)
    confidence = weighted / weight if weight else 0.0
    review_required = any(block["risk_flags"] for block in blocks)
    return {
        "raw_text": raw_text,
        "text_blocks": blocks,
        "confidence": round(confidence, 4),
        "source": source,
        "review_required": review_required,
    }


def _call_aliyun_edu_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    request = RecognizeEduQuestionOcrRequest(body=image_bytes, need_rotate=True)
    response = _create_aliyun_client().recognize_edu_question_ocr_with_options(request, RuntimeOptions())
    data = _get_result_data(response)
    return _result_from_blocks(
        _build_blocks(data.get("prism_wordsInfo", []) or []),
        data.get("content", ""),
        "aliyun_edu_question",
    )


def _call_aliyun_general_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    request = RecognizeGeneralRequest(body=image_bytes)
    response = _create_aliyun_client().recognize_general_with_options(request, RuntimeOptions())
    data = _get_result_data(response)
    content = data.get("Content", "").strip()
    return _result_from_blocks([
        {
            "text": content,
            "confidence": 0.99,
            "is_formula": False,
            "bbox": [],
            "bbox_rect": None,
            "risk_flags": [],
            "line": 0,
        }
    ] if content else [], content, "aliyun_general")
