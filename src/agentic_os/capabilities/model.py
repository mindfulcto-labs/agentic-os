"""Governed capability model.

A capability is not a raw tool. It is a declared unit of business action
with an input schema, an output schema, required permission scopes,
purpose tags, a risk tier and a rate limit. The governor decides whether
a principal may invoke it. The handler only runs after that decision.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from agentic_os.ontology.model import DomainGraph


class RiskTier(enum.StrEnum):
    """How much a capability can change the world.

    read: observes state only.
    act: changes business state (schedules, sends, updates).
    spend: commits money or creates financial obligations.
    """

    READ = "read"
    ACT = "act"
    SPEND = "spend"

    @property
    def rank(self) -> int:
        return {"read": 0, "act": 1, "spend": 2}[self.value]

    def covers(self, other: RiskTier) -> bool:
        """True if a grant at this tier permits a capability at the other tier."""
        return self.rank >= other.rank


class RateLimit(BaseModel):
    """Per-run invocation cap for a capability."""

    max_calls_per_run: int = Field(gt=0)


Handler = Callable[[DomainGraph, BaseModel], BaseModel]


class Capability(BaseModel):
    """A governed business capability."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    required_scopes: list[str]
    purpose_tags: list[str]
    risk_tier: RiskTier
    rate_limit: RateLimit
    handler: Any = Field(exclude=True)

    def input_schema(self) -> dict:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict:
        return self.output_model.model_json_schema()

    def describe(self) -> dict:
        """A serialisable description, used for listings and LLM planner prompts."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
            "output_schema": self.output_schema(),
            "required_scopes": self.required_scopes,
            "purpose_tags": self.purpose_tags,
            "risk_tier": self.risk_tier.value,
            "rate_limit": {"max_calls_per_run": self.rate_limit.max_calls_per_run},
        }


class CapabilityError(Exception):
    """Raised for unknown capabilities or handler failures."""
