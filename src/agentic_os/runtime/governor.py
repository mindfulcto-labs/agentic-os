"""The governor: every capability invocation passes through here.

Checks run in a fixed order and every check is recorded, pass or fail:

1. the capability exists in the registry
2. some grant covers the declared purpose
3. that grant covers the capability's required scopes
4. that grant's risk tier covers the capability's risk tier
5. the per-run rate limit has headroom
6. no policy predicate objects
7. daily budget for the tier has headroom
8. the approval gate approves (act and spend tiers only)

A denial is a first-class result with a reason, not an exception.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agentic_os.capabilities.model import CapabilityError, RiskTier
from agentic_os.capabilities.registry import CapabilityRegistry
from agentic_os.identity.model import Grant, Principal
from agentic_os.identity.store import PrincipalStore
from agentic_os.ontology.model import DomainGraph
from agentic_os.policy.engine import PolicyEngine
from agentic_os.runtime.approvals import ApprovalGate
from agentic_os.runtime.budgets import BudgetLedger
from agentic_os.runtime.state import InvocationRecord, RunState


class Check(BaseModel):
    name: str
    passed: bool
    detail: str


class Verdict(BaseModel):
    allowed: bool
    reason: str
    checks: list[Check] = Field(default_factory=list)


class InvocationResult(BaseModel):
    capability: str
    purpose: str
    params: dict[str, Any]
    verdict: Verdict
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0


class Governor:
    def __init__(
        self,
        registry: CapabilityRegistry,
        principals: PrincipalStore,
        ledger: BudgetLedger,
        policy_engine: PolicyEngine,
        approval_gate: ApprovalGate,
    ) -> None:
        self.registry = registry
        self.principals = principals
        self.ledger = ledger
        self.policy_engine = policy_engine
        self.approval_gate = approval_gate

    # -- authorisation ------------------------------------------------

    def authorise(
        self,
        principal: Principal,
        capability_name: str,
        purpose: str,
        params: dict[str, Any],
        run_state: RunState,
    ) -> Verdict:
        checks: list[Check] = []

        def deny(reason: str) -> Verdict:
            return Verdict(allowed=False, reason=reason, checks=checks)

        # 1. capability exists
        if not self.registry.has(capability_name):
            checks.append(
                Check(
                    name="capability_exists",
                    passed=False,
                    detail=f"{capability_name!r} is not a registered capability",
                )
            )
            return deny(f"capability {capability_name!r} is not registered")
        capability = self.registry.get(capability_name)
        checks.append(
            Check(name="capability_exists", passed=True, detail=f"{capability_name} is registered")
        )

        # 2. purpose granted
        purpose_grants = principal.matching_grants(purpose)
        if not purpose_grants:
            checks.append(
                Check(
                    name="purpose_granted",
                    passed=False,
                    detail=f"no grant for {principal.id!r} covers purpose {purpose!r}",
                )
            )
            return deny(f"purpose {purpose!r} is not granted to {principal.id!r}")
        checks.append(
            Check(
                name="purpose_granted",
                passed=True,
                detail=f"{len(purpose_grants)} grant(s) cover purpose {purpose!r}",
            )
        )

        # 3. scopes granted (within a purpose-matching grant)
        scope_grants = [g for g in purpose_grants if g.covers_scopes(capability.required_scopes)]
        if not scope_grants:
            checks.append(
                Check(
                    name="scopes_granted",
                    passed=False,
                    detail=(
                        f"required scopes {capability.required_scopes} are not covered "
                        f"by any grant with purpose {purpose!r}"
                    ),
                )
            )
            return deny(
                f"scopes {capability.required_scopes} not granted for purpose {purpose!r}"
            )
        checks.append(
            Check(
                name="scopes_granted",
                passed=True,
                detail=f"scopes {capability.required_scopes} covered",
            )
        )

        # 4. risk tier within the grant
        tier_grants: list[Grant] = [g for g in scope_grants if g.covers_tier(capability.risk_tier)]
        if not tier_grants:
            max_tier = max(g.max_risk_tier.rank for g in scope_grants)
            checks.append(
                Check(
                    name="risk_tier",
                    passed=False,
                    detail=(
                        f"capability is {capability.risk_tier.value} tier, grant allows "
                        f"up to rank {max_tier}"
                    ),
                )
            )
            return deny(
                f"risk tier {capability.risk_tier.value!r} exceeds the grant "
                f"for {principal.id!r}"
            )
        checks.append(
            Check(
                name="risk_tier",
                passed=True,
                detail=f"tier {capability.risk_tier.value} is within the grant",
            )
        )

        # 5. per-run rate limit
        calls_so_far = run_state.calls_of(capability.name)
        limit = capability.rate_limit.max_calls_per_run
        if calls_so_far >= limit:
            checks.append(
                Check(
                    name="rate_limit",
                    passed=False,
                    detail=f"{calls_so_far} call(s) this run, limit is {limit}",
                )
            )
            return deny(f"rate limit reached for {capability.name!r} ({limit} per run)")
        checks.append(
            Check(
                name="rate_limit",
                passed=True,
                detail=f"{calls_so_far} of {limit} calls used this run",
            )
        )

        # 6. policies
        violations = self.policy_engine.evaluate(run_state, capability)
        if violations:
            first = violations[0]
            checks.append(
                Check(
                    name="policy",
                    passed=False,
                    detail="; ".join(f"{v.policy}: {v.detail}" for v in violations),
                )
            )
            return deny(f"policy {first.policy!r} objects: {first.detail}")
        checks.append(
            Check(
                name="policy",
                passed=True,
                detail=f"{len(self.policy_engine.policies)} policy check(s) passed",
            )
        )

        # 7. budget
        remaining = self.ledger.remaining(principal, capability.risk_tier)
        if remaining is not None and remaining <= 0:
            checks.append(
                Check(
                    name="budget",
                    passed=False,
                    detail=f"{capability.risk_tier.value} budget for today is exhausted",
                )
            )
            return deny(
                f"daily {capability.risk_tier.value} budget exhausted for {principal.id!r}"
            )
        budget_detail = (
            "read tier is unbudgeted"
            if remaining is None
            else f"{remaining} {capability.risk_tier.value} invocation(s) left today"
        )
        checks.append(Check(name="budget", passed=True, detail=budget_detail))

        # 8. approval gate for mutating tiers
        if capability.risk_tier in (RiskTier.ACT, RiskTier.SPEND):
            approved, detail = self.approval_gate.request(principal, capability, params)
            checks.append(Check(name="approval", passed=approved, detail=detail))
            if not approved:
                return deny(f"approval declined: {detail}")
        else:
            checks.append(
                Check(name="approval", passed=True, detail="read tier needs no approval")
            )

        return Verdict(allowed=True, reason="all checks passed", checks=checks)

    # -- invocation ---------------------------------------------------

    def invoke(
        self,
        principal_id: str,
        capability_name: str,
        purpose: str,
        params: dict[str, Any],
        run_state: RunState,
        graph: DomainGraph,
    ) -> InvocationResult:
        started = time.perf_counter()
        principal = self.principals.get(principal_id)
        verdict = self.authorise(principal, capability_name, purpose, params, run_state)

        output: dict[str, Any] | None = None
        error: str | None = None

        if verdict.allowed:
            capability = self.registry.get(capability_name)
            try:
                validated = capability.input_model.model_validate(params)
                result = capability.handler(graph, validated)
                output = result.model_dump()
                self.ledger.charge(principal.id, capability.risk_tier)
            except ValidationError as exc:
                error = f"input validation failed: {exc.error_count()} error(s)"
                verdict = Verdict(
                    allowed=False,
                    reason=error,
                    checks=verdict.checks
                    + [Check(name="input_validation", passed=False, detail=str(exc))],
                )
            except CapabilityError as exc:
                # The invocation was authorised but the handler could not
                # complete. This is an execution error, not a denial.
                error = str(exc)

        tier = (
            self.registry.get(capability_name).risk_tier
            if self.registry.has(capability_name)
            else RiskTier.READ
        )
        run_state.record(
            InvocationRecord(
                step_index=len(run_state.records),
                capability=capability_name,
                purpose=purpose,
                risk_tier=tier,
                allowed=verdict.allowed,
                reason=error if (verdict.allowed and error) else verdict.reason,
            )
        )

        latency_ms = (time.perf_counter() - started) * 1000
        return InvocationResult(
            capability=capability_name,
            purpose=purpose,
            params=params,
            verdict=verdict,
            output=output,
            error=error,
            latency_ms=round(latency_ms, 3),
        )
