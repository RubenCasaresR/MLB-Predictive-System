import time
import logging
from functools import wraps
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    retryable_exceptions: Optional[tuple] = None,
) -> Callable:
    if retryable_exceptions is None:
        import requests
        retryable_exceptions = (ConnectionError, TimeoutError, requests.ConnectionError, requests.Timeout)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    delay = base_delay * (backoff ** attempt)
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                        f"in {delay:.1f}s: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
