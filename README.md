# Math3D — AI 数理化拍照搜题 + 交互课件

📱 拍照/文字提交题目 → DeepSeek AI 识别 → SymPy 精确计算 → 3D/2D 交互课件 → 离线可回看

支持 **立体几何、解析几何、代数、化学** 四大科目，覆盖 **26 种题型**。

## 🚀 快速开始

```bash
git clone https://github.com/junjun87/Math3D.git
cd Math3D
cp .env.example .env          # 编辑 .env，填写 LLM_API_KEY
docker compose up -d           # 启动全部服务
```

访问：前端 `http://localhost:5173` | API 文档 `http://localhost:8000/docs`

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 📷 拍照搜题 | 手机拍照 → 阿里云 OCR 识别文字 |
| ⌨️ 文字输入 | 直接输入题目，跳过 OCR |
| 🧠 AI 结构化 | DeepSeek LLM 自动识别科目/题型/已知条件 |
| 🔢 精确计算 | SymPy 符号引擎，输出精确值（1/3 而非 0.333） |
| 🎮 3D 课件 | 立体几何 Three.js 可旋转/缩放/顶点标注 |
| 📊 分步解析 | 所有科目提供详细解题步骤 + KaTeX 公式 |
| 📲 PWA | 添加到主屏幕，课件离线回看，像原生 App |

### 支持的科目与题型（26 种）

| 学科 | 题型 |
|------|------|
| 🔷 立体几何 | 线面角、二面角、异面直线夹角、点面距离、体积、表面积 — 支持正方体/长方体/棱锥/棱柱/四面体/圆柱/圆锥 |
| 📐 解析几何 | 直线方程、圆的方程、椭圆方程、双曲线方程、抛物线方程、距离计算、交点求解 |
| 📝 代数 | 一元一次方程、一元二次方程、方程组、不等式、数列、因式分解、函数性质分析 |
| ⚗️ 化学 | 方程式配平、物质的量计算、浓度计算、pH 计算、气体定律、化学计量 |

### 示例

```
立体几何: 正方体棱长2，求二面角A1-BD-C1 → cosθ = 1/3 + 3D旋转展示
解析几何: 过点(2,1)⊥直线3x-4y+5=0 → 4x+3y-11=0 + 分步
代   数: x²-5x+6=0 → x=2 或 x=3 + 判别式推导
化   学: Fe+O₂→Fe₃O₄ → 3Fe+2O₂→Fe₃O₄ + 矩阵求解
```

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS |
| 3D | Three.js |
| 公式 | KaTeX |
| 后端 | Python FastAPI + Celery |
| AI | DeepSeek API（兼容 Anthropic 格式） |
| 计算引擎 | SymPy |
| OCR | 阿里云 OCR API |
| 数据库 | PostgreSQL 16 + Redis 7 |
| 部署 | Docker Compose |

## 📁 项目结构

```
Math3D/
├── frontend/          # React SPA (PWA, 移动端优先)
├── backend/           # FastAPI + Celery Worker
│   └── app/
│       ├── api/       # 路由 (upload, problems, lessons, users)
│       ├── kernels/   # 计算内核 (geometry/analytic/algebra/chemistry)
│       └── services/  # LLM/Render 服务
└── docker-compose.yml
```

## 🔌 API 关键端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/problems/upload` | 上传图片 |
| POST | `/api/v1/problems/text` | 提交文字题目 |
| GET | `/api/v1/problems/{id}/ocr` | 轮询 OCR 结果 |
| POST | `/api/v1/problems/{id}/confirm` | 确认 OCR → 触发计算 |
| GET | `/api/v1/problems/{id}/lesson` | 获取课件结果 |
| GET | `/api/v1/lessons/{id}/view` | 查看课件 HTML |
| GET | `/api/v1/lessons/{id}/download` | 下载课件文件 |

## 🔧 开发

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev

# Worker
cd backend && celery -A app.tasks.celery_app worker --loglevel=info

# 数据库迁移
cd backend && alembic upgrade head
```

## 📊 当前状态

- [x] 立体几何内核（7 种几何体 / 6 种题型）
- [x] 解析几何内核（7 种题型）
- [x] 代数内核（7 种题型）
- [x] 化学内核（6 种题型）
- [x] DeepSeek LLM 多学科结构化识别
- [x] Celery 异步任务链全链路联调
- [x] 3D 交互课件 + 通用 KaTeX 课件
- [x] PWA 离线支持 + 添加到主屏幕
- [x] Docker 一键部署

## 📄 License

MIT
