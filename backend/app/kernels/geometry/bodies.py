"""
立体几何体的边拓扑库 (参照 edulab bodies.py)。

定义各种几何体的顶点标签、边连接关系和面构成。
顶点坐标由 SolidGeometryKernel 根据参数计算。
"""

from typing import TypedDict

# ---- 正方体 (Cube) ----
CUBE_VERTICES = ["A", "B", "C", "D", "A1", "B1", "C1", "D1"]

CUBE_EDGES = [
    # 底面
    ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
    # 顶面
    ("A1", "B1"), ("B1", "C1"), ("C1", "D1"), ("D1", "A1"),
    # 侧棱
    ("A", "A1"), ("B", "B1"), ("C", "C1"), ("D", "D1"),
]

CUBE_FACES = [
    ("ABCD", ["A", "B", "C", "D"]),          # 底面
    ("A1B1C1D1", ["A1", "B1", "C1", "D1"]),  # 顶面
    ("ABB1A1", ["A", "B", "B1", "A1"]),       # 前面
    ("BCC1B1", ["B", "C", "C1", "B1"]),       # 右面
    ("CDD1C1", ["C", "D", "D1", "C1"]),       # 后面
    ("DAA1D1", ["D", "A", "A1", "D1"]),       # 左面
]


# ---- 长方体 (Cuboid) ----
CUBOID_VERTICES = CUBE_VERTICES
CUBOID_EDGES = CUBE_EDGES
CUBOID_FACES = CUBE_FACES


# ---- 正四棱锥 (Pyramid) — 底面为正方形，顶点为 P ----
PYRAMID_VERTICES = ["P", "A", "B", "C", "D"]

PYRAMID_EDGES = [
    ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),  # 底面
    ("P", "A"), ("P", "B"), ("P", "C"), ("P", "D"),   # 侧棱
]

PYRAMID_FACES = [
    ("ABCD", ["A", "B", "C", "D"]),
    ("PAB", ["P", "A", "B"]),
    ("PBC", ["P", "B", "C"]),
    ("PCD", ["P", "C", "D"]),
    ("PDA", ["P", "D", "A"]),
]


# ---- 正三棱柱 (Triangular Prism) ----
PRISM_VERTICES = ["A", "B", "C", "A1", "B1", "C1"]

PRISM_EDGES = [
    ("A", "B"), ("B", "C"), ("C", "A"),          # 底面
    ("A1", "B1"), ("B1", "C1"), ("C1", "A1"),     # 顶面
    ("A", "A1"), ("B", "B1"), ("C", "C1"),         # 侧棱
]

PRISM_FACES = [
    ("ABC", ["A", "B", "C"]),
    ("A1B1C1", ["A1", "B1", "C1"]),
    ("ABB1A1", ["A", "B", "B1", "A1"]),
    ("BCC1B1", ["B", "C", "C1", "B1"]),
    ("CAA1C1", ["C", "A", "A1", "C1"]),
]


# ---- 正四面体 (Tetrahedron) ----
TETRAHEDRON_VERTICES = ["A", "B", "C", "D"]

TETRAHEDRON_EDGES = [
    ("A", "B"), ("A", "C"), ("A", "D"),
    ("B", "C"), ("B", "D"), ("C", "D"),
]

TETRAHEDRON_FACES = [
    ("ABC", ["A", "B", "C"]),
    ("ABD", ["A", "B", "D"]),
    ("ACD", ["A", "C", "D"]),
    ("BCD", ["B", "C", "D"]),
]


# ---- 圆柱 (Cylinder) — 使用近似多边形 ----
CYLINDER_VERTICES = [
    "A", "B", "C", "D", "E", "F", "G", "H",  # 底面 8 等分点
    "A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1",  # 顶面 8 等分点
]

CYLINDER_EDGES = [
    # 底面
    ("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
    ("E", "F"), ("F", "G"), ("G", "H"), ("H", "A"),
    # 顶面
    ("A1", "B1"), ("B1", "C1"), ("C1", "D1"), ("D1", "E1"),
    ("E1", "F1"), ("F1", "G1"), ("G1", "H1"), ("H1", "A1"),
    # 母线
    ("A", "A1"), ("B", "B1"), ("C", "C1"), ("D", "D1"),
    ("E", "E1"), ("F", "F1"), ("G", "G1"), ("H", "H1"),
]


# ---- 圆锥 (Cone) — 顶点为 P ----
CONE_VERTICES = [
    "P",
    "A", "B", "C", "D", "E", "F", "G", "H",  # 底面 8 等分点
]

CONE_EDGES = [
    # 底面
    ("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
    ("E", "F"), ("F", "G"), ("G", "H"), ("H", "A"),
    # 母线 (母线是 P 到底面各点)
    ("P", "A"), ("P", "B"), ("P", "C"), ("P", "D"),
    ("P", "E"), ("P", "F"), ("P", "G"), ("P", "H"),
]


# ---- 几何体注册表 ----
BODIES = {
    "cube": {
        "vertices": CUBE_VERTICES,
        "edges": CUBE_EDGES,
        "faces": CUBE_FACES,
    },
    "cuboid": {
        "vertices": CUBOID_VERTICES,
        "edges": CUBOID_EDGES,
        "faces": CUBOID_FACES,
    },
    "pyramid": {
        "vertices": PYRAMID_VERTICES,
        "edges": PYRAMID_EDGES,
        "faces": PYRAMID_FACES,
    },
    "prism": {
        "vertices": PRISM_VERTICES,
        "edges": PRISM_EDGES,
        "faces": PRISM_FACES,
    },
    "tetrahedron": {
        "vertices": TETRAHEDRON_VERTICES,
        "edges": TETRAHEDRON_EDGES,
        "faces": TETRAHEDRON_FACES,
    },
    "cylinder": {
        "vertices": CYLINDER_VERTICES,
        "edges": CYLINDER_EDGES,
        "faces": None,  # 圆柱体面是曲面，用参数方程渲染
    },
    "cone": {
        "vertices": CONE_VERTICES,
        "edges": CONE_EDGES,
        "faces": None,
    },
}


def get_body_edges(body_type: str) -> list[tuple[str, str]]:
    """获取几何体的边连接关系。"""
    body = BODIES.get(body_type, BODIES["cube"])
    return body["edges"]


def get_body_faces(body_type: str) -> list[tuple[str, list[str]]] | None:
    """获取几何体的面构成。"""
    body = BODIES.get(body_type, BODIES["cube"])
    return body["faces"]


def get_body_vertices(body_type: str) -> list[str]:
    """获取几何体的顶点标签列表。"""
    body = BODIES.get(body_type, BODIES["cube"])
    return body["vertices"]
