import pytest
from promptpressure.per_turn_metrics import compute_response_length_ratio, compute_turn_metrics


class TestResponseLengthRatio:
    def test_normal_ratio(self):
        ratio = compute_response_length_ratio("hello", "hello world this is a response")
        assert ratio == pytest.approx(6.0, rel=0.1)

    def test_equal_lengths(self):
        ratio = compute_response_length_ratio("abcde", "fghij")
        assert ratio == pytest.approx(1.0)

    def test_empty_user_message(self):
        ratio = compute_response_length_ratio("", "some response")
        assert ratio == 0.0

    def test_empty_response(self):
        ratio = compute_response_length_ratio("hello", "")
        assert ratio == 0.0

    def test_both_empty(self):
        ratio = compute_response_length_ratio("", "")
        assert ratio == 0.0


class TestComputeTurnMetrics:
    def test_returns_dict_with_length_ratio(self):
        result = compute_turn_metrics("short question", "a much longer detailed response here")
        assert "response_length_ratio" in result
        assert isinstance(result["response_length_ratio"], float)

    def test_turn_number_included(self):
        result = compute_turn_metrics("q", "a", turn_number=3)
        assert result["turn"] == 3
