"""
Tests for BrowserWorker
"""
import pytest
from src.browser_worker import (
    BrowserWorker,
    WorkerResult,
    ErrorType,
    _classify_error,
    _validate_url,
    _validate_path,
)


class TestErrorClassification:
    """Tests for error classification utilities"""

    def test_classify_timeout_error(self):
        import asyncio
        error_type, msg = _classify_error(asyncio.TimeoutError("timeout"))
        assert error_type == ErrorType.TIMEOUT

    def test_classify_connection_error(self):
        error_type, msg = _classify_error(ConnectionRefusedError("refused"))
        assert error_type == ErrorType.CONNECTION

    def test_classify_proxy_error_from_string(self):
        error_type, msg = _classify_error(Exception("proxy tunnel failed"))
        assert error_type == ErrorType.PROXY

    def test_classify_element_not_found(self):
        error_type, msg = _classify_error(Exception("selector not found"))
        assert error_type == ErrorType.ELEMENT_NOT_FOUND

    def test_classify_unknown_error(self):
        error_type, msg = _classify_error(Exception("some random error"))
        assert error_type == ErrorType.UNKNOWN


class TestURLValidation:
    """Tests for URL validation"""

    def test_valid_http_url(self):
        assert _validate_url("http://example.com") is None

    def test_valid_https_url(self):
        assert _validate_url("https://example.com") is None

    def test_empty_url(self):
        error = _validate_url("")
        assert error is not None
        assert "empty" in error.lower()

    def test_no_scheme_url(self):
        error = _validate_url("example.com")
        assert error is not None
        assert "http" in error.lower()

    def test_ftp_url_invalid(self):
        error = _validate_url("ftp://example.com")
        assert error is not None


class TestPathValidation:
    """Tests for path validation"""

    def test_valid_tmp_path(self):
        assert _validate_path("/tmp/screenshot.png") is None

    def test_valid_relative_path(self):
        assert _validate_path("screenshot.png") is None

    def test_empty_path(self):
        error = _validate_path("")
        assert error is not None
        assert "empty" in error.lower()

    def test_path_traversal(self):
        error = _validate_path("../../../etc/passwd")
        assert error is not None
        assert "traversal" in error.lower()

    def test_absolute_path_outside_allowed(self):
        error = _validate_path("/etc/passwd")
        assert error is not None
        assert "allowed" in error.lower()


class TestWorkerResult:
    """Tests for WorkerResult dataclass"""

    def test_success_result(self):
        result = WorkerResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.is_retryable is False

    def test_timeout_is_retryable(self):
        result = WorkerResult(
            success=False,
            error="timeout",
            error_type=ErrorType.TIMEOUT
        )
        assert result.is_retryable is True

    def test_connection_is_retryable(self):
        result = WorkerResult(
            success=False,
            error="connection error",
            error_type=ErrorType.CONNECTION
        )
        assert result.is_retryable is True

    def test_proxy_is_retryable(self):
        result = WorkerResult(
            success=False,
            error="proxy error",
            error_type=ErrorType.PROXY
        )
        assert result.is_retryable is True

    def test_validation_not_retryable(self):
        result = WorkerResult(
            success=False,
            error="validation error",
            error_type=ErrorType.VALIDATION
        )
        assert result.is_retryable is False

    def test_element_not_found_not_retryable(self):
        result = WorkerResult(
            success=False,
            error="element not found",
            error_type=ErrorType.ELEMENT_NOT_FOUND
        )
        assert result.is_retryable is False


class TestBrowserWorker:
    """Tests for BrowserWorker class"""

    def test_initialization(self):
        worker = BrowserWorker(
            worker_id="test_worker",
            headless=True,
        )
        assert worker.worker_id == "test_worker"
        assert worker.headless is True
        assert worker._page is None

    def test_navigate_without_start(self):
        worker = BrowserWorker(worker_id="test")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.navigate("https://example.com")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION
        assert "not started" in result.error.lower()

    def test_navigate_invalid_url(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.navigate("invalid-url")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_screenshot_path_validation(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.screenshot("../../../etc/passwd")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION
        assert "traversal" in result.error.lower()

    def test_click_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.click("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_fill_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.fill("", "value")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_evaluate_empty_script(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.evaluate("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_wait_for_selector_empty(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.wait_for_selector("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_scroll_invalid_direction(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.scroll(direction="invalid")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_hover_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.hover("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_select_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.select("", "value")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_get_text_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.get_text("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_type_empty_selector(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.type("", "text")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_press_empty_key(self):
        worker = BrowserWorker(worker_id="test")
        worker._page = object()  # Mock page existence
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.press("")
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_scroll_without_start(self):
        worker = BrowserWorker(worker_id="test")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.scroll()
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION

    def test_wait_for_navigation_without_start(self):
        worker = BrowserWorker(worker_id="test")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.wait_for_navigation()
        )
        assert result.success is False
        assert result.error_type == ErrorType.VALIDATION
