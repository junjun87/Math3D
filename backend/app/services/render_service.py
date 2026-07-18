"""
课件 HTML 渲染服务。

将计算内核的 JSON 结果注入 HTML 模板，生成可离线使用的交互式课件。
参照 edulab 的数据驱动模板模式。
"""

from __future__ import annotations
import json
import uuid
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

settings = get_settings()

# Jinja2 环境
_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=select_autoescape(["html"]),
)

# 内联的 3D 课件模板（不依赖文件系统的备用方案）
INLINE_SOLID_GEOMETRY_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Math3D — {{ body_type }} 课件</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; overflow: hidden; }
  #container { width: 100vw; height: 100vh; position: relative; }
  /* 底部控制栏 */
  #controls { position: absolute; bottom: 20px; left: 0; right: 0; display: flex; gap: 6px; z-index: 10; padding: 0 16px; overflow-x: auto; justify-content: center; }
  #controls button { padding: 8px 14px; border: none; border-radius: 20px; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.15); cursor: pointer; font-size: 13px; white-space: nowrap; flex-shrink: 0; }
  #controls button.active { background: #3b82f6; color: white; }
  /* 顶部信息面板 */
  #info-panel { position: absolute; top: 12px; right: 12px; background: rgba(255,255,255,0.95); border-radius: 12px; padding: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.15); max-width: 240px; z-index: 10; font-size: 13px; transition: transform 0.3s; }
  #info-panel.collapsed { transform: translateX(calc(100% + 20px)); }
  #info-toggle { position: absolute; top: 50%; left: -28px; transform: translateY(-50%); width: 24px; height: 48px; background: rgba(255,255,255,0.9); border: none; border-radius: 6px 0 0 6px; cursor: pointer; font-size: 14px; box-shadow: -2px 0 8px rgba(0,0,0,0.1); display: flex; align-items: center; justify-content: center; }
  #info-panel h3 { margin-bottom: 6px; color: #3b82f6; font-size: 14px; }
  .step-detail { padding: 4px 0; border-bottom: 1px solid #eee; font-size: 12px; color: #64748b; }
  .step-detail strong { color: #334155; }
  .answer-box { margin-top: 10px; padding: 10px; background: #eff6ff; border-radius: 8px; text-align: center; font-size: 16px; font-weight: bold; color: #1d4ed8; word-break: break-all; }
  #loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); font-size: 18px; color: #999; }
  /* 移动端适配 */
  @media (max-width: 600px) {
    #info-panel { max-width: 200px; font-size: 12px; top: 8px; right: 8px; padding: 8px; }
    #info-panel h3 { font-size: 12px; }
    .answer-box { font-size: 14px; padding: 8px; }
    #controls { bottom: 10px; gap: 4px; }
    #controls button { font-size: 12px; padding: 6px 10px; }
  }
</style>
</head>
<body>
<div id="container">
  <div id="loading">加载中...</div>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.170.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.170.0/examples/jsm/"
  }
}
</script>

<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// ============ 课件数据 ============
const LESSON_DATA = {{ lesson_data_json | safe }};

// ============ 初始化场景 ============
const container = document.getElementById("container");
container.innerHTML = "";

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf0f4f8);

const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
camera.position.set(4, 3, 5);
camera.lookAt(1, 1, 1);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
container.appendChild(renderer.domElement);

// 轨道控制
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(1, 1, 1);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.update();

// 光源
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 10, 5);
scene.add(dirLight);

// 网格
const gridHelper = new THREE.GridHelper(6, 6, 0xcccccc, 0xeeeeee);
scene.add(gridHelper);

// ============ 构建几何体 ============
const points = LESSON_DATA.points;
const edges = LESSON_DATA.edges || [];
const scale = LESSON_DATA.scale || 2;

// 比例缩放
const s = 2 / scale;

// 顶点球
const vertexGroup = new THREE.Group();
const vertexMeshMap = {};
const sphereGeom = new THREE.SphereGeometry(0.08, 16, 16);
const sphereMat = new THREE.MeshPhongMaterial({ color: 0x3b82f6 });

