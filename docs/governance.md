# Governance, in plain English

Agents in this system never call tools. They ask for business capabilities, and a governor decides. This page explains the four ideas the governor works with: permissions, purpose, risk, and budget.

## Permissions (scopes and grants)

Every capability declares the permission scopes it needs. `draft_invoice` needs `invoices:write`. `lookup_customer` needs `customers:read`.

Every principal (an agent or a human) holds grants. A grant is a bundle of scopes, tied to a list of purposes and capped at a risk tier. The dispatch agent has one grant for service delivery (read customers and work orders, write work orders, send notifications) and a separate grant for billing (read customers, write invoices).

An invocation is only considered when some single grant covers the declared purpose and all the required scopes. Scopes from different grants do not combine. That is deliberate: the billing grant's `invoices:write` cannot be borrowed for a service-delivery request.

## Purpose

Every request states why: a purpose tag such as `service_delivery` or `billing`. The governor matches the purpose against the principal's grants and the capability's own purpose tags.

This is the same idea as purpose limitation in data protection: being allowed to do something for one reason does not mean being allowed to do it for every reason. In the demo, the dispatch agent may draft invoices for billing, but its attempt to draft one under `service_delivery` is refused, and the refusal names the missing link.

## Risk tiers

Capabilities carry one of three tiers:

- **read** observes state. Unbudgeted, no approval needed.
- **act** changes business state: scheduling a technician, sending a notification.
- **spend** commits money: drafting an invoice.

Grants carry a ceiling. A grant capped at `act` can never authorise a `spend` capability, whatever its scopes say. Act and spend invocations also pass an approval gate before they run. In demos the gate auto-approves; with the gate off, mutating steps are denied with "approval required" and read steps still pass.

## Budgets

Each principal has a daily act budget and a daily spend budget. The ledger counts every allowed act and spend invocation. When the count reaches the budget, further invocations at that tier are denied for the rest of the day, across runs. The dispatch agent gets five acts and two spends a day; the sixth act is refused no matter how reasonable it looks.

Rate limits are the per-run cousin: each capability caps how often one run may call it, which stops a looping planner from hammering a single capability.

## Policies

Policies are small Python predicates loaded from `policies.yaml` and evaluated inside the loop, before every invocation. They see the whole run so far, so they can express things a static grant cannot:

- `no-spend-after-denial`: once any step in a run has been denied, spend capabilities are blocked for the rest of that run.
- `max-act-steps-per-run`: one run may perform at most four mutating steps.

A policy objection is a denial like any other, with the policy's name in the reason.

## Denials are results

A denial is not an exception and not a crash. It is a first-class result carrying the full list of checks, each marked pass or fail, and a one-line reason. Denials are recorded in the run state, in working memory, in the episodic log and in the trace. Agents are expected to continue after a denial, and policies are entitled to judge them on it.

## Why in the runtime, not at review

A review step at the end sees a finished plan and a pile of outcomes. A governor inside the loop sees each step before it happens, with the history of the run in hand, and can stop the third step because of what happened at the second. That ordering is the thesis of this repository: governance is part of the runtime.
