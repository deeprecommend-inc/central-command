"""
CCP - Central Command Platform

Orchestrates the Sense-Think-Command-Control-Learn cycle.
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Coroutine
from loguru import logger

from .sense import EventBus, MetricsCollector, StateSnapshot, SystemState, Event
from .think import (
    DecisionContext, TaskContext, Strategy, Decision,
    RulesEngine, RetryStrategy, AdaptiveStrategy
)
from .control import (
    Executor, ExecutionResult, Task, TaskState,
    FeedbackLoop, Feedback
)
from .learn import (
    KnowledgeStore, KnowledgeEntry,
    PatternDetector, PerformanceAnalyzer, PerformanceReport
)
from .web_agent import WebAgent, AgentConfig


@dataclass
class CycleResult:
    """Result of a complete CCP cycle"""
    task_id: str
    success: bool
    state: SystemState
    decision: Decision
    execution_result: ExecutionResult
    feedback: list[Feedback]
    duration: float = 0.0
    cycle_number: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "state": self.state.to_dict(),
            "decision": self.decision.to_dict(),
            "execution_result": self.execution_result.to_dict(),
            "feedback_count": len(self.feedback),
            "duration": self.duration,
            "cycle_number": self.cycle_number,
        }


class SenseLayer:
    """Aggregated Sense layer components"""

    def __init__(self):
        self.event_bus = EventBus()
        self.metrics = MetricsCollector()
        self.snapshot = StateSnapshot(
            event_bus=self.event_bus,
            metrics_collector=self.metrics,
        )

    def get_state(self) -> SystemState:
        """Get current system state"""
        return self.snapshot.get_current_state()

    def record_metric(self, name: str, value: float, tags: dict = None) -> None:
        """Record a metric"""
        self.metrics.record(name, value, tags)

    async def publish_event(self, event: Event) -> None:
        """Publish an event"""
        await self.event_bus.publish(event)


class ThinkLayer:
    """Aggregated Think layer components"""

    def __init__(self):
        self.rules_engine = RulesEngine.create_default()
        self.retry_strategy = RetryStrategy()
        self.adaptive_strategy = AdaptiveStrategy()

    def decide(
        self,
        state: SystemState,
        task_context: Optional[TaskContext] = None,
        events: list[Event] = None,
    ) -> Decision:
        """Make a decision based on context"""
        context = DecisionContext(
            system_state=state,
            task_context=task_context,
            recent_events=events or [],
        )

        decision = self.rules_engine.evaluate_first(context)
        if decision:
            return decision

        decision = self.adaptive_strategy.evaluate(context)
        if decision:
            return decision

        return Decision(action="proceed", confidence=0.5, reasoning="Default action")

    def add_rule(self, rule) -> None:
        """Add a custom rule"""
        self.rules_engine.add_rule(rule)


class ControlLayer:
    """Aggregated Control layer components"""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.executor = Executor(event_bus=event_bus)
        self.feedback_loop = FeedbackLoop(event_bus=event_bus)

    async def execute(
        self,
        task: Task,
        executor_fn: Callable[[Task], Coroutine[Any, Any, ExecutionResult]],
    ) -> ExecutionResult:
        """Execute a task"""
        return await self.executor.execute(task, executor_fn)

    async def process_result(self, result: ExecutionResult) -> list[Feedback]:
        """Process execution result through feedback loop"""
        return await self.feedback_loop.on_result(result)

    async def pause(self, task_id: str) -> bool:
        """Pause a task"""
        return await self.executor.pause(task_id)

    async def resume(self, task_id: str) -> bool:
        """Resume a task"""
        return await self.executor.resume(task_id)

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task"""
        return await self.executor.cancel(task_id)


