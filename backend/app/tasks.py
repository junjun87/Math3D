from __future__ import annotations

"""
Math3D 异步任务模块。

使用 Celery + Redis 处理：
1. OCR 文字识别
2. LLM 题目结构化
3. SymPy 计算
4. 课件 HTML 渲染

任务链: ocr_recognize → (用户确认) → llm_structure → sympy_compute → render_lesson
"""

import asyncio
import logging
import os
import uuid

import httpx
from celery import Celery
from celery import chain

from app.config import get_settings
from app.database import get_sync_db

logger = logging.getLogger("math3d.tasks")
settings = get_settings()

celery_app = Celery(
    "math3d",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_max_tasks_per_child=50,
)


# ========== OCR 识别任务 ==========

@celery_app.task(bind=True, name="ocr_recognize")
def ocr_recognize(self, problem_id: str) -> dict:
    """
    OCR 识别任务：优先 DeepSeek V4 视觉识图，失败回退阿里云 OCR。
    更新 Problem.ocr_raw_text 和 status。
    """
    from app.models import Problem

    logger.info(f"OCR task started for problem {problem_id}")

    with get_sync_db() as db:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if not problem:
            logger.error(f"Problem {problem_id} not found")
            return {"problem_id": problem_id, "status": "error", "error": "Problem not found"}

        try:
            # 读取上传的图片文件
            image_path = problem.image_url
            if image_path.startswith("/static/uploads/"):
                image_path = os.path.join(settings.UPLOAD_DIR, os.path.basename(image_path))

            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")

            # 识别题目文字（LLM 视觉优先，阿里云 OCR 回退）
            from app.services.ocr_service import recognize_text
            ocr_data = asyncio.run(recognize_text(image_path))
            raw_text = ocr_data.get("raw_text", "")
            confidence = ocr_data.get("confidence", 0.0)

            # 更新数据库
            problem.ocr_raw_text = raw_text
            problem.ocr_confidence = confidence
            problem.ocr_result = {
                "blocks": ocr_data.get("text_blocks", []),
                "source": ocr_data.get("source", "unknown"),
                "review_required": ocr_data.get("review_required", False),
            }
            problem.status = "ocr_done"

            logger.info(f"OCR done for problem {problem_id}: confidence={confidence:.3f}, "
                        f"text_preview={raw_text[:80]}")

            return {
                "problem_id": problem_id,
                "status": "ocr_done",
                "ocr_raw_text": raw_text,
                "ocr_confidence": confidence,
                "ocr_result": problem.ocr_result,
            }

        except FileNotFoundError as e:
            logger.error(f"OCR file error for problem {problem_id}: {e}")
            problem.status = "error"
            problem.error_message = str(e)
            return {"problem_id": problem_id, "status": "error", "error": str(e)}

        except Exception as e:
            logger.error(f"OCR failed for problem {problem_id}: {e}")
            problem.status = "error"
            problem.error_message = f"OCR error: {str(e)}"
            return {"problem_id": problem_id, "status": "error", "error": str(e)}


# ========== LLM 结构化任务 ==========

@celery_app.task(bind=True, name="llm_structure")
def llm_structure(self, problem_id: str) -> dict:
    """
    LLM 题目结构化任务：将 OCR 文本转换为结构化 JSON。
    更新 Problem.structured_json 和 status。
    """
    from app.models import Problem
    from app.services.llm_service import structure_problem

    logger.info(f"LLM structure task started for problem {problem_id}")

    with get_sync_db() as db:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if not problem:
            logger.error(f"Problem {problem_id} not found")
            return {"problem_id": problem_id, "status": "error", "error": "Problem not found"}

        if not problem.ocr_raw_text:
            logger.error(f"Problem {problem_id} has no OCR text")
            problem.status = "error"
            problem.error_message = "No OCR text to structure"
            return {"problem_id": problem_id, "status": "error", "error": "No OCR text"}

        try:
            # 调用 LLM 结构化（异步函数，用 asyncio.run 包装）
            structured = asyncio.run(structure_problem(problem.ocr_raw_text))

            if structured.get("subject") == "unknown":
                raise ValueError("LLM could not determine subject type")

            # 更新数据库
            problem.structured_json = structured
            problem.status = "computing"

            logger.info(f"LLM structure done for problem {problem_id}: "
                        f"{structured.get('body_type')}/{structured.get('target', {}).get('type')}")

            return {
                "problem_id": problem_id,
                "status": "computing",
                "structured_json": structured,
            }

        except Exception as e:
            logger.error(f"LLM structure failed for problem {problem_id}: {e}")
            problem.status = "error"
            problem.error_message = f"LLM error: {str(e)}"
            return {"problem_id": problem_id, "status": "error", "error": str(e)}


