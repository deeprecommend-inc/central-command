"""
Channel Protocol - Abstract interface for notification channels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ChannelStatus(Enum):
    """Channel health status"""
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ChannelMeta:
    """Channel metadata"""
    id: str
    label: str
    description: str = ""
    order: int = 0


@dataclass
class DeliveryResult:
    """Result of a message delivery attempt"""
    channel_id: str
    success: bool
    message_id: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Channel(Protocol):
    """
    Protocol for notification channels.

    Implementations: Slack, Teams, Email, Webhook
    """

    meta: ChannelMeta

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send a text message"""
        ...

    async def send_media(
        self,
        to: str,
        text: str,
        media_url: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send a message with media attachment"""
        ...

    async def health_check(self) -> ChannelStatus:
        """Check channel availability"""
        ...
