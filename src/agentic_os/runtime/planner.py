"""Planners: turn a goal into a plan of capability requests.

The planner proposes. The governor disposes. A planner never executes
anything itself; it only names the capabilities it wants, with a purpose
and parameters. The deterministic ScriptedPlanner makes the whole system
runnable offline and is what the demo and the eval harness use.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class PlannedStep(BaseModel):
    capability: str
    purpose: str
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class Plan(BaseModel):
    goal: str
    planner: str
    steps: list[PlannedStep]


class PlanningContext(BaseModel):
    """What a planner is allowed to see."""

    domain_summary: str
    capability_catalogue: list[dict]
    working_memory: str


class Planner(Protocol):
    name: str

    def plan(self, goal: str, context: PlanningContext) -> Plan: ...


class ScriptedPlanner:
    """Deterministic planner: replays a fixed list of steps for a goal.

    Used by the demo and the eval fixtures so every governance path can
    be exercised offline, repeatably.
    """

    name = "scripted"

    def __init__(self, steps: list[PlannedStep]) -> None:
        self.steps = steps

    def plan(self, goal: str, context: PlanningContext) -> Plan:
        return Plan(goal=goal, planner=self.name, steps=list(self.steps))
