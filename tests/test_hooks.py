"""
Tests for Hook System
"""
import asyncio
import pytest
from src.hooks import (
    HookRunner,
    HookRegistration,
    ON_CYCLE_START,
    ON_CYCLE_END,
    BEFORE_SENSE,
    AFTER_SENSE,
    BEFORE_THINK,
    ON_ERROR,
)


class TestHookRunner:
    def test_register_and_has_hooks(self):
        runner = HookRunner()

        async def handler(event):
            pass

        runner.register(ON_CYCLE_START, handler)
        assert runner.has_hooks(ON_CYCLE_START)
        assert not runner.has_hooks(ON_CYCLE_END)

    def test_unregister(self):
        runner = HookRunner()

        async def handler(event):
            pass

        runner.register(ON_CYCLE_START, handler)
        runner.unregister(ON_CYCLE_START, handler)
        assert not runner.has_hooks(ON_CYCLE_START)

    def test_unregister_nonexistent(self):
        runner = HookRunner()

        async def handler(event):
            pass

        # Should not raise
        runner.unregister("nonexistent", handler)

    @pytest.mark.asyncio
    async def test_run_void_parallel(self):
        runner = HookRunner()
        results = []

        async def handler1(event):
            results.append("h1")

        async def handler2(event):
            results.append("h2")

        runner.register(BEFORE_SENSE, handler1)
        runner.register(BEFORE_SENSE, handler2)

        await runner.run_void(BEFORE_SENSE, {"key": "value"})
        assert len(results) == 2
        assert "h1" in results
        assert "h2" in results

    @pytest.mark.asyncio
    async def test_run_void_no_hooks(self):
        runner = HookRunner()
        # Should not raise
        await runner.run_void(BEFORE_SENSE, {})

    @pytest.mark.asyncio
    async def test_run_void_error_isolation(self):
        runner = HookRunner()
        results = []

        async def bad_handler(event):
            raise RuntimeError("boom")

        async def good_handler(event):
            results.append("ok")

        runner.register(BEFORE_SENSE, bad_handler, plugin_id="bad")
        runner.register(BEFORE_SENSE, good_handler, plugin_id="good")

        # Should not raise despite bad_handler failing
        await runner.run_void(BEFORE_SENSE, {})
        assert "ok" in results

    @pytest.mark.asyncio
    async def test_run_modifying_sequential(self):
        runner = HookRunner()

        async def add_field(event):
            event["added"] = True
            return event

        async def modify_field(event):
            event["modified"] = True
            return event

        runner.register(BEFORE_THINK, add_field)
        runner.register(BEFORE_THINK, modify_field)

        result = await runner.run_modifying(BEFORE_THINK, {"original": True})
        assert result["original"]
        assert result["added"]
        assert result["modified"]

    @pytest.mark.asyncio
    async def test_run_modifying_error_continues(self):
        runner = HookRunner()

        async def bad_modifier(event):
            raise RuntimeError("fail")

        async def good_modifier(event):
            event["processed"] = True
            return event

        runner.register(BEFORE_THINK, bad_modifier, priority=10)
        runner.register(BEFORE_THINK, good_modifier, priority=0)

        result = await runner.run_modifying(BEFORE_THINK, {"data": "test"})
        assert result["processed"]

    @pytest.mark.asyncio
    async def test_run_modifying_no_hooks(self):
        runner = HookRunner()
        event = {"key": "value"}
        result = await runner.run_modifying(BEFORE_THINK, event)
        assert result is event

    def test_priority_ordering(self):
        runner = HookRunner()
        order = []

        async def high(event):
            order.append("high")

        async def low(event):
            order.append("low")

        runner.register(ON_CYCLE_START, low, priority=0)
        runner.register(ON_CYCLE_START, high, priority=100)

        # Verify internal ordering (higher priority first)
        hooks = runner._hooks[ON_CYCLE_START]
        assert hooks[0].priority == 100
        assert hooks[1].priority == 0

    def test_get_stats(self):
        runner = HookRunner()

        async def h(event):
            pass

        runner.register(ON_CYCLE_START, h)
        runner.register(ON_CYCLE_END, h)
        runner.register(ON_CYCLE_END, h, plugin_id="other")

        stats = runner.get_stats()
        assert stats["total_hooks"] == 3
        assert stats["hook_names"][ON_CYCLE_START] == 1
        assert stats["hook_names"][ON_CYCLE_END] == 2

    def test_hook_name_constants(self):
        assert ON_CYCLE_START == "on_cycle_start"
        assert ON_ERROR == "on_error"
        assert AFTER_SENSE == "after_sense"
