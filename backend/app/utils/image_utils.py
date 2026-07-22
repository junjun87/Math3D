import aiofiles
import aiofiles.os as aos
from PIL import Image, ImageFilter
import io


async def create_thumbnail(
    input_path: str,
    output_path: str,
    size: tuple[int, int] = (300, 300),
) -> bool:
    """创建缩略图。返回 True 表示成功，False 表示跳过（格式不支持）。"""
    try:
        async with aiofiles.open(input_path, "rb") as f:
            data = await f.read()

        if not data:
            return False

        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
        image.thumbnail(size, Image.LANCZOS)
        image.save(output_path, "JPEG", quality=85)
        return True
    except Exception:
        return False


async def compress_image(
    input_path: str,
    output_path: str,
    max_dimension: int = 1920,
    quality: int = 80,
) -> tuple[int, int]:
    """压缩图片，限制最大尺寸和质量。"""
    async with aiofiles.open(input_path, "rb") as f:
        data = await f.read()

    image = Image.open(io.BytesIO(data))
    image = image.convert("RGB")

    # 缩放
    w, h = image.size
    if max(w, h) > max_dimension:
        ratio = max_dimension / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        image = image.resize(new_size, Image.LANCZOS)

    image.save(output_path, "JPEG", quality=quality)
    return image.size


def preprocess_for_ocr(image_data: bytes) -> bytes:
    """[已废弃] OCR 预处理。

    此函数已被 ocr_service._preprocess_for_ocr() 替代。
    新实现：保留 RGB 色彩、不做 autocontrast、输出 PNG 无损格式。
    保留此函数仅为兼容旧调用方（当前无调用方）。
    """
    image = Image.open(io.BytesIO(image_data))
    image = image.convert("RGB")
    image = image.filter(ImageFilter.SHARPEN)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
