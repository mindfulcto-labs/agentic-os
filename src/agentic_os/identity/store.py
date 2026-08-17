"""Principal store: loads principals from YAML."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

from agentic_os.identity.model import IdentityError, Principal


class PrincipalStore:
    def __init__(self, principals: list[Principal]) -> None:
        self._principals: dict[str, Principal] = {}
        for principal in principals:
            if principal.id in self._principals:
                raise IdentityError(f"duplicate principal id: {principal.id!r}")
            self._principals[principal.id] = principal

    def get(self, principal_id: str) -> Principal:
        principal = self._principals.get(principal_id)
        if principal is None:
            raise IdentityError(f"unknown principal: {principal_id!r}")
        return principal

    def has(self, principal_id: str) -> bool:
        return principal_id in self._principals

    def ids(self) -> list[str]:
        return sorted(self._principals)

    def all(self) -> list[Principal]:
        return [self._principals[pid] for pid in self.ids()]


def load_principals_dict(data: dict) -> PrincipalStore:
    raw = data.get("principals")
    if not raw:
        raise IdentityError("principal definition needs a 'principals' list")
    return PrincipalStore([Principal.model_validate(item) for item in raw])


def load_principals(path: str | Path) -> PrincipalStore:
    with open(path, encoding="utf-8") as handle:
        return load_principals_dict(yaml.safe_load(handle))


def default_principals() -> PrincipalStore:
    """Load the packaged example principals."""
    source = resources.files("agentic_os.identity").joinpath("principals.yaml")
    return load_principals_dict(yaml.safe_load(source.read_text(encoding="utf-8")))
