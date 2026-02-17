"""
Teams Channel - Microsoft Teams Incoming Webhook notification.
"""
from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger

from .protocol import Channel, ChannelMeta, ChannelStatus, DeliveryResult


class TeamsChannel:
    """Microsoft Teams notification channel via Incoming Webhook"""

    def __init__(self, webhook_url: str = ""):
        self.meta = ChannelMeta(
            id="teams",
            label="Teams",
            description="Microsoft Teams webhook",
            order=20,
        )
        self._webhook_url = webhook_url

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send message via Teams Incoming Webhook. `to` is ignored (webhook is channel-bound)."""
        if not self._webhook_url:
            return DeliveryResult(
                channel_id=self.meta.id,
                success=False,
                error="No Teams webhook URL configured",
            )

        # Adaptive Card format
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": text,
                                "wrap": True,
                            }
                        ],
                    },
                }
            ],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    success = 200 <= resp.status < 300
                    return DeliveryResult(
                        channel_id=self.meta.id,
                        success=success,
                        message_id=str(resp.status),
                        error="" if success else f"HTTP {resp.status}",
                    )
        except Exception as e:
            logger.error(f"Teams webhook failed: {e}")
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
        """Send message with media as Adaptive Card image"""
        rich_text = f"{text}\n\n![media]({media_url})"
        return await self.send_message(to, rich_text, thread_id=thread_id, metadata=metadata)

    async def health_check(self) -> ChannelStatus:
        """Check Teams webhook availability"""
        if not self._webhook_url:
            return ChannelStatus.UNAVAILABLE
        return ChannelStatus.READY  # Teams webhooks have no test endpoint
