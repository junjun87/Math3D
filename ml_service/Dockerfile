# GPU 版本 — 需要 NVIDIA GPU 支持
FROM paddlepaddle/paddle:2.6.0-gpu-cuda11.8-cudnn8.9-trt8.5

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
