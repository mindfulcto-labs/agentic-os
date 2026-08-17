"""Principals, grants and budgets."""

import pytest

from agentic_os.capabilities import RiskTier
from agentic_os.identity import Grant, IdentityError, load_principals_dict


def test_default_principals_load(principals):
    expected = ["billing-agent", "dispatch-agent", "duty-manager", "reporting-agent"]
    assert principals.ids() == expected
    dispatch = principals.get("dispatch-agent")
    assert dispatch.kind == "agent"
    assert dispatch.budgets.act_per_day == 5
    assert dispatch.budgets.spend_per_day == 2


def test_grant_covering(principals):
    dispatch = principals.get("dispatch-agent")
    billing_grants = dispatch.matching_grants("billing")
    assert len(billing_grants) == 1
    grant = billing_grants[0]
    assert grant.covers_scopes(["invoices:write"])
    assert not grant.covers_scopes(["work_orders:write"])
    assert grant.covers_tier(RiskTier.SPEND)


def test_risk_tier_ordering():
    grant = Grant(scopes=["x:read"], purposes=["p"], max_risk_tier=RiskTier.ACT)
    assert grant.covers_tier(RiskTier.READ)
    assert grant.covers_tier(RiskTier.ACT)
    assert not grant.covers_tier(RiskTier.SPEND)


def test_unknown_principal_raises(principals):
    with pytest.raises(IdentityError, match="unknown principal"):
        principals.get("rogue-agent")


def test_duplicate_principal_id_rejected():
    definition = {
        "id": "twin",
        "kind": "agent",
        "display_name": "Twin",
        "grants": [{"scopes": ["a:read"], "purposes": ["p"], "max_risk_tier": "read"}],
        "budgets": {"act_per_day": 0, "spend_per_day": 0},
    }
    with pytest.raises(IdentityError, match="duplicate"):
        load_principals_dict({"principals": [definition, definition]})
