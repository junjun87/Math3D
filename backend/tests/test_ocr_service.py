from app.services.ocr_service import OCRServiceError, _get_result_data


def test_get_result_data_from_json_string():
    """response.body.data 为 JSON 字符串时能正确解析。"""
    class MockBody:
        data = '{"content":"x=1","prism_wordsInfo":[{"word":"x=1","prob":98,"recClassify":51,"pos":[0,0,20,10]}]}'
    result = _get_result_data(MockBody())

    assert result == {
        "content": "x=1",
        "prism_wordsInfo": [{
            "word": "x=1",
            "prob": 98,
            "recClassify": 51,
            "pos": [0, 0, 20, 10],
        }],
    }


def test_get_result_data_already_dict():
    """response.body.data 已经是 dict 时也能正确返回。"""
    class MockBody:
        data = {"content": "x=1", "prism_wordsInfo": []}
    result = _get_result_data(MockBody())
    assert result == {"content": "x=1", "prism_wordsInfo": []}


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
