from app.services.ocr_service import OCRServiceError, _get_result_data, _extract_text_from_response


def test_get_result_data_from_json_string():
    """response.body.data 为 JSON 字符串时能正确解析。"""
    class MockBody:
        data = '{"content":"x=1"}'
    result = _get_result_data(MockBody())
    assert result == {"content": "x=1"}


def test_get_result_data_already_dict():
    """response.body.data 已经是 dict 时也能正确返回。"""
    class MockBody:
        data = {"content": "x=1"}
    result = _get_result_data(MockBody())
    assert result == {"content": "x=1"}


def test_get_result_data_invalid_raises():
    """非 str 非 dict 应抛异常。"""
    class MockBody:
        data = 123
    try:
        _get_result_data(MockBody())
    except OCRServiceError:
        pass
    else:
        raise AssertionError("Should raise OCRServiceError")


def test_extract_text_anthropic_format():
    """Anthropic 格式: content[0].text"""
    text = _extract_text_from_response({"content": [{"type": "text", "text": "hello"}]})
    assert text == "hello"


def test_extract_text_openai_format():
    """OpenAI 格式: choices[0].message.content"""
    text = _extract_text_from_response({"choices": [{"message": {"content": "world"}}]})
    assert text == "world"


def test_extract_text_deepseek_format():
    """DeepSeek 兼容格式: content[0].text (无外层 type)"""
    text = _extract_text_from_response({"content": [{"text": "x=1"}]})
    assert text == "x=1"


def test_extract_text_unknown_raises():
    """无法识别的格式应抛异常。"""
    try:
        _extract_text_from_response({"unknown": "format"})
    except OCRServiceError:
        pass
    else:
        raise AssertionError("Should raise OCRServiceError")
