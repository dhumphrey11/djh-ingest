"""
Retry utilities with exponential backoff and jitter
"""

import asyncio
import random
import time
import logging
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps
import requests
from requests.exceptions import Timeout, ConnectionError


logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted"""
    pass


class RateLimitError(Exception):
    """Raised when rate limit is encountered"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
) -> float:
    """
    Calculate exponential backoff delay with optional jitter

    Args:
        attempt: Current attempt number (1-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Whether to add random jitter

    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)

    if jitter:
        # Add ±25% jitter
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def should_retry_exception(
    exception: Exception,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        Timeout,
        requests.exceptions.HTTPError,
        RateLimitError
    )
) -> bool:
    """
    Determine if an exception should trigger a retry

    Args:
        exception: The exception that occurred
        retryable_exceptions: Tuple of exception types that should be retried

    Returns:
        True if should retry, False otherwise
    """
    if isinstance(exception, requests.exceptions.HTTPError):
        # Retry on 5xx errors and 429 (rate limit)
        if hasattr(exception, 'response') and exception.response is not None:
            status_code = exception.response.status_code
            return status_code >= 500 or status_code == 429
        return True

    return isinstance(exception, retryable_exceptions)


def should_retry_response(response: requests.Response) -> bool:
    """
    Determine if a response should trigger a retry

    Args:
        response: The HTTP response

    Returns:
        True if should retry, False otherwise
    """
    # Retry on server errors and rate limiting
    return response.status_code >= 500 or response.status_code == 429


def extract_retry_after(response: requests.Response) -> Optional[int]:
    """
    Extract retry-after header from response

    Args:
        response: The HTTP response

    Returns:
        Retry-after delay in seconds, or None if not present
    """
    retry_after = response.headers.get('Retry-After')
    if retry_after:
        try:
            return int(retry_after)
        except ValueError:
            # Could be HTTP date format, but we'll just use default backoff
            pass
    return None


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        Timeout,
        requests.exceptions.HTTPError,
        RateLimitError
    )
):
    """
    Decorator for retrying functions with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exception types that should trigger retries

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_retries + 2):  # +1 for initial attempt, +1 for range
                try:
                    result = func(*args, **kwargs)

                    # Check if result is a response object that should be retried
                    if isinstance(result, requests.Response) and should_retry_response(result):
                        if attempt > max_retries:
                            raise requests.exceptions.HTTPError(
                                f"Max retries exceeded. Last status: {result.status_code}",
                                response=result
                            )

                        # Handle rate limiting
                        if result.status_code == 429:
                            retry_after = extract_retry_after(result)
                            if retry_after:
                                logger.warning(
                                    f"Rate limited. Waiting {retry_after}s before retry {attempt}/{max_retries}"
                                )
                                time.sleep(retry_after)
                                continue

                        # Regular backoff for other 5xx errors
                        delay = calculate_backoff(attempt, base_delay, max_delay, exponential_base, jitter)
                        logger.warning(
                            f"Request failed with status {result.status_code}. "
                            f"Retrying in {delay:.2f}s (attempt {attempt}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue

                    # Success case
                    if attempt > 1:
                        logger.info(f"Request succeeded on attempt {attempt}")
                    return result

                except Exception as e:
                    last_exception = e

                    if not should_retry_exception(e, retryable_exceptions):
                        # Non-retryable exception, re-raise immediately
                        raise

                    if attempt > max_retries:
                        # Max retries exceeded
                        logger.error(f"Max retries ({max_retries}) exceeded. Last exception: {e}")
                        raise RetryExhausted(f"Max retries exceeded: {e}") from e

                    # Handle rate limiting exception
                    if isinstance(e, RateLimitError) and e.retry_after:
                        logger.warning(
                            f"Rate limited. Waiting {e.retry_after}s before retry {attempt}/{max_retries}"
                        )
                        time.sleep(e.retry_after)
                        continue

                    # Calculate delay for regular exceptions
                    delay = calculate_backoff(attempt, base_delay, max_delay, exponential_base, jitter)
                    logger.warning(
                        f"Request failed with {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f}s (attempt {attempt}/{max_retries})"
                    )
                    time.sleep(delay)

            # This should never be reached, but just in case
            raise last_exception or RetryExhausted("Unexpected retry loop exit")

        return wrapper
    return decorator


async def async_retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        Timeout,
        requests.exceptions.HTTPError,
        RateLimitError
    )
):
    """
    Async decorator for retrying functions with exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_retries + 2):
                try:
                    result = await func(*args, **kwargs)

                    # Check if result is a response object that should be retried
                    if hasattr(result, 'status_code') and should_retry_response(result):
                        if attempt > max_retries:
                            raise requests.exceptions.HTTPError(
                                f"Max retries exceeded. Last status: {result.status_code}",
                                response=result
                            )

                        # Handle rate limiting
                        if result.status_code == 429:
                            retry_after = extract_retry_after(result)
                            if retry_after:
                                logger.warning(
                                    f"Rate limited. Waiting {retry_after}s before retry {attempt}/{max_retries}"
                                )
                                await asyncio.sleep(retry_after)
                                continue

                        delay = calculate_backoff(attempt, base_delay, max_delay, exponential_base, jitter)
                        logger.warning(
                            f"Request failed with status {result.status_code}. "
                            f"Retrying in {delay:.2f}s (attempt {attempt}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue

                    if attempt > 1:
                        logger.info(f"Request succeeded on attempt {attempt}")
                    return result

                except Exception as e:
                    last_exception = e

                    if not should_retry_exception(e, retryable_exceptions):
                        raise

                    if attempt > max_retries:
                        logger.error(f"Max retries ({max_retries}) exceeded. Last exception: {e}")
                        raise RetryExhausted(f"Max retries exceeded: {e}") from e

                    if isinstance(e, RateLimitError) and e.retry_after:
                        logger.warning(
                            f"Rate limited. Waiting {e.retry_after}s before retry {attempt}/{max_retries}"
                        )
                        await asyncio.sleep(e.retry_after)
                        continue

                    delay = calculate_backoff(attempt, base_delay, max_delay, exponential_base, jitter)
                    logger.warning(
                        f"Request failed with {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f}s (attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(delay)

            raise last_exception or RetryExhausted("Unexpected retry loop exit")

        return wrapper
    return decorator


# Convenience functions for common retry scenarios

def retry_api_call(
    func: Callable,
    *args,
    max_retries: int = 3,
    **kwargs
) -> Any:
    """
    Retry an API call with default settings

    Args:
        func: Function to call
        *args: Arguments to pass to function
        max_retries: Maximum number of retries
        **kwargs: Keyword arguments to pass to function

    Returns:
        Function result
    """
    @retry_with_backoff(max_retries=max_retries)
    def _wrapped():
        return func(*args, **kwargs)

    return _wrapped()


def retry_requests_get(url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """
    Retry a GET request with default settings

    Args:
        url: URL to request
        max_retries: Maximum number of retries
        **kwargs: Additional arguments for requests.get

    Returns:
        Response object
    """
    @retry_with_backoff(max_retries=max_retries)
    def _get():
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        return response

    return _get()
