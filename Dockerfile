# Math3D — 立体几何解题工具
# FastAPI + 前端静态文件 + PostgreSQL
FROM python:3.12-slim

WORKDIR /app

# 设置 Python 路径，使 backend 目录下的模块可以互相导入
ENV PYTHONPATH=/app/backend

# 替换为国内源（腾讯云 apt 镜像 + 阿里云 pip 镜像）
RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖（使用清华 pip 镜像）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制后端代码（前端由独立 nginx 容器托管）
COPY backend/ ./backend/

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

# 启动服务
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
