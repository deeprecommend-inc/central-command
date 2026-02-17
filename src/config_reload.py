"""
Config Hot Reload - Watches .env file for changes and triggers reload actions.

Uses mtime polling (no external dependencies like watchdog).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from loguru import logger

# Reload rules: key prefix -> action type
RELOAD_RULES: dict[str, str] = {
    "slack": "reload_channels",
    "teams": "reload_channels",
    "email": "reload_channels",
    "webhook": "reload_channels",
    "brightdata": "restart_required",
    "headless": "restart_required",
    "parallel": "restart_required",
}


@dataclass
class ReloadPlan:
    """Plan describing what to reload based on changed keys"""
    changed_keys: list[str]
    reload_channels: bool = False
    reload_hooks: bool = False
    restart_required: bool = False


def build_reload_plan(changed_keys: list[str]) -> ReloadPlan:
    """Build a reload plan from a list of changed setting keys"""
    plan = ReloadPlan(changed_keys=changed_keys)

    for key in changed_keys:
        key_lower = key.lower()
        for prefix, action in RELOAD_RULES.items():
            if key_lower.startswith(prefix):
                if action == "reload_channels":
                    plan.reload_channels = True
                elif action == "restart_required":
                    plan.restart_required = True
                break

    return plan


ReloadCallback = Callable[[ReloadPlan], Coroutine[Any, Any, None]]


class ConfigReloader:
    """
    Watches .env file for changes via mtime polling.

    Debounce: 300ms after detecting change before triggering reload.
    """

    def __init__(
        self,
        env_path: str = ".env",
        poll_interval: float = 2.0,
        debounce: float = 0.3,
    ):
        self._env_path = env_path
        self._poll_interval = poll_interval
        self._debounce = debounce
        self._last_mtime: float = 0.0
        self._last_values: dict[str, str] = {}
        self._callbacks: list[ReloadCallback] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def on_reload(self, callback: ReloadCallback) -> None:
        """Register a reload callback"""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start watching for changes"""
        self._running = True
        self._last_values = self._read_env()
        self._last_mtime = self._get_mtime()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"ConfigReloader started: {self._env_path}")

    async def stop(self) -> None:
        """Stop watching"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ConfigReloader stopped")

    def _get_mtime(self) -> float:
        """Get file modification time"""
        try:
            return os.path.getmtime(self._env_path)
        except OSError:
            return 0.0

    def _read_env(self) -> dict[str, str]:
        """Read .env file into a dict"""
        values: dict[str, str] = {}
        try:
            with open(self._env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        values[key.strip()] = value.strip().strip("\"'")
        except OSError:
            pass
        return values

    def _detect_changes(self) -> list[str]:
        """Detect changed keys between old and new values"""
        new_values = self._read_env()
        changed: list[str] = []

        all_keys = set(self._last_values.keys()) | set(new_values.keys())
        for key in all_keys:
            old = self._last_values.get(key, "")
            new = new_values.get(key, "")
            if old != new:
                changed.append(key)

        self._last_values = new_values
        return changed

    async def _poll_loop(self) -> None:
        """Main polling loop"""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)

                mtime = self._get_mtime()
                if mtime <= self._last_mtime:
                    continue

                # Debounce
                await asyncio.sleep(self._debounce)
                self._last_mtime = self._get_mtime()

                changed = self._detect_changes()
                if not changed:
                    continue

                plan = build_reload_plan(changed)
                logger.info(f"Config changed: {changed}")

                for callback in self._callbacks:
                    try:
                        await callback(plan)
                    except Exception as e:
                        logger.error(f"Reload callback error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ConfigReloader poll error: {e}")
