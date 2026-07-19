from app.services.ocr_service import OCRServiceError, _parse_aliyun_edu_response


def test_parse_aliyun_education_ocr_response():
    result = _parse_aliyun_edu_response({
        "Data": {
            "content": "x=1",
            "prism_wordsInfo": [{
                "word": "x=1",
                "prob": 98,
                "recClassify": 51,
                "pos": [0, 0, 20, 10],
            }],
        },
    })

    assert result == {
        "raw_text": "$$x=1$$",
        "text_blocks": [{
            "text": "x=1",
            "confidence": 0.98,
            "is_formula": True,
            "bbox": [0, 0, 20, 10],
        }],
        "confidence": 0.98,
    }


def test_parse_aliyun_education_ocr_response_rejects_empty_text():
    try:
        _parse_aliyun_edu_response({"Data": {}})
    except OCRServiceError as error:
        assert "no text" in str(error)
    else:
        raise AssertionError("Empty OCR response should be rejected")
