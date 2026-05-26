"""Tests para etl/retry.py (with_retry decorator)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl.retry import with_retry

# ============================================================================
# Estructura del decorador
# ============================================================================


class TestDecoratorStructure:
    def test_returns_callable(self):
        decorator = with_retry()
        assert callable(decorator)

    def test_wraps_function(self):
        @with_retry()
        def foo():
            return 42

        assert foo() == 42

    def test_preserves_func_name(self):
        @with_retry()
        def my_function():
            pass

        assert my_function.__name__ == "my_function"


# ============================================================================
# Éxito en primer intento
# ============================================================================


class TestSuccessFirstTry:
    def test_returns_value(self):
        @with_retry()
        def foo():
            return "ok"

        assert foo() == "ok"

    def test_called_once(self):
        call_count = 0

        @with_retry()
        def foo():
            nonlocal call_count
            call_count += 1
            return 42

        foo()
        assert call_count == 1

    def test_args_preserved(self):
        @with_retry()
        def add(a, b):
            return a + b

        assert add(3, 4) == 7

    def test_kwargs_preserved(self):
        @with_retry()
        def kw(**kwargs):
            return kwargs

        assert kw(x=1, y=2) == {"x": 1, "y": 2}


# ============================================================================
# Reintentos (retryable exceptions)
# ============================================================================


class TestRetryThenSuccess:
    def test_second_try_succeeds(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "ok"

        with patch("etl.retry.time.sleep"):
            assert flaky() == "ok"
            assert call_count == 2

    def test_third_try_succeeds(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("fail")
            return "done"

        with patch("etl.retry.time.sleep"):
            assert flaky() == "done"
            assert call_count == 3


class TestExhaustsRetries:
    def test_raises_last_exception(self):
        @with_retry(max_retries=2, base_delay=0.01)
        def always_fails():
            raise ConnectionError("boom")

        with patch("etl.retry.time.sleep"):
            with pytest.raises(ConnectionError, match="boom"):
                always_fails()

    def test_raises_on_retryable_after_exhaustion(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with patch("etl.retry.time.sleep"):
            with pytest.raises(TimeoutError):
                flaky()
            assert call_count == 3


class TestNonRetryableException:
    def test_propagates_immediately(self):
        call_count = 0

        @with_retry(max_retries=3)
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad value")

        with pytest.raises(ValueError):
            raises_value_error()
        assert call_count == 1

    def test_type_error_not_retried(self):
        call_count = 0

        @with_retry(max_retries=3)
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("bad type")

        with pytest.raises(TypeError):
            raises_type_error()
        assert call_count == 1


class TestCustomRetryableExceptions:
    def test_value_error_retried_when_custom(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,))
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("custom retryable")
            return "ok"

        with patch("etl.retry.time.sleep"):
            assert raises_value_error() == "ok"
            assert call_count == 2

    def test_connection_error_not_retried_if_not_in_custom(self):
        call_count = 0

        @with_retry(max_retries=3, retryable_exceptions=(ValueError,))
        def raises_connection_error():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("not retryable")

        with pytest.raises(ConnectionError):
            raises_connection_error()
        assert call_count == 1


# ============================================================================
# max_retries edge cases
# ============================================================================


class TestMaxRetriesEdgeCases:
    def test_max_retries_one(self):
        call_count = 0

        @with_retry(max_retries=1, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "ok"

        with patch("etl.retry.time.sleep"):
            with pytest.raises(ConnectionError):
                flaky()
            assert call_count == 1

    def test_default_max_retries_three(self):
        call_count = 0

        @with_retry()
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with patch("etl.retry.time.sleep"):
            with pytest.raises(ConnectionError):
                flaky()
            assert call_count == 3


# ============================================================================
# Exponential backoff
# ============================================================================


class TestExponentialBackoff:
    def test_delay_increases(self):
        sleeps = []

        def fake_sleep(delay):
            sleeps.append(delay)

        call_count = 0

        @with_retry(max_retries=4, base_delay=1.0, backoff=2.0)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with patch("etl.retry.time.sleep", side_effect=fake_sleep):
            with pytest.raises(ConnectionError):
                flaky()

        # 3 sleeps (attempts 0, 1, 2) with delays: 1, 2, 4
        assert len(sleeps) == 3
        assert sleeps == [1.0, 2.0, 4.0]

    def test_custom_backoff(self):
        sleeps = []

        def fake_sleep(delay):
            sleeps.append(delay)

        call_count = 0

        @with_retry(max_retries=3, base_delay=0.5, backoff=3.0)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with patch("etl.retry.time.sleep", side_effect=fake_sleep):
            with pytest.raises(ConnectionError):
                flaky()

        # 2 sleeps: 0.5, 1.5
        assert len(sleeps) == 2
        assert sleeps == [0.5, 1.5]

    def test_no_sleep_on_last_attempt(self):
        sleep_count = 0

        def fake_sleep(delay):
            nonlocal sleep_count
            sleep_count += 1

        call_count = 0

        @with_retry(max_retries=3, base_delay=1.0)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with patch("etl.retry.time.sleep", side_effect=fake_sleep):
            with pytest.raises(ConnectionError):
                flaky()

        # Only 2 sleeps for 3 attempts (no sleep on last)
        assert sleep_count == 2


# ============================================================================
# Default retryable exceptions
# ============================================================================


class TestDefaultExceptions:
    def test_connection_error_is_retryable(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def raises_conn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("conn fail")
            return "ok"

        with patch("etl.retry.time.sleep"):
            assert raises_conn() == "ok"
            assert call_count == 2

    def test_timeout_error_is_retryable(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def raises_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("timeout")
            return "ok"

        with patch("etl.retry.time.sleep"):
            assert raises_timeout() == "ok"
            assert call_count == 2


# ============================================================================
# Uso real: coincide con como lo usan los ingestores
# ============================================================================


class TestUsagePatterns:
    def test_empty_parentheses_pattern(self):
        @with_retry()
        def fetch():
            return "data"

        assert fetch() == "data"

    def test_with_custom_params_like_statcast(self):
        @with_retry(max_retries=3, base_delay=2.0)
        def fetch():
            return "data"

        assert fetch() == "data"
