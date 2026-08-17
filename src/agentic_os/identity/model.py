"""Principals and grants.

A principal is an agent or a human. A grant says what the principal may
do: which permission scopes, for which purposes, up to which risk tier.
Budgets cap how many act and spend invocations a principal gets per day.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentic_os.capabilities.model import RiskTier


class Grant(BaseModel):
    """A scoped permission: scopes x purposes x maximum risk tier."""

    scopes: list[str] = Field(min_length=1)
    purposes: list[str] = Field(min_length=1)
    max_risk_tier: RiskTier

    def covers_purpose(self, purpose: str) -> bool:
        return purpose in self.purposes

    def covers_scopes(self, required: list[str]) -> bool:
        return set(required).issubset(self.scopes)

    def covers_tier(self, tier: RiskTier) -> bool:
        return self.max_risk_tier.covers(tier)


class Budgets(BaseModel):
    """Daily invocation budgets by risk tier. Read invocations are unbudgeted."""

    act_per_day: int = Field(ge=0)
    spend_per_day: int = Field(ge=0)

    def limit_for(self, tier: RiskTier) -> int | None:
        if tier is RiskTier.ACT:
            return self.act_per_day
        if tier is RiskTier.SPEND:
            return self.spend_per_day
        return None


class Principal(BaseModel):
    """An agent or human known to the runtime."""

    id: str
    kind: Literal["agent", "human"]
    display_name: str
    description: str = ""
    grants: list[Grant] = Field(default_factory=list)
    budgets: Budgets

    def matching_grants(self, purpose: str) -> list[Grant]:
        return [grant for grant in self.grants if grant.covers_purpose(purpose)]


class IdentityError(Exception):
    """Raised for unknown principals or invalid identity definitions."""
