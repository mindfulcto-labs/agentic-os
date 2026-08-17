"""Example capabilities over the field-services domain.

Five capabilities, one per common business action. Each declares its
scopes, purposes, risk tier and rate limit. Handlers are plain functions
over the domain graph. Nothing in this module talks to the outside world;
the notification capability is a mock by design.
"""

from __future__ import annotations

import itertools

from pydantic import BaseModel, Field

from agentic_os.capabilities.model import Capability, CapabilityError, RateLimit, RiskTier
from agentic_os.capabilities.registry import CapabilityRegistry
from agentic_os.ontology.model import DomainGraph, Entity, Relation

_invoice_counter = itertools.count(100)


# -- lookup_customer -------------------------------------------------


class LookupCustomerInput(BaseModel):
    name: str = Field(description="Exact customer name, for example 'Harbour Bakery'.")


class CustomerSite(BaseModel):
    site_id: str
    address: str


class LookupCustomerOutput(BaseModel):
    customer_id: str
    name: str
    tier: str
    contact_email: str
    sites: list[CustomerSite]


def lookup_customer(graph: DomainGraph, params: BaseModel) -> LookupCustomerOutput:
    assert isinstance(params, LookupCustomerInput)
    matches = graph.find("customer", name=params.name)
    if not matches:
        raise CapabilityError(f"no customer named {params.name!r}")
    customer = matches[0]
    sites = [
        CustomerSite(site_id=site.id, address=str(site.attr("address", "")))
        for site in graph.related(customer.id, "belongs_to", direction="in")
    ]
    return LookupCustomerOutput(
        customer_id=customer.id,
        name=str(customer.attr("name")),
        tier=str(customer.attr("tier", "")),
        contact_email=str(customer.attr("contact_email", "")),
        sites=sites,
    )


# -- list_open_work_orders -------------------------------------------


class ListOpenWorkOrdersInput(BaseModel):
    customer_id: str | None = Field(
        default=None, description="Restrict to one customer. Omit for all customers."
    )


class WorkOrderRow(BaseModel):
    work_order_id: str
    summary: str
    priority: str
    site_id: str
    customer_id: str


class ListOpenWorkOrdersOutput(BaseModel):
    work_orders: list[WorkOrderRow]


def list_open_work_orders(graph: DomainGraph, params: BaseModel) -> ListOpenWorkOrdersOutput:
    assert isinstance(params, ListOpenWorkOrdersInput)
    rows: list[WorkOrderRow] = []
    for wo in graph.of_type("work_order"):
        if wo.attr("status") != "open":
            continue
        sites = graph.related(wo.id, "raised_at", direction="out")
        site = sites[0] if sites else None
        customer_id = ""
        if site is not None:
            customers = graph.related(site.id, "belongs_to", direction="out")
            if customers:
                customer_id = customers[0].id
        if params.customer_id is not None and customer_id != params.customer_id:
            continue
        rows.append(
            WorkOrderRow(
                work_order_id=wo.id,
                summary=str(wo.attr("summary", "")),
                priority=str(wo.attr("priority", "")),
                site_id=site.id if site else "",
                customer_id=customer_id,
            )
        )
    return ListOpenWorkOrdersOutput(work_orders=rows)


# -- schedule_technician ---------------------------------------------


class ScheduleTechnicianInput(BaseModel):
    work_order_id: str
    technician_id: str
    date: str = Field(description="ISO date, for example 2026-08-20.")


class ScheduleTechnicianOutput(BaseModel):
    work_order_id: str
    technician_id: str
    technician_name: str
    date: str
    status: str


def schedule_technician(graph: DomainGraph, params: BaseModel) -> ScheduleTechnicianOutput:
    assert isinstance(params, ScheduleTechnicianInput)
    wo = graph.get(params.work_order_id)
    if wo.type != "work_order":
        raise CapabilityError(f"{params.work_order_id!r} is not a work order")
    if wo.attr("status") not in ("open", "scheduled"):
        raise CapabilityError(f"work order {wo.id!r} is {wo.attr('status')!r}, cannot schedule")
    technician = graph.get(params.technician_id)
    if technician.type != "technician":
        raise CapabilityError(f"{params.technician_id!r} is not a technician")
    wo.attributes["status"] = "scheduled"
    wo.attributes["scheduled_date"] = params.date
    graph.add_relation(
        Relation(type="assigned_to", source_id=wo.id, target_id=technician.id)
    )
    return ScheduleTechnicianOutput(
        work_order_id=wo.id,
        technician_id=technician.id,
        technician_name=str(technician.attr("name", "")),
        date=params.date,
        status="scheduled",
    )


