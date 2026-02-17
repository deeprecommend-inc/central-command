"""
Webhook Channel - Generic HTTP POST notification.
"""
from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger

from .protocol import Channel, ChannelMeta, ChannelStatus, DeliveryResult


class WebhookChannel:
    """Generic webhook channel (POST JSON to any URL)"""

    def __init__(self, url: str = "", *, channel_id: str = "webhook", label: str = "Webhook"):
        self.meta = ChannelMeta(
            id=channel_id,
            label=label,
            description="Generic HTTP webhook",
            order=40,
        )
        self._url = url

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """POST JSON payload to webhook URL. `to` overrides the default URL."""
        url = to or self._url
        if not url:
            return DeliveryResult(
                channel_id=self.meta.id, success=False, error="No webhook URL",
            )

        payload: dict[str, Any] = {"text": text}
        if thread_id:
            payload["thread_id"] = thread_id
        if metadata:
            payload["metadata"] = metadata

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    success = 200 <= resp.status < 300
                    body = await resp.text()
                    return DeliveryResult(
                        channel_id=self.meta.id,
                        success=success,
                        message_id=str(resp.status),
                        error="" if success else f"HTTP {resp.status}: {body[:200]}",
                    )
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return DeliveryResult(
                channel_id=self.meta.id, success=False, error=str(e),
            )

    async def send_media(
        self,
        to: str,
        text: str,
        media_url: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send message with media_url included in payload"""
        meta = metadata or {}
        meta["media_url"] = media_url
        return await self.send_message(to, text, thread_id=thread_id, metadata=meta)

    async def health_check(self) -> ChannelStatus:
        """Check if the webhook URL is reachable"""
        if not self._url:
            return ChannelStatus.READY  # URL provided per-call
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(self._url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status < 500:
                        return ChannelStatus.READY
                    return ChannelStatus.DEGRADED
        except Exception:
            return ChannelStatus.UNAVAILABLE
