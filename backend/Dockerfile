FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（使用阿里云 apt 镜像加速）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（使用清华镜像加速）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 源码
COPY . .

# 创建上传和课件目录
RUN mkdir -p /app/uploads /app/lessons

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
