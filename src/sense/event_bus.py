"""
Event Bus - Pub/Sub event system
"""
import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional
from loguru import logger


@dataclass
class Event:
    """Immutable event data"""
    event_type: str
    source: str
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.event_type:
            raise ValueError("event_type is required")
        if not self.source:
            raise ValueError("source is required")


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async event bus for publish/subscribe pattern.

    Example:
        bus = EventBus()

        async def on_failure(event: Event):
            print(f"Failure: {event.data}")

        bus.subscribe("proxy.failure", on_failure)
        await bus.publish(Event("proxy.failure", "proxy_manager", {"reason": "timeout"}))
    """

    def __init__(self, max_history: int = 1000):
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: list[EventHandler] = []
        self._history: deque[Event] = deque(maxlen=max_history)
        self._max_history = max_history
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Event type pattern (use "*" for all events)
            handler: Async function to handle events
        """
        if event_type == "*":
            self._wildcard_subscribers.append(handler)
        else:
            self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to '{event_type}'")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """
        Unsubscribe from events.

        Returns:
            True if handler was found and removed
        """
        if event_type == "*":
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)
                return True
        else:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                return True
        return False

    async def publish(self, event: Event) -> int:
        """
        Publish an event to all subscribers.

        Args:
            event: Event to publish

        Returns:
            Number of handlers that received the event
        """
        self._history.append(event)

        handlers = list(self._subscribers.get(event.event_type, []))
        handlers.extend(self._wildcard_subscribers)

        if not handlers:
            logger.debug(f"No subscribers for '{event.event_type}'")
            return 0

        tasks = [self._safe_call(handler, event) for handler in handlers]
        await asyncio.gather(*tasks)
        logger.debug(f"Published '{event.event_type}' to {len(handlers)} handlers")
        return len(handlers)

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call handler with error handling"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Handler error for '{event.event_type}': {e}")

    def get_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[Event]:
        """
        Get event history.

        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum events to return
        """
        if event_type:
            events = [e for e in self._history if e.event_type == event_type]
            return events[-limit:]
        return list(self._history)[-limit:]

    def clear_history(self) -> None:
        """Clear event history"""
        self._history.clear()

    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """Get number of subscribers"""
        if event_type is None:
            total = sum(len(h) for h in self._subscribers.values())
            return total + len(self._wildcard_subscribers)
        if event_type == "*":
            return len(self._wildcard_subscribers)
        return len(self._subscribers.get(event_type, []))


class RedisEventBus(EventBus):
    """
    Redis-backed event bus for distributed systems.

    Uses Redis Pub/Sub for cross-process event distribution.
    Falls back to in-memory operation if Redis is unavailable.

    Example:
        bus = RedisEventBus(redis_url="redis://localhost:6379")

        async def on_task_complete(event: Event):
            print(f"Task completed: {event.data}")

        bus.subscribe("task.completed", on_task_complete)

        # Start listening (in background task)
        asyncio.create_task(bus.start_listening())

        # Publish (goes to Redis and all connected instances)
        await bus.publish(Event("task.completed", "worker", {"task_id": "123"}))
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel_prefix: str = "ccp:events:",
        max_history: int = 1000,
        history_ttl: int = 3600,  # 1 hour
    ):
        super().__init__(max_history)

        self._redis_url = redis_url
        self._channel_prefix = channel_prefix
        self._history_ttl = history_ttl
        self._redis = None
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False

    async def _get_redis(self):
        """Lazy Redis connection"""
        if self._redis is not None:
            return self._redis

        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self._redis_url)
            await self._redis.ping()
            logger.info(f"Connected to Redis: {self._redis_url}")
            return self._redis
        except ImportError:
            logger.warning("redis package not installed, using in-memory only")
            return None
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory only")
            return None

    async def publish(self, event: Event) -> int:
        """Publish event to Redis and local subscribers"""
        # Store in local history
        self._history.append(event)

        # Publish to Redis
        redis_client = await self._get_redis()
        if redis_client:
            try:
                import json
                channel = f"{self._channel_prefix}{event.event_type}"
                message = json.dumps({
                    "event_type": event.event_type,
                    "source": event.source,
                    "data": event.data,
                    "timestamp": event.timestamp,
                })
                await redis_client.publish(channel, message)

                # Also store in Redis list for history
                history_key = f"{self._channel_prefix}history"
                await redis_client.lpush(history_key, message)
                await redis_client.ltrim(history_key, 0, self._max_history - 1)
                await redis_client.expire(history_key, self._history_ttl)

                logger.debug(f"Published to Redis: {channel}")
            except Exception as e:
                logger.error(f"Redis publish failed: {e}")

        # Call local handlers
        handlers = list(self._subscribers.get(event.event_type, []))
        handlers.extend(self._wildcard_subscribers)

        if handlers:
            tasks = [self._safe_call(handler, event) for handler in handlers]
            await asyncio.gather(*tasks)

        return len(handlers)

    async def start_listening(self) -> None:
        """Start listening for Redis events"""
        redis_client = await self._get_redis()
        if not redis_client:
            logger.warning("Redis not available, skipping listener")
            return

        self._running = True
        self._pubsub = redis_client.pubsub()

        # Subscribe to all event channels
        pattern = f"{self._channel_prefix}*"
        await self._pubsub.psubscribe(pattern)
        logger.info(f"Listening for Redis events: {pattern}")

        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "pmessage":
                    await self._handle_redis_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        finally:
            await self._pubsub.punsubscribe(pattern)
            self._running = False

    async def stop_listening(self) -> None:
        """Stop the Redis listener"""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

    async def _handle_redis_message(self, message: dict) -> None:
        """Handle incoming Redis message"""
        try:
            import json
            data = json.loads(message["data"])

            event = Event(
                event_type=data["event_type"],
                source=data["source"],
                data=data.get("data", {}),
                timestamp=data.get("timestamp", time.time()),
            )

            # Call local handlers (skip publish to avoid loop)
            handlers = list(self._subscribers.get(event.event_type, []))
            handlers.extend(self._wildcard_subscribers)

            if handlers:
                tasks = [self._safe_call(handler, event) for handler in handlers]
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Failed to handle Redis message: {e}")

    async def get_redis_history(self, limit: int = 100) -> list[Event]:
        """Get event history from Redis"""
        redis_client = await self._get_redis()
        if not redis_client:
            return self.get_history(limit=limit)

        try:
            import json
            history_key = f"{self._channel_prefix}history"
            messages = await redis_client.lrange(history_key, 0, limit - 1)

            events = []
            for msg in messages:
                data = json.loads(msg)
                events.append(Event(
                    event_type=data["event_type"],
                    source=data["source"],
                    data=data.get("data", {}),
                    timestamp=data.get("timestamp", time.time()),
                ))
            return events
        except Exception as e:
            logger.error(f"Failed to get Redis history: {e}")
            return self.get_history(limit=limit)

    async def close(self) -> None:
        """Close Redis connections"""
        await self.stop_listening()
        if self._redis:
            await self._redis.close()
            self._redis = None

    def get_stats(self) -> dict:
        """Get event bus statistics"""
        return {
            "local_subscribers": self.get_subscriber_count(),
            "history_count": len(self._history),
            "redis_connected": self._redis is not None,
            "listener_running": self._running,
        }


def create_event_bus(
    backend: str = "memory",
    **kwargs,
) -> EventBus:
    """
    Factory function to create event bus.

    Args:
        backend: "memory" or "redis"
        **kwargs: Backend-specific options

    Returns:
        EventBus instance
    """
    if backend == "memory":
        return EventBus(**kwargs)
    elif backend == "redis":
        return RedisEventBus(**kwargs)
    else:
        raise ValueError(f"Unknown backend: {backend}")
