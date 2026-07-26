"""
Math3D Web 后端
提供：
  - POST /api/solve   接收题面，返回渲染后的 HTML 字符串
  - GET  /api/health  健康检查
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from geometry_kernel import solve
import llm_parser

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Math3D - Solid Geometry")

# 允许前端跨域：同源部署下本可不启用；为兼容本地 file:// 开发保留通配，但不允许携带 credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# 第三方 API 防护配置
# ═══════════════════════════════════════════════════════════════════════════════
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "10485760"))  # 10 MB
MAX_PROBLEM_LEN = int(os.getenv("MAX_PROBLEM_LEN", "2000"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
RATE_LIMIT_WINDOW = 60


class InMemoryRateLimiter:
    """基于客户端 IP 的滑动窗口限流（单机内存实现；多实例需改 Redis）。"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._history: dict[str, deque] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        now = time.time()
        async with self._lock:
            dq = self._history.setdefault(key, deque())
            while dq and dq[0] < now - self.window:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True


rate_limiter = InMemoryRateLimiter(
    max_requests=RATE_LIMIT_PER_MINUTE, window_seconds=RATE_LIMIT_WINDOW
)


def _client_id(request: Request) -> str:
    """获取客户端标识；若经反向代理，优先取 X-Forwarded-For 第一段。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/api/health":
        return await call_next(request)
    client = _client_id(request)
    if not await rate_limiter.is_allowed(client):
        logger.warning("Rate limit exceeded for client=%s path=%s", client, request.url.path)
        return JSONResponse(
            {"success": False, "error": "请求过于频繁，请稍后再试"},
            status_code=429,
        )
    return await call_next(request)


FRONTEND_DIR = (Path(__file__).parent / ".." / "frontend").resolve()
TEMPLATE_PATH = Path(__file__).with_name("template.html")
PLACEHOLDER = "__LESSON_DATA__"


def _build_lesson_data(solution) -> dict:
    """将 Solution 转换为模板所需的 lesson data 格式。

    ⚠️ 与 geometry_kernel._build_lesson_data() 对应 —— 修改 dict 结构时两边需同步。
    """
    # 3D 坐标：优先使用 three_points，否则从 SolidModel 构建
    if solution.three_points:
        points = solution.three_points
    else:
        points = {
            p.name: [p.x, p.y, p.z]
            for p in solution.model.points
        }

    # 几何拓扑
    edges = solution.edges or [
        {"a": s.p1.name if hasattr(s, 'p1') else s.get("from", ""),
         "b": s.p2.name if hasattr(s, 'p2') else s.get("to", "")}
        for s in solution.model.segments
    ]

    return {
        "lesson": {
            "language": "zh-CN",
            "meta": getattr(solution, "lesson_meta", "交互解题"),
            "title": solution.problem,
            "answerLabel": getattr(solution, "answer_label", "答案"),
            "answerValue": f"${solution.answer_latex}$",
        },
        "steps": solution.steps,
        "model": {
            "points": points,
            "spheres": solution.spheres or [p.name for p in solution.model.points],
            "edges": edges,
            "elements": getattr(solution, "elements", {}),
            "target": getattr(solution, "target", [1, 0.5, 1]),
            "initialCamera": getattr(solution, "initial_camera", [5, 4, 6]),
        },
        "textOnly": getattr(solution, "text_only", False),
    }


def _internal_error_response() -> JSONResponse:
    """返回不暴露内部细节的通用 500 错误。"""
    return JSONResponse(
        {"success": False, "error": "服务器内部错误，请稍后重试"},
        status_code=500,
    )


class SolveRequest(BaseModel):
    problem: str


@app.post("/api/ocr")
async def ocr_image(image: UploadFile = File(...)):
    """拍照 OCR：上传图片，调用视觉 LLM 提取题目文本。"""
    try:
        # 校验文件类型
        media_type = image.content_type or ""
        if media_type not in ("image/jpeg", "image/png", "image/webp", "image/bmp", "image/heic", "image/heif"):
            logger.warning("OCR: rejected content_type=%s", media_type)
            return JSONResponse(
                {"success": False, "error": "不支持的文件类型，请上传 JPEG/PNG/WebP/BMP/HEIC 图片"},
                status_code=400,
            )

        # 校验文件大小
        contents = await image.read()
        if len(contents) > MAX_IMAGE_SIZE:
            logger.warning("OCR: image too large size=%dKB", len(contents) // 1024)
            return JSONResponse(
                {"success": False, "error": f"图片过大（最大 {MAX_IMAGE_SIZE // 1024 // 1024} MB）"},
                status_code=400,
            )

        logger.info("OCR: received image type=%s size=%dKB filename=%s",
                     media_type, len(contents) // 1024, image.filename)
        image_b64 = base64.b64encode(contents).decode("utf-8")
        text = llm_parser.ocr_image(image_b64, media_type)
        logger.info("OCR: success, text length=%d", len(text))
        return {"success": True, "text": text}
    except llm_parser.LLMNotConfiguredError as e:
        logger.warning("OCR: LLM not configured - %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=503)
    except Exception:
        logger.exception("OCR: unexpected error")
        return _internal_error_response()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/solve")
def solve_problem(req: SolveRequest):
    try:
        if len(req.problem) > MAX_PROBLEM_LEN:
            return JSONResponse(
                {"success": False, "error": f"题目文字过长（最大 {MAX_PROBLEM_LEN} 字符）"},
                status_code=400,
            )
        if not req.problem.strip():
            return JSONResponse(
                {"success": False, "error": "题目不能为空"},
                status_code=400,
            )

        solution = solve(req.problem)
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        if PLACEHOLDER in template:
            # New template: single JSON placeholder
            lesson_data = _build_lesson_data(solution)
            html = template.replace(
                PLACEHOLDER,
                json.dumps(lesson_data, ensure_ascii=False),
            )
        else:
            # Old template: multiple {{ }} placeholders (legacy)
            html = (
                template
                .replace("{{ title }}", "立体几何解题")
                .replace("{{ problem }}", solution.problem)
                .replace("{{ answer_latex }}", solution.answer_latex)
                .replace("{{ answer_value }}", f"{solution.answer_value:.6f}")
                .replace("{{ model_json }}", json.dumps(solution.model.to_three(), ensure_ascii=False))
                .replace("{{ steps_json }}", json.dumps(solution.steps, ensure_ascii=False))
            )

        return JSONResponse({
            "success": True,
            "html": html,
            "problem": solution.problem,
            "answer_latex": solution.answer_latex,
            "answer_value": solution.answer_value,
        })
    except ValueError as e:
        # 业务/用户输入类错误（如题型不支持），可把可读信息返回给客户端
        logger.warning("solve_problem: user error - %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception:
        logger.exception("solve_problem: unexpected error")
        return _internal_error_response()


# 托管前端静态文件（同源部署，必须在路由之后挂载）
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
