"""
Metrics Collector - Time-series metrics collection
"""
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional
from loguru import logger


@dataclass
class Metric:
    """Single metric data point"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedMetric:
    """Aggregated metric statistics"""
    name: str
    count: int
    sum: float
    min: float
    max: float
    avg: float
    window_seconds: float

    @property
    def rate(self) -> float:
        """Events per second"""
        if self.window_seconds > 0:
            return self.count / self.window_seconds
        return 0.0


class MetricsCollector:
    """
    In-memory metrics collector with time-window aggregation.

    Example:
        collector = MetricsCollector()
        collector.record("request.duration", 0.5, {"endpoint": "/api"})
        collector.record("request.duration", 0.3, {"endpoint": "/api"})

        stats = collector.get_aggregated("request.duration", timedelta(minutes=5))
        print(f"Avg: {stats.avg}, Count: {stats.count}")
    """

    def __init__(self, max_points: int = 10000, retention_seconds: float = 3600):
        self._metrics: dict[str, deque[Metric]] = {}
        self._max_points = max_points
        self._retention_seconds = retention_seconds
        self._counters: dict[str, float] = {}

    def record(
        self,
        name: str,
        value: float,
        tags: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Record a metric data point.

        Args:
            name: Metric name (e.g., "request.duration")
            value: Metric value
            tags: Optional key-value tags
        """
        metric = Metric(name=name, value=value, tags=tags or {})
        if name not in self._metrics:
            self._metrics[name] = deque(maxlen=self._max_points)
        self._metrics[name].append(metric)
        logger.debug(f"Recorded metric: {name}={value}")

    def increment(self, name: str, value: float = 1.0) -> float:
        """
        Increment a counter.

        Args:
            name: Counter name
            value: Increment amount

        Returns:
            New counter value
        """
        self._counters[name] = self._counters.get(name, 0.0) + value
        return self._counters[name]

    def get_counter(self, name: str) -> float:
        """Get current counter value"""
        return self._counters.get(name, 0.0)

    def reset_counter(self, name: str) -> None:
        """Reset counter to zero"""
        self._counters[name] = 0.0

    def get_aggregated(
        self,
        name: str,
        window: timedelta,
        tags: Optional[dict[str, str]] = None,
    ) -> Optional[AggregatedMetric]:
        """
        Get aggregated statistics for a metric.

        Args:
            name: Metric name
            window: Time window for aggregation
            tags: Optional tag filter

        Returns:
            AggregatedMetric or None if no data
        """
        if name not in self._metrics:
            return None

        now = time.time()
        cutoff = now - window.total_seconds()

        points = [
            m for m in self._metrics[name]
            if m.timestamp >= cutoff
        ]

        if tags:
            points = [
                m for m in points
                if all(m.tags.get(k) == v for k, v in tags.items())
            ]

        if not points:
            return None

        values = [m.value for m in points]
        return AggregatedMetric(
            name=name,
            count=len(values),
            sum=sum(values),
            min=min(values),
            max=max(values),
            avg=sum(values) / len(values),
            window_seconds=window.total_seconds(),
        )

    def get_latest(self, name: str, count: int = 1) -> list[Metric]:
        """Get latest N metrics"""
        if name not in self._metrics:
            return []
        return list(self._metrics[name])[-count:]

    def get_all_names(self) -> list[str]:
        """Get all metric names"""
        return list(self._metrics.keys())

    def cleanup(self) -> int:
        """
        Remove old metrics beyond retention period.

        Returns:
            Number of removed data points
        """
        cutoff = time.time() - self._retention_seconds
        removed = 0

        for name in list(self._metrics.keys()):
            before = len(self._metrics[name])
            filtered = [m for m in self._metrics[name] if m.timestamp >= cutoff]
            removed += before - len(filtered)

            if not filtered:
                del self._metrics[name]
            else:
                self._metrics[name] = deque(filtered, maxlen=self._max_points)

        if removed > 0:
            logger.debug(f"Cleaned up {removed} old metrics")
        return removed

    def clear(self) -> None:
        """Clear all metrics"""
        self._metrics.clear()
        self._counters.clear()

    def get_stats(self) -> dict:
        """Get collector statistics"""
        total_points = sum(len(m) for m in self._metrics.values())
        return {
            "metric_names": len(self._metrics),
            "total_points": total_points,
            "counters": len(self._counters),
            "max_points": self._max_points,
            "retention_seconds": self._retention_seconds,
        }
