import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Problem, Lesson

router = APIRouter()


@router.get("/problems/{problem_id}")
async def get_problem(
    problem_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取题目详情和状态。"""
    result = await db.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(404, "Problem not found")

    return _problem_to_dict(problem)


@router.get("/problems/{problem_id}/ocr")
async def get_ocr_result(
    problem_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取 OCR 识别结果（轮询此接口直到 status 为 ocr_done 或 error）。"""
    result = await db.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(404, "Problem not found")

    return {
        "problem_id": str(problem.id),
        "status": problem.status,
        "ocr_raw_text": problem.ocr_raw_text,
        "ocr_confidence": problem.ocr_confidence,
        "ocr_blocks": (problem.ocr_result or {}).get("blocks", []),
        "ocr_source": (problem.ocr_result or {}).get("source"),
        "ocr_review_required": (problem.ocr_result or {}).get("review_required", False),
        "error_message": problem.error_message,
    }


@router.post("/problems/{problem_id}/confirm")
async def confirm_problem(
    problem_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """用户确认或修正 OCR 识别结果，触发计算。"""
    result = await db.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(404, "Problem not found")

    # 用户可修正 OCR 文本
    if "corrected_text" in data and data["corrected_text"]:
        problem.ocr_raw_text = data["corrected_text"]

    problem.status = "confirmed"
    await db.flush()

    # 触发后续计算任务
    from app.tasks import solve_and_render
    solve_and_render.delay(str(problem.id))

    return {
        "problem_id": str(problem.id),
        "status": problem.status,
        "message": "Confirmed. Computation started."
    }


@router.get("/history")
async def get_history(
    user_id: uuid.UUID = None,
    status: str = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取历史记录列表。"""
    query = select(Problem).order_by(desc(Problem.created_at))

    if user_id:
        query = query.where(Problem.user_id == user_id)
    if status:
        query = query.where(Problem.status == status)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    problems = result.scalars().all()

    return {
        "items": [_problem_to_dict(p) for p in problems],
        "total": len(problems),
        "limit": limit,
        "offset": offset,
    }


def _problem_to_dict(p: Problem) -> dict:
    return {
        "id": str(p.id),
        "user_id": str(p.user_id) if p.user_id else None,
        "image_url": p.image_url,
        "thumbnail_url": p.image_thumbnail_url,
        "status": p.status,
        "subject": p.structured_json.get("subject") if p.structured_json else None,
        "ocr_summary": (p.ocr_raw_text[:200] + "...") if p.ocr_raw_text and len(p.ocr_raw_text) > 200 else p.ocr_raw_text,
        "error_message": p.error_message,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
