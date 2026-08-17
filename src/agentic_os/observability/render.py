"""Plain-text rendering of run traces for the CLI."""

from __future__ import annotations

import json

from agentic_os.observability.trace import RunTrace

ALLOWED_MARK = "[allowed]"
DENIED_MARK = "[DENIED]"


def render_trace(trace: RunTrace, verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append(f"run      {trace.run_id}")
    lines.append(f"agent    {trace.principal_id}")
    lines.append(f"goal     {trace.goal}")
    lines.append(f"planner  {trace.planner}")
    lines.append(f"started  {trace.started_at}")
    lines.append("")
    for index, inv in enumerate(trace.invocations, start=1):
        mark = ALLOWED_MARK if inv.verdict.allowed else DENIED_MARK
        lines.append(
            f"step {index}: {inv.capability} (purpose={inv.purpose}) "
            f"{mark} {inv.latency_ms:.1f} ms"
        )
        if not inv.verdict.allowed:
            lines.append(f"        reason: {inv.verdict.reason}")
        elif inv.error:
            lines.append(f"        execution error: {inv.error}")
        elif verbose and inv.output is not None:
            payload = json.dumps(inv.output, default=str)
            if len(payload) > 200:
                payload = payload[:200] + "..."
            lines.append(f"        output: {payload}")
        if verbose:
            for check in inv.verdict.checks:
                status = "pass" if check.passed else "FAIL"
                lines.append(f"        check {check.name}: {status} ({check.detail})")
    lines.append("")
    summary = trace.summary
    lines.append(
        f"summary  {summary.steps_allowed} allowed, {summary.steps_denied} denied, "
        f"{summary.errors} error(s), {summary.total_latency_ms:.1f} ms total"
    )
    return "\n".join(lines)