class LearnLayer:
    """Aggregated Learn layer components"""

    def __init__(
        self,
        metrics_collector: Optional[MetricsCollector] = None,
        state_snapshot: Optional[StateSnapshot] = None,
    ):
        self.knowledge = KnowledgeStore()
        self.patterns = PatternDetector()
        self.analyzer = PerformanceAnalyzer(
            metrics_collector=metrics_collector,
            state_snapshot=state_snapshot,
        )

    def record(self, key: str, value: Any, confidence: float = 1.0) -> None:
        """Record knowledge"""
        entry = KnowledgeEntry(
            key=key,
            value=value,
            confidence=confidence,
            source="ccp",
        )
        self.knowledge.store(entry)

    def query(self, key: str) -> Optional[KnowledgeEntry]:
        """Query knowledge"""
        return self.knowledge.query(key)

    def analyze_events(self, events: list[Event]) -> list:
        """Analyze events for patterns"""
        return self.patterns.analyze_events(events)

    def generate_report(self) -> PerformanceReport:
        """Generate performance report"""
        return self.analyzer.generate_report()


class CCPOrchestrator:
    """
    Central Command Platform Orchestrator.

    Coordinates the Sense-Think-Command-Control-Learn cycle.

    Example:
        config = AgentConfig(parallel_sessions=5)

        async with CCPOrchestrator(config) as ccp:
            result = await ccp.run("https://example.com")
            print(f"Success: {result.success}")
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        web_agent: Optional[WebAgent] = None,
    ):
        self._config = config or AgentConfig()
        self._cycle_count = 0
        self._is_closed = False

        self.sense = SenseLayer()
        self.think = ThinkLayer()
        self.control = ControlLayer(event_bus=self.sense.event_bus)
        self.learn = LearnLayer(
            metrics_collector=self.sense.metrics,
            state_snapshot=self.sense.snapshot,
        )

        self._web_agent = web_agent
        self._owns_web_agent = web_agent is None

        self.control.feedback_loop.on_adjustment(self._handle_adjustment)

    async def __aenter__(self) -> "CCPOrchestrator":
        """Async context manager entry"""
        if self._web_agent is None:
            # Create WebAgent with Sense layer integration
            self._web_agent = WebAgent(
                self._config,
                event_bus=self.sense.event_bus,
                metrics_collector=self.sense.metrics,
            )
            await self._web_agent.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit"""
        await self.cleanup()

    async def cleanup(self) -> None:
        """Clean up resources"""
        if self._is_closed:
            return

        if self._owns_web_agent and self._web_agent:
            await self._web_agent.cleanup()

        self._is_closed = True
        logger.info("CCP Orchestrator cleaned up")

    @property
    def is_closed(self) -> bool:
        """Check if orchestrator is closed"""
        return self._is_closed

    async def run(
        self,
        target: str,
        task_type: str = "navigate",
        params: dict = None,
    ) -> CycleResult:
        """
        Run a complete CCP cycle.

        Args:
            target: Target URL or identifier
            task_type: Type of task
            params: Additional parameters

        Returns:
            CycleResult with complete cycle information
        """
        if self._is_closed:
            raise RuntimeError("Orchestrator is closed")

        self._cycle_count += 1
        cycle_start = time.time()
        task_id = f"ccp_{self._cycle_count}_{int(time.time())}"

        logger.info(f"Starting CCP cycle {self._cycle_count}: {task_type} -> {target}")

        state = self.sense.get_state()
        self.sense.snapshot.save_snapshot()

        task_context = TaskContext(
            task_id=task_id,
            task_type=task_type,
            target_url=target if task_type == "navigate" else None,
            max_retries=self._config.max_retries,
        )

        events = self.sense.event_bus.get_history(limit=20)
        decision = self.think.decide(state, task_context, events)
        logger.debug(f"Decision: {decision.action} ({decision.reasoning})")

        if decision.action == "abort":
            return CycleResult(
                task_id=task_id,
                success=False,
                state=state,
                decision=decision,
                execution_result=ExecutionResult(
                    task_id=task_id,
                    success=False,
                    error=decision.reasoning,
                    state=TaskState.CANCELLED,
                ),
                feedback=[],
                duration=time.time() - cycle_start,
                cycle_number=self._cycle_count,
            )

        if decision.action == "wait":
            delay = decision.params.get("delay", 5.0)
            await asyncio.sleep(delay)

        task = Task(
            task_id=task_id,
            task_type=task_type,
            target=target,
            params=params or {},
            max_retries=self._config.max_retries,
        )

        async def execute_task(t: Task) -> ExecutionResult:
            return await self._execute_command(t)

        result = await self.control.execute(task, execute_task)

        feedback = await self.control.process_result(result)

        self._record_learning(result, decision, feedback)

        if result.success:
            self.sense.snapshot.record_success()
        else:
            self.sense.snapshot.record_error()

        self.sense.record_metric("cycle.duration", time.time() - cycle_start)
        self.sense.record_metric("cycle.success", 1.0 if result.success else 0.0)

        await self.sense.publish_event(Event(
            event_type="cycle.completed",
            source="ccp",
            data={
                "task_id": task_id,
                "success": result.success,
                "cycle_number": self._cycle_count,
            },
        ))

        cycle_result = CycleResult(
            task_id=task_id,
            success=result.success,
            state=state,
            decision=decision,
            execution_result=result,
            feedback=feedback,
            duration=time.time() - cycle_start,
            cycle_number=self._cycle_count,
        )

        logger.info(
            f"CCP cycle {self._cycle_count} completed: "
            f"{'success' if result.success else 'failed'} "
            f"in {cycle_result.duration:.2f}s"
        )

        return cycle_result

    async def run_parallel(
        self,
        targets: list[str],
        task_type: str = "navigate",
    ) -> list[CycleResult]:
        """
        Run multiple CCP cycles in parallel.

        Args:
            targets: List of targets
            task_type: Type of task

        Returns:
            List of CycleResults
        """
        tasks = [self.run(target, task_type) for target in targets]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_command(self, task: Task) -> ExecutionResult:
        """Execute command layer (WebAgent)"""
        if not self._web_agent:
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                error="WebAgent not initialized",
                error_type="configuration",
            )

        try:
            if task.task_type == "navigate":
                result = await self._web_agent.navigate(task.target)
                return ExecutionResult(
                    task_id=task.task_id,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                    error_type=result.error_type.value if result.error_type else None,
                    retries=result.retries,
                    duration=result.duration,
                )
            else:
                return ExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    error=f"Unknown task type: {task.task_type}",
                    error_type="validation",
                )
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                error_type="execution_error",
            )

    def _record_learning(
        self,
        result: ExecutionResult,
        decision: Decision,
        feedback: list[Feedback],
    ) -> None:
        """Record learning from cycle"""
        self.learn.record(
            f"cycle.{result.task_id}.success",
            result.success,
            confidence=0.9,
        )

        self.learn.record(
            f"decision.{decision.action}.accuracy",
            1.0 if result.success else 0.0,
            confidence=decision.confidence,
        )

        events = self.sense.event_bus.get_history(limit=50)
        patterns = self.learn.analyze_events(events)
        for pattern in patterns:
            self.learn.record(
                f"pattern.{pattern.pattern_type}",
                pattern.to_dict(),
                confidence=pattern.confidence,
            )

    def _handle_adjustment(self, adjustment) -> None:
        """Handle feedback loop adjustments"""
        logger.info(
            f"Applying adjustment: {adjustment.parameter} = "
            f"{adjustment.recommended_value}"
        )

    def get_stats(self) -> dict:
        """Get orchestrator statistics"""
        return {
            "cycle_count": self._cycle_count,
            "is_closed": self._is_closed,
            "sense": {
                "metrics": self.sense.metrics.get_stats(),
                "events": self.sense.event_bus.get_subscriber_count(),
            },
            "think": {
                "rules": len(self.think.rules_engine),
            },
            "control": self.control.executor.get_stats(),
            "learn": {
                "knowledge": self.learn.knowledge.get_stats(),
            },
        }

    def get_report(self) -> PerformanceReport:
        """Generate performance report"""
        return self.learn.generate_report()
