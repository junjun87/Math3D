# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Math3D MVP——立体几何解题工具。用户输入几何题面，后端通过 sympy 进行精确计算，返回一个自包含的 HTML 页面，其中包含可交互的 Three.js 3D 场景和逐步呈现的 MathJax 解题过程。前端点击生成后跳转至全屏解题页。

## 常用命令

```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
source .venv/bin/activate       # macOS/Linux

# 安装依赖
python -m pip install -r requirements.txt

# 启动后端（带热重载）
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# 托管前端（可选——也可以直接打开文件）
cd frontend
python -m http.server 3000
```

## 架构

```
用户 (frontend/index.html)
  ├─ 📷 拍照 → POST /api/ocr {image} ──► llm_parser.ocr_image()
  │      ├─► 阿里云 RecognizeEduQuestionOcr（题目识别，按次计费）
  │      ├─► RecognizeAdvanced 降级（通用文字识别）
  │      └─► DeepSeek LLM 规范化（修复数学符号 + 过滤图形标注）
  │
  └─ 题面文字 ──► POST /api/solve {problem: "…"} ──► backend/app.py
        │                                 ├─► llm_parser.py (LLM 题面解析，可选)
        │                                 ├─► solver_registry.py (题型路由)
        │                                 └─► geometry_kernel.py (sympy 精确计算)
        │                                       ├─► bodies.py (几何体拓扑)
        │                                       └─► Solution 数据类
        ◄── template.html（__LESSON_DATA__ 占位符）
        ◄── JSONResponse {html, answer_latex, answer_value}
  ◄── 跳转全屏解题页（浏览器后退可回输入页）
```

生产部署时 FastAPI 同时托管前端静态文件（同源），无需额外 Web 服务器。

### 后端 (`backend/`)

- **`app.py`** — FastAPI 服务。`/api/solve` 接收题面，调用 `geometry_kernel.solve()` 返回解题 HTML。`/api/ocr` 接收图片，调用视觉 LLM 提取题目文字。`/api/health` 健康检查。生产模式下通过 `StaticFiles` 挂载 `frontend/` 实现同源部署。CORS 完全放开。
- **`geometry_kernel.py`** — 计算核心。数据类：`Point`、`Segment`、`SolidModel`、`Solution`。使用 sympy 精确有理数/根式运算（`.answer_value` 前绝不浮点）。`solve()` 优先调用 `llm_parser` 做结构化题面解析，失败降级为关键词匹配。内置 4 种题型求解器（通过 `@register_solver` 注册）。
- **`solver_registry.py`** — `@register_solver(shape, query)` 装饰器将求解函数注册到全局映射表，供 LLM prompt 动态生成和题面路由。
- **`llm_parser.py`** — 三个功能：(1) `ocr_image()` 优先阿里云文字识别 OCR（教育场景题目识别 + 通用文字识别降级），然后 DeepSeek LLM 规范化数学符号并过滤图形标注；(2) `parse_problem()` 通过 OpenAI 兼容 API 将题面解析为结构化 spec；(3) 不可用时静默降级为关键词匹配。配置：`ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`（阿里云 OCR）+ `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（题面解析 + OCR 规范化）。
- **`bodies.py`** — 几何体拓扑库（`cuboid`、`quad_pyramid`、`tri_pyramid`、`prism`）。返回 `{spheres, edges}` 供 3D 渲染。与 `geometry_kernel.py` 的坐标计算分离。
- **`scripts/generate.py`** — CLI 工具：从命令行直接生成解题 HTML 文件（`python scripts/generate.py cube ./out.html`）。
- **`template.html`** — 输出页面模板。使用 `__LESSON_DATA__` JSON 占位符。左侧 420px 解题面板（题面卡 + 答案卡 + 步骤 + 上一步/下一步），右侧弹性 3D 画布。Three.js r160 模块（OrbitControls + CSS2DRenderer）+ MathJax 3（CDN）。右上角含下载 HTML 按钮。

### 前端 (`frontend/`)

- **`index.html`** — 多页面 UI（首页/拍照/相册/文字输入/历史记录）。拍照后前端自动压缩图片（Canvas resize + HEIC→JPEG），再调用 `/api/ocr` 识别，识别结果直接送 `/api/solve` 求解。纯静态 HTML，同源部署无需配置 API 地址。

### Docker 部署

```bash
# 推荐：docker compose（自动加载 .env）
docker compose up -d --build

# 或手动
docker build -t math3d .
docker run -d -p 8000:8000 --name math3d --env-file .env math3d
```

容器内 FastAPI 同时服务 API 和前端静态文件，访问 `http://<ip>:8000` 即可使用。

## 添加新题型

1. 编写 `solve_*()` 函数，用 `@register_solver("shape_type", "query_type")` 注册。
2. 构建 `Solution`（题面、解题步骤、精确答案、3D 坐标、高亮元素）。
3. 新几何体的坐标在 `geometry_kernel.py` 中构建（如 `build_regular_quad_pyramid()`），拓扑结构在 `bodies.py` 中定义。
4. 模板是数据驱动的——`elements` 字典定义高亮几何体（line/plane/arrow/axes/sphere），模板无需修改即可渲染新题型。
