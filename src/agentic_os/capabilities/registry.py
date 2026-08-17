"""Capability registry: the catalogue of governed business capabilities."""

from __future__ import annotations

from agentic_os.capabilities.model import Capability, CapabilityError


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> Capability:
        if capability.name in self._capabilities:
            raise CapabilityError(f"capability already registered: {capability.name!r}")
        self._capabilities[capability.name] = capability
        return capability

    def get(self, name: str) -> Capability:
        capability = self._capabilities.get(name)
        if capability is None:
            raise CapabilityError(f"capability not registered: {name!r}")
        return capability

    def has(self, name: str) -> bool:
        return name in self._capabilities

    def names(self) -> list[str]:
        return sorted(self._capabilities)

    def all(self) -> list[Capability]:
        return [self._capabilities[name] for name in self.names()]

    def describe_all(self) -> list[dict]:
        return [capability.describe() for capability in self.all()]
