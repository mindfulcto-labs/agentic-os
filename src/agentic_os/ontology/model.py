"""Ontology data model.

The ontology gives agents a shared understanding of the business.
It is deliberately small: typed entities, typed relations, and a graph
that can be queried. Nothing here is specific to one domain. The example
domain (a field-services company) lives in a YAML file next to this module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntityType(BaseModel):
    """A kind of business object, for example a customer or a work order."""

    name: str
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)


class RelationType(BaseModel):
    """A kind of link between two entity types."""

    name: str
    source: str
    target: str
    description: str = ""


class Entity(BaseModel):
    """A concrete business object in the graph."""

    id: str
    type: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    def attr(self, name: str, default: Any = None) -> Any:
        return self.attributes.get(name, default)


class Relation(BaseModel):
    """A concrete link between two entities."""

    type: str
    source_id: str
    target_id: str


class OntologyError(Exception):
    """Raised when a domain definition is inconsistent."""


class DomainGraph(BaseModel):
    """A validated, queryable domain graph.

    Agents ground their context by querying this graph. Capabilities
    read from it and write to it. It is the single source of business
    state in this reference implementation.
    """

    name: str
    description: str = ""
    entity_types: dict[str, EntityType] = Field(default_factory=dict)
    relation_types: dict[str, RelationType] = Field(default_factory=dict)
    entities: dict[str, Entity] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list)

    # -- construction -------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        if entity.type not in self.entity_types:
            raise OntologyError(f"unknown entity type: {entity.type!r}")
        if entity.id in self.entities:
            raise OntologyError(f"duplicate entity id: {entity.id!r}")
        self.entities[entity.id] = entity
        return entity

    def add_relation(self, relation: Relation) -> Relation:
        rel_type = self.relation_types.get(relation.type)
        if rel_type is None:
            raise OntologyError(f"unknown relation type: {relation.type!r}")
        source = self.entities.get(relation.source_id)
        target = self.entities.get(relation.target_id)
        if source is None:
            raise OntologyError(f"relation source not found: {relation.source_id!r}")
        if target is None:
            raise OntologyError(f"relation target not found: {relation.target_id!r}")
        if source.type != rel_type.source:
            raise OntologyError(
                f"relation {relation.type!r} expects source type {rel_type.source!r}, "
                f"got {source.type!r}"
            )
        if target.type != rel_type.target:
            raise OntologyError(
                f"relation {relation.type!r} expects target type {rel_type.target!r}, "
                f"got {target.type!r}"
            )
        self.relations.append(relation)
        return relation

    # -- queries ------------------------------------------------------

    def get(self, entity_id: str) -> Entity:
        entity = self.entities.get(entity_id)
        if entity is None:
            raise OntologyError(f"entity not found: {entity_id!r}")
        return entity

    def of_type(self, type_name: str) -> list[Entity]:
        return [e for e in self.entities.values() if e.type == type_name]

    def find(self, type_name: str, **attributes: Any) -> list[Entity]:
        """Find entities of a type whose attributes match the given values."""
        results = []
        for entity in self.of_type(type_name):
            if all(entity.attr(key) == value for key, value in attributes.items()):
                results.append(entity)
        return results

    def related(
        self,
        entity_id: str,
        relation_type: str | None = None,
        direction: str = "out",
    ) -> list[Entity]:
        """Entities linked to the given entity.

        direction "out" follows relations where the entity is the source,
        "in" follows relations where it is the target.
        """
        if direction not in ("out", "in"):
            raise ValueError("direction must be 'out' or 'in'")
        results: list[Entity] = []
        for relation in self.relations:
            if relation_type is not None and relation.type != relation_type:
                continue
            if direction == "out" and relation.source_id == entity_id:
                results.append(self.get(relation.target_id))
            elif direction == "in" and relation.target_id == entity_id:
                results.append(self.get(relation.source_id))
        return results

    def summary(self) -> str:
        """A short text description of the domain, used to ground LLM planners."""
        lines = [f"Domain: {self.name}. {self.description}".strip()]
        for et in self.entity_types.values():
            count = len(self.of_type(et.name))
            lines.append(f"- {et.name}: {et.description} ({count} in graph)")
        for rt in self.relation_types.values():
            lines.append(f"- relation {rt.name}: {rt.source} -> {rt.target}")
        return "\n".join(lines)