# ========== SymPy 计算任务 ==========

@celery_app.task(bind=True, name="sympy_compute")
def sympy_compute(self, problem_id: str) -> dict:
    """
    SymPy 计算任务：根据学科路由到对应计算内核。
    创建 Lesson 记录，写入 kernel_result。
    """
    from app.models import Problem, Lesson

    logger.info(f"SymPy compute task started for problem {problem_id}")

    with get_sync_db() as db:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if not problem:
            logger.error(f"Problem {problem_id} not found")
            return {"problem_id": problem_id, "status": "error", "error": "Problem not found"}

        if not problem.structured_json:
            logger.error(f"Problem {problem_id} has no structured_json")
            problem.status = "error"
            problem.error_message = "No structured problem data to compute"
            return {"problem_id": problem_id, "status": "error", "error": "No structured data"}

        try:
            subject = problem.structured_json.get("subject", "solid_geometry")

            if subject == "solid_geometry":
                result = _compute_solid_geometry(problem.structured_json)
            elif subject == "analytic_geometry":
                result = _compute_analytic_geometry(problem.structured_json)
            elif subject == "algebra":
                result = _compute_algebra(problem.structured_json)
            elif subject == "chemistry":
                result = _compute_chemistry(problem.structured_json)
            else:
                result = _compute_stub("unknown", "未知学科")

            # 创建或更新 Lesson
            lesson = db.query(Lesson).filter(Lesson.problem_id == problem_id).first()
            if not lesson:
                lesson = Lesson(problem_id=uuid.UUID(problem_id))

            kernel_dict = {
                "subject": result.get("subject", subject),
                "body_type": result.get("body_type", ""),
                "problem_type": result.get("problem_type", ""),
                "answer": result.get("answer", {}),
                "steps": result.get("steps", []),
                "model_3d": result.get("model_3d", {}),
            }

            lesson.kernel_result = kernel_dict
            lesson.subject = result.get("subject", subject)
            db.add(lesson)

            logger.info(f"SymPy compute done for problem {problem_id}: "
                        f"answer={result.get('answer', {}).get('latex', 'N/A')}")

            return {
                "problem_id": problem_id,
                "status": "computing",
                "answer": result.get("answer", {}),
            }

        except Exception as e:
            logger.error(f"SymPy compute failed for problem {problem_id}: {e}", exc_info=True)
            problem.status = "error"
            problem.error_message = f"Computation error: {str(e)}"
            return {"problem_id": problem_id, "status": "error", "error": str(e)}


def _compute_solid_geometry(structured_json: dict) -> dict:
    """调用立体几何计算内核。"""
    from app.kernels.geometry.kernel import SolidGeometryKernel
    kernel = SolidGeometryKernel()
    result = kernel.compute(structured_json)
    return {
        "subject": result.subject,
        "body_type": result.body_type,
        "problem_type": result.problem_type,
        "answer": result.answer,
        "steps": result.steps,
        "model_3d": result.model_3d,
    }


def _compute_analytic_geometry(structured_json: dict) -> dict:
    """调用解析几何计算内核。"""
    from app.kernels.analytic.kernel import AnalyticGeometryKernel
    kernel = AnalyticGeometryKernel()
    return kernel.compute(structured_json)


def _compute_algebra(structured_json: dict) -> dict:
    """调用代数计算内核。"""
    from app.kernels.algebra.kernel import AlgebraKernel
    kernel = AlgebraKernel()
    return kernel.compute(structured_json)


def _compute_chemistry(structured_json: dict) -> dict:
    """调用化学计算内核。"""
    from app.kernels.chemistry.kernel import ChemistryKernel
    kernel = ChemistryKernel()
    return kernel.compute(structured_json)


