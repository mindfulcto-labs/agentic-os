"""Episodic memory: an append-only JSONL log of every run, per principal.

Each line is one event: run started, invocation allowed, invocation
denied, run finished. The log survives the process, so an operator can
answer "what did this agent do yesterday" without any extra tooling.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MEMORY_DIR = Path(".agentic_os") / "memory"


class EpisodicLog:
    def __init__(self, base_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
        self.base_dir = Path(base_dir)

    def _path_for(self, principal_id: str) -> Path:
        return self.base_dir / f"{principal_id}.jsonl"

    def append(self, principal_id: str, event: str, payload: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        with open(self._path_for(principal_id), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def read(self, principal_id: str) -> list[dict[str, Any]]:
        path = self._path_for(principal_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events
