"""
Channel Registry - Manages registered channels and dispatches messages.
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from .protocol import Channel, ChannelStatus, DeliveryResult


class ChannelRegistry:
    """Registry for notification channels"""

    def __init__(self):
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register a channel"""
        cid = channel.meta.id
        if cid in self._channels:
            raise ValueError(f"Channel already registered: {cid}")
        self._channels[cid] = channel
        logger.info(f"Channel registered: {cid} ({channel.meta.label})")

    def unregister(self, channel_id: str) -> None:
        """Unregister a channel"""
        if channel_id not in self._channels:
            raise KeyError(f"Channel not found: {channel_id}")
        del self._channels[channel_id]
        logger.info(f"Channel unregistered: {channel_id}")

    def get(self, channel_id: str) -> Channel:
        """Get a channel by ID"""
        if channel_id not in self._channels:
            raise KeyError(f"Channel not found: {channel_id}")
        return self._channels[channel_id]

    def list_channels(self) -> list[dict[str, Any]]:
        """List all registered channels"""
        channels = sorted(self._channels.values(), key=lambda c: c.meta.order)
        return [
            {
                "id": ch.meta.id,
                "label": ch.meta.label,
                "description": ch.meta.description,
                "order": ch.meta.order,
            }
            for ch in channels
        ]

    async def send_to(
        self,
        channel_id: str,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send a message to a specific channel"""
        channel = self.get(channel_id)
        try:
            return await channel.send_message(
                to, text, thread_id=thread_id, metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Channel {channel_id} send failed: {e}")
            return DeliveryResult(
                channel_id=channel_id, success=False, error=str(e),
            )

    async def broadcast(
        self,
        channel_ids: list[str],
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[DeliveryResult]:
        """Send a message to multiple channels in parallel"""
        tasks = [
            self.send_to(cid, to, text, thread_id=thread_id, metadata=metadata)
            for cid in channel_ids
        ]
        return await asyncio.gather(*tasks)

    async def health_check_all(self) -> dict[str, ChannelStatus]:
        """Check health of all registered channels"""
        results: dict[str, ChannelStatus] = {}
        for cid, channel in self._channels.items():
            try:
                results[cid] = await channel.health_check()
            except Exception:
                results[cid] = ChannelStatus.UNAVAILABLE
        return results

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_channels": len(self._channels),
            "channels": list(self._channels.keys()),
        }
