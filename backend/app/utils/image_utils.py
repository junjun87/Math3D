import aiofiles
import aiofiles.os as aos
from PIL import Image, ImageEnhance, ImageFilter
import io


async def create_thumbnail(
    input_path: str,
    output_path: str,
    size: tuple[int, int] = (300, 300),
) -> None:
    """创建缩略图。"""
    async with aiofiles.open(input_path, "rb") as f:
        data = await f.read()

    image = Image.open(io.BytesIO(data))
    image = image.convert("RGB")
    image.thumbnail(size, Image.LANCZOS)
    image.save(output_path, "JPEG", quality=85)


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
    """OCR 预处理：灰度化、增强对比度、降噪。"""
    image = Image.open(io.BytesIO(image_data))
    image = image.convert("L")  # 灰度化

    # 增强对比度
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # 锐化
    image = image.filter(ImageFilter.SHARPEN)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
