"""Budget ledger: daily act and spend counters per principal.

In-memory by design. A production system would back this with a store
that survives restarts. The interface is the point: the governor asks
"how much budget is left today" before every act or spend invocation.
"""

from __future__ import annotations

from datetime import date

from agentic_os.capabilities.model import RiskTier
from agentic_os.identity.model import Principal


class BudgetLedger:
    def __init__(self) -> None:
        self._usage: dict[tuple[str, str, str], int] = {}

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def used(self, principal_id: str, tier: RiskTier, day: str | None = None) -> int:
        key = (principal_id, tier.value, day or self._today())
        return self._usage.get(key, 0)

    def remaining(self, principal: Principal, tier: RiskTier) -> int | None:
        """Budget left today, or None when the tier is unbudgeted (read)."""
        limit = principal.budgets.limit_for(tier)
        if limit is None:
            return None
        return limit - self.used(principal.id, tier)

    def charge(self, principal_id: str, tier: RiskTier) -> None:
        if tier is RiskTier.READ:
            return
        key = (principal_id, tier.value, self._today())
        self._usage[key] = self._usage.get(key, 0) + 1