def _compute_stub(subject: str, display_name: str) -> dict:
    """未实现学科的占位返回值。"""
    return {
        "subject": subject,
        "body_type": "",
        "problem_type": "",
        "answer": {
            "latex": "N/A",
            "exact": "N/A",
            "numeric": 0,
        },
        "steps": [{
            "step_number": 1,
            "title": f"{display_name}内核开发中",
            "description": f"{display_name}计算内核尚未实现，将在后续版本中支持。",
            "formula": "",
            "result": "敬请期待 🚧",
        }],
        "model_3d": {},
    }


# ========== 课件渲染任务 ==========

@celery_app.task(bind=True, name="render_lesson")
def render_lesson(self, problem_id: str) -> dict:
    """
    课件渲染任务：根据学科类型选择对应渲染器。
    更新 Lesson.html_content / html_file_path 和 Problem.status = "done"。
    """
    from app.models import Problem, Lesson

    logger.info(f"Render lesson task started for problem {problem_id}")

    with get_sync_db() as db:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        lesson = db.query(Lesson).filter(Lesson.problem_id == problem_id).first()

        if not problem:
            logger.error(f"Problem {problem_id} not found")
            return {"problem_id": problem_id, "status": "error", "error": "Problem not found"}

        if not lesson or not lesson.kernel_result:
            logger.error(f"Lesson not found for problem {problem_id}")
            problem.status = "error"
            problem.error_message = "No kernel result to render"
            return {"problem_id": problem_id, "status": "error", "error": "No kernel result"}

        try:
            subject = lesson.kernel_result.get("subject", "solid_geometry")

            if subject == "solid_geometry":
                from app.services.render_service import render_solid_geometry_lesson
                html = render_solid_geometry_lesson(lesson.kernel_result)
            else:
                from app.services.render_service import render_generic_lesson
                html = render_generic_lesson(lesson.kernel_result)

            # 保存到文件
            lesson_dir = settings.LESSON_DIR
            filename = f"lesson_{uuid.uuid4().hex[:12]}.html"
            filepath = os.path.join(lesson_dir, filename)
            os.makedirs(lesson_dir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            # 更新数据库
            lesson.html_content = html
            lesson.html_file_path = filepath
            problem.status = "done"

            logger.info(f"Render done for problem {problem_id}: file={filepath}")

            return {
                "problem_id": problem_id,
                "status": "done",
                "lesson_id": str(lesson.id),
                "html_file_path": filepath,
            }

        except Exception as e:
            logger.error(f"Render failed for problem {problem_id}: {e}", exc_info=True)
            problem.status = "error"
            problem.error_message = f"Render error: {str(e)}"
            return {"problem_id": problem_id, "status": "error", "error": str(e)}


# ========== 编排任务 ==========

@celery_app.task(bind=True, name="solve_and_render")
def solve_and_render(self, problem_id: str) -> dict:
    """
    完整求解流程：LLM 结构化 → SymPy 计算 → 课件渲染（Celery chain）。
    用于用户确认 OCR 结果后触发。跳过 OCR，直接从结构化开始。
    """
    logger.info(f"Solve-and-render chain started for problem {problem_id}")

    # 使用 Celery chain 串联三个任务
    task_chain = chain(
        llm_structure.si(problem_id),
        sympy_compute.si(problem_id),
        render_lesson.si(problem_id),
    )
    result = task_chain.apply_async()

    logger.info(f"Chain dispatched for problem {problem_id}: chain_id={result.id}")

    return {
        "problem_id": problem_id,
        "status": "chain_started",
        "chain_task_id": str(result.id),
        "stages": ["llm_structure", "sympy_compute", "render_lesson"],
    }


# ========== 文字提交任务（跳过 OCR） ==========

@celery_app.task(bind=True, name="process_text_input")
def process_text_input(self, problem_id: str) -> dict:
    """
    处理文字输入的题目：直接启动 LLM → SymPy → Render 链。
    因为文字输入不需要 OCR 识别步骤。
    """
    logger.info(f"Process text input started for problem {problem_id}")

    # 直接将 OCR 文本状态设为完成，然后启动后续链
    with get_sync_db() as db:
        from app.models import Problem
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if problem:
            problem.status = "ocr_done"

    # 启动求解链
    return solve_and_render(problem_id)
