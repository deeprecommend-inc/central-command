"""
Strategy - Decision making strategies
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from loguru import logger

from .decision_context import DecisionContext


@dataclass
class Decision:
    """Result of a strategic decision"""
    action: str  # "proceed", "retry", "abort", "switch_proxy", "wait"
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reasoning: str = ""
    priority: int = 0  # Higher = more important
    signature: Any = None  # PQC signature, optional

    def __post_init__(self):
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict:
        d = {
            "action": self.action,
            "params": self.params,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "priority": self.priority,
        }
        if self.signature is not None:
            d["signature"] = self.signature.to_dict() if hasattr(self.signature, "to_dict") else str(self.signature)
        return d

    def signable_bytes(self) -> bytes:
        """Deterministic JSON serialization for signing"""
        import json
        payload = {
            "action": self.action,
            "params": self.params,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class Strategy(ABC):
    """
    Abstract base class for decision strategies.

    Example:
        class CustomStrategy(Strategy):
            def evaluate(self, context: DecisionContext) -> Optional[Decision]:
                if context.success_rate < 0.5:
                    return Decision("abort", reasoning="Too many failures")
                return Decision("proceed")
    """

    @abstractmethod
    def evaluate(self, context: DecisionContext) -> Optional[Decision]:
        """
        Evaluate context and return a decision.

        Args:
            context: Decision context with all relevant information

        Returns:
            Decision or None if strategy doesn't apply
        """
        pass

    @property
    def name(self) -> str:
        """Strategy name"""
        return self.__class__.__name__


class RetryStrategy(Strategy):
    """
    Strategy for retry decisions.

    Decides whether to retry a failed operation based on:
    - Error type (retryable vs non-retryable)
    - Retry count
    - System health
    """

    RETRYABLE_ERRORS = {"timeout", "connection", "proxy"}
    NON_RETRYABLE_ERRORS = {"element_not_found", "validation", "browser_closed"}

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

    def evaluate(self, context: DecisionContext) -> Optional[Decision]:
        """Evaluate retry decision"""
        task = context.task_context
        if not task:
            return None

        if not task.last_error_type:
            return Decision("proceed", confidence=1.0, reasoning="No error to retry")

        error_type = task.last_error_type.lower()

        if error_type in self.NON_RETRYABLE_ERRORS:
            return Decision(
                action="abort",
                confidence=0.95,
                reasoning=f"Non-retryable error: {error_type}",
            )

        if not task.can_retry:
            return Decision(
                action="abort",
                params={"reason": "max_retries_exceeded"},
                confidence=0.9,
                reasoning=f"Exceeded max retries ({self.max_retries})",
            )

        if error_type in self.RETRYABLE_ERRORS:
            delay = self._calculate_backoff(task.retry_count)
            return Decision(
                action="retry",
                params={
                    "delay": delay,
                    "switch_proxy": error_type == "proxy",
                },
                confidence=0.8,
                reasoning=f"Retryable error: {error_type}, attempt {task.retry_count + 1}",
            )

        if not context.is_healthy:
            return Decision(
                action="wait",
                params={"delay": 5.0},
                confidence=0.7,
                reasoning="System unhealthy, waiting before retry",
            )

        return Decision(
            action="retry",
            params={"delay": self._calculate_backoff(task.retry_count)},
            confidence=0.6,
            reasoning=f"Unknown error, attempting retry",
        )

    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.backoff_base * (2 ** retry_count)
        return min(delay, self.backoff_max)


class ProxySelectionStrategy(Strategy):
    """
    Strategy for proxy selection.

    Decides which proxy to use based on:
    - Health scores
    - Recent failures
    - Geographic distribution
    """

    def __init__(self, health_threshold: float = 0.5):
        self.health_threshold = health_threshold

    def evaluate(self, context: DecisionContext) -> Optional[Decision]:
        """Evaluate proxy selection decision"""
        proxy_stats = context.system_state.proxy_stats

        if not proxy_stats:
            return Decision(
                action="use_default_proxy",
                confidence=0.5,
                reasoning="No proxy stats available",
            )

        healthy_proxies = []
        for country, stats in proxy_stats.items():
            if isinstance(stats, dict):
                health = stats.get("health_score", 0)
                if health >= self.health_threshold:
                    healthy_proxies.append((country, health))

        if not healthy_proxies:
            return Decision(
                action="reset_proxies",
                confidence=0.7,
                reasoning="No healthy proxies, resetting all",
            )

        healthy_proxies.sort(key=lambda x: x[1], reverse=True)
        best_country = healthy_proxies[0][0]
        best_health = healthy_proxies[0][1]

        return Decision(
            action="select_proxy",
            params={
                "country": best_country,
                "health_score": best_health,
            },
            confidence=best_health,
            reasoning=f"Selected {best_country} with health {best_health:.2f}",
        )


class AdaptiveStrategy(Strategy):
    """
    Adaptive strategy that adjusts behavior based on system state.
    """

    def __init__(self):
        self.retry_strategy = RetryStrategy()
        self.proxy_strategy = ProxySelectionStrategy()

    def evaluate(self, context: DecisionContext) -> Optional[Decision]:
        """Evaluate adaptive decision"""
        if context.get_error_frequency() > 0.5:
            return Decision(
                action="reduce_parallelism",
                params={"factor": 0.5},
                confidence=0.8,
                reasoning="High error rate, reducing parallelism",
                priority=10,
            )

        if context.success_rate < 0.3:
            return Decision(
                action="pause_operations",
                params={"duration": 60},
                confidence=0.9,
                reasoning="Critical success rate, pausing",
                priority=20,
            )

        task = context.task_context
        if task and task.last_error_type:
            return self.retry_strategy.evaluate(context)

        if not context.is_healthy:
            return self.proxy_strategy.evaluate(context)

        return Decision(
            action="proceed",
            confidence=0.9,
            reasoning="System healthy, proceeding normally",
        )
