"""
Hook System - Extension points for the CCP cycle.

Supports two hook types:
- Void hooks: fire-and-forget, parallel execution, error-isolated
- Modifying hooks: sequential execution, payload modification
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from loguru import logger

# Hook name constants
ON_CYCLE_START = "on_cycle_start"
ON_CYCLE_END = "on_cycle_end"
BEFORE_SENSE = "before_sense"
AFTER_SENSE = "after_sense"
BEFORE_THINK = "before_think"
AFTER_THINK = "after_think"
BEFORE_COMMAND = "before_command"
AFTER_COMMAND = "after_command"
BEFORE_CONTROL = "before_control"
AFTER_CONTROL = "after_control"
ON_ERROR = "on_error"

HookHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


@dataclass
class HookRegistration:
    """A registered hook handler"""
    hook_name: str
    handler: HookHandler
    plugin_id: str = ""
    priority: int = 0


class HookRunner:
    """
    Manages hook registration and execution.

    Void hooks run in parallel with error isolation.
    Modifying hooks run sequentially and can alter the event payload.
    """

    def __init__(self):
        self._hooks: dict[str, list[HookRegistration]] = {}

    def register(
        self,
        hook_name: str,
        handler: HookHandler,
        *,
        plugin_id: str = "",
        priority: int = 0,
    ) -> None:
        """Register a hook handler"""
        reg = HookRegistration(
            hook_name=hook_name,
            handler=handler,
            plugin_id=plugin_id,
            priority=priority,
        )
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(reg)
        # Sort by priority (higher first)
        self._hooks[hook_name].sort(key=lambda r: r.priority, reverse=True)

    def unregister(self, hook_name: str, handler: HookHandler) -> None:
        """Unregister a hook handler"""
        if hook_name not in self._hooks:
            return
        self._hooks[hook_name] = [
            r for r in self._hooks[hook_name] if r.handler is not handler
        ]
        if not self._hooks[hook_name]:
            del self._hooks[hook_name]

    def has_hooks(self, hook_name: str) -> bool:
        """Check if any hooks are registered for a name"""
        return bool(self._hooks.get(hook_name))

    async def run_void(self, hook_name: str, event: dict[str, Any]) -> None:
        """
        Run void hooks in parallel.
        Errors are logged but do not propagate.
        """
        hooks = self._hooks.get(hook_name, [])
        if not hooks:
            return

        async def _safe_run(reg: HookRegistration) -> None:
            try:
                await reg.handler(event)
            except Exception as e:
                logger.error(
                    f"Hook error [{hook_name}] plugin={reg.plugin_id}: {e}"
                )

        await asyncio.gather(*[_safe_run(r) for r in hooks])

    async def run_modifying(
        self, hook_name: str, event: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run modifying hooks sequentially.
        Each handler receives the event and may return a modified version.
        """
        hooks = self._hooks.get(hook_name, [])
        current = event
        for reg in hooks:
            try:
                result = await reg.handler(current)
                if isinstance(result, dict):
                    current = result
            except Exception as e:
                logger.error(
                    f"Modifying hook error [{hook_name}] plugin={reg.plugin_id}: {e}"
                )
        return current

    def get_stats(self) -> dict[str, Any]:
        """Get hook statistics"""
        return {
            "total_hooks": sum(len(v) for v in self._hooks.values()),
            "hook_names": {
                name: len(handlers) for name, handlers in self._hooks.items()
            },
        }
