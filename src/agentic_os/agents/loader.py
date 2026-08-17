"""Load and validate declarative agent definitions.

Validation happens in two passes. Pydantic checks the shape and reports
precise error paths. Semantic checks then verify the definition against
the capability registry and the policy catalogue: every capability must
exist, no capability may sit above the declared risk ceiling, every
scripted step must stay inside the definition's own grants, and every
named policy must be defined.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from agentic_os.agents.model import AgentDefinition, AgentDefinitionError
from agentic_os.capabilities.registry import CapabilityRegistry
from agentic_os.policy.engine import PolicyEngine


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"]) or "(root)"
        lines.append(f"{path}: {error['msg']}")
    return "; ".join(lines)


def validate_definition(
    definition: AgentDefinition,
    registry: CapabilityRegistry,
    policy_engine: PolicyEngine,
) -> list[str]:
    """Return a list of problems. Empty list means the definition is sound."""
    problems: list[str] = []

    for index, name in enumerate(definition.capabilities):
        if not registry.has(name):
            problems.append(f"capabilities[{index}]: {name!r} is not a registered capability")
            continue
        capability = registry.get(name)
        if not definition.risk_ceiling.covers(capability.risk_tier):
            problems.append(
                f"capabilities[{index}]: {name!r} is {capability.risk_tier.value} tier, "
                f"above the declared risk ceiling {definition.risk_ceiling.value!r}"
            )

    known_policies = {policy.name for policy in policy_engine.policies}
    for index, name in enumerate(definition.policies):
        if name not in known_policies:
            problems.append(f"policies[{index}]: {name!r} is not a defined policy")

    if definition.planner == "scripted" and not definition.script:
        problems.append("script: a scripted agent needs at least one step")

    for index, step in enumerate(definition.script):
        if step.capability not in definition.capabilities:
            problems.append(
                f"script[{index}]: capability {step.capability!r} is not granted "
                f"to this agent"
            )
        if step.purpose not in definition.purposes:
            problems.append(
                f"script[{index}]: purpose {step.purpose!r} is not one of the agent's "
                f"purposes {definition.purposes}"
            )

    if definition.budgets.spend_per_day > 0 and definition.risk_ceiling.rank < 2:
        problems.append(
            "budgets.spend_per_day: a spend budget is pointless below a spend risk ceiling"
        )

    return problems


def load_definition_file(
    path: str | Path,
    registry: CapabilityRegistry,
    policy_engine: PolicyEngine,
) -> AgentDefinition:
    """Load one YAML definition and raise with precise paths on any problem."""
    path = Path(path)
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise AgentDefinitionError(f"{path.name}: definition must be a YAML mapping")
    try:
        definition = AgentDefinition.model_validate(data)
    except ValidationError as exc:
        raise AgentDefinitionError(
            f"{path.name}: {_format_validation_error(exc)}"
        ) from exc
    problems = validate_definition(definition, registry, policy_engine)
    if problems:
        raise AgentDefinitionError(f"{path.name}: " + "; ".join(problems))
    return definition


def packaged_definition_paths() -> list[Path]:
    root = resources.files("agentic_os.agents").joinpath("definitions")
    return sorted(Path(str(root)).glob("*.yaml"))


def discover_definitions(
    registry: CapabilityRegistry,
    policy_engine: PolicyEngine,
    extra_dir: str | Path | None = None,
) -> dict[str, AgentDefinition]:
    """Load packaged definitions, then any in extra_dir (which win on name clashes)."""
    definitions: dict[str, AgentDefinition] = {}
    paths = list(packaged_definition_paths())
    if extra_dir is not None and Path(extra_dir).is_dir():
        paths += sorted(Path(extra_dir).glob("*.yaml"))
    for path in paths:
        definition = load_definition_file(path, registry, policy_engine)
        definitions[definition.name] = definition
    return definitions
