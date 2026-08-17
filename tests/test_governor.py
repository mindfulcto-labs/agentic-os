"""The governor: every check, allow and deny, as first-class verdicts."""

from agentic_os.runtime.state import RunState


def make_state(principal_id: str = "dispatch-agent") -> RunState:
    return RunState(run_id="test-run", principal_id=principal_id, goal="test goal")


def invoke(runtime, principal, capability, purpose, params, state=None):
    state = state or make_state(principal)
    return runtime.governor.invoke(
        principal_id=principal,
        capability_name=capability,
        purpose=purpose,
        params=params,
        run_state=state,
        graph=runtime.graph,
    ), state


def test_read_capability_allowed(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "lookup_customer", "service_delivery", {"name": "Harbour Bakery"}
    )
    assert result.verdict.allowed
    assert result.output["customer_id"] == "cust-001"
    assert result.latency_ms >= 0


def test_every_check_is_recorded_on_allow(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "lookup_customer", "service_delivery", {"name": "Harbour Bakery"}
    )
    names = [check.name for check in result.verdict.checks]
    assert names == [
        "capability_exists",
        "purpose_granted",
        "scopes_granted",
        "risk_tier",
        "rate_limit",
        "policy",
        "budget",
        "approval",
    ]
    assert all(check.passed for check in result.verdict.checks)


def test_unknown_capability_denied(runtime):
    result, _ = invoke(runtime, "dispatch-agent", "teleport_technician", "service_delivery", {})
    assert not result.verdict.allowed
    assert "not registered" in result.verdict.reason


def test_purpose_not_granted_denied(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "lookup_customer", "marketing", {"name": "Harbour Bakery"}
    )
    assert not result.verdict.allowed
    assert "purpose" in result.verdict.reason


def test_scope_not_granted_denied(runtime):
    result, _ = invoke(
        runtime,
        "reporting-agent",
        "schedule_technician",
        "service_delivery",
        {"work_order_id": "wo-001", "technician_id": "tech-002", "date": "2026-08-20"},
    )
    assert not result.verdict.allowed
    assert "scopes" in result.verdict.reason


def test_denial_carries_failed_check_detail(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "draft_invoice", "service_delivery",
        {"work_order_id": "wo-001", "amount": 100.0},
    )
    assert not result.verdict.allowed
    failed = [check for check in result.verdict.checks if not check.passed]
    assert failed[0].name == "scopes_granted"


def test_spend_budget_enforced(runtime):
    state = make_state("billing-agent")
    for _ in range(3):
        result, _ = invoke(
            runtime, "billing-agent", "draft_invoice", "billing",
            {"work_order_id": "wo-001", "amount": 50.0}, state,
        )
        assert result.verdict.allowed
    result, _ = invoke(
        runtime, "billing-agent", "draft_invoice", "billing",
        {"work_order_id": "wo-001", "amount": 50.0}, state,
    )
    assert not result.verdict.allowed
    assert "budget" in result.verdict.reason


def test_rate_limit_enforced_per_run(runtime):
    state = make_state()
    for _ in range(3):
        result, _ = invoke(
            runtime, "dispatch-agent", "send_notification", "service_delivery",
            {"customer_id": "cust-001", "message": "update"}, state,
        )
        assert result.verdict.allowed
    result, _ = invoke(
        runtime, "dispatch-agent", "send_notification", "service_delivery",
        {"customer_id": "cust-001", "message": "update"}, state,
    )
    assert not result.verdict.allowed
    assert "rate limit" in result.verdict.reason


def test_approval_gate_denies_act_when_off(make_runtime):
    runtime = make_runtime(auto_approve=False)
    result, _ = invoke(
        runtime, "dispatch-agent", "schedule_technician", "service_delivery",
        {"work_order_id": "wo-001", "technician_id": "tech-002", "date": "2026-08-20"},
    )
    assert not result.verdict.allowed
    assert "approval" in result.verdict.reason


def test_approval_gate_skipped_for_read(make_runtime):
    runtime = make_runtime(auto_approve=False)
    result, _ = invoke(
        runtime, "dispatch-agent", "lookup_customer", "service_delivery",
        {"name": "Harbour Bakery"},
    )
    assert result.verdict.allowed


def test_invalid_params_are_denied_not_crashed(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "schedule_technician", "service_delivery",
        {"work_order_id": "wo-001"},
    )
    assert not result.verdict.allowed
    assert "validation" in result.verdict.reason


def test_handler_failure_is_an_error_not_a_denial(runtime):
    result, _ = invoke(
        runtime, "dispatch-agent", "lookup_customer", "service_delivery",
        {"name": "No Such Company"},
    )
    assert result.verdict.allowed
    assert result.output is None
    assert "no customer" in result.error
