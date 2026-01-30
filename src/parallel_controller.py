"""
Parallel Controller - Manages multiple browser workers with retry logic
"""
import asyncio
import time
from typing import Optional, Callable, Any, Coroutine, TYPE_CHECKING
from dataclasses import dataclass
from loguru import logger

from .proxy_manager import ProxyManager, ProxyConfig
from .ua_manager import UserAgentManager, BrowserProfile
from .browser_worker import BrowserWorker, WorkerResult, ErrorType

if TYPE_CHECKING:
    from .sense import EventBus, MetricsCollector


@dataclass
class TaskResult:
    """Result from parallel task execution"""

    worker_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    retries: int = 0
    duration: float = 0.0


class ParallelController:
    """Manages parallel browser workers with proxy and UA rotation"""

    # Retry settings
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 30.0  # seconds

    # Retryable error types
    RETRYABLE_ERRORS = {
        ErrorType.TIMEOUT,
        ErrorType.CONNECTION,
        ErrorType.PROXY,
    }

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        ua_manager: Optional[UserAgentManager] = None,
        max_workers: int = 5,
        headless: bool = True,
        max_retries: int = 3,
        event_bus: Optional["EventBus"] = None,
        metrics_collector: Optional["MetricsCollector"] = None,
    ):
        self.proxy_manager = proxy_manager
        self.ua_manager = ua_manager or UserAgentManager()
        self.max_workers = max_workers
        self.headless = headless
        self.max_retries = max_retries
        self._workers: dict[str, BrowserWorker] = {}
        self._semaphore = asyncio.Semaphore(max_workers)
        self._event_bus = event_bus
        self._metrics = metrics_collector

    async def _create_worker(self, worker_id: str) -> BrowserWorker:
        """Create a new worker with fresh proxy and profile"""
        proxy = None
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy(new_session=True)

        profile = self.ua_manager.get_random_profile(session_id=worker_id)

        worker = BrowserWorker(
            worker_id=worker_id,
            proxy=proxy,
            profile=profile,
            headless=self.headless,
        )

        await worker.start()
        self._workers[worker_id] = worker
        return worker

    async def _cleanup_worker(self, worker_id: str) -> None:
        """Clean up and remove worker"""
        if worker_id in self._workers:
            try:
                await self._workers[worker_id].stop()
            except Exception as e:
                logger.debug(f"Worker cleanup error (ignored): {e}")
            finally:
                del self._workers[worker_id]
                self.ua_manager.clear_session(worker_id)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.BASE_DELAY * (2 ** attempt)
        return min(delay, self.MAX_DELAY)

    def _is_retryable(self, result: WorkerResult) -> bool:
        """Check if error is retryable based on error type"""
        if result.success:
            return False

        # Use error_type if available
        if result.error_type is not None:
            return result.error_type in self.RETRYABLE_ERRORS

        # Fallback to string matching for backward compatibility
        return self._is_proxy_error_legacy(result.error or "")

    def _is_proxy_error_legacy(self, error: str) -> bool:
        """Legacy check for proxy-related errors (fallback)"""
        proxy_errors = [
            "proxy",
            "connection refused",
            "connection reset",
            "connection error",
            "timeout",
            "econnrefused",
            "econnreset",
            "etimedout",
            "tunnel",
            "network",
            "socket",
            "unreachable",
            "502",
            "503",
            "504",
            "407",
        ]
        error_lower = error.lower()
        return any(e in error_lower for e in proxy_errors)

    async def _publish_event(self, event_type: str, data: dict) -> None:
        """Publish event to event bus if available"""
        if self._event_bus:
            from .sense import Event
            event = Event(event_type=event_type, source="parallel_controller", data=data)
            await self._event_bus.publish(event)

    async def run_task(
        self,
        task_id: str,
        task_fn: Callable[[BrowserWorker], Coroutine[Any, Any, WorkerResult]],
    ) -> TaskResult:
        """Run a single task with automatic worker management and retry"""
        worker_id = f"worker_{task_id}"
        last_error = None
        last_error_type = None
        retries = 0
        start_time = time.time()

        # Publish task started event
        await self._publish_event("task.started", {"task_id": task_id, "worker_id": worker_id})

        async with self._semaphore:
            for attempt in range(self.max_retries + 1):
                current_worker_id = f"{worker_id}_attempt{attempt}"
                worker = None

                try:
                    # Create worker with fresh proxy on retry
                    worker = await self._create_worker(current_worker_id)
                    task_start = time.time()
                    result = await task_fn(worker)
                    task_duration = time.time() - task_start

                    # Record proxy stats with timing
                    if self.proxy_manager and worker.proxy:
                        session_id = worker.proxy.session_id or ""
                        country = worker.proxy.country
                        if result.success:
                            self.proxy_manager.record_success(
                                session_id,
                                response_time=task_duration,
                                country=country
                            )
                        else:
                            self.proxy_manager.record_failure(session_id, country=country)

                    if result.success:
                        duration = time.time() - start_time
                        # Record metrics
                        if self._metrics:
                            self._metrics.record("task.duration", duration, {"task_id": task_id})
                            self._metrics.record("task.success", 1.0, {"task_id": task_id})
                            self._metrics.increment("task.total_success")
                        # Publish success event
                        await self._publish_event("task.completed", {
                            "task_id": task_id,
                            "success": True,
                            "retries": attempt,
                            "duration": duration,
                        })
                        return TaskResult(
                            worker_id=worker_id,
                            success=True,
                            data=result.data,
                            retries=attempt,
                            duration=duration,
                        )

                    # Check if we should retry
                    last_error = result.error
                    last_error_type = result.error_type

                    if attempt < self.max_retries and self._is_retryable(result):
                        delay = self._calculate_delay(attempt)
                        logger.warning(
                            f"Task {task_id} failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                            f"error_type={result.error_type.value if result.error_type else 'unknown'}, "
                            f"retrying in {delay:.1f}s: {result.error}"
                        )
                        retries = attempt + 1
                        # Publish retry event
                        await self._publish_event("task.retry", {
                            "task_id": task_id,
                            "attempt": attempt + 1,
                            "error": result.error,
                            "error_type": result.error_type.value if result.error_type else "unknown",
                        })
                        await self._cleanup_worker(current_worker_id)
                        await asyncio.sleep(delay)
                        continue

                    # Non-retryable error or max retries reached
                    duration = time.time() - start_time
                    # Record failure metrics
                    if self._metrics:
                        self._metrics.record("task.duration", duration, {"task_id": task_id})
                        self._metrics.record("task.failure", 1.0, {"task_id": task_id, "error_type": result.error_type.value if result.error_type else "unknown"})
                        self._metrics.increment("task.total_failure")
                    # Publish failure event
                    await self._publish_event("task.failed", {
                        "task_id": task_id,
                        "error": result.error,
                        "error_type": result.error_type.value if result.error_type else "unknown",
                        "retries": attempt,
                        "duration": duration,
                    })
                    return TaskResult(
                        worker_id=worker_id,
                        success=False,
                        error=result.error,
                        error_type=result.error_type,
                        retries=attempt,
                        duration=duration,
                    )

                except asyncio.CancelledError:
                    logger.warning(f"Task {task_id} cancelled")
                    raise

                except Exception as e:
                    last_error = str(e)
                    last_error_type = ErrorType.UNKNOWN

                    # Classify exception
                    if isinstance(e, asyncio.TimeoutError):
                        last_error_type = ErrorType.TIMEOUT
                    elif isinstance(e, (ConnectionError, ConnectionRefusedError, ConnectionResetError)):
                        last_error_type = ErrorType.CONNECTION

                    logger.error(
                        f"Task {task_id} exception (attempt {attempt + 1}): "
                        f"type={last_error_type.value}, error={e}"
                    )

                    if attempt < self.max_retries and last_error_type in self.RETRYABLE_ERRORS:
                        delay = self._calculate_delay(attempt)
                        logger.warning(f"Retrying in {delay:.1f}s with new proxy")
                        retries = attempt + 1
                        await self._publish_event("task.retry", {
                            "task_id": task_id,
                            "attempt": attempt + 1,
                            "error": str(e),
                            "error_type": last_error_type.value,
                        })
                        await self._cleanup_worker(current_worker_id)
                        await asyncio.sleep(delay)
                        continue

                    duration = time.time() - start_time
                    if self._metrics:
                        self._metrics.record("task.duration", duration, {"task_id": task_id})
                        self._metrics.record("task.failure", 1.0, {"task_id": task_id, "error_type": last_error_type.value})
                        self._metrics.increment("task.total_failure")
                    await self._publish_event("task.failed", {
                        "task_id": task_id,
                        "error": str(e),
                        "error_type": last_error_type.value,
                        "retries": attempt,
                        "duration": duration,
                    })
                    return TaskResult(
                        worker_id=worker_id,
                        success=False,
                        error=str(e),
                        error_type=last_error_type,
                        retries=attempt,
                        duration=duration,
                    )

                finally:
                    await self._cleanup_worker(current_worker_id)

            # Max retries exceeded
            duration = time.time() - start_time
            if self._metrics:
                self._metrics.record("task.duration", duration, {"task_id": task_id})
                self._metrics.record("task.failure", 1.0, {"task_id": task_id, "error_type": "max_retries"})
                self._metrics.increment("task.total_failure")
            await self._publish_event("task.failed", {
                "task_id": task_id,
                "error": f"Max retries exceeded: {last_error}",
                "error_type": last_error_type.value if last_error_type else "unknown",
                "retries": retries,
                "duration": duration,
            })
            return TaskResult(
                worker_id=worker_id,
                success=False,
                error=f"Max retries exceeded: {last_error}",
                error_type=last_error_type,
                retries=retries,
                duration=duration,
            )

    async def run_parallel(
        self,
        tasks: list[tuple[str, Callable[[BrowserWorker], Coroutine[Any, Any, WorkerResult]]]],
    ) -> list[TaskResult]:
        """Run multiple tasks in parallel"""
        if not tasks:
            logger.warning("No tasks provided to run_parallel")
            return []

        logger.info(f"Running {len(tasks)} tasks with max {self.max_workers} workers")
        start_time = time.time()

        coroutines = [self.run_task(task_id, task_fn) for task_id, task_fn in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_type = ErrorType.UNKNOWN
                if isinstance(result, asyncio.TimeoutError):
                    error_type = ErrorType.TIMEOUT
                elif isinstance(result, asyncio.CancelledError):
                    error_type = ErrorType.UNKNOWN

                final_results.append(
                    TaskResult(
                        worker_id=f"worker_{tasks[i][0]}",
                        success=False,
                        error=str(result),
                        error_type=error_type,
                    )
                )
            else:
                final_results.append(result)

        total_duration = time.time() - start_time
        success_count = sum(1 for r in final_results if r.success)
        retry_count = sum(r.retries for r in final_results)

        logger.info(
            f"Completed: {success_count}/{len(tasks)} successful, "
            f"{retry_count} total retries, {total_duration:.2f}s total"
        )

        return final_results

    async def cleanup_all(self) -> None:
        """Clean up all workers"""
        for worker_id in list(self._workers.keys()):
            await self._cleanup_worker(worker_id)

    def get_stats(self) -> dict:
        """Get controller statistics"""
        return {
            "active_workers": len(self._workers),
            "max_workers": self.max_workers,
            "max_retries": self.max_retries,
        }
