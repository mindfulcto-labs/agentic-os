"""The capability registry and the five example capabilities."""

import pytest

from agentic_os.capabilities import CapabilityError, RiskTier
from agentic_os.capabilities.field_services import (
    DraftInvoiceInput,
    ListOpenWorkOrdersInput,
    LookupCustomerInput,
    ScheduleTechnicianInput,
    SendNotificationInput,
)


def test_registry_lists_five_capabilities(registry):
    assert registry.names() == [
        "draft_invoice",
        "list_open_work_orders",
        "lookup_customer",
        "schedule_technician",
        "send_notification",
    ]


def test_capability_declarations(registry):
    invoice = registry.get("draft_invoice")
    assert invoice.risk_tier is RiskTier.SPEND
    assert invoice.required_scopes == ["invoices:write"]
    assert "billing" in invoice.purpose_tags
    schema = invoice.input_schema()
    assert "work_order_id" in schema["properties"]


def test_describe_all_is_serialisable(registry):
    described = registry.describe_all()
    assert len(described) == 5
    for item in described:
        assert {"name", "risk_tier", "required_scopes", "input_schema"} <= set(item)


def test_unknown_capability_raises(registry):
    with pytest.raises(CapabilityError, match="not registered"):
        registry.get("teleport_technician")


def test_lookup_customer_handler(registry, graph):
    capability = registry.get("lookup_customer")
    output = capability.handler(graph, LookupCustomerInput(name="Harbour Bakery"))
    assert output.customer_id == "cust-001"
    assert {site.site_id for site in output.sites} == {"site-001", "site-004"}


def test_list_open_work_orders_filters_by_customer(registry, graph):
    capability = registry.get("list_open_work_orders")
    output = capability.handler(graph, ListOpenWorkOrdersInput(customer_id="cust-001"))
    assert {row.work_order_id for row in output.work_orders} == {"wo-001", "wo-005"}
    everything = capability.handler(graph, ListOpenWorkOrdersInput())
    assert len(everything.work_orders) == 4


def test_schedule_technician_mutates_graph(registry, graph):
    capability = registry.get("schedule_technician")
    output = capability.handler(
        graph,
        ScheduleTechnicianInput(
            work_order_id="wo-001", technician_id="tech-002", date="2026-08-20"
        ),
    )
    assert output.status == "scheduled"
    wo = graph.get("wo-001")
    assert wo.attr("status") == "scheduled"
    assigned = graph.related("wo-001", "assigned_to", direction="out")
    assert assigned[0].id == "tech-002"


def test_schedule_rejects_closed_work_order(registry, graph):
    capability = registry.get("schedule_technician")
    with pytest.raises(CapabilityError, match="cannot schedule"):
        capability.handler(
            graph,
            ScheduleTechnicianInput(
                work_order_id="wo-004", technician_id="tech-001", date="2026-08-20"
            ),
        )


def test_draft_invoice_creates_entity_and_relation(registry, graph):
    capability = registry.get("draft_invoice")
    before = len(graph.of_type("invoice"))
    output = capability.handler(graph, DraftInvoiceInput(work_order_id="wo-001", amount=240.0))
    assert output.status == "draft"
    assert len(graph.of_type("invoice")) == before + 1
    billed = graph.related(output.invoice_id, "bills", direction="out")
    assert billed[0].id == "wo-001"


def test_send_notification_is_a_mock(registry, graph):
    capability = registry.get("send_notification")
    output = capability.handler(
        graph, SendNotificationInput(customer_id="cust-001", message="hello")
    )
    assert output.transport == "mock"
    assert output.delivered is False
    assert output.recipient == "ops@harbourbakery.example"
