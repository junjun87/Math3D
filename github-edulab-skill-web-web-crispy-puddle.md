# Math3D — 拍照搜题 + AI 解析 + 交互课件 Web 应用设计方案

## Context

参照 GitHub 开源项目 [wy51ai/edulab](https://github.com/wy51ai/edulab)（672 Star, Apache 2.0），设计一个完整的 Web 应用。edulab 的核心价值在于：**拍照上传数学/化学题目 → AI 视觉识别 → sympy 精确计算 → 生成内嵌 Three.js 的交互式 3D/2D HTML 课件**。

与 edulab 不同的是，本方案是一个 **独立的 Web 应用**（非 Claude Code 插件），采用前后端分离架构，面向真实用户场景：学生/教师用手机拍照上传试题，服务端解析计算，Web 端呈现可交互的结果页面。

## 技术栈确认

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | React 18 + Vite + TypeScript | 移动端优先，PWA 支持拍照 |
| 3D 渲染 | Three.js (react-three-fiber) | 立体几何、化学反应 3D 模型 |
| 2D 渲染 | Canvas + KaTeX | 解析几何图形、数学公式 |
| 后端 | Python FastAPI + Uvicorn | 异步高性能 API |
| OCR 引擎 | PaddleOCR (PP-OCRv5) | 中文手写/印刷体识别 |
| LLM | Claude API / 本地模型 | 题目结构化理解 |
| 符号计算 | SymPy | 精确数学计算（无浮点误差） |
| 数据库 | PostgreSQL + Redis | 持久化 + 缓存/任务队列 |
| 任务队列 | Celery + Redis | 异步 OCR + 计算任务 |
| 部署 | Docker Compose | 一键部署 |

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    手机浏览器 (PWA)                       │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ 拍照/上传 │→│ 题目确认  │→│ 交互课件查看 (Three.js) │   │
│  └─────────┘  └──────────┘  └──────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────┐
│                  Nginx (反向代理)                         │
│            /api/* → FastAPI    / → React SPA             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI 后端                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ OCR 服务  │ │ LLM 服务 │ │ 计算引擎  │ │ 渲染引擎  │  │
│  │ PaddleOCR│ │ 题目解析  │ │  SymPy   │ │ 模板组装  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐                              │
│  │ 用户管理  │ │ 历史记录  │                              │
│  └──────────┘ └──────────┘                              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│            Celery Worker (异步任务)                       │
│   OCR 识别任务  │  sympy 计算任务  │  课件生成任务        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              数据层                                       │
│   PostgreSQL (题库/用户/历史)  │  Redis (缓存/队列)       │
│   MinIO/OSS (图片存储)        │  File System (课件HTML)  │
└─────────────────────────────────────────────────────────┘
```

---

## 二、目录结构规划

```
Math3D/
├── docker-compose.yml                 # 一键部署
├── .env.example                       # 环境变量模板
├── README.md
│
├── frontend/                          # React 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── public/
│   │   └── manifest.json              # PWA 配置
│   └── src/
│       ├── main.tsx                   # 入口
│       ├── App.tsx                    # 路由配置
│       ├── pages/
│       │   ├── HomePage.tsx           # 首页：拍照/上传入口
│       │   ├── CapturePage.tsx        # 拍照/上传页
│       │   ├── ConfirmPage.tsx        # 题目确认页（OCR回显）
│       │   ├── ResultPage.tsx         # 课件查看页
│       │   └── HistoryPage.tsx        # 历史记录页
│       ├── components/
│       │   ├── camera/
│       │   │   └── CameraCapture.tsx  # 手机摄像头组件
│       │   ├── ocr/
│       │   │   └── OcrConfirm.tsx     # OCR 结果确认组件
│       │   ├── viewer/
│       │   │   ├── Geometry3D.tsx     # 立体几何 3D 查看器 (react-three-fiber)
│       │   │   ├── ConicGraph.tsx     # 圆锥曲线 2D 图形
│       │   │   ├── Chemistry3D.tsx    # 化学反应 3D 查看器
│       │   │   └── AlgebraSteps.tsx   # 代数分步解析
│       │   └── common/
│       │       ├── LatexRenderer.tsx  # KaTeX 公式渲染
│       │       └── StepNavigation.tsx # 分步导航
│       ├── hooks/
│       │   ├── useCamera.ts           # 摄像头 hook
│       │   └── useUpload.ts           # 上传 hook
│       ├── services/
│       │   └── api.ts                 # API 请求封装
│       ├── stores/
│       │   └── appStore.ts            # 状态管理 (zustand)
│       └── styles/
│
├── backend/                           # FastAPI 后端
│   ├── requirements.txt
│   ├── alembic.ini                    # 数据库迁移
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── config.py                  # 配置管理
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── upload.py              # 图片上传 API
│   │   │   ├── problems.py            # 题目 CRUD API
│   │   │   ├── lessons.py             # 课件 API
│   │   │   └── users.py               # 用户 API
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── problem.py             # 题目 ORM
│   │   │   ├── lesson.py              # 课件 ORM
│   │   │   └── user.py                # 用户 ORM
│   │   ├── services/
│   │   │   ├── ocr_service.py         # PaddleOCR 服务封装
│   │   │   ├── llm_service.py         # LLM 题目结构化
│   │   │   ├── solver_service.py      # 题目求解调度
│   │   │   └── render_service.py      # 课件 HTML 生成
│   │   ├── kernels/                   # 计算内核（参照 edulab）
│   │   │   ├── __init__.py
│   │   │   ├── geometry/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── kernel.py          # 立体几何 sympy 计算核心
│   │   │   │   ├── bodies.py          # 立体边拓扑库
│   │   │   │   └── templates/         # 3D 课件 HTML 模板
│   │   │   ├── analytic/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── kernel.py          # 解析几何 sympy 计算核心
│   │   │   │   ├── conics.py          # 圆锥曲线定义库
│   │   │   │   └── templates/         # 2D 课件 HTML 模板
│   │   │   ├── algebra/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── kernel.py          # 代数方程求解核心
│   │   │   │   └── templates/
│   │   │   └── chemistry/
│   │   │       ├── __init__.py
│   │   │       ├── kernel.py          # 化学反应计算核心
│   │   │       └── templates/
│   │   ├── templates/                 # Jinja2 课件模板
│   │   │   ├── base.html              # 基础课件模板
│   │   │   ├── solid_geometry.html    # 立体几何课件
│   │   │   ├── analytic_geometry.html # 解析几何课件
│   │   │   ├── algebra.html           # 代数课件
│   │   │   └── chemistry.html         # 化学课件
│   │   └── utils/
│   │       ├── image_utils.py         # 图片预处理
│   │       └── latex_utils.py         # LaTeX 工具
│   └── tests/
│
├── ml_service/                        # PaddleOCR 推理服务（独立容器）
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                    # OCR 独立 FastAPI
│       └── models/                    # PaddleOCR 模型文件
│
├── scripts/
│   ├── init_db.py                     # 初始化数据库
│   └── seed_data.py                   # 种子数据
│
└── docs/
    ├── architecture.md
    └── api.md
```

---

## 三、核心工作流设计

### 3.1 主流程（从拍照到课件）

```
用户拍照 → 上传图片 → OCR识别 → 题目确认 → LLM结构化 → sympy计算 → 课件生成 → 交互展示
   ↓          ↓         ↓         ↓          ↓           ↓          ↓          ↓
 CapturePage  POST    Celery    ConfirmPage  LLM      Celery    Render     ResultPage
             /upload   Task      (用户确认)  Service    Task     Service
```

### 3.2 详细 API 设计

```
POST   /api/v1/problems/upload        # 上传图片，返回 task_id
GET    /api/v1/problems/{id}/ocr       # 获取 OCR 结果（轮询）
POST   /api/v1/problems/{id}/confirm   # 确认/修正 OCR 识别结果
POST   /api/v1/problems/{id}/solve     # 触发计算，返回 task_id
GET    /api/v1/problems/{id}/lesson    # 获取课件结果（轮询）
GET    /api/v1/lessons/{id}            # 获取课件 HTML 内容
GET    /api/v1/lessons/{id}/view       # 课件查看页
GET    /api/v1/history                 # 历史记录列表
```

### 3.3 异步任务流 (Celery)

```python
# 任务链
chain(
    ocr_recognize.s(task_id),          # 1. PaddleOCR 文字识别
    llm_structure.s(task_id),          # 2. LLM 结构化题目
    sympy_compute.s(task_id),          # 3. sympy 精确计算
    render_lesson.s(task_id),          # 4. 生成课件 HTML
)
```

---

## 四、关键模块设计

### 4.1 OCR 服务

参照 PaddleOCRFastAPI 方案：
- 使用 PP-OCRv5 中文识别模型
- 独立 FastAPI 容器（GPU 支持）
- 支持数学公式区域的特殊处理（公式区域标记）
- 返回结构化文本 + 置信度

输入：原始图片 → 图片预处理（去噪、增强对比度、旋转校正）→ PaddleOCR 识别
输出：`{ "text": "...", "formulas": [...], "confidence": 0.95 }`

### 4.2 LLM 题目结构化

PaddleOCR 拿到原始文本后，通过 LLM 理解题目语义，输出标准化 JSON：

```json
{
  "subject": "solid_geometry",
  "body_type": "cube",
  "description": "正方体 ABCD-A1B1C1D1 中，棱长为 2",
  "question": "求直线 AB1 与平面 A1C1D 的夹角",
  "given": { "edge_length": 2, "vertices": ["A","B","C","D","A1","B1","C1","D1"] },
  "target": { "type": "line_plane_angle", "line": "AB1", "plane": "A1C1D" },
  "language": "zh"
}
```

### 4.3 计算内核（核心 — 参照 edulab 设计）

遵循 edulab 的核心原则：**所有数值（最终答案、分步中间值、3D 坐标、参数范围）全部来自同一次 sympy 计算调用**。

```
ProblemSpec → Kernel.compute() → {
    answer: { value: √6/3, latex: "\\frac{\\sqrt{6}}{3}" },
    steps: [{ title: "建立坐标系", ... }, { title: "求法向量", ... }],
    model_3d: {
        points: { A: [0,0,0], B: [2,0,0], ... },  // Three.js 坐标
        edges: [[A,B], [B,C], ...],                 // 边拓扑
        highlights: [[AB1, A1C1D], ...],            // 分步高亮
        cameras: [{ pos, lookAt }],                  // 分步视角
    }
}
```

### 4.4 课件渲染引擎

采用 **数据驱动模板** 模式（参照 edulab 的 `lesson.html` 和 `board.html`）：

- 模板文件是完整的 HTML，内嵌 Three.js/Canvas + KaTeX
- 预留 `__LESSON_DATA__` 占位符
- 后端将计算内核的结果 JSON 注入模板，生成完整课件
- 课件以独立 HTML 文件存储，可直接下载离线使用

前端 ResultPage 支持两种展示模式：
1. **在线渲染模式**：React 组件直接解析 JSON 数据，用 react-three-fiber 渲染
2. **iframe 嵌入模式**：直接加载服务端生成的完整 HTML 课件（支持下载）

---

## 五、数据库 Schema

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname VARCHAR(100),
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 题目表
CREATE TABLE problems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    image_url TEXT NOT NULL,                  -- 原始图片 URL
    image_thumbnail_url TEXT,                  -- 缩略图
    ocr_raw_text TEXT,                         -- PaddleOCR 原始结果
    ocr_confidence FLOAT,                      -- OCR 置信度
    structured_json JSONB,                     -- LLM 结构化结果
    status VARCHAR(50) DEFAULT 'uploaded',     -- uploaded/ocr_done/confirmed/computing/done/error
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 课件表
CREATE TABLE lessons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id UUID REFERENCES problems(id) UNIQUE,
    kernel_result JSONB NOT NULL,              -- sympy 计算结果
    html_content TEXT,                         -- 完整课件 HTML
    html_file_path TEXT,                       -- 课件文件路径
    subject VARCHAR(50),                       -- solid_geometry/analytic_geometry/algebra/chemistry
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 六、移动端适配方案

### 6.1 PWA 支持
- `manifest.json` 配置，支持添加到主屏幕
- Service Worker 缓存核心资源
- 全屏拍照体验

### 6.2 拍照上传
- 使用 `<input type="file" accept="image/*" capture="environment">` 调起后置摄像头
- 支持相册选择已有图片
- 上传前图片压缩（Canvas resize，限制最大 1920px，JPEG 质量 0.8）
- 支持拖拽裁剪区域

### 6.3 响应式设计
- Mobile First 设计原则
- Tailwind CSS 或 Ant Design Mobile
- 课件查看页支持横屏全屏模式

---

## 七、分阶段实施计划

### Phase 1：基础骨架 + 单学科 MVP（立体几何）
- [ ] 项目初始化：monorepo 结构、Docker 环境
- [ ] FastAPI 基础框架 + DB 模型
- [ ] React + Vite 项目搭建 + 基础路由
- [ ] 图片上传 API + 图片存储
- [ ] PaddleOCR 容器集成
- [ ] 立体几何计算内核（参照 edulab geometry_kernel.py + bodies.py）
- [ ] 3D 课件 HTML 模板（Three.js，参照 lesson.html）
- [ ] 基础拍照页 + 课件查看页
- [ ] Celery 异步任务链集成

### Phase 2：LLM 题目理解 + 题目确认
- [ ] LLM 服务集成（题目结构化 Prompt 工程）
- [ ] OCR 结果确认页（可编辑修正）
- [ ] 题目结构化 JSON Schema 定义

### Phase 3：学科扩展
- [ ] 解析几何/圆锥曲线计算内核 + 模板
- [ ] 代数方程计算内核 + 模板
- [ ] 化学反应计算内核 + 模板

### Phase 4：用户体验完善
- [ ] PWA 完整支持
- [ ] 历史记录 + 收藏
- [ ] 课件下载功能
- [ ] 用户反馈机制
- [ ] 性能优化（缓存、CDN）

---

## 八、核心设计原则（继承自 edulab）

1. **单源真理**：所有显示数值（答案、坐标、尺寸）均来自同一次 sympy 计算，确保一致性
2. **精确计算**：使用 sympy 符号计算，杜绝浮点近似误差（如 √6/3 而非 0.816）
3. **数据驱动模板**：计算内核产出纯 JSON 数据，注入通用模板，计算与渲染解耦
4. **离线可用**：生成的课件为单个 HTML，无外部依赖，任何浏览器可打开
5. **用户确认回路**：OCR → 回显确认 → 计算，防止识别错误传播

## 九、验证方案

1. **单元测试**：sympy 计算内核的正确性（对比已知答案）
2. **API 测试**：上传测试图片，验证完整链路
3. **E2E 测试**：Playwright 模拟手机拍照 → 课件展示全流程
4. **人工验证**：选取 20 道典型题目，对比人工解答与系统输出
