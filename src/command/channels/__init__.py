"""
Command Layer - Channel Distribution System
"""
from .protocol import Channel, ChannelMeta, ChannelStatus, DeliveryResult
from .registry import ChannelRegistry
from .slack import SlackChannel
from .teams import TeamsChannel
from .email import EmailChannel
from .webhook import WebhookChannel

__all__ = [
    "Channel",
    "ChannelMeta",
    "ChannelStatus",
    "DeliveryResult",
    "ChannelRegistry",
    "SlackChannel",
    "TeamsChannel",
    "EmailChannel",
    "WebhookChannel",
]
