"""
Tests for Config Hot Reload
"""
import asyncio
import os
import tempfile
import pytest
from src.config_reload import (
    ConfigReloader,
    ReloadPlan,
    build_reload_plan,
    RELOAD_RULES,
)


class TestReloadPlan:
    def test_channel_changes(self):
        plan = build_reload_plan(["SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN"])
        assert plan.reload_channels
        assert not plan.restart_required

    def test_teams_change(self):
        plan = build_reload_plan(["TEAMS_WEBHOOK_URL"])
        assert plan.reload_channels

    def test_email_change(self):
        plan = build_reload_plan(["EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT"])
        assert plan.reload_channels

    def test_webhook_change(self):
        plan = build_reload_plan(["WEBHOOK_URLS"])
        assert plan.reload_channels

    def test_core_changes_require_restart(self):
        plan = build_reload_plan(["BRIGHTDATA_USERNAME"])
        assert plan.restart_required
        assert not plan.reload_channels

    def test_headless_requires_restart(self):
        plan = build_reload_plan(["HEADLESS"])
        assert plan.restart_required

    def test_parallel_requires_restart(self):
        plan = build_reload_plan(["PARALLEL_SESSIONS"])
        assert plan.restart_required

    def test_mixed_changes(self):
        plan = build_reload_plan(["SLACK_WEBHOOK_URL", "BRIGHTDATA_HOST"])
        assert plan.reload_channels
        assert plan.restart_required

    def test_unknown_key(self):
        plan = build_reload_plan(["SOME_UNKNOWN_KEY"])
        assert not plan.reload_channels
        assert not plan.restart_required

    def test_empty_changes(self):
        plan = build_reload_plan([])
        assert not plan.reload_channels
        assert not plan.restart_required


class TestConfigReloader:
    def test_init(self):
        reloader = ConfigReloader(env_path="/nonexistent/.env")
        assert reloader._poll_interval == 2.0
        assert reloader._debounce == 0.3

    @pytest.mark.asyncio
    async def test_start_stop(self):
        reloader = ConfigReloader(env_path="/nonexistent/.env", poll_interval=0.1)
        await reloader.start()
        assert reloader._running
        assert reloader._task is not None
        await reloader.stop()
        assert not reloader._running
        assert reloader._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        reloader = ConfigReloader()
        # Should not raise
        await reloader.stop()

    def test_read_env(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY1=value1\n")
            f.write("KEY2=value2\n")
            f.write("# comment\n")
            f.write("\n")
            f.write('KEY3="quoted"\n')
            path = f.name

        try:
            reloader = ConfigReloader(env_path=path)
            values = reloader._read_env()
            assert values["KEY1"] == "value1"
            assert values["KEY2"] == "value2"
            assert values["KEY3"] == "quoted"
        finally:
            os.unlink(path)

    def test_read_env_missing_file(self):
        reloader = ConfigReloader(env_path="/nonexistent/.env")
        values = reloader._read_env()
        assert values == {}

    def test_detect_changes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY1=value1\nKEY2=value2\n")
            path = f.name

        try:
            reloader = ConfigReloader(env_path=path)
            reloader._last_values = {"KEY1": "value1", "KEY2": "old_value"}
            changed = reloader._detect_changes()
            assert "KEY2" in changed
        finally:
            os.unlink(path)

    def test_on_reload_callback(self):
        reloader = ConfigReloader()
        callbacks = []

        async def cb(plan):
            callbacks.append(plan)

        reloader.on_reload(cb)
        assert len(reloader._callbacks) == 1
