"""
PaddleOCR 推理服务 — 独立 FastAPI 容器。

用于接收图片并返回 OCR 识别结果。
CPU 模式启动：uvicorn app.main:app --host 0.0.0.0 --port 8001
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

app = FastAPI(title="Math3D OCR Service", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

logger = logging.getLogger("ocr_service")
logging.basicConfig(level=logging.INFO)

# 延迟加载 PaddleOCR（减少内存占用）
_ocr_engine = None


def get_ocr_engine():
    """懒加载 PaddleOCR 引擎。"""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                use_gpu=False,
                show_log=False,
            )
            logger.info("PaddleOCR engine initialized (CPU mode)")
        except ImportError:
            logger.warning("PaddleOCR not installed, using mock mode")
            _ocr_engine = MockOCREngine()
    return _ocr_engine


class MockOCREngine:
    """PaddleOCR 的 mock 实现，用于开发和测试。"""
    def ocr(self, img_path, cls=True):
        return [[
            [
                [[0, 0], [100, 0], [100, 30], [0, 30]],
                ("[Mock OCR] 在正方体ABCD-A1B1C1D1中，棱长为2，求直线AB1与平面A1C1D的夹角", 0.95),
            ]
        ]]


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "PaddleOCR" if _ocr_engine and not isinstance(_ocr_engine, MockOCREngine) else "mock"}


@app.post("/ocr/recognize")
async def recognize_text(file: UploadFile = File(...)):
    """识别图片中的文字。"""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are supported")

    import tempfile
    import os

    # 保存临时文件
    contents = await file.read()
    suffix = ".jpg"
    if file.filename:
        suffix = os.path.splitext(file.filename)[1] or ".jpg"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        engine = get_ocr_engine()
        result = engine.ocr(tmp_path, cls=True)

        # 提取文本
        texts = []
        if result and result[0]:
            for line in result[0]:
                texts.append({
                    "text": line[1][0],
                    "confidence": float(line[1][1]),
                    "bbox": line[0],
                })

        raw_text = "\n".join(t["text"] for t in texts)
        avg_confidence = sum(t["confidence"] for t in texts) / len(texts) if texts else 0

        return {
            "raw_text": raw_text,
            "text_blocks": texts,
            "confidence": round(avg_confidence, 4),
        }

    finally:
        os.unlink(tmp_path)
