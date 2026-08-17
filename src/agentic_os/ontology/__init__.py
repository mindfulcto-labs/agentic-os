"""Business-domain ontology: entity types, relations and a queryable graph."""

from agentic_os.ontology.loader import default_domain, load_domain, load_domain_dict
from agentic_os.ontology.model import (
    DomainGraph,
    Entity,
    EntityType,
    OntologyError,
    Relation,
    RelationType,
)

__all__ = [
    "DomainGraph",
    "Entity",
    "EntityType",
    "OntologyError",
    "Relation",
    "RelationType",
    "default_domain",
    "load_domain",
    "load_domain_dict",
]
