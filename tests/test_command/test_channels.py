"""
Tests for Command Layer - Channel Distribution System
"""
import pytest
from src.command.channels.protocol import (
    Channel, ChannelMeta, ChannelStatus, DeliveryResult,
)
from src.command.channels.registry import ChannelRegistry


class MockChannel:
    """Test double for Channel protocol"""

    def __init__(self, channel_id: str = "mock", success: bool = True):
        self.meta = ChannelMeta(
            id=channel_id, label=f"Mock {channel_id}", description="Test channel",
        )
        self._success = success
        self.sent_messages: list[dict] = []

    async def send_message(self, to, text, *, thread_id="", metadata=None):
        self.sent_messages.append({"to": to, "text": text, "thread_id": thread_id})
        return DeliveryResult(
            channel_id=self.meta.id,
            success=self._success,
            message_id="msg_001" if self._success else "",
            error="" if self._success else "mock error",
        )

    async def send_media(self, to, text, media_url, *, thread_id="", metadata=None):
        return await self.send_message(to, f"{text} [{media_url}]", thread_id=thread_id)

    async def health_check(self):
        return ChannelStatus.READY if self._success else ChannelStatus.UNAVAILABLE


class TestChannelProtocol:
    def test_mock_channel_satisfies_protocol(self):
        ch = MockChannel()
        assert isinstance(ch, Channel)

    def test_channel_meta(self):
        meta = ChannelMeta(id="test", label="Test", description="Desc", order=5)
        assert meta.id == "test"
        assert meta.label == "Test"
        assert meta.order == 5


class TestDeliveryResult:
    def test_success_result(self):
        r = DeliveryResult(channel_id="ch", success=True, message_id="msg_1")
        assert r.success
        assert r.channel_id == "ch"
        assert r.error == ""

    def test_failure_result(self):
        r = DeliveryResult(channel_id="ch", success=False, error="timeout")
        assert not r.success
        assert r.error == "timeout"

    def test_metadata(self):
        r = DeliveryResult(
            channel_id="ch", success=True, metadata={"key": "value"},
        )
        assert r.metadata == {"key": "value"}


class TestChannelRegistry:
    def test_register_and_get(self):
        reg = ChannelRegistry()
        ch = MockChannel("test")
        reg.register(ch)
        assert reg.get("test") is ch

    def test_register_duplicate_raises(self):
        reg = ChannelRegistry()
        ch = MockChannel("test")
        reg.register(ch)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ch)

    def test_unregister(self):
        reg = ChannelRegistry()
        ch = MockChannel("test")
        reg.register(ch)
        reg.unregister("test")
        with pytest.raises(KeyError):
            reg.get("test")

    def test_unregister_missing_raises(self):
        reg = ChannelRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_get_missing_raises(self):
        reg = ChannelRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_list_channels(self):
        reg = ChannelRegistry()
        reg.register(MockChannel("b"))
        reg.register(MockChannel("a"))
        channels = reg.list_channels()
        assert len(channels) == 2
        assert channels[0]["id"] in ("a", "b")

    @pytest.mark.asyncio
    async def test_send_to(self):
        reg = ChannelRegistry()
        ch = MockChannel("test")
        reg.register(ch)
        result = await reg.send_to("test", "#general", "hello")
        assert result.success
        assert result.channel_id == "test"
        assert len(ch.sent_messages) == 1
        assert ch.sent_messages[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_send_to_missing_channel(self):
        reg = ChannelRegistry()
        with pytest.raises(KeyError):
            await reg.send_to("nonexistent", "to", "text")

    @pytest.mark.asyncio
    async def test_send_to_failure_channel(self):
        reg = ChannelRegistry()
        ch = MockChannel("fail", success=False)
        reg.register(ch)
        result = await reg.send_to("fail", "to", "text")
        assert not result.success
        assert result.error == "mock error"

    @pytest.mark.asyncio
    async def test_broadcast(self):
        reg = ChannelRegistry()
        ch1 = MockChannel("ch1")
        ch2 = MockChannel("ch2")
        reg.register(ch1)
        reg.register(ch2)
        results = await reg.broadcast(["ch1", "ch2"], "to", "msg")
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        reg = ChannelRegistry()
        reg.register(MockChannel("ok", success=True))
        reg.register(MockChannel("fail", success=False))
        statuses = await reg.health_check_all()
        assert statuses["ok"] == ChannelStatus.READY
        assert statuses["fail"] == ChannelStatus.UNAVAILABLE

    def test_get_stats(self):
        reg = ChannelRegistry()
        reg.register(MockChannel("a"))
        reg.register(MockChannel("b"))
        stats = reg.get_stats()
        assert stats["total_channels"] == 2
        assert "a" in stats["channels"]
        assert "b" in stats["channels"]
