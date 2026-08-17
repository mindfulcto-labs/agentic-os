"""The agent loop, the governor, budgets, approvals and planners.

Exports are resolved lazily (PEP 562). The observability module records
runtime results, and the agent loop writes traces through observability.
Lazy resolution keeps that pair of imports acyclic whichever side is
imported first.
"""

from importlib import import_module

_EXPORTS = {
    "AgentRuntime": "agentic_os.runtime.agent",
    "RunResult": "agentic_os.runtime.agent",
    "ApprovalGate": "agentic_os.runtime.approvals",
    "AutoApprovalGate": "agentic_os.runtime.approvals",
    "CallbackApprovalGate": "agentic_os.runtime.approvals",
    "BudgetLedger": "agentic_os.runtime.budgets",
    "Check": "agentic_os.runtime.governor",
    "Governor": "agentic_os.runtime.governor",
    "InvocationResult": "agentic_os.runtime.governor",
    "Verdict": "agentic_os.runtime.governor",
    "Plan": "agentic_os.runtime.planner",
    "PlannedStep": "agentic_os.runtime.planner",
    "Planner": "agentic_os.runtime.planner",
    "PlanningContext": "agentic_os.runtime.planner",
    "ScriptedPlanner": "agentic_os.runtime.planner",
    "InvocationRecord": "agentic_os.runtime.state",
    "RunState": "agentic_os.runtime.state",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return __all__
