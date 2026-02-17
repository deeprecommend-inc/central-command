"""
Slack Channel - Webhook and Bot API notification.
"""
from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger

from .protocol import Channel, ChannelMeta, ChannelStatus, DeliveryResult


class SlackChannel:
    """
    Slack notification channel.

    Supports two modes:
    - Webhook: Simple Incoming Webhook URL
    - Bot API: chat.postMessage with Bot Token
    """

    def __init__(
        self,
        webhook_url: str = "",
        bot_token: str = "",
        default_channel: str = "",
    ):
        self.meta = ChannelMeta(
            id="slack",
            label="Slack",
            description="Slack messaging",
            order=10,
        )
        self._webhook_url = webhook_url
        self._bot_token = bot_token
        self._default_channel = default_channel

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send message via Slack. `to` is channel name/ID."""
        if self._bot_token:
            return await self._send_bot_api(to, text, thread_id=thread_id)
        if self._webhook_url:
            return await self._send_webhook(text, thread_id=thread_id)
        return DeliveryResult(
            channel_id=self.meta.id,
            success=False,
            error="No Slack credentials configured",
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
        """Send message with media as Slack attachment"""
        rich_text = f"{text}\n<{media_url}|Media>"
        return await self.send_message(to, rich_text, thread_id=thread_id, metadata=metadata)

    async def health_check(self) -> ChannelStatus:
        """Check Slack connectivity"""
        if self._bot_token:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {self._bot_token}"}
                    async with session.post(
                        "https://slack.com/api/auth.test",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        data = await resp.json()
                        if data.get("ok"):
                            return ChannelStatus.READY
                        return ChannelStatus.DEGRADED
            except Exception:
                return ChannelStatus.UNAVAILABLE
        if self._webhook_url:
            return ChannelStatus.READY  # Webhooks have no test endpoint
        return ChannelStatus.UNAVAILABLE

    async def _send_webhook(self, text: str, *, thread_id: str = "") -> DeliveryResult:
        """Send via Incoming Webhook"""
        payload: dict[str, Any] = {"text": text}
        if thread_id:
            payload["thread_ts"] = thread_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    success = resp.status == 200
                    return DeliveryResult(
                        channel_id=self.meta.id,
                        success=success,
                        error="" if success else f"HTTP {resp.status}",
                    )
        except Exception as e:
            logger.error(f"Slack webhook failed: {e}")
            return DeliveryResult(
                channel_id=self.meta.id, success=False, error=str(e),
            )

    async def _send_bot_api(
        self, channel: str, text: str, *, thread_id: str = "",
    ) -> DeliveryResult:
        """Send via Bot API (chat.postMessage)"""
        target = channel or self._default_channel
        if not target:
            return DeliveryResult(
                channel_id=self.meta.id,
                success=False,
                error="No target channel specified",
            )

        payload: dict[str, Any] = {"channel": target, "text": text}
        if thread_id:
            payload["thread_ts"] = thread_id

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    success = data.get("ok", False)
                    return DeliveryResult(
                        channel_id=self.meta.id,
                        success=success,
                        message_id=data.get("ts", ""),
                        error="" if success else data.get("error", "Unknown error"),
                    )
        except Exception as e:
            logger.error(f"Slack Bot API failed: {e}")
            return DeliveryResult(
                channel_id=self.meta.id, success=False, error=str(e),
            )
