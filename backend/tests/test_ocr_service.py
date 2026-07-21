from app.services.ocr_service import (
    OCRServiceError,
    _build_blocks,
    _build_raw_text,
    _get_result_data,
    _result_from_blocks,
)


def test_get_result_data_from_json_string():
    class MockBody:
        data = '{"content":"x=1"}'

    assert _get_result_data(MockBody()) == {"content": "x=1"}


def test_get_result_data_already_dict():
    class MockBody:
        data = {"content": "x=1"}

    assert _get_result_data(MockBody()) == {"content": "x=1"}


def test_get_result_data_invalid_raises():
    class MockBody:
        data = 123

    try:
        _get_result_data(MockBody())
    except OCRServiceError:
        pass
    else:
        raise AssertionError("Should raise OCRServiceError")


def test_formula_blocks_are_ordered_by_coordinates_and_kept_on_their_line():
    blocks = _build_blocks([
        {"word": "=", "prob": 99, "recClassify": 51, "pos": [{"x": 42, "y": 20}, {"x": 48, "y": 20}, {"x": 48, "y": 32}, {"x": 42, "y": 32}]},
        {"word": "x", "prob": 99, "recClassify": 51, "pos": [{"x": 20, "y": 20}, {"x": 30, "y": 20}, {"x": 30, "y": 32}, {"x": 20, "y": 32}]},
        {"word": "2", "prob": 80, "recClassify": 51, "pos": [{"x": 56, "y": 20}, {"x": 62, "y": 20}, {"x": 62, "y": 32}, {"x": 56, "y": 32}]},
        {"word": "求解", "prob": 99, "recClassify": 0, "pos": [{"x": 20, "y": 60}, {"x": 50, "y": 60}, {"x": 50, "y": 72}, {"x": 20, "y": 72}]},
    ])

    assert [block["text"] for block in blocks] == ["x", "=", "2", "求解"]
    assert [block["line"] for block in blocks] == [0, 0, 0, 1]
    assert "low_confidence" in blocks[2]["risk_flags"]
    assert _build_raw_text(blocks) == "$$x=2$$\n求解"


def test_result_requires_review_when_a_block_has_a_risk_flag():
    blocks = _build_blocks([
        {"word": "x?", "prob": 70, "recClassify": 51, "pos": []},
    ])

    result = _result_from_blocks(blocks, "", "test")

    assert result["review_required"] is True
    assert result["source"] == "test"
