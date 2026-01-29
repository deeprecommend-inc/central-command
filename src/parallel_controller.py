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


class ParallelController:
    """Manages parallel browser workers with proxy and UA rotation"""

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        ua_manager: Optional[UserAgentManager] = None,
        max_workers: int = 5,
        headless: bool = True,
    ):
        self.proxy_manager = proxy_manager
        self.ua_manager = ua_manager or UserAgentManager()
        self.max_workers = max_workers
        self.headless = headless
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

    async def run_task(
        self,
        task_id: str,
        task_fn: Callable[[BrowserWorker], Coroutine[Any, Any, WorkerResult]],
    ) -> TaskResult:
        """Run a single task with automatic worker management"""
        worker_id = f"worker_{task_id}"

        async with self._semaphore:
            try:
                worker = await self._create_worker(worker_id)
                result = await task_fn(worker)

                # Record proxy stats
                if self.proxy_manager and worker.proxy and worker.proxy.session_id:
                    if result.success:
                        self.proxy_manager.record_success(worker.proxy.session_id)
                    else:
                        self.proxy_manager.record_failure(worker.proxy.session_id)

                return TaskResult(
                    worker_id=worker_id,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                )

            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                return TaskResult(worker_id=worker_id, success=False, error=str(e))

            finally:
                await self._cleanup_worker(worker_id)

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
