"""
求解器注册表：将 (shape_type, query_type) 映射到求解函数。

用法：
    @register_solver("cube", "line_plane_angle")
    def solve_line_plane_angle_cube(edge=2): ...
"""

from __future__ import annotations

from typing import Callable, Dict, List

_registry: Dict[tuple, Callable] = {}


def register_solver(shape_type: str, query_type: str):
    """装饰器：将函数注册为指定几何体和问题类型的求解器。"""
    def decorator(func: Callable):
        key = (shape_type, query_type)
        if key in _registry:
            raise ValueError(f"Solver already registered for {key}")
        _registry[key] = func
        return func
    return decorator


def get_solver(shape_type: str, query_type: str) -> Callable | None:
    """根据几何体类型和问题类型获取求解器，未注册时返回 None。"""
    return _registry.get((shape_type, query_type))


def list_supported_types() -> Dict[str, List[str]]:
    """返回已注册的 {几何体类型: [问题类型列表]}，供 LLM prompt 动态生成。"""
    result: Dict[str, List[str]] = {}
    for (shape, query) in _registry:
        result.setdefault(shape, []).append(query)
    return result
