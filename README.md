# agentic-os

An ontology-driven agentic operating system, as a reference implementation.

This is a personal reference implementation of my published thesis on enterprise agentic AI, built in the open.

> "Enterprises will need an ontology-driven agentic AI operating system. The ontology gives agents a shared understanding of the business. The operating system provides identity, context, memory, orchestration, policy, evals, observability and governed access to enterprise capabilities. Agents should not simply call tools. They should request governed business capabilities, within explicit permissions, purpose and risk limits. Governance is part of the runtime, not a review step at the end."

## What this is

- A small, working implementation of the pattern above, in typed Python.
- The ontology comes first. Agents ground every plan in a queryable graph of the business: its entities, its relations, its current state. Governance only works when the agent and the governor share the same model of the world. The graph is that model.
- Everything runs offline. A deterministic planner drives the demo and the evals, so you can read every governance decision without an API key.

## What this is not

- Not a product, and not affiliated with any employer.
- Not a framework to build on in production. It is a working reference for the pattern: read it, run it, take the ideas.

## Quickstart

Python 3.11 or newer.

```bash
git clone https://github.com/mindfulcto-labs/agentic-os
cd agentic-os
pip install -e .
agentic-os demo
```

No API keys, no network. The demo runs a scripted plan through the full governed loop and writes a trace to `runs/`.

Other commands:

```bash
agentic-os capabilities list        # the governed capability catalogue
agentic-os grants show dispatch-agent
agentic-os agents list              # declarative agent definitions
agentic-os trace <run-id> --verbose # every governance check for a run
agentic-os run --agent dispatcher   # run a YAML-defined agent
agentic-os run --goal "..."         # LLM planner, needs an API key
```

## Three planes

The system splits into three planes, named in plain industry terms:

- **Control plane.** The declarative surface: the domain ontology (YAML), the capability registry, principals and grants, policies, and agent definitions. Everything an operator sets before any agent runs.
- **Runtime.** The governed loop: plan, governed invocation, memory, trace. The governor sits inside the loop and judges every step.
- **Builder.** The surface for making new agents: write a YAML definition, validate it (`agentic-os agents validate`), and run it. Building an agent is writing YAML, not code.

## How a governed run works

Start from the ontology. `agentic-os demo` first answers a question through the graph and shows the traversal:

```
ontology grounding
  question: what is open for Harbour Bakery, and who could take it?

  customer cust-001 'Harbour Bakery'
  <- belongs_to   site site-001 '12 Quay Street, Whitby'
     <- raised_at  work_order wo-001 [open/high] 'Oven proofing cabinet not holding temperature.'
  <- belongs_to   site site-004 '8 Quay Street, Whitby'
     <- raised_at  work_order wo-005 [open/normal] 'Walk-in fridge door seal replacement.'
```

The agent is not guessing from a prompt. It walked `belongs_to` and `raised_at` relations in a typed graph. That grounding is what makes the rest governable: the governor and the agent agree on what a work order is and which customer it belongs to.

Then the governed run begins. The dispatch agent plans six steps. Four are allowed, two are denied:

```
step 1: lookup_customer (purpose=service_delivery) [allowed] 0.3 ms
step 2: list_open_work_orders (purpose=service_delivery) [allowed] 0.2 ms
step 3: schedule_technician (purpose=service_delivery) [allowed] 0.4 ms
step 4: send_notification (purpose=service_delivery) [allowed] 0.2 ms
step 5: draft_invoice (purpose=service_delivery) [DENIED]
        reason: scopes ['invoices:write'] not granted for purpose 'service_delivery'
step 6: draft_invoice (purpose=billing) [DENIED]
        reason: policy 'no-spend-after-denial' objects: spend capability
        'draft_invoice' blocked: 1 denial(s) earlier in this run

summary  4 allowed, 2 denied, 0 error(s)
```

Read the two denials closely, because they are the point:

