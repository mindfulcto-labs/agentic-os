"""Approval gate for mutating capabilities.

Act and spend invocations pass through an approval gate before they run.
Demos use auto-approval. A real deployment would route the request to a
human queue and block or reschedule until someone answers.
"""

from __future__ import annotations

from typing import Any, Protocol

from agentic_os.capabilities.model import Capability
from agentic_os.identity.model import Principal


class ApprovalGate(Protocol):
    def request(
        self, principal: Principal, capability: Capability, params: dict[str, Any]
    ) -> tuple[bool, str]:
        """Return (approved, detail)."""
        ...


class AutoApprovalGate:
    """Approves or declines everything. Used for demos and evals."""

    def __init__(self, approve: bool = True) -> None:
        self.approve = approve

    def request(
        self, principal: Principal, capability: Capability, params: dict[str, Any]
    ) -> tuple[bool, str]:
        if self.approve:
            return True, "auto-approved (demo mode)"
        return False, "approval required and no approver is configured"


class CallbackApprovalGate:
    """Delegates the decision to a caller-supplied function."""

    def __init__(self, callback) -> None:
        self.callback = callback

    def request(
        self, principal: Principal, capability: Capability, params: dict[str, Any]
    ) -> tuple[bool, str]:
        approved = bool(self.callback(principal, capability, params))
        detail = "approved by callback" if approved else "declined by callback"
        return approved, detail
