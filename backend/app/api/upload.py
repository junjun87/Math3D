import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from pydantic import BaseModel
import aiofiles
import os

from app.config import get_settings
from app.database import get_db
from app.models import Problem
from app.utils.image_utils import create_thumbnail, compress_image

router = APIRouter()
settings = get_settings()


class TextInputRequest(BaseModel):
    text: str


# ========== 图片上传 ==========

@router.post("/problems/upload", response_model=dict)
async def upload_problem_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传试题图片，返回 problem_id 和任务状态。"""
    # 验证文件类型
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(400, f"File too large: {file_size_mb:.1f}MB > {settings.MAX_UPLOAD_SIZE_MB}MB")

    # 保存文件
    ext = Path(file.filename).suffix or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(contents)
        await f.flush()

    # 创建缩略图（失败不影响上传流程）
    thumb_filename = f"thumb_{filename}"
    thumb_path = os.path.join(settings.UPLOAD_DIR, thumb_filename)
    thumb_ok = await create_thumbnail(filepath, thumb_path)

    # 创建数据库记录
    problem = Problem(
        image_url=f"/static/uploads/{filename}",
        image_thumbnail_url=f"/static/uploads/{thumb_filename}",
        status="uploaded",
    )
    db.add(problem)
    await db.flush()

    # 触发 OCR 异步任务
    from app.tasks import ocr_recognize
    ocr_recognize.delay(str(problem.id))

    return {
        "problem_id": str(problem.id),
        "status": problem.status,
        "image_url": problem.image_url,
        "thumbnail_url": problem.image_thumbnail_url,
    }


# ========== 文字输入 ==========

@router.post("/problems/text", response_model=dict)
async def submit_text_problem(
    data: TextInputRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    提交文字题目（无需拍照）。
    直接创建 Problem 记录并触发 LLM 结构化 → 计算 → 课件链。
    """
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Text content is required")
    if len(text) > 2000:
        raise HTTPException(400, "Text too long (max 2000 characters)")

    # 创建数据库记录（无图片）
    problem = Problem(
        image_url="",  # 文字输入无图片
        ocr_raw_text=text,
        status="ocr_done",  # 跳过 OCR
    )
    db.add(problem)
    await db.flush()

    # 触发求解链（跳过 OCR，直接从 LLM 结构化开始）
    from app.tasks import solve_and_render
    solve_and_render.delay(str(problem.id))

    return {
        "problem_id": str(problem.id),
        "status": "computing",
        "message": "Text problem submitted. Computation started.",
    }