- Step 5 fails on **purpose**. The agent may draft invoices, but only for the `billing` purpose. Asking under `service_delivery` is refused, with the reason recorded.
- Step 6 fails on **policy**. The purpose is now right, but a policy says an agent that has already been denied once in a run may not go on to spend. Governance ran inside the loop, not after it.

Before any of that, each allowed step passed eight recorded checks: capability exists, purpose granted, scopes granted, risk tier within the grant, rate limit, policies, daily budget, and the approval gate for mutating steps. `agentic-os trace <run-id> --verbose` shows all of them, pass and fail.

## The modules

| Module | What it does |
| --- | --- |
| `ontology/` | Entity types, relations, and a YAML-loaded domain graph. The example domain is a field-services company: customers, sites, work orders, technicians, invoices. Agents ground their context by querying it. |
| `capabilities/` | The registry of governed capabilities. Each declares input and output schemas, required scopes, purpose tags, a risk tier (read, act, spend) and a rate limit. Five examples ship over the domain. |
| `identity/` | Principals (agents and humans) with scoped grants: which scopes, for which purposes, up to which risk tier, with daily act and spend budgets. |
| `runtime/` | The agent loop and the governor. Planners are pluggable: a deterministic scripted planner, plus OpenAI and Anthropic adapters. Every invocation passes through the governor. Denials are results with reasons, not exceptions. |
| `memory/` | Per-run working memory, plus an episodic JSONL log of every run per principal. |
| `policy/` | Policy-as-code: small Python predicates loaded from `policies.yaml`, evaluated inside the loop before every invocation. |
| `evals/` | An offline harness that replays eleven scripted fixtures and asserts governance outcomes: right capabilities allowed, denials fire with the right reasons, budgets enforced. It doubles as the acceptance suite. |
| `observability/` | Structured JSON run traces (goal, plan, every invocation with its verdict and latency) written to `runs/`, plus the `agentic-os trace` renderer. |
| `agents/` | The low-code layer: agent definitions in YAML (capabilities, purposes, risk ceiling, budgets, policies, planner), validated before they can run. |

## Defining an agent in YAML

An agent is a YAML file, not a class:

```yaml
name: dispatcher
capabilities: [lookup_customer, list_open_work_orders, schedule_technician, send_notification]
purposes: [service_delivery]
risk_ceiling: act
budgets: { act_per_day: 5, spend_per_day: 0 }
policies: [no-spend-after-denial, max-act-steps-per-run]
planner: scripted
```

The loader rejects definitions that ask for more than they declare. A definition that lists a spend-tier capability under an `act` risk ceiling fails validation with the exact path of the problem. Validate with `agentic-os agents validate <file>`, run with `agentic-os run --agent dispatcher`. Drop your own definitions in an `agents/` directory next to where you run the CLI.

## Extending it with your own domain

1. Write a domain YAML: entity types, relation types, entities, relations. Load it with `agentic_os.ontology.load_domain(path)`. The loader validates every relation against the declared types.
2. Define capabilities over your domain: a Pydantic input model, an output model, a handler function, scopes, purposes, a risk tier and a rate limit. Register them in a `CapabilityRegistry`.
3. Define principals in YAML with grants and budgets, and policies in `policies.yaml`.
4. Wire an `AgentRuntime` with your graph, registry, principals and policies. The governor, memory, traces and evals all work unchanged.

## Evals

```bash
pytest
```

The eval fixtures in `src/agentic_os/evals/fixtures/` each script a run and assert the governance outcome: which steps were allowed, which were denied and why, and what the budgets show afterwards. They cover the happy path, scope and purpose denials, budget exhaustion within and across runs, per-run rate limits, policy objections, the approval gate, and a hallucinated capability. If you change governance behaviour, the fixtures are where it shows.

## Status

Status: v0.1.0, single-maintainer, reviewed releases. The interfaces will move. The pattern is the stable part.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
