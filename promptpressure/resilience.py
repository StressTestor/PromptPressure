"""Retry logic, error classification, and backoff for PromptPressure API calls.

Extracted from cli.py to keep the eval runner focused on orchestration.
"""

import asyncio


def is_retryable(error):
    """Check if an error is a transient infrastructure failure worth retrying.

    Matches: 429, 503, 529, rate limit, overloaded, too many requests,
    service unavailable.
    """
    err_str = str(error).lower()
    return any(code in err_str for code in (
        "429", "503", "529", "overloaded", "rate limit",
        "too many requests", "service unavailable",
    ))


def classify_error(error):
    """Classify an error as 'infra' (retryable/transient) or 'model' (real failure).

    infra: rate limits, timeouts, connection failures, empty responses.
    model: bad requests, auth errors, unexpected responses, anything else.
    """
    if is_retryable(error):
        return "infra"
    err_str = str(error).lower()
    if any(x in err_str for x in ("timeout", "timed out", "connection", "empty response")):
        return "infra"
    return "model"


async def retry_with_backoff(fn, max_retries=3, base_delay=5.0, max_delay=60.0):
    """Call fn with exponential backoff on retryable errors.

    Args:
        fn: async callable to execute.
        max_retries: max retry attempts after initial failure.
        base_delay: initial backoff in seconds.
        max_delay: maximum backoff cap in seconds.

    Returns:
        (result, retries_used) tuple on success.

    Raises:
        The last exception if all retries are exhausted or
        the error is not retryable.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = await fn()
            return result, attempt
        except Exception as e:
            last_error = e
            if not is_retryable(e) or attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)
    raise last_error