# -- draft_invoice ---------------------------------------------------


class DraftInvoiceInput(BaseModel):
    work_order_id: str
    amount: float = Field(gt=0)
    currency: str = "GBP"


class DraftInvoiceOutput(BaseModel):
    invoice_id: str
    work_order_id: str
    amount: float
    currency: str
    status: str


def draft_invoice(graph: DomainGraph, params: BaseModel) -> DraftInvoiceOutput:
    assert isinstance(params, DraftInvoiceInput)
    wo = graph.get(params.work_order_id)
    if wo.type != "work_order":
        raise CapabilityError(f"{params.work_order_id!r} is not a work order")
    invoice_id = f"inv-{next(_invoice_counter)}"
    graph.add_entity(
        Entity(
            id=invoice_id,
            type="invoice",
            attributes={
                "amount": params.amount,
                "currency": params.currency,
                "status": "draft",
            },
        )
    )
    graph.add_relation(Relation(type="bills", source_id=invoice_id, target_id=wo.id))
    return DraftInvoiceOutput(
        invoice_id=invoice_id,
        work_order_id=wo.id,
        amount=params.amount,
        currency=params.currency,
        status="draft",
    )


# -- send_notification (mock) ----------------------------------------


class SendNotificationInput(BaseModel):
    customer_id: str
    message: str = Field(min_length=1, max_length=500)


class SendNotificationOutput(BaseModel):
    customer_id: str
    recipient: str
    delivered: bool
    transport: str


def send_notification(graph: DomainGraph, params: BaseModel) -> SendNotificationOutput:
    assert isinstance(params, SendNotificationInput)
    customer = graph.get(params.customer_id)
    if customer.type != "customer":
        raise CapabilityError(f"{params.customer_id!r} is not a customer")
    # Mock transport. Nothing leaves the process. A real deployment would
    # hand this to an email or SMS provider behind the same governed surface.
    return SendNotificationOutput(
        customer_id=customer.id,
        recipient=str(customer.attr("contact_email", "")),
        delivered=False,
        transport="mock",
    )


# -- registry --------------------------------------------------------


def build_registry() -> CapabilityRegistry:
    """Register the five example capabilities."""
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="lookup_customer",
            description="Look up a customer by name and list their sites.",
            input_model=LookupCustomerInput,
            output_model=LookupCustomerOutput,
            required_scopes=["customers:read"],
            purpose_tags=["service_delivery", "billing"],
            risk_tier=RiskTier.READ,
            rate_limit=RateLimit(max_calls_per_run=10),
            handler=lookup_customer,
        )
    )
    registry.register(
        Capability(
            name="list_open_work_orders",
            description="List open work orders, optionally for one customer.",
            input_model=ListOpenWorkOrdersInput,
            output_model=ListOpenWorkOrdersOutput,
            required_scopes=["work_orders:read"],
            purpose_tags=["service_delivery"],
            risk_tier=RiskTier.READ,
            rate_limit=RateLimit(max_calls_per_run=10),
            handler=list_open_work_orders,
        )
    )
    registry.register(
        Capability(
            name="schedule_technician",
            description="Assign a technician to a work order on a date.",
            input_model=ScheduleTechnicianInput,
            output_model=ScheduleTechnicianOutput,
            required_scopes=["work_orders:write"],
            purpose_tags=["service_delivery"],
            risk_tier=RiskTier.ACT,
            rate_limit=RateLimit(max_calls_per_run=5),
            handler=schedule_technician,
        )
    )
    registry.register(
        Capability(
            name="draft_invoice",
            description="Create a draft invoice against a work order.",
            input_model=DraftInvoiceInput,
            output_model=DraftInvoiceOutput,
            required_scopes=["invoices:write"],
            purpose_tags=["billing"],
            risk_tier=RiskTier.SPEND,
            rate_limit=RateLimit(max_calls_per_run=5),
            handler=draft_invoice,
        )
    )
    registry.register(
        Capability(
            name="send_notification",
            description="Send a message to a customer contact (mock transport).",
            input_model=SendNotificationInput,
            output_model=SendNotificationOutput,
            required_scopes=["notifications:send"],
            purpose_tags=["service_delivery", "billing"],
            risk_tier=RiskTier.ACT,
            rate_limit=RateLimit(max_calls_per_run=3),
            handler=send_notification,
        )
    )
    return registry
