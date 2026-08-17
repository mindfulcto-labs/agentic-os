"""The domain graph: loading, validation and traversal."""

import pytest

from agentic_os.ontology import (
    Entity,
    OntologyError,
    Relation,
    default_domain,
    load_domain,
    load_domain_dict,
)


def test_default_domain_loads(graph):
    assert graph.name == "field-services"
    assert set(graph.entity_types) == {"customer", "site", "work_order", "technician", "invoice"}
    assert len(graph.of_type("customer")) == 3
    assert len(graph.of_type("work_order")) == 5


def test_find_by_attribute(graph):
    matches = graph.find("customer", name="Harbour Bakery")
    assert len(matches) == 1
    assert matches[0].id == "cust-001"


def test_traversal_customer_to_open_work_orders(graph):
    customer = graph.find("customer", name="Harbour Bakery")[0]
    sites = graph.related(customer.id, "belongs_to", direction="in")
    assert {site.id for site in sites} == {"site-001", "site-004"}
    orders = [wo for site in sites for wo in graph.related(site.id, "raised_at", direction="in")]
    open_orders = [wo for wo in orders if wo.attr("status") == "open"]
    assert {wo.id for wo in open_orders} == {"wo-001", "wo-005"}


def test_unknown_entity_raises(graph):
    with pytest.raises(OntologyError, match="not found"):
        graph.get("cust-999")


def test_add_entity_rejects_unknown_type(graph):
    with pytest.raises(OntologyError, match="unknown entity type"):
        graph.add_entity(Entity(id="x-1", type="spaceship"))


def test_add_relation_validates_endpoint_types(graph):
    with pytest.raises(OntologyError, match="expects source type"):
        graph.add_relation(Relation(type="belongs_to", source_id="cust-001", target_id="cust-002"))


def test_relation_type_must_reference_known_entity_types():
    data = {
        "name": "broken",
        "entity_types": [{"name": "customer"}],
        "relation_types": [{"name": "belongs_to", "source": "site", "target": "customer"}],
    }
    with pytest.raises(OntologyError, match="unknown source type"):
        load_domain_dict(data)


def test_load_domain_from_file(tmp_path):
    path = tmp_path / "tiny.yaml"
    path.write_text(
        """
name: tiny
entity_types:
  - name: customer
entities:
  - id: c-1
    type: customer
    attributes: { name: Test Ltd }
""",
        encoding="utf-8",
    )
    graph = load_domain(path)
    assert graph.get("c-1").attr("name") == "Test Ltd"


def test_summary_mentions_types_and_relations():
    text = default_domain().summary()
    assert "customer" in text
    assert "belongs_to" in text
