"""
Edulab MVP Web 后端
提供：
  - POST /api/solve   接收题面，返回渲染后的 HTML 字符串
  - GET  /api/health  健康检查
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from geometry_kernel import solve

app = FastAPI(title="Edulab MVP - Solid Geometry")

# 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = (Path(__file__).parent / ".." / "frontend").resolve()
TEMPLATE_PATH = Path(__file__).with_name("template.html")
PLACEHOLDER = "__LESSON_DATA__"


def _build_lesson_data(solution) -> dict:
    """将 Solution 转换为模板所需的 lesson data 格式。"""
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
    }


class SolveRequest(BaseModel):
    problem: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/solve")
def solve_problem(req: SolveRequest):
    try:
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
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# 托管前端静态文件（同源部署，必须在路由之后挂载）
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
