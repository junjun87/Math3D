# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## 项目概述

Math3D 是一个**拍照搜题 + AI 解析 + 交互课件** Web 应用，参照 [wy51ai/edulab](https://github.com/wy51ai/edulab) 设计。手机拍照上传数学/化学题目，服务端 OCR+LLM 识别结构化 → sympy 精确计算 → 生成内嵌 Three.js 的交互式 3D/2D HTML 课件。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS |
| 3D 渲染 | Three.js (react-three-fiber) |
| 2D/公式 | Canvas + KaTeX |
| 后端 | Python FastAPI + Uvicorn |
| OCR | PaddleOCR (PP-OCRv5)，独立容器 |
| LLM | Claude API / OpenAI |
| 符号计算 | SymPy |
| 数据库 | PostgreSQL 16 + Redis 7 |
| 任务队列 | Celery |

## 常用命令

```bash
# ======== Docker 开发环境 ========
docker compose up -d                     # 启动全部服务
docker compose up -d postgres redis      # 仅启动基础设施
docker compose logs -f backend           # 查看后端日志

# ======== 后端开发 ========
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# ======== 前端开发 ========
cd frontend
npm install
npm run dev                              # 开发服务器 :5173

# ======== OCR 服务 ========
cd ml_service
uvicorn app.main:app --port 8001

# ======== Celery Worker ========
cd backend
celery -A app.tasks.celery_app worker --loglevel=info

# ======== 数据库 ========
cd backend
alembic upgrade head                     # 运行迁移
alembic revision --autogenerate -m "..." # 创建迁移
```

## 核心架构

### 目录结构

```
Math3D/
├── frontend/          # React SPA (PWA, 移动端优先)
├── backend/           # FastAPI + Celery Worker
│   └── app/
│       ├── api/       # 路由层: upload, problems, lessons, users
│       ├── kernels/   # SymPy 计算内核
│       │   └── geometry/  # 立体几何 (已实现核心)
│       └── services/  # OCR/LLM/Render 服务层
├── ml_service/        # PaddleOCR 独立推理容器
└── docker-compose.yml
```

### 数据流

```
拍照上传 → OCR识别 → 用户确认 → LLM结构化 → sympy计算 → 课件生成 → 3D展示
POST      Celery    ConfirmPage  LLM         Celery     Render    ResultPage
/upload   Task      (可修正)    Service      Task      Service
```

### 核心设计原则（继承自 edulab）

1. **单源真理**：所有数值（答案、坐标、尺寸）来自同一次 sympy 计算
2. **精确计算**：sympy 符号计算，杜绝浮点误差（输出 √6/3 而非 0.816）
3. **数据驱动模板**：计算内核产出 JSON → 注入通用 HTML 模板 → 离线可用
4. **用户确认回路**：OCR → 回显确认 → 计算，防止识别错误传播

### 计算内核

`backend/app/kernels/geometry/kernel.py` — 立体几何 SymPy 计算核心
- `SolidGeometryKernel.compute(problem)` 接受结构化题目 JSON，返回 `ComputationResult`
- 问题类型: line_plane_angle, dihedral_angle, skew_line_angle, point_plane_distance, volume
- 坐标法 + 向量法统一求解，所有中间步骤输出 LaTeX

`backend/app/kernels/geometry/bodies.py` — 几何体边/面拓扑库
- 支持: cube, cuboid, pyramid, prism, tetrahedron, cylinder, cone
- `BODIES` 注册表定义顶点标签、边连接、面构成

### API 关键端点

```
POST /api/v1/problems/upload       # 上传图片，返回 problem_id
GET  /api/v1/problems/{id}/ocr     # 获取 OCR 结果（轮询）
POST /api/v1/problems/{id}/confirm # 确认/修正 → 触发计算
GET  /api/v1/problems/{id}/lesson  # 获取课件结果（轮询）
GET  /api/v1/lessons/{id}/view     # 查看课件 HTML
GET  /api/v1/lessons/{id}/download # 下载离线 HTML
```

### 数据库表

- `users` — 用户（id, nickname, avatar_url）
- `problems` — 题目（image_url, ocr_raw_text, structured_json/JSONB, status）
- `lessons` — 课件（kernel_result/JSONB, html_content, html_file_path）

## 当前状态

- [x] Phase 1 MVP: 项目骨架、Docker 环境、前后端基础框架
- [x] 立体几何计算内核（正方体线面角等核心题型）
- [x] 3D 课件 HTML 模板（Three.js，离线可用）
- [x] OCR 服务容器（PaddleOCR，含 Mock 模式）
- [x] LLM 题目结构化集成（DeepSeek + 多学科 prompt）
- [x] Celery 异步任务链联调（端到端验证通过）
- [x] Phase 2: 多学科 LLM 支持（解析几何/代数/化学识别 + 通用课件渲染）
- [x] 解析几何内核（直线/圆/椭圆/双曲线/抛物线 + 距离/交点/切线）
- [x] 代数内核（一次/二次方程、方程组、不等式、数列、因式分解、函数性质）
- [x] 化学内核（方程式配平/物质的量/浓度/pH/气体定律/化学计量）
- [x] PWA 完整支持（离线缓存/添加到主屏幕/独立窗口）
