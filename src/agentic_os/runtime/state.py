"""Run state: what has happened so far in the current run.

The governor and the policy engine both read this. It is the ground truth
for rate limits, "steps so far" policies, and the final trace.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentic_os.capabilities.model import RiskTier


class InvocationRecord(BaseModel):
    step_index: int
    capability: str
    purpose: str
    risk_tier: RiskTier
    allowed: bool
    reason: str


class RunState(BaseModel):
    run_id: str
    principal_id: str
    goal: str
    records: list[InvocationRecord] = Field(default_factory=list)

    def record(self, record: InvocationRecord) -> None:
        self.records.append(record)

    def calls_of(self, capability: str) -> int:
        """Allowed invocations of one capability so far in this run."""
        return sum(1 for r in self.records if r.capability == capability and r.allowed)

    def denial_count(self) -> int:
        return sum(1 for r in self.records if not r.allowed)

    def had_denial(self) -> bool:
        return self.denial_count() > 0

    def act_step_count(self) -> int:
        """Allowed act and spend invocations so far in this run."""
        return sum(
            1
            for r in self.records
            if r.allowed and r.risk_tier in (RiskTier.ACT, RiskTier.SPEND)
        )
