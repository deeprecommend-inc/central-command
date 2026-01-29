"""
Parallel Controller - Manages multiple browser workers
"""
import asyncio
from typing import Optional, Callable, Any, Coroutine
from dataclasses import dataclass
from loguru import logger

from .proxy_manager import ProxyManager, ProxyConfig
from .ua_manager import UserAgentManager, BrowserProfile
from .browser_worker import BrowserWorker, WorkerResult


@dataclass
class TaskResult:
    """Result from parallel task execution"""

    worker_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    retries: int = 0


class ParallelController:
    """Manages parallel browser workers with proxy and UA rotation"""

    # Retry settings
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 30.0  # seconds

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        ua_manager: Optional[UserAgentManager] = None,
        max_workers: int = 5,
        headless: bool = True,
        max_retries: int = 3,
    ):
        self.proxy_manager = proxy_manager
        self.ua_manager = ua_manager or UserAgentManager()
        self.max_workers = max_workers
        self.headless = headless
        self.max_retries = max_retries
        self._workers: dict[str, BrowserWorker] = {}
        self._semaphore = asyncio.Semaphore(max_workers)

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
            await self._workers[worker_id].stop()
            del self._workers[worker_id]
            self.ua_manager.clear_session(worker_id)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.BASE_DELAY * (2 ** attempt)
        return min(delay, self.MAX_DELAY)

    def _is_proxy_error(self, error: str) -> bool:
        """Check if error is proxy-related"""
        proxy_errors = [
            "proxy",
            "connection refused",
            "connection reset",
            "timeout",
            "ECONNREFUSED",
            "ETIMEDOUT",
            "tunnel",
        ]
        error_lower = error.lower()
        return any(e in error_lower for e in proxy_errors)

    async def run_task(
        self,
        task_id: str,
        task_fn: Callable[[BrowserWorker], Coroutine[Any, Any, WorkerResult]],
    ) -> TaskResult:
        """Run a single task with automatic worker management and retry"""
        worker_id = f"worker_{task_id}"
        last_error = None
        retries = 0

        async with self._semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    # Create worker with fresh proxy on retry
                    worker = await self._create_worker(f"{worker_id}_attempt{attempt}")
                    result = await task_fn(worker)

                    # Record proxy stats
                    if self.proxy_manager and worker.proxy and worker.proxy.session_id:
                        if result.success:
                            self.proxy_manager.record_success(worker.proxy.session_id)
                        else:
                            self.proxy_manager.record_failure(worker.proxy.session_id)

                    if result.success:
                        return TaskResult(
                            worker_id=worker_id,
                            success=True,
                            data=result.data,
                            retries=attempt,
                        )

                    # Check if we should retry
                    last_error = result.error
                    if attempt < self.max_retries and self._is_proxy_error(result.error or ""):
                        delay = self._calculate_delay(attempt)
                        logger.warning(
                            f"Task {task_id} failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                            f"retrying in {delay:.1f}s with new proxy: {result.error}"
                        )
                        await self._cleanup_worker(f"{worker_id}_attempt{attempt}")
                        await asyncio.sleep(delay)
                        retries = attempt + 1
                        continue

                    return TaskResult(
                        worker_id=worker_id,
                        success=False,
                        error=result.error,
                        retries=attempt,
                    )

                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Task {task_id} exception (attempt {attempt + 1}): {e}")

                    if attempt < self.max_retries and self._is_proxy_error(str(e)):
                        delay = self._calculate_delay(attempt)
                        logger.warning(f"Retrying in {delay:.1f}s with new proxy")
                        await self._cleanup_worker(f"{worker_id}_attempt{attempt}")
                        await asyncio.sleep(delay)
                        retries = attempt + 1
                        continue

                    return TaskResult(
                        worker_id=worker_id,
                        success=False,
                        error=str(e),
                        retries=attempt,
                    )

                finally:
                    await self._cleanup_worker(f"{worker_id}_attempt{attempt}")

            return TaskResult(
                worker_id=worker_id,
                success=False,
                error=f"Max retries exceeded: {last_error}",
                retries=retries,
            )

    async def run_parallel(
        self,
        tasks: list[tuple[str, Callable[[BrowserWorker], Coroutine[Any, Any, WorkerResult]]]],
    ) -> list[TaskResult]:
        """Run multiple tasks in parallel"""
        logger.info(f"Running {len(tasks)} tasks with max {self.max_workers} workers")

        coroutines = [self.run_task(task_id, task_fn) for task_id, task_fn in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    TaskResult(
                        worker_id=f"worker_{tasks[i][0]}",
                        success=False,
                        error=str(result),
                    )
                )
            else:
                final_results.append(result)

        success_count = sum(1 for r in final_results if r.success)
        logger.info(f"Completed: {success_count}/{len(tasks)} successful")

        return final_results

    async def cleanup_all(self) -> None:
        """Clean up all workers"""
        for worker_id in list(self._workers.keys()):
            await self._cleanup_worker(worker_id)
