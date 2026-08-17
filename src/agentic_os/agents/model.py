"""Declarative agent definitions.

Building an agent is writing YAML, not code. A definition names the
capabilities the agent may request, the purposes it may claim, a risk
ceiling, daily budgets, the policies that watch it, and which planner
drives it. The loader validates all of that against the capability
registry and the policy catalogue before the agent can run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentic_os.capabilities.model import RiskTier
from agentic_os.identity.model import Budgets, Grant, Principal
from agentic_os.runtime.planner import PlannedStep


class AgentDefinition(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    description: str = ""
    goal_template: str = ""
    capabilities: list[str] = Field(min_length=1)
    purposes: list[str] = Field(min_length=1)
    risk_ceiling: RiskTier
    budgets: Budgets
    policies: list[str] = Field(default_factory=list)
    planner: Literal["scripted", "llm"] = "scripted"
    script: list[PlannedStep] = Field(default_factory=list)

    def to_principal(self, scopes: list[str]) -> Principal:
        """Build the runtime principal this definition stands for.

        The grant is derived, never widened: the scopes are exactly the
        required scopes of the granted capabilities, the purposes and
        risk ceiling come straight from the definition.
        """
        return Principal(
            id=self.name,
            kind="agent",
            display_name=self.name,
            description=self.description,
            grants=[
                Grant(
                    scopes=sorted(set(scopes)),
                    purposes=list(self.purposes),
                    max_risk_tier=self.risk_ceiling,
                )
            ],
            budgets=self.budgets,
        )


class AgentDefinitionError(Exception):
    """Raised when a definition is invalid, with the offending path in the message."""
