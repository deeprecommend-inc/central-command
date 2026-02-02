"""
Feedback Loop - Continuous improvement through feedback
"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from loguru import logger

from .executor import ExecutionResult
from ..sense import EventBus, Event, MetricsCollector


@dataclass
class Feedback:
    """Feedback from execution"""
    task_id: str
    success: bool
    metric_type: str  # "response_time", "error_rate", "success_rate"
    value: float
    timestamp: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "metric_type": self.metric_type,
            "value": self.value,
            "timestamp": self.timestamp,
            "context": self.context,
        }


@dataclass
class Adjustment:
    """Recommended adjustment based on feedback"""
    parameter: str
    current_value: Any
    recommended_value: Any
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "confidence": self.confidence,
            "reason": self.reason,
        }


AdjustmentHandler = Callable[[Adjustment], None]


class FeedbackLoop:
    """
    Collects execution feedback and suggests adjustments.

    Example:
        loop = FeedbackLoop(metrics_collector=metrics)

        # Register adjustment handler
        loop.on_adjustment(lambda adj: print(f"Adjust {adj.parameter}"))

        # Process execution result
        await loop.on_result(result)

        # Get recommended adjustments
        adjustments = loop.get_adjustments()
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        window_size: int = 100,
    ):
        self._event_bus = event_bus
        self._metrics = metrics_collector
        self._window_size = window_size
        self._feedback_history: list[Feedback] = []
        self._adjustment_handlers: list[AdjustmentHandler] = []
        self._current_params: dict[str, Any] = {
            "parallel_sessions": 5,
            "timeout": 30.0,
            "retry_delay": 1.0,
            "max_retries": 3,
        }

    async def on_result(self, result: ExecutionResult) -> list[Feedback]:
        """
        Process an execution result and generate feedback.

        Args:
            result: Execution result

        Returns:
            List of generated feedback items
        """
        feedback_items = []

        success_feedback = Feedback(
            task_id=result.task_id,
            success=result.success,
            metric_type="success",
            value=1.0 if result.success else 0.0,
            context={"error_type": result.error_type},
        )
        feedback_items.append(success_feedback)

        if result.duration > 0:
            duration_feedback = Feedback(
                task_id=result.task_id,
                success=result.success,
                metric_type="response_time",
                value=result.duration,
            )
            feedback_items.append(duration_feedback)

        if result.retries > 0:
            retry_feedback = Feedback(
                task_id=result.task_id,
                success=result.success,
                metric_type="retries",
                value=float(result.retries),
            )
            feedback_items.append(retry_feedback)

        for fb in feedback_items:
            self._record_feedback(fb)

        if self._metrics:
            self._metrics.record("feedback.success", success_feedback.value)
            if result.duration > 0:
                self._metrics.record("feedback.duration", result.duration)

        await self._check_adjustments()

        return feedback_items

    def _record_feedback(self, feedback: Feedback) -> None:
        """Record feedback in history"""
        self._feedback_history.append(feedback)
        if len(self._feedback_history) > self._window_size:
            self._feedback_history = self._feedback_history[-self._window_size:]

    async def _check_adjustments(self) -> None:
        """Check if adjustments are needed based on recent feedback"""
        if len(self._feedback_history) < 10:
            return

        adjustments = self.get_adjustments()
        for adj in adjustments:
            if adj.confidence >= 0.7:
                logger.info(
                    f"Adjustment recommended: {adj.parameter} "
                    f"{adj.current_value} -> {adj.recommended_value} "
                    f"({adj.reason})"
                )
                for handler in self._adjustment_handlers:
                    try:
                        handler(adj)
                    except Exception as e:
                        logger.error(f"Adjustment handler error: {e}")

                if self._event_bus:
                    await self._event_bus.publish(Event(
                        event_type="feedback.adjustment",
                        source="feedback_loop",
                        data=adj.to_dict(),
                    ))

    def get_adjustments(self) -> list[Adjustment]:
        """
        Analyze feedback and suggest parameter adjustments.

        Returns:
            List of recommended adjustments
        """
        adjustments = []

        success_fb = [
            fb for fb in self._feedback_history
            if fb.metric_type == "success"
        ]
        if success_fb:
            success_rate = sum(fb.value for fb in success_fb) / len(success_fb)

            if success_rate < 0.5:
                adjustments.append(Adjustment(
                    parameter="parallel_sessions",
                    current_value=self._current_params["parallel_sessions"],
                    recommended_value=max(1, self._current_params["parallel_sessions"] // 2),
                    confidence=0.8,
                    reason=f"Low success rate ({success_rate:.1%}), reduce parallelism",
                ))

            if success_rate < 0.7:
                adjustments.append(Adjustment(
                    parameter="max_retries",
                    current_value=self._current_params["max_retries"],
                    recommended_value=min(5, self._current_params["max_retries"] + 1),
                    confidence=0.7,
                    reason=f"Moderate success rate ({success_rate:.1%}), increase retries",
                ))

        duration_fb = [
            fb for fb in self._feedback_history
            if fb.metric_type == "response_time"
        ]
        if duration_fb:
            avg_duration = sum(fb.value for fb in duration_fb) / len(duration_fb)

            if avg_duration > 20:
                adjustments.append(Adjustment(
                    parameter="timeout",
                    current_value=self._current_params["timeout"],
                    recommended_value=min(60, self._current_params["timeout"] * 1.5),
                    confidence=0.75,
                    reason=f"High avg response time ({avg_duration:.1f}s), increase timeout",
                ))

        retry_fb = [
            fb for fb in self._feedback_history
            if fb.metric_type == "retries" and fb.value > 0
        ]
        if retry_fb:
            avg_retries = sum(fb.value for fb in retry_fb) / len(retry_fb)
            retry_rate = len(retry_fb) / len(success_fb) if success_fb else 0

            if retry_rate > 0.3 and avg_retries > 1:
                adjustments.append(Adjustment(
                    parameter="retry_delay",
                    current_value=self._current_params["retry_delay"],
                    recommended_value=min(5.0, self._current_params["retry_delay"] * 1.5),
                    confidence=0.65,
                    reason=f"High retry rate ({retry_rate:.1%}), increase delay",
                ))

        return adjustments

    def on_adjustment(self, handler: AdjustmentHandler) -> None:
        """Register an adjustment handler"""
        self._adjustment_handlers.append(handler)

    def update_params(self, params: dict[str, Any]) -> None:
        """Update current parameter values"""
        self._current_params.update(params)

    def get_summary(self) -> dict:
        """Get feedback summary"""
        if not self._feedback_history:
            return {
                "status": "no_data",
                "samples": 0,
                "current_params": self._current_params,
            }

        success_fb = [fb for fb in self._feedback_history if fb.metric_type == "success"]
        duration_fb = [fb for fb in self._feedback_history if fb.metric_type == "response_time"]

        return {
            "samples": len(self._feedback_history),
            "success_rate": (
                sum(fb.value for fb in success_fb) / len(success_fb)
                if success_fb else 0
            ),
            "avg_duration": (
                sum(fb.value for fb in duration_fb) / len(duration_fb)
                if duration_fb else 0
            ),
            "adjustment_handlers": len(self._adjustment_handlers),
            "current_params": self._current_params,
        }

    def clear_history(self) -> None:
        """Clear feedback history"""
        self._feedback_history.clear()
