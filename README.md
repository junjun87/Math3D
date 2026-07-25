# Math3D — 立体几何交互解题

最小可行产品：📷 拍照/相册/文字输入立体几何题面 → 阿里云教育 OCR（按次计费）+ DeepSeek 文字规范化 → sympy 精确计算 → 全屏可交互 Three.js 3D 解题网页，右上角一键下载 HTML。

## 当前支持题型

- 正方体：直线与平面所成角、异面直线夹角、点到平面距离
- 正四棱锥：直线与平面所成角
- 支持随机出题（随机题型 + 随机参数，自动筛除答案不规整的组合）
- 支持 LLM 自然语言题面解析（可选，通过环境变量配置）
- 支持拍照 OCR：阿里云文字识别（教育场景题目识别）+ DeepSeek LLM 规范化

## 项目结构

```
.
├── backend/
│   ├── app.py               # FastAPI 服务（/api/solve + /api/ocr + 同源托管前端）
│   ├── geometry_kernel.py   # sympy 精确计算核心 + 题型求解器
│   ├── solver_registry.py   # @register_solver 题型注册表
│   ├── llm_parser.py        # 阿里云 OCR + DeepSeek 题面解析与规范化
│   ├── bodies.py            # 几何体拓扑库（顶点 + 棱）
│   ├── template.html        # Three.js 数据驱动模板
│   └── scripts/
│       └── generate.py      # CLI：直接生成解题 HTML 文件
├── frontend/
│   └── index.html           # 多页面 UI（拍照/相册/文字/历史）
├── docker-compose.yml       # Docker Compose 一键部署
├── .env.example             # 阿里云 OCR + LLM 配置模板
├── Dockerfile               # Docker 镜像构建
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 创建并激活虚拟环境

```bash
python -m venv .venv
# Windows (Git Bash)
source .venv/Scripts/activate
# macOS / Linux
source .venv/bin/activate
```

### 2. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 3. 启动后端

```bash
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 打开前端

**Docker 部署（推荐）：** 后端同源托管前端，访问 `http://localhost:8000` 即可。

**本地开发：** 启动后端后访问 `http://localhost:8000`（FastAPI 已同源托管前端静态文件），或直接打开 `frontend/index.html`（浏览器需允许 `file://` 跨域请求）。

## Docker 部署

```bash
# 1. 配置 OCR + LLM（可选，不配置则 OCR 不可用，题面解析降级为关键词匹配）
cp .env.example .env
# 编辑 .env 填入阿里云 AccessKey + DeepSeek API 密钥

# 2. 启动
docker compose up -d

# 3. 更新
docker compose up -d --build
```

## 使用流程

1. 📷 **拍照搜题** / 🖼️ 从相册选择 / ⌨️ 文字输入 — 三种方式提交题目
2. 阿里云 OCR 自动识别题目文字 + DeepSeek 修复数学符号（拍照模式）
3. 点击「生成解题页」→ 自动跳转至全屏 3D 交互解题页
4. 按「上一步/下一步」浏览解题过程，左侧公式与右侧 3D 高亮联动
5. 点击右上角「下载 HTML」保存自包含课件
6. 浏览器后退回到输入页

## 扩展下一个题型

1. 新增求解函数，用 `@register_solver("shape", "query")` 注册
2. 输出 `Solution`（problem、steps、answer_latex、answer_value、3D 坐标与元素）
3. 新几何体的坐标在 `geometry_kernel.py` 构建，拓扑在 `bodies.py` 定义
4. 模板数据驱动——无需修改 `template.html`

## 下一步建议

- 扩展更多几何体（正四面体、三棱柱、球体）和题型（二面角、体积）
- 支持手写输入 / 草图画图识别
- 增加历史记录云端同步
