"""
bodies.py — 几何体拓扑库（哪些顶点、哪些棱）。

与 geometry_kernel.py 配合：kernel 负责精确坐标，bodies 负责标准棱连接，
两者合成 3D 渲染所需的 model（spheres + edges）。常见几何体在此内置；
罕见几何体可在具体题目里手写 edges。
"""

from __future__ import annotations


def _edge(a: str, b: str, **kw) -> dict:
    e = {"a": a, "b": b}
    e.update(kw)
    return e


def cuboid(
    bottom: tuple = ("A", "B", "C", "D"),
    top: tuple = ("A1", "B1", "C1", "D1"),
) -> dict:
    """长方体 / 正方体：底面四边形、顶面四边形、四条竖棱。

    Returns:
        {"spheres": list[str], "edges": list[dict]}
    """
    a, b, c, d = bottom
    a1, b1, c1, d1 = top
    edges = [
        # 底面
        _edge(a, b), _edge(b, c), _edge(c, d), _edge(d, a),
        # 顶面
        _edge(a1, b1), _edge(b1, c1), _edge(c1, d1), _edge(d1, a1),
        # 竖棱
        _edge(a, a1), _edge(b, b1), _edge(c, c1), _edge(d, d1),
    ]
    return {"spheres": [a, b, c, d, a1, b1, c1, d1], "edges": edges}


def cube() -> dict:
    """正方体（cuboid 的别名，使用标准命名 ABCD-A1B1C1D1）。"""
    return cuboid()


def quad_pyramid(
    apex: str = "P",
    base: tuple = ("A", "B", "C", "D"),
) -> dict:
    """正四棱锥：底面四边形 + 顶点到各底点。

    Returns:
        {"spheres": list[str], "edges": list[dict]}
    """
    a, b, c, d = base
    edges = [
        _edge(a, b), _edge(b, c), _edge(c, d), _edge(d, a),
        _edge(apex, a), _edge(apex, b), _edge(apex, c), _edge(apex, d),
    ]
    return {"spheres": [apex, a, b, c, d], "edges": edges}


def tri_pyramid(
    apex: str = "P",
    base: tuple = ("A", "B", "C"),
) -> dict:
    """三棱锥（四面体）。

    Returns:
        {"spheres": list[str], "edges": list[dict]}
    """
    a, b, c = base
    edges = [
        _edge(a, b), _edge(b, c), _edge(c, a),
        _edge(apex, a), _edge(apex, b), _edge(apex, c),
    ]
    return {"spheres": [apex, a, b, c], "edges": edges}


def prism(
    bottom: tuple = ("A", "B", "C"),
    top: tuple = ("A1", "B1", "C1"),
) -> dict:
    """棱柱：上下同形多边形 + 竖棱（顶点数任意，按顺序一一对应）。

    Returns:
        {"spheres": list[str], "edges": list[dict]}
    """
    n = len(bottom)
    edges = []
    for i in range(n):
        edges.append(_edge(bottom[i], bottom[(i + 1) % n]))
        edges.append(_edge(top[i], top[(i + 1) % n]))
        edges.append(_edge(bottom[i], top[i]))
    return {"spheres": list(bottom) + list(top), "edges": edges}
