"""Policy engine: loads policies.yaml and evaluates predicates in the loop."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

from agentic_os.capabilities.model import Capability
from agentic_os.policy.predicates import PREDICATES

if TYPE_CHECKING:
    from agentic_os.runtime.state import RunState


class PolicyError(Exception):
    """Raised for unknown rules or invalid policy definitions."""


class Policy(BaseModel):
    name: str
    description: str = ""
    rule: str
    params: dict[str, Any] = Field(default_factory=dict)


class PolicyViolation(BaseModel):
    policy: str
    detail: str


class PolicyEngine:
    def __init__(self, policies: list[Policy]) -> None:
        for policy in policies:
            if policy.rule not in PREDICATES:
                raise PolicyError(
                    f"policy {policy.name!r} references unknown rule {policy.rule!r}"
                )
        self.policies = policies

    def evaluate(self, run_state: RunState, capability: Capability) -> list[PolicyViolation]:
        """Return violations for the proposed invocation. Empty list means compliant."""
        violations: list[PolicyViolation] = []
        for policy in self.policies:
            predicate = PREDICATES[policy.rule]
            compliant, detail = predicate(run_state, capability, policy.params)
            if not compliant:
                violations.append(PolicyViolation(policy=policy.name, detail=detail))
        return violations


def load_policies_dict(data: dict) -> PolicyEngine:
    raw = data.get("policies", [])
    return PolicyEngine([Policy.model_validate(item) for item in raw])


def load_policies(path: str | Path) -> PolicyEngine:
    with open(path, encoding="utf-8") as handle:
        return load_policies_dict(yaml.safe_load(handle))


def default_policies() -> PolicyEngine:
    """Load the packaged example policies."""
    source = resources.files("agentic_os.policy").joinpath("policies.yaml")
    return load_policies_dict(yaml.safe_load(source.read_text(encoding="utf-8")))
