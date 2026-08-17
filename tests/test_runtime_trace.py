"""The agent loop end to end, and the trace it leaves behind."""

from agentic_os.observability import TraceWriter, render_trace
from agentic_os.runtime.planner import PlannedStep, ScriptedPlanner

STEPS = [
    PlannedStep(
        capability="lookup_customer",
        purpose="service_delivery",
        params={"name": "Harbour Bakery"},
    ),
    PlannedStep(
        capability="schedule_technician",
        purpose="service_delivery",
        params={"work_order_id": "wo-001", "technician_id": "tech-002", "date": "2026-08-20"},
    ),
    PlannedStep(
        capability="draft_invoice",
        purpose="service_delivery",
        params={"work_order_id": "wo-001", "amount": 240.0},
    ),
]


def test_run_produces_trace_file(runtime, tmp_path):
    result = runtime.run("dispatch-agent", "fix and invoice", ScriptedPlanner(STEPS))
    trace = result.trace
    assert trace.summary.steps_planned == 3
    assert trace.summary.steps_allowed == 2
    assert trace.summary.steps_denied == 1
    path = tmp_path / "runs" / f"{trace.run_id}.json"
    assert path.exists()


def test_trace_is_loadable_and_faithful(runtime, tmp_path):
    result = runtime.run("dispatch-agent", "fix and invoice", ScriptedPlanner(STEPS))
    writer = TraceWriter(tmp_path / "runs")
    loaded = writer.load(result.trace.run_id)
    assert loaded.goal == "fix and invoice"
    assert [inv.capability for inv in loaded.invocations] == [
        "lookup_customer",
        "schedule_technician",
        "draft_invoice",
    ]
    denied = loaded.invocations[2]
    assert not denied.verdict.allowed
    assert "scopes" in denied.verdict.reason
    assert all(inv.latency_ms >= 0 for inv in loaded.invocations)


def test_denial_is_remembered_in_working_memory(runtime):
    result = runtime.run("dispatch-agent", "fix and invoice", ScriptedPlanner(STEPS))
    denied_entry = result.trace.working_memory["step_2_draft_invoice"]
    assert denied_entry["denied"] is True
    assert "scopes" in denied_entry["reason"]


def test_render_trace_plain_and_verbose(runtime):
    result = runtime.run("dispatch-agent", "fix and invoice", ScriptedPlanner(STEPS))
    plain = render_trace(result.trace)
    assert "[DENIED]" in plain
    assert "[allowed]" in plain
    verbose = render_trace(result.trace, verbose=True)
    assert "check capability_exists: pass" in verbose


def test_budget_ledger_spans_runs(runtime):
    act_step = [
        PlannedStep(
            capability="schedule_technician",
            purpose="service_delivery",
            params={"work_order_id": "wo-001", "technician_id": "tech-002", "date": "2026-08-20"},
        )
    ]
    from agentic_os.capabilities.model import RiskTier

    runtime.run("dispatch-agent", "book it", ScriptedPlanner(act_step))
    assert runtime.ledger.used("dispatch-agent", RiskTier.ACT) == 1
    remaining = runtime.ledger.remaining(
        runtime.principals.get("dispatch-agent"), RiskTier.ACT
    )
    assert remaining == 4
