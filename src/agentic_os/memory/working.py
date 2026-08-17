"""Per-agent working memory.

Working memory holds what the agent has learned during the current run:
capability outputs, notes, and denials. Planners can read it to ground
later steps. It is small and in-process by design.
"""

from __future__ import annotations

from typing import Any


class WorkingMemory:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def remember(self, key: str, value: Any) -> None:
        self._items[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self._items.get(key, default)

    def forget(self, key: str) -> None:
        self._items.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._items)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._items)

    def as_context(self) -> str:
        """A short text rendering, used to ground LLM planners."""
        if not self._items:
            return "(working memory is empty)"
        lines = []
        for key, value in self._items.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
