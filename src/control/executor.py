"""
Executor - Task execution management
"""
import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional
from loguru import logger

from .state_machine import TaskState, StateMachine, StateMachineRegistry
from ..sense import EventBus, Event


@dataclass
class Task:
    """Task definition"""
    task_id: str
    task_type: str
    target: str  # URL or identifier
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    max_retries: int = 3
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "target": self.target,
            "params": self.params,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "created_at": self.created_at,
        }


@dataclass
class ExecutionResult:
    """Result of task execution"""
    task_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    retries: int = 0
    duration: float = 0.0
    state: TaskState = TaskState.COMPLETED

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "retries": self.retries,
            "duration": self.duration,
            "state": self.state.value,
        }


TaskExecutor = Callable[[Task], Coroutine[Any, Any, ExecutionResult]]


class Executor:
    """
    Manages task execution with state tracking and control.

    Example:
        executor = Executor(event_bus=bus)

        async def my_executor(task: Task) -> ExecutionResult:
            # Execute task
            return ExecutionResult(task.task_id, success=True)

        result = await executor.execute(task, my_executor)
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        max_concurrent: int = 10,
        max_results: int = 10000,
    ):
        self._event_bus = event_bus
        self._registry = StateMachineRegistry()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._pause_events: dict[str, asyncio.Event] = {}
        self._cancel_flags: dict[str, bool] = {}
        self._results: OrderedDict[str, ExecutionResult] = OrderedDict()
        self._max_results = max_results

    async def execute(
        self,
        task: Task,
        executor: TaskExecutor,
    ) -> ExecutionResult:
        """
        Execute a task with state management.

        Args:
            task: Task to execute
            executor: Function to execute the task

        Returns:
            ExecutionResult
        """
        sm = self._registry.create(task.task_id)
        self._pause_events[task.task_id] = asyncio.Event()
        self._pause_events[task.task_id].set()
        self._cancel_flags[task.task_id] = False

        start_time = time.time()

        try:
            async with self._semaphore:
                sm.transition_to(TaskState.RUNNING, "Execution started")
                await self._publish_event("task.started", task.task_id, task.to_dict())

                while not self._cancel_flags.get(task.task_id, False):
                    await self._pause_events[task.task_id].wait()

                    if self._cancel_flags.get(task.task_id, False):
                        break

                    try:
                        result = await asyncio.wait_for(
                            executor(task),
                            timeout=task.timeout,
                        )
                        break
                    except asyncio.TimeoutError:
                        result = ExecutionResult(
                            task_id=task.task_id,
                            success=False,
                            error="Execution timeout",
                            error_type="timeout",
                        )
                        break
                    except Exception as e:
                        result = ExecutionResult(
                            task_id=task.task_id,
                            success=False,
                            error=str(e),
                            error_type="execution_error",
                        )
                        break

                if self._cancel_flags.get(task.task_id, False):
                    sm.transition_to(TaskState.CANCELLED, "Cancelled by user")
                    result = ExecutionResult(
                        task_id=task.task_id,
                        success=False,
                        error="Task cancelled",
                        state=TaskState.CANCELLED,
                    )
                elif result.success:
                    sm.transition_to(TaskState.COMPLETED, "Execution successful")
                    result.state = TaskState.COMPLETED
                else:
                    sm.transition_to(TaskState.FAILED, result.error or "Unknown error")
                    result.state = TaskState.FAILED

        except Exception as e:
            logger.error(f"Executor error for {task.task_id}: {e}")
            if not sm.is_terminal:
                sm.transition_to(TaskState.FAILED, str(e))
            result = ExecutionResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                error_type="executor_error",
                state=TaskState.FAILED,
            )

        finally:
            result.duration = time.time() - start_time
            self._results[task.task_id] = result
            while len(self._results) > self._max_results:
                self._results.popitem(last=False)
            await self._publish_event(
                "task.completed" if result.success else "task.failed",
                task.task_id,
                result.to_dict(),
            )
            self._cleanup_task(task.task_id)

        return result

    async def pause(self, task_id: str) -> bool:
        """
        Pause a running task.

        Returns:
            True if task was paused
        """
        sm = self._registry.get(task_id)
        if not sm or sm.state != TaskState.RUNNING:
            return False

        sm.transition_to(TaskState.PAUSED, "Paused by user")
        self._pause_events[task_id].clear()
        await self._publish_event("task.paused", task_id, {})
        return True

    async def resume(self, task_id: str) -> bool:
        """
        Resume a paused task.

        Returns:
            True if task was resumed
        """
        sm = self._registry.get(task_id)
        if not sm or sm.state != TaskState.PAUSED:
            return False

        sm.transition_to(TaskState.RUNNING, "Resumed by user")
        self._pause_events[task_id].set()
        await self._publish_event("task.resumed", task_id, {})
        return True

    async def cancel(self, task_id: str) -> bool:
        """
        Cancel a task.

        Returns:
            True if cancellation was requested
        """
        sm = self._registry.get(task_id)
        if not sm or sm.is_terminal:
            return False

        self._cancel_flags[task_id] = True
        if task_id in self._pause_events:
            self._pause_events[task_id].set()

        await self._publish_event("task.cancellation_requested", task_id, {})
        return True

    def get_state(self, task_id: str) -> Optional[TaskState]:
        """Get current state of a task"""
        sm = self._registry.get(task_id)
        return sm.state if sm else None

    def get_result(self, task_id: str) -> Optional[ExecutionResult]:
        """Get execution result for a task"""
        return self._results.get(task_id)

    def get_active_tasks(self) -> list[str]:
        """Get IDs of active tasks"""
        return [sm.task_id for sm in self._registry.get_active()]

    def get_stats(self) -> dict:
        """Get executor statistics"""
        machines = self._registry.get_all()
        by_state = {}
        for sm in machines:
            state = sm.state.value
            by_state[state] = by_state.get(state, 0) + 1

        successful = sum(1 for r in self._results.values() if r.success)
        failed = sum(1 for r in self._results.values() if not r.success)

        return {
            "total_tasks": len(machines),
            "active_tasks": len(self._registry.get_active()),
            "by_state": by_state,
            "completed_successful": successful,
            "completed_failed": failed,
            "results_cached": len(self._results),
        }

    async def _publish_event(
        self,
        event_type: str,
        task_id: str,
        data: dict,
    ) -> None:
        """Publish event to event bus"""
        if self._event_bus:
            await self._event_bus.publish(Event(
                event_type=event_type,
                source="executor",
                data={"task_id": task_id, **data},
            ))

    def _cleanup_task(self, task_id: str) -> None:
        """Clean up task resources"""
        if task_id in self._pause_events:
            del self._pause_events[task_id]
        if task_id in self._cancel_flags:
            del self._cancel_flags[task_id]
