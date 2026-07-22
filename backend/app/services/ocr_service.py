"""阿里云 OCR 题目识别服务。"""

import json
import logging
import os

from app.config import get_settings

logger = logging.getLogger("ocr_service")
settings = get_settings()


class OCRServiceError(RuntimeError):
    """题目识别失败。"""


async def recognize_text(image_path: str) -> dict:
    """识别图片中的题目文字（阿里云 OCR）。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info("OCR image: %s, size=%d bytes", image_path, os.path.getsize(image_path))

    if not settings.ALIBABA_CLOUD_ACCESS_KEY_ID or not settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET:
        raise OCRServiceError("Alibaba Cloud OCR credentials not configured")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as error:
        raise OCRServiceError(f"Failed to read image: {error}") from error

    ocr_bytes = _preprocess_for_ocr(image_bytes)
    try:
        result = _call_aliyun_edu_ocr(ocr_bytes)
    except Exception as edu_error:
        logger.warning("Alibaba Edu OCR failed: %s; falling back to General", edu_error)
        try:
            result = _call_aliyun_general_ocr(ocr_bytes)
        except Exception as gen_error:
            raise OCRServiceError("All OCR methods failed") from gen_error

    # LLM 后处理：修正 OCR 残留的 LaTeX/数学符号错误
    raw_text = result.get("raw_text", "")
    if raw_text:
        try:
            from app.services.llm_service import clean_ocr_with_llm
            cleaned = await clean_ocr_with_llm(raw_text)
            if cleaned and cleaned != raw_text:
                logger.info("LLM cleanup improved OCR text")
                result["raw_text"] = cleaned
                result["llm_cleaned"] = True
        except Exception as exc:
            logger.warning("LLM OCR cleanup error (ignored): %s", exc)

    return result


# ─── 阿里云 OCR（fallback）────────────────────────────────────

def _preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """OCR 预处理：RGB 保留 + 轻量锐化（经验证有效）。

    设计原则（阿里云文档 + 实验验证）：
    - 保留 RGB 色彩 — API 模型在彩色图像上训练，灰度化降低 recClassify 公式检测
    - 不做 autocontrast — API 已内置图像增强（反光/扭曲/模糊自动处理）
    - 轻量锐化 — 实践证明提升文字/符号边缘清晰度，API 内置增强不会与之冲突
    - 输出 JPEG q98（近无损）— PNG 体积膨胀易超 API 10MB 限制
    """
    from PIL import Image, ImageFilter
    import io as pil_io

    img = Image.open(pil_io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = img.filter(ImageFilter.SHARPEN)
    buf = pil_io.BytesIO()
    img.save(buf, format="JPEG", quality=98)
    result = buf.getvalue()
    logger.info("OCR preprocess: RGB %dx%d + sharpen -> %d bytes (JPEG q98)", img.size[0], img.size[1], len(result))
    return result


def _create_aliyun_client():
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_tea_openapi.models import Config as OcrConfig

    config = OcrConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
        read_timeout=30000,
        connect_timeout=10000,
    )
    return Client(config)


def _get_result_data(response) -> dict:
    raw = response.body.data
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise OCRServiceError(f"Unexpected response data type: {type(raw).__name__}")


def _clean_edu_formula_latex(formula: str) -> str:
    """清理 EduFormula 返回的 LaTeX 字符串。

    EduFormula 输出示例：
      y = \\sqrt { \\frac { \\left( x - 1 \\right) \\cos 2 x }
               { \\left( 2 x + 3 \\right) \\left( 3 - 4 x \\right) } }

    问题：
    - 命令和括号间有多余空格：\\sqrt { → \\sqrt{
    - \\left ( → \\left(
    - 花括号内部前后有空格：{ x - 1 } → {x - 1}
    """
    import re

    # 1. LaTeX 命令后的空格：\\sqrt { → \\sqrt{，\\frac { → \\frac{
    #    匹配 \\命令名 后跟空格+{
    formula = re.sub(r'(\\[a-zA-Z]+)\s+\{', r'\1{', formula)

    # 2. \\left ( → \\left(，\\right ) → \\right)
    for cmd in (r'\\left', r'\\right', r'\\big', r'\\Big', r'\\bigg', r'\\Bigg',
                r'\\biggl', r'\\biggr', r'\\Biggl', r'\\Biggr', r'\\bigl', r'\\bigr'):
        formula = re.sub(rf'({cmd})\s+\(', r'\1(', formula)
        formula = re.sub(rf'({cmd})\s+\)', r'\1)', formula)
        formula = re.sub(rf'({cmd})\s+\[', r'\1[', formula)
        formula = re.sub(rf'({cmd})\s+\]', r'\1]', formula)
        formula = re.sub(rf'({cmd})\s+\.', r'\1.', formula)
        formula = re.sub(rf'({cmd})\s+\\\{{', r'\1\\{', formula)
        formula = re.sub(rf'({cmd})\s+\\\}}', r'\1\\}', formula)
        formula = re.sub(rf'({cmd})\s+\\\|', r'\1\\|', formula)

    # 3. 花括号内部前后空格：{ x-1 } → {x-1}
    formula = re.sub(r'\{\s+', '{', formula)
    formula = re.sub(r'\s+\}', '}', formula)

    # 4. 残留多余空格（不影响 LaTeX 命令的空格）：多个空格 → 单个
    formula = re.sub(r'  +', ' ', formula)

    return formula.strip()


def _call_aliyun_edu_formula(image_bytes: bytes) -> str | None:
    """调用阿里云印刷体数学公式识别 API，返回 LaTeX 字符串。

    RecognizeEduFormula 是公式专用识别接口，官方宣称 98% 准确率，
    对根号、分数、上下标等复杂公式结构的识别优于 RecognizeEduQuestionOcr。
    图片限制：长宽 < 1024px。
    """
    from alibabacloud_ocr_api20210707.models import RecognizeEduFormulaRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    try:
        logger.info("Calling RecognizeEduFormula (%d bytes)", len(image_bytes))
        request = RecognizeEduFormulaRequest(body=image_bytes)
        runtime = RuntimeOptions()
        response = _create_aliyun_client().recognize_edu_formula_with_options(request, runtime)
        data = _get_result_data(response)
        formula = (data.get("content") or "").strip()
        if formula:
            logger.info("EduFormula result: %s", formula[:120])
        return formula or None
    except Exception as exc:
        logger.warning("RecognizeEduFormula failed: %s", exc)
        return None


def _crop_formula_region(image_bytes: bytes, bbox: list) -> bytes | None:
    """从原图中裁剪公式区域，用于 EduFormula 二次精识别。

    bbox 格式：顺时针四点 [{x,y}, {x,y}, {x,y}, {x,y}]（左上、右上、右下、左下）。
    返回裁剪并缩放到 ≤1024px 的 PNG 字节，失败返回 None。
    """
    from PIL import Image
    import io as pil_io

    if not bbox or len(bbox) < 4:
        return None
    try:
        img = Image.open(pil_io.BytesIO(image_bytes))
        # 从四点坐标计算外接矩形
        xs = [p.get("x", 0) for p in bbox]
        ys = [p.get("y", 0) for p in bbox]
        left, top = int(min(xs)), int(min(ys))
        right, bottom = int(max(xs)), int(max(ys))
        # 扩展 40px 边距给公式周围留上下文（根号上横线、大括号、积分号等高符号需要更多空间）
        pad = 40
        left = max(0, left - pad)
        top = max(0, top - pad)
        right = min(img.size[0], right + pad)
        bottom = min(img.size[1], bottom + pad)
        if right <= left or bottom <= top:
            return None
        crop = img.crop((left, top, right, bottom))
        # 缩放到 ≤1024px（EduFormula API 限制）
        w, h = crop.size
        if max(w, h) > 1024:
            ratio = 1024 / max(w, h)
            crop = crop.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = pil_io.BytesIO()
        crop.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Crop formula region failed: %s", exc)
        return None


def _get_block_rect(bbox: list) -> tuple[int, int, int, int] | None:
    """从四点 bbox 提取外接矩形 (x, y, w, h)。失败返回 None。"""
    if not bbox or len(bbox) < 4:
        return None
    try:
        xs = [p.get("x", 0) for p in bbox]
        ys = [p.get("y", 0) for p in bbox]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - x), int(max(ys) - y)
        return (x, y, w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def _rect_overlap_ratio(rect_a: tuple, rect_b: tuple) -> float:
    """计算两个矩形 (x, y, w, h) 的交集占 rect_a 面积的比例。"""
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    # 交集
    ix = max(ax, bx)
    iy = max(ay, by)
    iw = min(ax + aw, bx + bw) - ix
    ih = min(ay + ah, by + bh) - iy
    if iw <= 0 or ih <= 0:
        return 0.0
    intersection = iw * ih
    area_a = aw * ah
    return intersection / area_a if area_a > 0 else 0.0


def _merge_bboxes(bbox_a: list, bbox_b: list) -> list | None:
    """合并两个四点 bbox，返回能包住两者的最小外接矩形四点。

    每个 bbox 格式：顺时针四点 [{x,y}, {x,y}, {x,y}, {x,y}]。
    返回格式相同（外接矩形的四角）。
    """
    if not bbox_a or not bbox_b:
        return bbox_a or bbox_b
    try:
        all_xs = [p.get("x", 0) for p in bbox_a + bbox_b]
        all_ys = [p.get("y", 0) for p in bbox_b + bbox_a]
        left, right = min(all_xs), max(all_xs)
        top, bottom = min(all_ys), max(all_ys)
        return [
            {"x": left, "y": top},
            {"x": right, "y": top},
            {"x": right, "y": bottom},
            {"x": left, "y": bottom},
        ]
    except Exception:
        return bbox_a


def _group_nearby_formula_blocks(blocks: list) -> list[list[int]]:
    """将物理位置邻近的公式块分组，以便合并裁剪区域送 EduFormula。

    两个公式块视为"邻近"的条件：
    - 水平间距 < 50px 且垂直重叠 > 40%（同行相邻）
    - 或垂直间距 < 30px 且水平重叠 > 30%（邻行对齐）

    返回分组后的索引列表，每个元素是一个索引组（已排序）。
    """
    # 收集有 bbox 的公式块索引和 rect
    formula_entries = []
    for i, b in enumerate(blocks):
        if b.get("is_formula") and b.get("bbox"):
            rect = _get_block_rect(b["bbox"])
            if rect:
                formula_entries.append((i, rect))

    if len(formula_entries) <= 1:
        return [[i] for i, _ in formula_entries] if formula_entries else []

    # 并查集分组
    n = len(formula_entries)
    parent = list(range(n))

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for a_idx in range(n):
        ai, ar = formula_entries[a_idx]
        ax, ay, aw, ah = ar
        for b_idx in range(a_idx + 1, n):
            bi, br = formula_entries[b_idx]
            bx, by, bw, bh = br

            # 水平邻近：同行，间距 < 50px
            h_gap = max(0, bx - (ax + aw)) if bx >= ax else max(0, ax - (bx + bw))
            v_overlap = min(ay + ah, by + bh) - max(ay, by)
            v_overlap_ratio = v_overlap / min(ah, bh) if min(ah, bh) > 0 else 0

            if h_gap < 50 and v_overlap_ratio > 0.4:
                _union(a_idx, b_idx)
                continue

            # 垂直邻近：邻行，间距 < 30px
            v_gap = max(0, by - (ay + ah)) if by >= ay else max(0, ay - (by + bh))
            h_overlap = min(ax + aw, bx + bw) - max(ax, bx)
            h_overlap_ratio = h_overlap / min(aw, bw) if min(aw, bw) > 0 else 0

            if v_gap < 30 and h_overlap_ratio > 0.3:
                _union(a_idx, b_idx)

    # 按根节点分组
    groups_dict = {}
    for i in range(n):
        root = _find(i)
        groups_dict.setdefault(root, []).append(formula_entries[i][0])

    # 每组内按原列表顺序排序
    groups = []
    for indices in groups_dict.values():
        indices.sort()
        groups.append(indices)

    # 按组内首个索引排序（保持阅读顺序）
    groups.sort(key=lambda g: g[0])

    if len(groups) < len(formula_entries):
        logger.info(
            "Formula grouping: %d blocks → %d groups", len(formula_entries), len(groups)
        )

    return groups


def _contains_chinese(text: str) -> bool:
    """检测文本是否包含中文字符。"""
    import re
    return bool(re.search(r'[一-鿿　-〿＀-￯]', text))


def _sanitize_formula_for_edu(text: str) -> str:
    """从 OCR 公式文本中移除中文/标点，提取纯数学部分送给 EduFormula。

    EduFormula 是纯公式识别 API，遇到中文字符会输出乱码。
    此函数移除中文、中文标点、全角符号，只保留 ASCII 数学符号和 LaTeX 命令。
    """
    import re
    # 移除中文字符、中文标点（、，。：；！？（）【】《》等）
    cleaned = re.sub(r'[一-鿿　-〿＀-￯]', '', text)
    # 移除中文标点（保留 · 作为数学乘点、～ 作为波浪号）
    cleaned = re.sub(r'[，。：；！？「」『』【】《》…—＠＃＄％＾＆＊]', '', cleaned)
    # 中文括号替换为英文（可能包裹数学表达式）
    cleaned = cleaned.replace('（', '(').replace('）', ')')
    cleaned = cleaned.replace('［', '[').replace('］', ']')
    # 全角竖线替换为半角（可能是绝对值符号）
    cleaned = cleaned.replace('｜', '|')
    # 清理多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _is_non_question_text(text: str, rect: tuple | None) -> bool:
    """判断文本块是否为非题目内容（习题标题、页码、图例标识等），应过滤掉。"""
    import re
    # 习题章节标题：√...练、○...练 等模式
    # 限制：√/○ 后跟 1-6 个中文/空白字符再跟"练/训/测/题"（防止误杀数学 √ 符号）
    if re.match(r'^[√○]\s*[一-鿿\s]{1,6}(练|训|测|题)$', text):
        return True
    # 图表/示例标识：图1、图2-1、如图、示例1、例1、(第x题图) 等
    if re.match(r'^[（(]?第?\s*\d+[）)]?\s*题[图圖]?[）)]?$', text):
        return True
    if re.match(r'^[（(]?图[圖]?\s*\d[\d\-.]*[）)]?$', text):
        return True
    if re.match(r'^[（(]?如[图圖右左上下][所]?[示]?[）)]?$', text):
        return True
    if re.match(r'^(示例|例)\s*\d+[：:]*$', text):
        return True
    # 纯数字页码（位于页面边缘的小字）
    if re.match(r'^\d{1,3}$', text) and rect:
        _, y, _, h = rect
        # 页码通常在页面顶部或底部
        if y < 100 or y > 3000:
            return True
    # 极短且低置信的孤立符号
    if len(text) <= 1 and not text.isalnum():
        return True
    return False


def _call_aliyun_edu_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeEduQuestionOcrRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeEduQuestionOcr")
    request = RecognizeEduQuestionOcrRequest(body=image_bytes, need_rotate=True)
    runtime = RuntimeOptions()
    response = _create_aliyun_client().recognize_edu_question_ocr_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("content", "").strip()
    words_info = data.get("prism_wordsInfo", []) or []

    # ── 解析图案（图表）区域 ──
    figures = data.get("figure", []) or []
    figure_rects = []
    for fig in figures:
        x = fig.get("x", 0)
        y = fig.get("y", 0)
        w = fig.get("w", 0)
        h = fig.get("h", 0)
        if w > 0 and h > 0:
            figure_rects.append((int(x), int(y), int(w), int(h)))
    if figure_rects:
        logger.info("Detected %d figure region(s) in question image", len(figure_rects))

    # ── 提取文字块，过滤图表区域 + 非题目内容 ──
    text_blocks = []
    skipped_figure = 0
    skipped_non_q = 0
    for item in words_info:
        word = item.get("word", "").strip()
        if not word:
            continue
        prob = item.get("prob", 95)
        bbox = item.get("pos", [])
        rect = _get_block_rect(bbox)

        # 过滤：与图表区域重叠 > 50% 的文字块（图表内的标注，不是题目正文）
        if rect and figure_rects:
            in_figure = any(_rect_overlap_ratio(rect, fr) > 0.5 for fr in figure_rects)
            if in_figure:
                skipped_figure += 1
                logger.debug("Skip figure text: %r", word[:40])
                continue

        # 过滤：非题目内容（章节标题、页码等）
        if _is_non_question_text(word, rect):
            skipped_non_q += 1
            logger.debug("Skip non-question text: %r", word[:40])
            continue

        text_blocks.append({
            "text": word,
            "confidence": float(prob) / 100.0,
            "is_formula": item.get("recClassify", 0) == 51,
            "bbox": bbox,
        })

    if skipped_figure or skipped_non_q:
        logger.info("Filtered: %d figure-annotation + %d non-question block(s)",
                     skipped_figure, skipped_non_q)

    # 合并相邻同类块，避免公式被切成碎片（如 C_1 = 6 切成 $$C_1$$$$=$$$$6$$）
    merged = []
    for b in text_blocks:
        if merged and merged[-1]["is_formula"] == b["is_formula"]:
            # 文本块用空格连接；公式块直接拼接（避免空格破坏 LaTeX 语法如 a ^2）
            sep = "" if b["is_formula"] else " "
            merged[-1]["text"] += sep + b["text"]
            # 合并置信度取平均
            merged[-1]["confidence"] = (merged[-1]["confidence"] + b["confidence"]) / 2
            # 合并 bbox — 确保 EduFormula 裁剪区域覆盖完整公式
            merged[-1]["bbox"] = _merge_bboxes(merged[-1].get("bbox", []), b.get("bbox", []))
        else:
            merged.append(dict(b))

    # 对所有公式块调用 EduFormula 二次精识别，获取规范 LaTeX
    # （EduQuestionOcr 即使高置信度也输出纯文本如 a/b，EduFormula 输出 \frac{a}{b}，98% 准确率）
    #
    # 先按物理位置分组：邻近的公式块可能属于同一个公式表达式，
    # 合并 bbox 后一次性送 EduFormula，减少碎片化识别错误
    formula_groups = _group_nearby_formula_blocks(merged)
    formula_enhanced = 0
    formula_skipped_chinese = 0
    formula_skipped_short = 0
    for group in formula_groups:
        # 检查组内文本是否有中文
        group_text = "".join(merged[idx]["text"] for idx in group)
        has_chinese = any('一' <= c <= '鿿' or '　' <= c <= '〿' or '＀' <= c <= '￯'
                         for c in group_text)
        if has_chinese:
            # 剔除非中文部分后再尝试 EduFormula（中文会影响 API 识别精度）
            for idx in group:
                sanitized = _sanitize_formula_for_edu(merged[idx]["text"])
                if sanitized and len(sanitized) >= 3:
                    # 保存原始文本，用清洗后的纯数学部分送 EduFormula
                    pass  # 继续下面的流程
            # 如果清洗后仍有足够长的纯公式部分，尝试 EduFormula
            clean_group_text = "".join(
                _sanitize_formula_for_edu(merged[idx]["text"]) for idx in group
            )
            if not clean_group_text or len(clean_group_text) < 3:
                formula_skipped_chinese += len(group)
                continue
            # 有可用的纯公式部分，继续（不跳过）
            group_text = clean_group_text  # 用于后续阈值检查

        if len(group) == 1:
            b = merged[group[0]]
            if not b.get("bbox"):
                continue
            # 用清洗后的文本判断裁剪是否有意义
            clean_text = _sanitize_formula_for_edu(b["text"])
            if not clean_text or len(clean_text) < 3:
                continue
            crop_bytes = _crop_formula_region(image_bytes, b["bbox"])
        else:
            # 多个邻近公式块 → 合并 bbox 为一个大的裁剪区域
            combined_bbox = _merge_bboxes(merged[group[0]]["bbox"], merged[group[1]]["bbox"])
            for idx in group[2:]:
                combined_bbox = _merge_bboxes(combined_bbox, merged[idx]["bbox"])
            crop_bytes = _crop_formula_region(image_bytes, combined_bbox)

        if crop_bytes:
            better = _call_aliyun_edu_formula(crop_bytes)
            # 对合并组，取组内原文字总长度作为阈值参考
            orig_len = sum(len(merged[idx]["text"]) for idx in group)
            if better and len(better) >= orig_len * 0.3:
                cleaned = _clean_edu_formula_latex(better)
                logger.info("EduFormula enhanced (group=%d): %r -> %r",
                           len(group),
                           " + ".join(merged[idx]["text"][:40] for idx in group),
                           cleaned[:80])
                # 将结果写入组内第一个公式块，其余标记为空
                merged[group[0]]["text"] = cleaned
                merged[group[0]]["confidence"] = max(merged[group[0]]["confidence"], 0.95)
                for idx in group[1:]:
                    merged[idx]["text"] = ""
                    merged[idx]["confidence"] = 0
                formula_enhanced += len(group)
            elif has_chinese:
                # EduFormula 失败，回退：剔除中文/标点（保留纯数学部分）
                for idx in group:
                    sanitized = _sanitize_formula_for_edu(merged[idx]["text"])
                    if sanitized and len(sanitized) >= 3:
                        merged[idx]["text"] = sanitized
                formula_skipped_chinese += len(group)
    # 清理被清空的公式块
    merged = [b for b in merged if b["text"].strip()]

    if formula_enhanced or formula_skipped_chinese:
        logger.info("EduFormula: %d enhanced + %d skipped (Chinese-mixed) in %d group(s)",
                     formula_enhanced, formula_skipped_chinese, len(formula_groups))

    raw_text = "".join(
        f"$${b['text']}$$" if b["is_formula"] else b["text"]
        for b in merged
    ) if merged else content

    if not raw_text:
        raise OCRServiceError("Alibaba Edu OCR returned no text")

    raw_text = _clean_ocr_text(raw_text)
    confidence = sum(b["confidence"] for b in text_blocks) / len(text_blocks) if text_blocks else 0.99
    logger.info("Edu OCR: %d blocks, conf=%.3f, text=%s", len(text_blocks), confidence, raw_text[:200])
    return {"raw_text": raw_text, "text_blocks": text_blocks, "confidence": round(confidence, 4)}


def _global_symbol_cleanup(text: str) -> str:
    """全局数学符号 → LaTeX 转换（不区分是否在 $$ 块内）。

    OCR 经常不会将所有数学符号标记为公式块，导致 ∠、°、√、₁ 等
    以纯文本形式存在。这一步在所有 $$ 处理之前运行，确保这些符号
    无论出现在哪里都能被正确转换。

    Returns:
        转换后的文本（Unicode 数学符号已替换为 LaTeX 命令）。
    """
    import re

    # ── Unicode 下标数字：₀₁₂₃₄₅₆₇₈₉ → _{0} _{1} ... _{9} ──
    SUBSCRIPTS = str.maketrans({
        '₀': '_{0}', '₁': '_{1}', '₂': '_{2}', '₃': '_{3}', '₄': '_{4}',
        '₅': '_{5}', '₆': '_{6}', '₇': '_{7}', '₈': '_{8}', '₉': '_{9}',
    })
    text = text.translate(SUBSCRIPTS)

    # ── Unicode 上标数字：⁰¹²³⁴⁵⁶⁷⁸⁹ → ^{0} ^{1} ... ^{9} ──
    SUPERSCRIPTS = str.maketrans({
        '⁰': '^{0}', '¹': '^{1}', '²': '^{2}', '³': '^{3}', '⁴': '^{4}',
        '⁵': '^{5}', '⁶': '^{6}', '⁷': '^{7}', '⁸': '^{8}', '⁹': '^{9}',
    })
    text = text.translate(SUPERSCRIPTS)

    # ── 上标字符（常用，非数字）：ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖ ʳˢᵗᵘᵛʷˣʸᶻ ──
    SUPERSCRIPT_LETTERS = str.maketrans({
        'ᵃ': '^{a}', 'ᵇ': '^{b}', 'ᶜ': '^{c}', 'ᵈ': '^{d}', 'ᵉ': '^{e}',
        'ᶠ': '^{f}', 'ᵍ': '^{g}', 'ʰ': '^{h}', 'ⁱ': '^{i}', 'ʲ': '^{j}',
        'ᵏ': '^{k}', 'ˡ': '^{l}', 'ᵐ': '^{m}', 'ⁿ': '^{n}', 'ᵒ': '^{o}',
        'ᵖ': '^{p}', 'ʳ': '^{r}', 'ˢ': '^{s}', 'ᵗ': '^{t}', 'ᵘ': '^{u}',
        'ᵛ': '^{v}', 'ʷ': '^{w}', 'ˣ': '^{x}', 'ʸ': '^{y}', 'ᶻ': '^{z}',
    })
    text = text.translate(SUPERSCRIPT_LETTERS)

    # ── 度数符号：30° → 30^{\\circ}（全局） ──
    text = re.sub(r'(\d+)\s*°', r'\1^{\\circ}', text)
    text = re.sub(r'(\d+)\s*deg\b', r'\1^{\\circ}', text)

    # ── 根号 √（Unicode 字符） → \\sqrt ──
    text = re.sub(r'√', r'\\sqrt', text)

    # ── 角度符号 ∠ → \\angle ──
    text = re.sub(r'∠', r'\\angle ', text)

    # ── 其他高优先级 Unicode 符号（不依赖公式块检测） ──
    GLOBAL_UNICODE_MAP = [
        # 希腊字母（最常被 OCR 漏标为公式的）
        (r'Δ', r'\\Delta '), (r'θ', r'\\theta '), (r'π', r'\\pi '),
        (r'α', r'\\alpha '), (r'β', r'\\beta '), (r'γ', r'\\gamma '),
        (r'λ', r'\\lambda '), (r'μ', r'\\mu '), (r'σ', r'\\sigma '),
        (r'φ', r'\\phi '), (r'ω', r'\\omega '), (r'Σ', r'\\Sigma '),
        (r'Ω', r'\\Omega '), (r'δ', r'\\delta '), (r'ε', r'\\varepsilon '),
        (r'ρ', r'\\rho '),
        # 关系符号
        (r'⊥', r'\\perp '), (r'∥', r'\\parallel '),
        (r'≤', r'\\leq '), (r'≥', r'\\geq '),
        (r'≠', r'\\neq '), (r'≈', r'\\approx '),
        (r'∈', r'\\in '), (r'⊂', r'\\subset '),
        (r'⊆', r'\\subseteq '), (r'∪', r'\\cup '), (r'∩', r'\\cap '),
        # 运算符
        (r'÷', r'\\div '), (r'±', r'\\pm '),
        (r'∞', r'\\infty '), (r'∂', r'\\partial '),
        (r'∫', r'\\int '), (r'∑', r'\\sum '), (r'∏', r'\\prod '),
        # 箭头
        (r'→', r'\\rightarrow '), (r'←', r'\\leftarrow '),
        (r'↑', r'\\uparrow '), (r'↓', r'\\downarrow '),
        (r'↔', r'\\leftrightarrow '),
        # 其他
        (r'△', r'\\triangle '), (r'∵', r'\\because '), (r'∴', r'\\therefore '),
        (r'∀', r'\\forall '), (r'∃', r'\\exists '),
        (r'∅', r'\\emptyset '), (r'∉', r'\\notin '),
    ]
    for uchar, latex in GLOBAL_UNICODE_MAP:
        text = re.sub(uchar, latex, text)

    return text


def _clean_ocr_text(text: str) -> str:
    """清理 OCR 文本杂质：公式内空格、LaTeX 块合并、常见数学符号 OCR 错误修正。"""
    import re

    # 0. 全局 Unicode 数学符号 → LaTeX（不依赖 $$ 公式块检测）
    text = _global_symbol_cleanup(text)

    # 1. 修复公式块内多余空格和中文标点污染
    def _fix_formula_spaces(m):
        content = m.group(1)
        # 先移除中文标点（OCR 常把中文逗号/分号混入公式块）
        content = re.sub(r'[，。：；！？·「」『』【】《》…—～｜]', ' ', content)
        # 去掉相邻字母/数字之间的空格
        content = re.sub(r'(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9_{}\\])', '', content)
        content = re.sub(r'(?<=[A-Za-z0-9_{}])\s+(?=[+\-=×÷<>])', '', content)
        content = re.sub(r'(?<=[+\-=×÷<>])\s+(?=[A-Za-z0-9])', '', content)
        return f'$${content}$$'

    text = re.sub(r'\$\$(.+?)\$\$', _fix_formula_spaces, text)

    # 2. 合并相邻的 $$...$$ 块：$$A$$$$B$$ → $$AB$$
    text = re.sub(r'\$\$\s*\$\$', '', text)

    # 3. 修复三个美元符
    text = text.replace('$$$', '$$')

    # 4. 修复公式块内常见 OCR 数学符号错误
    def _fix_math_symbols(m):
        """对 $$...$$ 内部的 LaTeX 内容做符号纠错。

        原则：只处理确定性的 OCR 错误（Unicode 符号→LaTeX、常见 ASCII 模式）。
        不做基于上下文的猜测替换（如 a→α、B→β、0→θ），
        因为这些字符本身就是合法的数学符号/变量，误替换的代价太高。
        希腊字母识别交给 EduFormula 专用公式 API 处理。
        """
        formula = m.group(1)

        # ── OCR 常见碎片修复：\alpha → alpha → \alpha 循环纠正 ──
        # 当 OCR 把 LaTeX 命令反斜杠丢了时修复
        formula = re.sub(r'(?<![\\a-zA-Z])a(?=lpha)', r'\\a', formula)  # alpha → \alpha
        formula = re.sub(r'(?<![\\a-zA-Z])b(?=eta)', r'\\b', formula)   # beta → \beta
        formula = re.sub(r'(?<![\\a-zA-Z])t(?=heta)', r'\\t', formula)  # theta → \theta

        # ── LaTeX 命令与后续字母粘连：\angleABC → \angle ABC ──
        # 常见命令后紧跟大写字母/数字/字母时插入空格或花括号
        formula = re.sub(
            r'\\(angle|triangle|sqrt|frac|cdot|times|div|pm|circ|prime|infty|leq|geq|neq|approx|rightarrow|Rightarrow|Leftrightarrow|because|therefore|sum|prod|int|lim|vec|hat|bar|dot|tilde|ddot|overrightarrow|overleftarrow)(?=[A-Za-z\d])',
            r'\\\1 ',
            formula,
        )

        # ── 箭头/关系符号（OCR 常见错误） ──
        formula = re.sub(r'->(?!>)', r'\\rightarrow ', formula)
        formula = re.sub(r'→', r'\\rightarrow ', formula)
        formula = re.sub(r'<=>(?!>)', r'\\Leftrightarrow ', formula)
        formula = re.sub(r'=>(?!>)', r'\\Rightarrow ', formula)
        # <= → \leq（但排除 <=>、<==、<<= 等复合符号）
        formula = re.sub(r'(?<![<=])<=(?![=>])', r'\\leq ', formula)
        # >= → \geq（但排除 >=>、>>= 等复合符号）
        formula = re.sub(r'(?<![>=])>=(?![=>])', r'\\geq ', formula)

        # ── 根号：OCR 常把 √ 识别成 v 或 V ──
        # 限制：v/V 前面必须是行首/中文/标点/空白（不是字母），
        # 后面括号内不能只是单个变量名（排除 v(x)、V(t) 等函数调用）
        formula = re.sub(
            r'(^|[\s，。：；！？（【《\-–—一-鿿])v\s*(?=[\(\{](?!\s*[a-zA-Z]\s*[\)\}]))',
            lambda m: m.group(1) + r'\sqrt',
            formula,
        )
        formula = re.sub(
            r'(^|[\s，。：；！？（【《\-–—一-鿿])V\s*(?=[\(\{](?!\s*[a-zA-Z]\s*[\)\}]))',
            lambda m: m.group(1) + r'\sqrt',
            formula,
        )

        # ── 角度符号：30° → 30^{\circ} ──
        formula = re.sub(r'(\d+)°', r'\1^{\\circ}', formula)
        formula = re.sub(r'(\d+)\s*deg\b', r'\1^{\\circ}', formula)

        # ── 乘号：数字之间的 x → ×，· → \cdot ──
        formula = re.sub(r'(?<=\d)\s*x\s*(?=\d)', r' \\times ', formula)
        formula = re.sub(r'(?<=\d|\))\s*·\s*(?=\d|\()', r' \\cdot ', formula)

        # ── Unicode 数学符号 → LaTeX（确定性转换，无歧义） ──
        # 希腊字母（小写）
        formula = re.sub(r'α', r'\\alpha ', formula)
        formula = re.sub(r'β', r'\\beta ', formula)
        formula = re.sub(r'γ', r'\\gamma ', formula)
        formula = re.sub(r'δ', r'\\delta ', formula)
        formula = re.sub(r'ε', r'\\varepsilon ', formula)
        formula = re.sub(r'θ', r'\\theta ', formula)
        formula = re.sub(r'λ', r'\\lambda ', formula)
        formula = re.sub(r'μ', r'\\mu ', formula)
        formula = re.sub(r'π', r'\\pi ', formula)
        formula = re.sub(r'ρ', r'\\rho ', formula)
        formula = re.sub(r'σ', r'\\sigma ', formula)
        formula = re.sub(r'φ', r'\\phi ', formula)
        formula = re.sub(r'ω', r'\\omega ', formula)
        # 希腊字母（大写）
        formula = re.sub(r'Δ', r'\\Delta ', formula)
        formula = re.sub(r'Σ', r'\\Sigma ', formula)
        formula = re.sub(r'Ω', r'\\Omega ', formula)
        formula = re.sub(r'Π', r'\\Pi ', formula)
        formula = re.sub(r'Γ', r'\\Gamma ', formula)
        formula = re.sub(r'Θ', r'\\Theta ', formula)
        formula = re.sub(r'Λ', r'\\Lambda ', formula)
        formula = re.sub(r'Φ', r'\\Phi ', formula)
        # 关系/集合符号
        formula = re.sub(r'∠', r'\\angle ', formula)
        formula = re.sub(r'⊥', r'\\perp ', formula)
        formula = re.sub(r'∥', r'\\parallel ', formula)
        formula = re.sub(r'∈', r'\\in ', formula)
        formula = re.sub(r'∉', r'\\notin ', formula)
        formula = re.sub(r'⊂', r'\\subset ', formula)
        formula = re.sub(r'⊆', r'\\subseteq ', formula)
        formula = re.sub(r'∪', r'\\cup ', formula)
        formula = re.sub(r'∩', r'\\cap ', formula)
        formula = re.sub(r'∀', r'\\forall ', formula)
        formula = re.sub(r'∃', r'\\exists ', formula)
        formula = re.sub(r'∅', r'\\emptyset ', formula)
        # 运算符
        formula = re.sub(r'∫', r'\\int ', formula)
        formula = re.sub(r'∑', r'\\sum ', formula)
        formula = re.sub(r'∏', r'\\prod ', formula)
        formula = re.sub(r'√', r'\\sqrt', formula)
        formula = re.sub(r'∂', r'\\partial ', formula)
        formula = re.sub(r'∞', r'\\infty ', formula)
        # 之前的映射保留
        formula = re.sub(r'÷', r'\\div ', formula)
        formula = re.sub(r'△', r'\\triangle ', formula)
        formula = re.sub(r'≠', r'\\neq ', formula)
        formula = re.sub(r'≈', r'\\approx ', formula)
        formula = re.sub(r'±', r'\\pm ', formula)
        formula = re.sub(r'∵', r'\\because ', formula)
        formula = re.sub(r'∴', r'\\therefore ', formula)

        # ── 无穷符号：只匹配独立的 "oo"（前后都不是字母），排除单词内的 oo ──
        formula = re.sub(r'(?<![a-zA-Z])oo(?![a-zA-Z])', r'\\infty', formula)

        # ── 清理多余空格 ──
        formula = re.sub(r'\s+', ' ', formula).strip()

        return f'$${formula}$$'

    text = re.sub(r'\$\$(.+?)\$\$', _fix_math_symbols, text)

    # 5. 分数结构恢复：将公式块中的 (expr)/(expr) 转为 \frac{expr}{expr}
    #    仅当 EduFormula 失败回退到原始文本时有用
    def _recover_fractions(m):
        """恢复被 OCR 压扁的分数结构。支持嵌套括号。"""
        formula = m.group(1)

        # 5a. 括号分数：(expr)/(expr) → \frac{expr}{expr}
        #     支持嵌套括号：使用括号深度计数匹配
        def _replace_paren_fraction(match):
            num = match.group(1)
            den = match.group(2)
            return f'\\frac{{{num}}}{{{den}}}'

        # 匹配 ( ... ) / ( ... )，其中括号内部支持嵌套
        # 使用非贪婪匹配 + 递归模式
        formula = re.sub(
            r'\(((?:[^()]|\([^()]*\))*)\)\s*/\s*\(((?:[^()]|\([^()]*\))*)\)',
            _replace_paren_fraction,
            formula,
        )

        # 5b. 简单数字分数：1/2, 3/4 等（仅限个位数，避免误匹配日期如 2024/05）
        formula = re.sub(
            r'(?<!\d)(\d)\s*/\s*(\d)(?!\d)',
            r'\\frac{\1}{\2}',
            formula,
        )

        # 5c. 代数表达式分数：x/y → \frac{x}{y}、x^2/y → \frac{x^2}{y}
        #     排除 + - * 避免运算符歧义（如 a-b/c 不应变成 \frac{a-b}{c}）
        formula = re.sub(
            r'([a-zA-Z0-9^_{}\\]+)\s*/\s*([a-zA-Z0-9^_{}\\]+)',
            r'\\frac{\1}{\2}',
            formula,
        )

        return f'$${formula}$$'

    text = re.sub(r'\$\$(.+?)\$\$', _recover_fractions, text)

    return text


def _call_aliyun_general_ocr(image_bytes: bytes) -> dict:
    from alibabacloud_ocr_api20210707.models import RecognizeGeneralRequest
    from alibabacloud_tea_util.models import RuntimeOptions

    logger.info("Calling RecognizeGeneral (fallback)")
    request = RecognizeGeneralRequest(body=image_bytes)
    runtime = RuntimeOptions()
    response = _create_aliyun_client().recognize_general_with_options(request, runtime)
    data = _get_result_data(response)

    content = data.get("Content", "").strip()
    if not content:
        raise OCRServiceError("Alibaba General OCR returned no text")

    # General OCR 返回纯文本无公式检测，应用符号后处理校正
    content = _clean_ocr_text(content)

    logger.info("General OCR (post-processed): %s", content[:200])
    return {"raw_text": content, "text_blocks": [{"text": content, "confidence": 0.99, "bbox": []}], "confidence": 0.99}
