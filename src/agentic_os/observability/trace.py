"""Structured run traces.

Every run writes one JSON file to the runs directory: the goal, the plan,
each invocation with its governance verdict and latency, and a summary.
The trace is the audit record. If it is not in the trace, it did not
happen through the runtime.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from agentic_os.runtime.governor import InvocationResult
from agentic_os.runtime.planner import Plan

DEFAULT_RUNS_DIR = Path("runs")


class RunSummary(BaseModel):
    steps_planned: int
    steps_allowed: int
    steps_denied: int
    errors: int
    total_latency_ms: float


class RunTrace(BaseModel):
    run_id: str
    principal_id: str
    goal: str
    planner: str
    started_at: str
    finished_at: str
    plan: Plan
    invocations: list[InvocationResult] = Field(default_factory=list)
    summary: RunSummary
    working_memory: dict = Field(default_factory=dict)


def build_summary(invocations: list[InvocationResult], planned: int) -> RunSummary:
    allowed = sum(1 for inv in invocations if inv.verdict.allowed)
    return RunSummary(
        steps_planned=planned,
        steps_allowed=allowed,
        steps_denied=len(invocations) - allowed,
        errors=sum(1 for inv in invocations if inv.error),
        total_latency_ms=round(sum(inv.latency_ms for inv in invocations), 3),
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TraceWriter:
    def __init__(self, runs_dir: str | Path = DEFAULT_RUNS_DIR) -> None:
        self.runs_dir = Path(runs_dir)

    def path_for(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def write(self, trace: RunTrace) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(trace.run_id)
        path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, run_id: str) -> RunTrace:
        path = self.path_for(run_id)
        if not path.exists():
            raise FileNotFoundError(f"no trace for run {run_id!r} in {self.runs_dir}/")
        return RunTrace.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def run_ids(self) -> list[str]:
        if not self.runs_dir.exists():
            return []
        return sorted(p.stem for p in self.runs_dir.glob("*.json"))
