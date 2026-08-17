"""Policy-as-code: predicates evaluated inside the loop."""

import pytest

from agentic_os.capabilities.model import RiskTier
from agentic_os.policy import PolicyError, load_policies_dict
from agentic_os.runtime.state import InvocationRecord, RunState


def record(capability: str, tier: RiskTier, allowed: bool, index: int = 0) -> InvocationRecord:
    return InvocationRecord(
        step_index=index,
        capability=capability,
        purpose="billing",
        risk_tier=tier,
        allowed=allowed,
        reason="test",
    )


def state_with(records) -> RunState:
    state = RunState(run_id="r", principal_id="p", goal="g")
    for item in records:
        state.record(item)
    return state


def test_default_policies_load(policies):
    assert [policy.name for policy in policies.policies] == [
        "no-spend-after-denial",
        "max-act-steps-per-run",
    ]


def test_unknown_rule_rejected():
    with pytest.raises(PolicyError, match="unknown rule"):
        load_policies_dict({"policies": [{"name": "bad", "rule": "does_not_exist"}]})


def test_clean_state_passes_all_policies(policies, registry):
    state = state_with([])
    assert policies.evaluate(state, registry.get("draft_invoice")) == []


def test_no_spend_after_denial_fires(policies, registry):
    state = state_with([record("schedule_technician", RiskTier.ACT, allowed=False)])
    violations = policies.evaluate(state, registry.get("draft_invoice"))
    assert len(violations) == 1
    assert violations[0].policy == "no-spend-after-denial"


def test_no_spend_after_denial_ignores_read(policies, registry):
    state = state_with([record("schedule_technician", RiskTier.ACT, allowed=False)])
    assert policies.evaluate(state, registry.get("lookup_customer")) == []


def test_max_act_steps_fires_at_limit(policies, registry):
    records = [
        record("schedule_technician", RiskTier.ACT, allowed=True, index=i) for i in range(4)
    ]
    state = state_with(records)
    violations = policies.evaluate(state, registry.get("send_notification"))
    assert [v.policy for v in violations] == ["max-act-steps-per-run"]
    assert "limit 4" in violations[0].detail


def test_max_act_steps_does_not_count_reads(policies, registry):
    records = [record("lookup_customer", RiskTier.READ, allowed=True, index=i) for i in range(6)]
    state = state_with(records)
    assert policies.evaluate(state, registry.get("send_notification")) == []
