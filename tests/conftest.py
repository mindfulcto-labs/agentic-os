"""Shared fixtures: a fresh governed world per test, writing under tmp_path."""

from __future__ import annotations

import pytest

from agentic_os.capabilities.field_services import build_registry
from agentic_os.identity.store import default_principals
from agentic_os.ontology.loader import default_domain
from agentic_os.policy.engine import default_policies
from agentic_os.runtime.agent import AgentRuntime
from agentic_os.runtime.approvals import AutoApprovalGate


@pytest.fixture
def graph():
    return default_domain()


@pytest.fixture
def registry():
    return build_registry()


@pytest.fixture
def principals():
    return default_principals()


@pytest.fixture
def policies():
    return default_policies()


@pytest.fixture
def make_runtime(graph, registry, principals, policies, tmp_path):
    def factory(auto_approve: bool = True, **overrides) -> AgentRuntime:
        kwargs = {
            "graph": graph,
            "registry": registry,
            "principals": principals,
            "policy_engine": policies,
            "approval_gate": AutoApprovalGate(approve=auto_approve),
            "runs_dir": tmp_path / "runs",
            "memory_dir": tmp_path / "memory",
        }
        kwargs.update(overrides)
        return AgentRuntime(**kwargs)

    return factory


@pytest.fixture
def runtime(make_runtime):
    return make_runtime()
