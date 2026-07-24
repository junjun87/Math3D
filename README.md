# Edulab MVP - 立体几何解题

最小可行产品：输入立体几何题面，后端用 sympy 精确计算，生成全屏可交互 Three.js 3D 解题网页，右上角一键下载 HTML。

## 当前支持题型

- 正方体：直线与平面所成角、异面直线夹角、点到平面距离
- 正四棱锥：直线与平面所成角
- 支持随机出题（随机题型 + 随机参数，自动筛除答案不规整的组合）
- 支持 LLM 自然语言题面解析（可选，通过环境变量配置）

## 项目结构

```
.
├── backend/
│   ├── app.py               # FastAPI 服务（生产模式同源托管前端）
│   ├── geometry_kernel.py   # sympy 精确计算核心 + 题型求解器
│   ├── solver_registry.py   # @register_solver 题型注册表
│   ├── llm_parser.py        # LLM 自然语言题面解析（可选）
│   ├── bodies.py            # 几何体拓扑库（顶点 + 棱）
│   ├── template.html        # Three.js 数据驱动模板
│   └── scripts/
│       └── generate.py      # CLI：直接生成解题 HTML 文件
├── frontend/
│   └── index.html           # 题面录入 + 预览 + 下载
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

**本地开发：** 直接用浏览器打开 `frontend/index.html`（需将 `API_BASE` 改为 `http://localhost:8000`），或用静态服务器：

```bash
cd frontend
python -m http.server 3000
```

然后访问 http://localhost:3000。

## Docker 部署

```bash
docker build -t edulab-mvp .
docker run -d -p 8000:8000 --name edulab edulab-mvp
```

可选的 LLM 题面解析通过环境变量配置：

```bash
docker run -d -p 8000:8000 \
  -e LLM_API_KEY=sk-xxx \
  -e LLM_BASE_URL=https://api.openai.com/v1 \
  -e LLM_MODEL=gpt-4o-mini \
  --name edulab edulab-mvp
```

## 使用流程

1. 输入或修改题目
2. 点击「生成解题页」→ 自动跳转至全屏 3D 交互解题页
3. 按「上一步/下一步」浏览解题过程，左侧公式与右侧 3D 高亮联动
4. 点击右上角「下载 HTML」保存自包含课件
5. 浏览器后退回到输入页

## 扩展下一个题型

1. 新增求解函数，用 `@register_solver("shape", "query")` 注册
2. 输出 `Solution`（problem、steps、answer_latex、answer_value、3D 坐标与元素）
3. 新几何体的坐标在 `geometry_kernel.py` 构建，拓扑在 `bodies.py` 定义
4. 模板数据驱动——无需修改 `template.html`

## 下一步建议

- 添加拍照 / 手写输入入口
- 扩展更多几何体（正四面体、三棱柱、球体）和题型（二面角、体积）
- 接入多模态 LLM 直接从图片解析题面
