"""The declarative agents layer: YAML definitions, validated before running."""

import pytest

from agentic_os.agents import (
    AgentDefinitionError,
    discover_definitions,
    load_definition_file,
)

VALID = """
name: surveyor
description: Reads the graph and reports.
capabilities: [lookup_customer, list_open_work_orders]
purposes: [service_delivery]
risk_ceiling: read
budgets: { act_per_day: 0, spend_per_day: 0 }
policies: [no-spend-after-denial]
planner: scripted
script:
  - capability: lookup_customer
    purpose: service_delivery
    params: { name: Harbour Bakery }
"""


def write(tmp_path, text, name="agent.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_definition_loads(tmp_path, registry, policies):
    definition = load_definition_file(write(tmp_path, VALID), registry, policies)
    assert definition.name == "surveyor"
    assert definition.risk_ceiling.value == "read"


def test_packaged_definitions_discoverable(registry, policies):
    definitions = discover_definitions(registry, policies)
    assert {"dispatcher", "billing-clerk"} <= set(definitions)
    assert definitions["dispatcher"].planner == "scripted"
    assert definitions["billing-clerk"].planner == "llm"


def test_shape_errors_report_paths(tmp_path, registry, policies):
    broken = VALID.replace("risk_ceiling: read", "risk_ceiling: reckless")
    with pytest.raises(AgentDefinitionError, match="risk_ceiling"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_unknown_capability_rejected(tmp_path, registry, policies):
    broken = VALID.replace("list_open_work_orders", "teleport_technician")
    with pytest.raises(AgentDefinitionError, match=r"capabilities\[1\].*not a registered"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_over_privileged_definition_rejected(tmp_path, registry, policies):
    """A spend-tier capability under a read ceiling must not load."""
    broken = VALID.replace("list_open_work_orders", "draft_invoice")
    with pytest.raises(AgentDefinitionError, match="above the declared risk ceiling"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_unknown_policy_rejected(tmp_path, registry, policies):
    broken = VALID.replace("no-spend-after-denial", "no-such-policy")
    with pytest.raises(AgentDefinitionError, match=r"policies\[0\]"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_script_outside_own_grant_rejected(tmp_path, registry, policies):
    broken = VALID + """
  - capability: schedule_technician
    purpose: service_delivery
    params: { work_order_id: wo-001, technician_id: tech-002, date: "2026-08-20" }
"""
    with pytest.raises(AgentDefinitionError, match=r"script\[1\].*not granted"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_scripted_agent_needs_a_script(tmp_path, registry, policies):
    broken = VALID.split("script:")[0]
    with pytest.raises(AgentDefinitionError, match="at least one step"):
        load_definition_file(write(tmp_path, broken), registry, policies)


def test_definition_becomes_a_principal(tmp_path, registry, policies):
    definition = load_definition_file(write(tmp_path, VALID), registry, policies)
    scopes = []
    for name in definition.capabilities:
        scopes.extend(registry.get(name).required_scopes)
    principal = definition.to_principal(scopes)
    assert principal.id == "surveyor"
    assert principal.grants[0].scopes == ["customers:read", "work_orders:read"]
    assert principal.grants[0].max_risk_tier.value == "read"