for (const [label, pos] of Object.entries(points)) {
  const mesh = new THREE.Mesh(sphereGeom, sphereMat);
  mesh.position.set(pos[0] * s, pos[2] * s, pos[1] * s);  // y/z swap for Three.js
  vertexGroup.add(mesh);
  vertexMeshMap[label] = mesh;
}
scene.add(vertexGroup);

// 棱边
const edgeGroup = new THREE.Group();
const edgeMat = new THREE.LineBasicMaterial({ color: 0x334155 });
for (const [a, b] of edges) {
  if (points[a] && points[b]) {
    const pa = points[a], pb = points[b];
    const geom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(pa[0] * s, pa[2] * s, pa[1] * s),
      new THREE.Vector3(pb[0] * s, pb[2] * s, pb[1] * s),
    ]);
    edgeGroup.add(new THREE.Line(geom, edgeMat));
  }
}
scene.add(edgeGroup);

// 面（半透明）
if (LESSON_DATA.faces) {
  for (const [name, faceVertices] of LESSON_DATA.faces) {
    if (faceVertices.length >= 3) {
      const triPoints = faceVertices.slice(0, 3).map(v => {
        const p = points[v];
        return new THREE.Vector3(p[0] * s, p[2] * s, p[1] * s);
      });
      const faceGeom = new THREE.BufferGeometry();
      const vertices = new Float32Array([
        triPoints[0].x, triPoints[0].y, triPoints[0].z,
        triPoints[1].x, triPoints[1].y, triPoints[1].z,
        triPoints[2].x, triPoints[2].y, triPoints[2].z,
      ]);
      faceGeom.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
      faceGeom.computeVertexNormals();
      const faceMesh = new THREE.Mesh(
        faceGeom,
        new THREE.MeshPhongMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.3, side: THREE.DoubleSide })
      );
      scene.add(faceMesh);
    }
  }
}

// 坐标标签
function createLabel(text, position) {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 32;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#1e40af";
  ctx.font = "bold 20px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(text, 32, 24);
  const texture = new THREE.CanvasTexture(canvas);
  const spriteMat = new THREE.SpriteMaterial({ map: texture });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.position.copy(position);
  sprite.scale.set(0.4, 0.2, 1);
  return sprite;
}

for (const [label, pos] of Object.entries(points)) {
  const sprite = createLabel(label, new THREE.Vector3(pos[0] * s + 0.15, pos[2] * s + 0.15, pos[1] * s));
  scene.add(sprite);
}

// LaTeX 渲染 (KaTeX)
const katexLink = document.createElement("link");
katexLink.rel = "stylesheet";
katexLink.href = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css";
document.head.appendChild(katexLink);
const katexScript = document.createElement("script");
katexScript.src = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js";
document.head.appendChild(katexScript);

// ============ 构建 UI ============
const controlsDiv = document.createElement("div");
controlsDiv.id = "controls";
container.appendChild(controlsDiv);

