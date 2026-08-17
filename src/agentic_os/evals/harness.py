"""Offline eval harness.

Fixtures are YAML files. Each one scripts an agent run (or several runs
sharing one budget ledger) through the deterministic planner and asserts
the governance outcome: which capabilities were allowed, which were
denied and why, and how much budget was used. The pytest suite replays
every fixture, so the evals double as the acceptance suite.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from agentic_os.capabilities.field_services import build_registry
from agentic_os.capabilities.model import RiskTier
from agentic_os.identity.store import default_principals
from agentic_os.observability.trace import RunTrace
from agentic_os.ontology.loader import default_domain
from agentic_os.policy.engine import default_policies
from agentic_os.runtime.agent import AgentRuntime
from agentic_os.runtime.approvals import AutoApprovalGate
from agentic_os.runtime.planner import PlannedStep, ScriptedPlanner


class ExpectedDenial(BaseModel):
    capability: str
    reason_contains: str


class RunExpectation(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    denied: list[ExpectedDenial] = Field(default_factory=list)


class FixtureRun(BaseModel):
    goal: str
    steps: list[PlannedStep]
    expect: RunExpectation


class BudgetExpectation(BaseModel):
    act_used: int | None = None
    spend_used: int | None = None


class Fixture(BaseModel):
    name: str
    description: str = ""
    principal: str
    auto_approve: bool = True
    runs: list[FixtureRun]
    expect_budgets: BudgetExpectation | None = None


class EvalOutcome(BaseModel):
    fixture: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    traces: list[RunTrace] = Field(default_factory=list)


def load_fixture(path: str | Path) -> Fixture:
    with open(path, encoding="utf-8") as handle:
        return Fixture.model_validate(yaml.safe_load(handle))


def fixture_paths() -> list[Path]:
    """Paths of the packaged fixtures, sorted by name."""
    root = resources.files("agentic_os.evals").joinpath("fixtures")
    return sorted(Path(str(root)).glob("*.yaml"))


def _check_run(fixture_run: FixtureRun, trace: RunTrace, failures: list[str]) -> None:
    allowed = [inv.capability for inv in trace.invocations if inv.verdict.allowed]
    denied = [inv for inv in trace.invocations if not inv.verdict.allowed]

    if allowed != fixture_run.expect.allowed:
        failures.append(
            f"goal {fixture_run.goal!r}: expected allowed {fixture_run.expect.allowed}, "
            f"got {allowed}"
        )
    if len(denied) != len(fixture_run.expect.denied):
        failures.append(
            f"goal {fixture_run.goal!r}: expected {len(fixture_run.expect.denied)} denial(s), "
            f"got {len(denied)}: {[d.verdict.reason for d in denied]}"
        )
        return
    for expected, actual in zip(fixture_run.expect.denied, denied, strict=True):
        if actual.capability != expected.capability:
            failures.append(
                f"goal {fixture_run.goal!r}: expected denial of {expected.capability!r}, "
                f"got {actual.capability!r}"
            )
        if expected.reason_contains.lower() not in actual.verdict.reason.lower():
            failures.append(
                f"goal {fixture_run.goal!r}: denial reason {actual.verdict.reason!r} "
                f"does not contain {expected.reason_contains!r}"
            )


def run_fixture(fixture: Fixture, work_dir: str | Path | None = None) -> EvalOutcome:
    """Replay one fixture in a fresh world and check its expectations."""
    base = Path(work_dir) if work_dir else Path(".agentic_os") / "evals"
    runtime = AgentRuntime(
        graph=default_domain(),
        registry=build_registry(),
        principals=default_principals(),
        policy_engine=default_policies(),
        approval_gate=AutoApprovalGate(approve=fixture.auto_approve),
        runs_dir=base / "runs",
        memory_dir=base / "memory",
    )

    failures: list[str] = []
    traces: list[RunTrace] = []
    for fixture_run in fixture.runs:
        planner = ScriptedPlanner(fixture_run.steps)
        result = runtime.run(fixture.principal, fixture_run.goal, planner)
        traces.append(result.trace)
        _check_run(fixture_run, result.trace, failures)

    if fixture.expect_budgets is not None:
        principal_id = fixture.principal
        if fixture.expect_budgets.act_used is not None:
            used = runtime.ledger.used(principal_id, RiskTier.ACT)
            if used != fixture.expect_budgets.act_used:
                failures.append(
                    f"expected {fixture.expect_budgets.act_used} act budget used, got {used}"
                )
        if fixture.expect_budgets.spend_used is not None:
            used = runtime.ledger.used(principal_id, RiskTier.SPEND)
            if used != fixture.expect_budgets.spend_used:
                failures.append(
                    f"expected {fixture.expect_budgets.spend_used} spend budget used, got {used}"
                )

    return EvalOutcome(fixture=fixture.name, passed=not failures, failures=failures, traces=traces)


def run_all(work_dir: str | Path | None = None) -> list[EvalOutcome]:
    return [run_fixture(load_fixture(path), work_dir) for path in fixture_paths()]
