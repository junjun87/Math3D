#!/usr/bin/env python3
"""
generate.py — 把结构化课程数据注入 template/lesson.html，产出单页 HTML。

数据全部由 geometry_kernel.py 的确定性计算驱动：
坐标、向量、最终答案均为 sympy 精确计算结果，3D 坐标与解题数值同源。

用法:
    python scripts/generate.py cube           ./cube.html       # 正方体·线面角
    python scripts/generate.py skew           ./skew.html       # 异面直线夹角
    python scripts/generate.py distance       ./dist.html       # 点面距离
    python scripts/generate.py pyramid        ./pyramid.html    # 正四棱锥·线面角
    python scripts/generate.py point_range    ./point_range.html # 正方体·动点取值范围
    python scripts/generate.py random 7       ./random.html     # 随机出题
    python scripts/generate.py list                             # 列出已注册题型
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = SKILL_DIR / "template.html"
PLACEHOLDER = "__LESSON_DATA__"

sys.path.insert(0, str(SKILL_DIR))
import geometry_kernel as gk  # noqa: E402


def _build_lesson_data(sol: gk.Solution) -> dict:
    """将 Solution 转为模板 lesson data 格式。"""
    # 3D 坐标
    tp = sol.three_points
    if not tp:
        tp = {
            p.name: [p.x, p.y, p.z]
            for p in sol.model.points
        }

    # 棱
    edges = sol.edges
    if not edges:
        edges = [
            {"a": s.p1.name if hasattr(s, 'p1') else s.get("from", ""),
             "b": s.p2.name if hasattr(s, 'p2') else s.get("to", "")}
            for s in sol.model.segments
        ]

    return {
        "lesson": {
            "language": "zh-CN",
            "meta": sol.lesson_meta or "交互解题",
            "title": sol.problem,
            "answerLabel": sol.answer_label or "答案",
            "answerValue": f"${sol.answer_latex}$",
        },
        "steps": sol.steps,
        "model": {
            "points": tp,
            "spheres": sol.spheres or list(tp.keys()),
            "edges": edges,
            "elements": sol.elements or {},
            "target": sol.target or [1, 0.5, 1],
            "initialCamera": sol.initial_camera or [5, 4, 6],
        },
    }


def render_html(sol: gk.Solution, out_path: Path) -> Path:
    """把 Solution 注入模板，写出 HTML。"""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError(f"模板中未找到占位符 {PLACEHOLDER}")

    data = _build_lesson_data(sol)
    payload = json.dumps(data, ensure_ascii=False)
    html = template.replace(PLACEHOLDER, payload)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / "solution.html"

    if cmd == "list":
        from solver_registry import list_supported_types
        types = list_supported_types()
        for shape, queries in types.items():
            for q in queries:
                print(f"  {shape} + {q}")
        return

    solvers = {
        "cube": gk.solve_line_plane_angle_cube,
        "skew": gk.solve_cube_line_line_angle,
        "distance": gk.solve_cube_point_plane_distance,
        "pyramid": gk.solve_pyramid_line_plane_angle,
        "point_range": gk.solve_cube_point_range,
    }

    if cmd == "random":
        seed = int(sys.argv[2]) if len(sys.argv) > 2 else None
        sol = gk.generate_random(seed=seed)
    elif cmd in solvers:
        sol = solvers[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(solvers)} | random | list")
        sys.exit(1)

    path = render_html(sol, out)
    print(f"生成: {path}")
    print(f"答案: {sol.answer_latex} = {sol.answer_value}")


if __name__ == "__main__":
    main()
