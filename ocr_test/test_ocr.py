"""
OCR 最小化测试 — 直接在服务器上运行，不依赖 Docker。
用法: python3 test_ocr.py /path/to/image.jpg
"""

import sys, os, json, base64, io

def test_ocr(image_path: str) -> dict:
    # 1. 读取图片，统一转为 JPEG
    from PIL import Image
    img = Image.open(image_path)
    print(f"[1] 原始图片: {img.size}, mode={img.mode}, format={img.format}")

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > 2048:
        ratio = 2048 / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        print(f"[2] 缩放到: {img.size}")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    img_bytes = buf.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode()
    print(f"[3] JPEG 大小: {len(img_bytes) / 1024:.0f}KB, base64 长度: {len(img_b64)}")

    # 2. 调用阿里云 OCR
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    ak_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    ak_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

    if not ak_id:
        print("ERROR: 请设置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID / _SECRET")
        sys.exit(1)

    config = OcrConfig(
        access_key_id=ak_id,
        access_key_secret=ak_secret,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
    )
    client = Client(config)

    # 方法A: base64
    req = RecognizeGeneralRequest(
        body=json.dumps({"ImageBase64": img_b64}, ensure_ascii=False),
    )
    print("[4] 调用 OCR API (base64)...")
    resp = client.recognize_general(req)
    data = resp.body.to_map()

    # 方法B: 如果A失败，用 URL
    # (后续测试可切换)

    print(f"[5] 响应: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
    content = data.get("Data", {}).get("Content", "")
    print(f"[6] 识别结果:\n{content}")

    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 test_ocr.py <图片路径>")
        sys.exit(1)

    # 从 .env 加载环境变量
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    test_ocr(sys.argv[1])
