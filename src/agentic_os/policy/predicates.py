"""Built-in policy predicates.

A predicate is a small Python function. It receives the run state so far,
the capability the agent wants to invoke next, and the policy parameters
from policies.yaml. It returns (compliant, detail). Policies run inside
the loop, before every invocation, not as a review step at the end.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentic_os.capabilities.model import Capability, RiskTier

if TYPE_CHECKING:
    from agentic_os.runtime.state import RunState

Predicate = Callable[["RunState", Capability, dict[str, Any]], tuple[bool, str]]

PREDICATES: dict[str, Predicate] = {}


def predicate(name: str) -> Callable[[Predicate], Predicate]:
    def register(fn: Predicate) -> Predicate:
        PREDICATES[name] = fn
        return fn

    return register


@predicate("no_spend_after_denial")
def no_spend_after_denial(
    run_state: RunState, capability: Capability, params: dict[str, Any]
) -> tuple[bool, str]:
    """Block spend capabilities once any invocation in this run was denied.

    A denial means the agent is already outside its lane. Committing money
    after that is the wrong direction of travel.
    """
    if capability.risk_tier is RiskTier.SPEND and run_state.had_denial():
        return False, (
            f"spend capability {capability.name!r} blocked: "
            f"{run_state.denial_count()} denial(s) earlier in this run"
        )
    return True, "no earlier denial, or capability is not spend tier"


@predicate("max_act_steps")
def max_act_steps(
    run_state: RunState, capability: Capability, params: dict[str, Any]
) -> tuple[bool, str]:
    """Cap the number of act and spend steps in a single run."""
    limit = int(params.get("limit", 3))
    if capability.risk_tier in (RiskTier.ACT, RiskTier.SPEND):
        used = run_state.act_step_count()
        if used >= limit:
            return False, f"run already used {used} act/spend steps (limit {limit})"
    return True, "within act-step limit"


@predicate("deny_capability")
def deny_capability(
    run_state: RunState, capability: Capability, params: dict[str, Any]
) -> tuple[bool, str]:
    """Deny listed capabilities outright. Useful for incident lockdowns."""
    blocked = params.get("capabilities", [])
    if capability.name in blocked:
        return False, f"capability {capability.name!r} is blocked by policy"
    return True, "capability is not on the blocked list"
