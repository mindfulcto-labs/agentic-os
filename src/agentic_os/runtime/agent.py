"""The agent loop.

goal -> plan -> governed invocation -> memory -> trace

The loop is short on purpose. All the interesting decisions live in the
governor and the policy engine. A denial does not stop the run; it is
recorded, remembered, and later steps are judged with that history in
view (some policies exist exactly for that).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel

from agentic_os.capabilities.registry import CapabilityRegistry
from agentic_os.identity.store import PrincipalStore
from agentic_os.memory.episodic import EpisodicLog
from agentic_os.memory.working import WorkingMemory
from agentic_os.observability.trace import (
    RunTrace,
    TraceWriter,
    build_summary,
    now_iso,
)
from agentic_os.ontology.model import DomainGraph
from agentic_os.policy.engine import PolicyEngine
from agentic_os.runtime.approvals import ApprovalGate, AutoApprovalGate
from agentic_os.runtime.budgets import BudgetLedger
from agentic_os.runtime.governor import Governor, InvocationResult
from agentic_os.runtime.planner import Plan, Planner, PlanningContext
from agentic_os.runtime.state import RunState


class RunResult(BaseModel):
    trace: RunTrace
    trace_path: str


class AgentRuntime:
    def __init__(
        self,
        graph: DomainGraph,
        registry: CapabilityRegistry,
        principals: PrincipalStore,
        policy_engine: PolicyEngine,
        approval_gate: ApprovalGate | None = None,
        ledger: BudgetLedger | None = None,
        runs_dir: str | Path = "runs",
        memory_dir: str | Path = Path(".agentic_os") / "memory",
    ) -> None:
        self.graph = graph
        self.registry = registry
        self.principals = principals
        self.ledger = ledger or BudgetLedger()
        self.governor = Governor(
            registry=registry,
            principals=principals,
            ledger=self.ledger,
            policy_engine=policy_engine,
            approval_gate=approval_gate or AutoApprovalGate(approve=True),
        )
        self.trace_writer = TraceWriter(runs_dir)
        self.episodic = EpisodicLog(memory_dir)

    def _planning_context(self, memory: WorkingMemory) -> PlanningContext:
        return PlanningContext(
            domain_summary=self.graph.summary(),
            capability_catalogue=self.registry.describe_all(),
            working_memory=memory.as_context(),
        )

    def run(self, principal_id: str, goal: str, planner: Planner) -> RunResult:
        principal = self.principals.get(principal_id)
        run_id = uuid.uuid4().hex[:12]
        started_at = now_iso()
        memory = WorkingMemory()
        run_state = RunState(run_id=run_id, principal_id=principal.id, goal=goal)

        self.episodic.append(principal.id, "run_started", {"run_id": run_id, "goal": goal})

        plan: Plan = planner.plan(goal, self._planning_context(memory))
        invocations: list[InvocationResult] = []

        for index, step in enumerate(plan.steps):
            result = self.governor.invoke(
                principal_id=principal.id,
                capability_name=step.capability,
                purpose=step.purpose,
                params=step.params,
                run_state=run_state,
                graph=self.graph,
            )
            invocations.append(result)

            key = f"step_{index}_{step.capability}"
            if result.verdict.allowed and result.output is not None:
                memory.remember(key, result.output)
                self.episodic.append(
                    principal.id,
                    "invocation_allowed",
                    {"run_id": run_id, "capability": step.capability, "purpose": step.purpose},
                )
            else:
                memory.remember(
                    key, {"denied": True, "reason": result.error or result.verdict.reason}
                )
                self.episodic.append(
                    principal.id,
                    "invocation_denied" if not result.verdict.allowed else "invocation_error",
                    {
                        "run_id": run_id,
                        "capability": step.capability,
                        "purpose": step.purpose,
                        "reason": result.error or result.verdict.reason,
                    },
                )

        summary = build_summary(invocations, planned=len(plan.steps))
        trace = RunTrace(
            run_id=run_id,
            principal_id=principal.id,
            goal=goal,
            planner=plan.planner,
            started_at=started_at,
            finished_at=now_iso(),
            plan=plan,
            invocations=invocations,
            summary=summary,
            working_memory=memory.snapshot(),
        )
        path = self.trace_writer.write(trace)
        self.episodic.append(
            principal.id,
            "run_finished",
            {
                "run_id": run_id,
                "allowed": summary.steps_allowed,
                "denied": summary.steps_denied,
            },
        )
        return RunResult(trace=trace, trace_path=str(path))
