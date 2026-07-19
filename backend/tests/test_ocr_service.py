from app.services.ocr_service import OCRServiceError, _parse_data_field


def test_parse_data_field_from_json_string():
    """Data 字段为 JSON 字符串时能正确解析。"""
    result = _parse_data_field({
        "Data": '{"content":"x=1","prism_wordsInfo":[{"word":"x=1","prob":98,"recClassify":51,"pos":[0,0,20,10]}]}',
        "RequestId": "xxx",
    })

    assert result == {
        "content": "x=1",
        "prism_wordsInfo": [{
            "word": "x=1",
            "prob": 98,
            "recClassify": 51,
            "pos": [0, 0, 20, 10],
        }],
    }


def test_parse_data_field_as_dict():
    """Data 字段已经是 dict 时也能正确返回。"""
    result = _parse_data_field({
        "Data": {"content": "x=1", "prism_wordsInfo": []},
        "RequestId": "xxx",
    })
    assert result == {"content": "x=1", "prism_wordsInfo": []}


def test_parse_data_field_empty_string_raises():
    """空字符串不是合法的 dict，应抛异常。"""
    try:
        _parse_data_field({"Data": ""})
    except OCRServiceError:
        pass
    else:
        raise AssertionError("Should raise OCRServiceError for empty string Data")
