"""
Email Channel - Async SMTP notification.
"""
from __future__ import annotations

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from loguru import logger

from .protocol import Channel, ChannelMeta, ChannelStatus, DeliveryResult


class EmailChannel:
    """Email notification channel via SMTP"""

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_address: str = "",
    ):
        self.meta = ChannelMeta(
            id="email",
            label="Email",
            description="SMTP email notification",
            order=30,
        )
        self._host = smtp_host
        self._port = smtp_port
        self._user = smtp_user
        self._password = smtp_password
        self._from = from_address

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """Send email. `to` is recipient address. `thread_id` used as subject prefix."""
        if not self._host:
            return DeliveryResult(
                channel_id=self.meta.id,
                success=False,
                error="No SMTP host configured",
            )

        subject = metadata.get("subject", "CCP Notification") if metadata else "CCP Notification"
        if thread_id:
            subject = f"Re: [{thread_id}] {subject}"

        msg = MIMEText(text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._from or self._user
        msg["To"] = to

        try:
            import aiosmtplib

            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._user or None,
                password=self._password or None,
                use_tls=self._port == 465,
                start_tls=self._port == 587,
            )
            return DeliveryResult(
                channel_id=self.meta.id,
                success=True,
                message_id=msg.get("Message-ID", ""),
            )
        except ImportError:
            return DeliveryResult(
                channel_id=self.meta.id,
                success=False,
                error="aiosmtplib not installed",
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")
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
        """Send email with media URL in body"""
        full_text = f"{text}\n\nMedia: {media_url}"
        return await self.send_message(to, full_text, thread_id=thread_id, metadata=metadata)

    async def health_check(self) -> ChannelStatus:
        """Check SMTP connectivity"""
        if not self._host:
            return ChannelStatus.UNAVAILABLE
        try:
            import aiosmtplib

            smtp = aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                timeout=5,
            )
            await smtp.connect()
            await smtp.quit()
            return ChannelStatus.READY
        except ImportError:
            return ChannelStatus.UNAVAILABLE
        except Exception:
            return ChannelStatus.DEGRADED
