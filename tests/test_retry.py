"""Tests for retry logic, error classification, and retryable detection in cli.py."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from promptpressure.cli import _is_retryable, _classify_error, _retry_with_backoff


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------

class TestIsRetryable:
    def test_429_is_retryable(self):
        assert _is_retryable(Exception("Client error '429 Too Many Requests'")) is True

    def test_503_is_retryable(self):
        assert _is_retryable(Exception("Server error '503 Service Unavailable'")) is True

    def test_529_is_retryable(self):
        assert _is_retryable(Exception("Server error '529 Overloaded'")) is True

    def test_rate_limit_text_is_retryable(self):
        assert _is_retryable(Exception("rate limit exceeded")) is True

    def test_overloaded_is_retryable(self):
        assert _is_retryable(Exception("The server is overloaded")) is True

    def test_too_many_requests_is_retryable(self):
        assert _is_retryable(Exception("too many requests, please slow down")) is True

    def test_service_unavailable_is_retryable(self):
        assert _is_retryable(Exception("service unavailable temporarily")) is True

    def test_400_is_not_retryable(self):
        assert _is_retryable(Exception("Client error '400 Bad Request'")) is False

    def test_404_is_not_retryable(self):
        assert _is_retryable(Exception("Client error '404 Not Found'")) is False

    def test_401_is_not_retryable(self):
        assert _is_retryable(Exception("Client error '401 Unauthorized'")) is False

    def test_generic_error_not_retryable(self):
        assert _is_retryable(Exception("something went wrong")) is False

    def test_empty_error_not_retryable(self):
        assert _is_retryable(Exception("")) is False


# ---------------------------------------------------------------------------
# _classify_error
# ---------------------------------------------------------------------------

class TestClassifyError:
    def test_429_is_infra(self):
        assert _classify_error(Exception("429 Too Many Requests")) == "infra"

    def test_503_is_infra(self):
        assert _classify_error(Exception("503 Service Unavailable")) == "infra"

    def test_timeout_is_infra(self):
        assert _classify_error(Exception("request timed out after 60s")) == "infra"

    def test_connection_error_is_infra(self):
        assert _classify_error(Exception("All connection attempts failed")) == "infra"

    def test_empty_response_is_infra(self):
        assert _classify_error(Exception("empty response from server")) == "infra"

    def test_400_is_model(self):
        assert _classify_error(Exception("400 Bad Request")) == "model"

    def test_404_is_model(self):
        assert _classify_error(Exception("404 Not Found")) == "model"

    def test_generic_is_model(self):
        assert _classify_error(Exception("invalid JSON in response")) == "model"

    def test_402_is_model(self):
        assert _classify_error(Exception("402 Payment Required")) == "model"


# ---------------------------------------------------------------------------
# _retry_with_backoff
# ---------------------------------------------------------------------------

class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        fn = AsyncMock(return_value="ok")
        result, retries = await _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert retries == 0
        fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 Too Many Requests")
            return "ok"

        result, retries = await _retry_with_backoff(flaky, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert retries == 2
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self):
        fn = AsyncMock(side_effect=Exception("503 Service Unavailable"))
        with pytest.raises(Exception, match="503"):
            await _retry_with_backoff(fn, max_retries=2, base_delay=0.01)
        assert fn.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        fn = AsyncMock(side_effect=Exception("400 Bad Request"))
        with pytest.raises(Exception, match="400"):
            await _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        fn.assert_called_once()  # no retries for non-retryable

    @pytest.mark.asyncio
    async def test_zero_retries_means_single_attempt(self):
        fn = AsyncMock(side_effect=Exception("429 Too Many Requests"))
        with pytest.raises(Exception, match="429"):
            await _retry_with_backoff(fn, max_retries=0, base_delay=0.01)
        fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_503_then_succeeds(self):
        call_count = 0

        async def flaky_503():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("503 Service Unavailable")
            return "recovered"

        result, retries = await _retry_with_backoff(flaky_503, max_retries=3, base_delay=0.01)
        assert result == "recovered"
        assert retries == 1
