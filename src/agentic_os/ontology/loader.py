"""Load a domain graph from a YAML definition."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

from agentic_os.ontology.model import (
    DomainGraph,
    Entity,
    EntityType,
    OntologyError,
    Relation,
    RelationType,
)


def load_domain_dict(data: dict) -> DomainGraph:
    """Build and validate a DomainGraph from a parsed YAML dictionary."""
    if "name" not in data:
        raise OntologyError("domain definition needs a 'name'")
    graph = DomainGraph(name=data["name"], description=data.get("description", ""))
    for raw in data.get("entity_types", []):
        et = EntityType.model_validate(raw)
        graph.entity_types[et.name] = et
    for raw in data.get("relation_types", []):
        rt = RelationType.model_validate(raw)
        if rt.source not in graph.entity_types:
            raise OntologyError(f"relation {rt.name!r} has unknown source type {rt.source!r}")
        if rt.target not in graph.entity_types:
            raise OntologyError(f"relation {rt.name!r} has unknown target type {rt.target!r}")
        graph.relation_types[rt.name] = rt
    for raw in data.get("entities", []):
        graph.add_entity(Entity.model_validate(raw))
    for raw in data.get("relations", []):
        graph.add_relation(Relation.model_validate(raw))
    return graph


def load_domain(path: str | Path) -> DomainGraph:
    """Load a domain graph from a YAML file on disk."""
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return load_domain_dict(data)


def default_domain() -> DomainGraph:
    """Load the packaged example domain: a field-services company."""
    source = resources.files("agentic_os.ontology.domains").joinpath("field_services.yaml")
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return load_domain_dict(data)
