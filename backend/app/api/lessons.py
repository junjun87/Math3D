import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles
import os

from app.database import get_db
from app.models import Lesson, Problem

router = APIRouter()


@router.get("/problems/{problem_id}/lesson")
async def get_problem_lesson(
    problem_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取题目对应的课件元数据（轮询此接口直到 status 为 done）。"""
    result = await db.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(404, "Problem not found")

    lesson_result = await db.execute(
        select(Lesson).where(Lesson.problem_id == problem_id)
    )
    lesson = lesson_result.scalar_one_or_none()

    return {
        "problem_id": str(problem.id),
        "status": problem.status,
        "has_lesson": lesson is not None,
        "lesson": _lesson_to_dict(lesson) if lesson else None,
        "error_message": problem.error_message,
    }


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取课件详情和计算结果。"""
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    return _lesson_to_dict(lesson)


@router.get("/lessons/{lesson_id}/view", response_class=HTMLResponse)
async def view_lesson_html(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """直接查看课件 HTML 页面（iframe 模式）。"""
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    # 优先返回文件路径
    if lesson.html_file_path and os.path.exists(lesson.html_file_path):
        async with aiofiles.open(lesson.html_file_path, "r", encoding="utf-8") as f:
            html = await f.read()
        return HTMLResponse(content=html)

    # 否则返回数据库中的内容
    if lesson.html_content:
        return HTMLResponse(content=lesson.html_content)

    raise HTTPException(404, "Lesson HTML not available")


@router.get("/lessons/{lesson_id}/download")
async def download_lesson(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """下载课件 HTML 文件。"""
    from fastapi.responses import FileResponse

    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    if lesson.html_file_path and os.path.exists(lesson.html_file_path):
        return FileResponse(
            lesson.html_file_path,
            media_type="text/html",
            filename=f"lesson_{lesson.id}.html",
        )

    raise HTTPException(404, "Lesson file not available")


def _lesson_to_dict(lesson: Lesson) -> dict:
    return {
        "id": str(lesson.id),
        "problem_id": str(lesson.problem_id),
        "subject": lesson.subject,
        "kernel_result": lesson.kernel_result,
        "created_at": lesson.created_at.isoformat() if lesson.created_at else None,
    }