// 步骤按钮 — 点击更新信息面板内容
if (LESSON_DATA.steps) {
  LESSON_DATA.steps.forEach((step, i) => {
    const btn = document.createElement("button");
    btn.textContent = `步骤 ${step.step_number}`;
    btn.onclick = () => {
      document.querySelectorAll("#controls button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      // 更新信息面板中的步骤详情
      const info = document.getElementById("step-info");
      if (info) {
        info.innerHTML = `<div class="step-detail"><strong>${step.title || ""}</strong></div>
          <div class="step-detail">${step.description || ""}</div>
          ${step.formula ? `<div class="step-detail">${step.formula}</div>` : ""}
          ${step.result ? `<div class="step-detail" style="color:#3b82f6;margin-top:2px;">→ ${step.result}</div>` : ""}`;
        // 渲染步骤中的 LaTeX
        if (window.katex) {
          info.querySelectorAll(".step-detail").forEach(el => {
            try { katex.render(el.textContent, el, { throwOnError: false }); } catch(e) {}
          });
        }
      }
    };
    if (i === 0) btn.classList.add("active");
    controlsDiv.appendChild(btn);
  });
}

// 信息面板 — 可折叠
const infoPanel = document.createElement("div");
infoPanel.id = "info-panel";
const firstStep = LESSON_DATA.steps?.[0];
infoPanel.innerHTML = `
  <button id="info-toggle">◀</button>
  <h3>📐 ${LESSON_DATA.body_type || "立体几何"}</h3>
  <div id="step-info">
    <div class="step-detail"><strong>${firstStep?.title || ""}</strong></div>
    <div class="step-detail">${firstStep?.description || ""}</div>
    ${firstStep?.formula ? `<div class="step-detail">${firstStep.formula}</div>` : ""}
    ${firstStep?.result ? `<div class="step-detail" style="color:#3b82f6;margin-top:2px;">→ ${firstStep.result}</div>` : ""}
  </div>
  <div class="answer-box" id="answer-box"></div>
`;
container.appendChild(infoPanel);

// 折叠/展开
const toggleBtn = infoPanel.querySelector("#info-toggle");
let panelVisible = true;
toggleBtn.onclick = () => {
  panelVisible = !panelVisible;
  infoPanel.classList.toggle("collapsed", !panelVisible);
  toggleBtn.textContent = panelVisible ? "◀" : "▶";
};

// 渲染答案
setTimeout(() => {
  const answerEl = document.getElementById("answer-box");
  if (LESSON_DATA.answer?.latex && LESSON_DATA.answer.latex !== "N/A") {
    if (window.katex) {
      try { katex.render(LESSON_DATA.answer.latex, answerEl, { throwOnError: false }); }
      catch(e) { answerEl.textContent = "答案: " + LESSON_DATA.answer.latex; }
    } else {
      answerEl.textContent = "答案: " + LESSON_DATA.answer.latex;
    }
  } else {
    answerEl.textContent = "答案: N/A";
  }
}, 300);

// ============ 动画循环 ============
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

// 窗口大小调整
window.addEventListener("resize", () => {
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
});

console.log("Math3D Lesson Ready:", LESSON_DATA);
</script>
</body>
</html>"""


def render_solid_geometry_lesson(kernel_result: dict) -> str:
    """
    将立体几何计算结果渲染为独立 HTML 课件。

    Args:
        kernel_result: SolidGeometryKernel.compute() 的输出

    Returns:
        完整的 HTML 字符串
    """
    model_3d = kernel_result.get("model_3d", {})
    lesson_data = {
        "body_type": kernel_result.get("body_type", "cube"),
        "points": model_3d.get("points", {}),
        "edges": model_3d.get("edges", []),
        "faces": model_3d.get("faces"),
        "scale": model_3d.get("scale", 2),
        "steps": kernel_result.get("steps", []),
        "answer": kernel_result.get("answer", {}),
    }

    lesson_data_json = json.dumps(lesson_data, ensure_ascii=False)

    # 使用内联模板（不依赖文件系统）
    return INLINE_SOLID_GEOMETRY_TEMPLATE.replace(
        "{{ lesson_data_json | safe }}", lesson_data_json
    )


GENERIC_LESSON_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Math3D — {{ subject_name }} 课件</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f5f5; min-height: 100vh; }
  .container { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
  .header { text-align: center; padding: 32px 0; }
  .header h1 { font-size: 24px; color: #1e293b; margin-bottom: 8px; }
  .header .subject-tag { display: inline-block; padding: 4px 12px; border-radius: 20px;
         background: #eff6ff; color: #3b82f6; font-size: 14px; }
  .card { background: white; border-radius: 16px; padding: 20px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .card h3 { font-size: 16px; color: #3b82f6; margin-bottom: 12px; }
  .step-item { padding: 12px 0; border-bottom: 1px solid #f1f5f9; }
  .step-item:last-child { border-bottom: none; }
  .step-title { font-weight: 600; color: #334155; margin-bottom: 4px; }
  .step-desc { color: #64748b; font-size: 14px; }
  .step-formula { background: #f8fafc; padding: 8px 12px; border-radius: 8px;
                  margin-top: 6px; font-family: monospace; font-size: 14px;
                  overflow-x: auto; }
  .answer-box { text-align: center; padding: 24px; background: #eff6ff;
                border-radius: 12px; font-size: 24px; font-weight: bold; color: #1d4ed8; }
  .empty-state { text-align: center; padding: 48px 16px; color: #94a3b8; }
  .empty-state .icon { font-size: 48px; margin-bottom: 16px; }
  .description-box { background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px;
                     padding: 16px; margin-bottom: 16px; color: #92400e; font-size: 15px; }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ subject_name }} 课件</h1>
    <span class="subject-tag">{{ subject_name }}</span>
  </div>

  <div class="description-box" id="description"></div>

  <div class="card">
    <h3>📝 解题分步</h3>
    <div id="steps-container"></div>
  </div>

  <div class="card">
    <h3>✅ 答案</h3>
    <div class="answer-box" id="answer-box"></div>
  </div>
</div>

<script>
const LESSON_DATA = {{ lesson_data_json | safe }};

// 题目描述
const descEl = document.getElementById("description");
if (LESSON_DATA.description) {
  descEl.textContent = "📋 " + LESSON_DATA.description;
  descEl.style.display = "block";
} else {
  descEl.style.display = "none";
}

// 解题分步
const stepsContainer = document.getElementById("steps-container");
if (LESSON_DATA.steps && LESSON_DATA.steps.length > 0) {
  LESSON_DATA.steps.forEach(step => {
    const item = document.createElement("div");
    item.className = "step-item";
    item.innerHTML = `
      <div class="step-title">步骤 ${step.step_number}: ${step.title || ""}</div>
      <div class="step-desc">${step.description || ""}</div>
      ${step.formula ? `<div class="step-formula">${step.formula}</div>` : ""}
      ${step.result ? `<div class="step-desc" style="color:#3b82f6;margin-top:4px;">${step.result}</div>` : ""}
    `;
    stepsContainer.appendChild(item);
  });
} else {
  stepsContainer.innerHTML = '<div class="empty-state"><div class="icon">🔢</div><div>分步解析将在内核实现后展示</div></div>';
}

// 答案渲染
const answerBox = document.getElementById("answer-box");
if (LESSON_DATA.answer && LESSON_DATA.answer.latex && LESSON_DATA.answer.latex !== "N/A") {
  try { katex.render(LESSON_DATA.answer.latex, answerBox, { throwOnError: false }); }
  catch(e) { answerBox.textContent = LESSON_DATA.answer.latex; }
} else {
  answerBox.textContent = "待计算";
}

// 渲染页面中的 KaTeX 公式
if (window.katex) {
  document.querySelectorAll(".step-formula, .step-desc").forEach(el => {
    const text = el.textContent || "";
    if (text.includes("\\")) {
      try { katex.render(text, el, { throwOnError: false }); }
      catch(e) { /* keep as-is */ }
    }
  });
}
</script>
</body>
</html>"""

SUBJECT_NAMES = {
    "solid_geometry": "立体几何",
    "analytic_geometry": "解析几何",
    "algebra": "代数",
    "chemistry": "化学",
    "unknown": "数理化",
}


def render_generic_lesson(kernel_result: dict) -> str:
    """
    通用课件渲染（解析几何/代数/化学等非 3D 科目）。
    生成包含分步解析和 KaTeX 答案展示的 HTML 页面。
    """
    subject = kernel_result.get("subject", "unknown")
    subject_name = SUBJECT_NAMES.get(subject, "数理化")

    lesson_data = {
        "subject": subject,
        "description": kernel_result.get("description", ""),
        "steps": kernel_result.get("steps", []),
        "answer": kernel_result.get("answer", {}),
        "subject_name": subject_name,
    }

    lesson_data_json = json.dumps(lesson_data, ensure_ascii=False)

    return GENERIC_LESSON_TEMPLATE.replace(
        "{{ lesson_data_json | safe }}", lesson_data_json
    ).replace(
        "{{ subject_name }}", subject_name
    )


async def save_lesson_html(html: str, lesson_dir: str | None = None) -> str:
    """保存课件 HTML 文件，返回文件路径。"""
    if lesson_dir is None:
        lesson_dir = settings.LESSON_DIR

    filename = f"lesson_{uuid.uuid4().hex[:12]}.html"
    filepath = os.path.join(lesson_dir, filename)

    os.makedirs(lesson_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return filepath
