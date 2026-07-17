# Math3D — 拍照搜题 + AI 解析 + 交互课件

拍照上传数学/化学题目，AI 视觉识别 + sympy 精确计算，生成内嵌 Three.js 的交互式 3D/2D 课件。

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> && cd Math3D

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填写 LLM_API_KEY

# 3. 启动服务（CPU 模式）
docker compose up -d

# 4. 访问
# 前端: http://localhost:5173
# 后端 API 文档: http://localhost:8000/docs
```

## 📁 项目结构

```
Math3D/
├── frontend/          # React + Vite + TypeScript 前端 (PWA)
├── backend/           # Python FastAPI 后端
├── ml_service/        # PaddleOCR 推理服务
├── scripts/           # 运维脚本
├── docs/              # 文档
└── docker-compose.yml # 一键部署配置
```

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS |
| 3D 渲染 | Three.js (react-three-fiber) |
| 数学公式 | KaTeX |
| 后端 | Python FastAPI + Uvicorn |
| OCR | PaddleOCR (PP-OCRv5) |
| LLM | Claude API |
| 计算引擎 | SymPy |
| 数据库 | PostgreSQL + Redis |
| 任务队列 | Celery |

## 📖 开发指南

```bash
# 后端开发
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# 前端开发
cd frontend
npm install
npm run dev

# 数据库迁移
cd backend
alembic upgrade head
```

## 📄 License

MIT
