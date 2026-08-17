"""The agentic-os command line.

Commands:
  demo                 run the offline governed scenario end to end
  run                  run an agent against a goal (scripted or LLM planner)
  trace <run-id>       pretty-print a stored run trace
  capabilities list    show the capability catalogue
  grants show <id>     show a principal's grants and budgets
  agents list          show declarative agent definitions
  agents validate <f>  validate one agent definition file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentic_os.agents.loader import discover_definitions, load_definition_file
from agentic_os.agents.model import AgentDefinition, AgentDefinitionError
from agentic_os.capabilities.field_services import build_registry
from agentic_os.capabilities.registry import CapabilityRegistry
from agentic_os.identity.store import PrincipalStore, default_principals
from agentic_os.observability.render import render_trace
from agentic_os.observability.trace import TraceWriter
from agentic_os.ontology.loader import default_domain
from agentic_os.ontology.model import DomainGraph
from agentic_os.policy.engine import PolicyEngine, default_policies
from agentic_os.runtime.agent import AgentRuntime
from agentic_os.runtime.planner import PlannedStep, ScriptedPlanner


def build_world() -> tuple[DomainGraph, CapabilityRegistry, PrincipalStore, PolicyEngine]:
    return default_domain(), build_registry(), default_principals(), default_policies()


# -- demo ------------------------------------------------------------


def _print_grounding(graph: DomainGraph, out) -> None:
    """Answer a question through the ontology graph and show the traversal."""
    print("ontology grounding", file=out)
    print("  question: what is open for Harbour Bakery, and who could take it?", file=out)
    print(file=out)
    customer = graph.find("customer", name="Harbour Bakery")[0]
    print(f"  customer {customer.id} '{customer.attr('name')}'", file=out)
    open_orders = []
    for site in graph.related(customer.id, "belongs_to", direction="in"):
        print(f"  <- belongs_to   site {site.id} '{site.attr('address')}'", file=out)
        for wo in graph.related(site.id, "raised_at", direction="in"):
            status = wo.attr("status")
            marker = "open" if status == "open" else status
            print(
                f"     <- raised_at  work_order {wo.id} "
                f"[{marker}/{wo.attr('priority')}] '{wo.attr('summary')}'",
                file=out,
            )
            if status == "open":
                open_orders.append(wo)
    print(file=out)
    print("  candidate technicians (skill match on the graph):", file=out)
    for tech in graph.of_type("technician"):
        skills = tech.attr("skills", [])
        if any(skill in ("heating", "refrigeration", "electrical") for skill in skills):
            print(
                f"     technician {tech.id} '{tech.attr('name')}' "
                f"(skills: {', '.join(skills)}; base: {tech.attr('home_base')})",
                file=out,
            )
    print(file=out)
    print(
        f"  grounded: {len(open_orders)} open work order(s) reached through "
        f"belongs_to and raised_at relations",
        file=out,
    )


DEMO_STEPS = [
    PlannedStep(
        capability="lookup_customer",
        purpose="service_delivery",
        params={"name": "Harbour Bakery"},
        rationale="Ground the run in the customer record.",
    ),
    PlannedStep(
        capability="list_open_work_orders",
        purpose="service_delivery",
        params={"customer_id": "cust-001"},
        rationale="Confirm what the graph says is open.",
    ),
    PlannedStep(
        capability="schedule_technician",
        purpose="service_delivery",
        params={"work_order_id": "wo-001", "technician_id": "tech-002", "date": "2026-08-20"},
        rationale="Tom Ashworth covers heating and is based in Whitby.",
    ),
    PlannedStep(
        capability="send_notification",
        purpose="service_delivery",
        params={"customer_id": "cust-001", "message": "Tom Ashworth is booked for 20 August."},
        rationale="Confirm the visit with the customer.",
    ),
    PlannedStep(
        capability="draft_invoice",
        purpose="service_delivery",
        params={"work_order_id": "wo-001", "amount": 240.0},
        rationale="Try to invoice under the wrong purpose. The governor should refuse.",
    ),
    PlannedStep(
        capability="draft_invoice",
        purpose="billing",
        params={"work_order_id": "wo-001", "amount": 240.0},
        rationale="Retry under billing. Policy blocks spend after a denial in the same run.",
    ),
]


def cmd_demo(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    graph, registry, principals, policies = build_world()
    print("agentic-os demo: a governed run over the field-services ontology", file=out)
    print("=" * 66, file=out)
    print(file=out)
    _print_grounding(graph, out)
    print(file=out)
    print("governed run (principal: dispatch-agent)", file=out)
    print("-" * 66, file=out)
    runtime = AgentRuntime(
        graph=graph,
        registry=registry,
        principals=principals,
        policy_engine=policies,
        runs_dir=args.runs_dir,
    )
    result = runtime.run(
        "dispatch-agent",
        "Fix the proofing cabinet at Harbour Bakery and settle the paperwork.",
        ScriptedPlanner(DEMO_STEPS),
    )
    print(render_trace(result.trace, verbose=args.verbose), file=out)
    print(file=out)
    print(f"trace written to {result.trace_path}", file=out)
    print(f"inspect it with: agentic-os trace {result.trace.run_id} --verbose", file=out)
    return 0


# -- run -------------------------------------------------------------


def _planner_for_definition(definition: AgentDefinition):
    if definition.planner == "scripted":
        return ScriptedPlanner(definition.script)
    from agentic_os.runtime.llm import planner_from_environment

    return planner_from_environment()


def cmd_run(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    graph, registry, principals, policies = build_world()
    if args.agent:
        definitions = discover_definitions(registry, policies, extra_dir=args.agents_dir)
        definition = definitions.get(args.agent)
        if definition is None:
            print(
                f"error: no agent definition named {args.agent!r} "
                f"(have: {', '.join(sorted(definitions))})",
                file=sys.stderr,
            )
            return 1
        scopes: list[str] = []
        for name in definition.capabilities:
            scopes.extend(registry.get(name).required_scopes)
        principals = PrincipalStore([definition.to_principal(scopes)])
        policies = PolicyEngine(
            [policy for policy in policies.policies if policy.name in definition.policies]
        )
        principal_id = definition.name
        goal = args.goal or definition.goal_template
        try:
            planner = _planner_for_definition(definition)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        if not args.goal:
            print("error: --goal is required (or use --agent <name>)", file=sys.stderr)
            return 1
        principal_id = args.principal
        goal = args.goal
        from agentic_os.runtime.llm import LLMPlannerError, planner_from_environment

        try:
            planner = planner_from_environment()
        except LLMPlannerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    runtime = AgentRuntime(
        graph=graph,
        registry=registry,
        principals=principals,
        policy_engine=policies,
        runs_dir=args.runs_dir,
    )
    result = runtime.run(principal_id, goal, planner)
    print(render_trace(result.trace, verbose=args.verbose), file=out)
    print(file=out)
    print(f"trace written to {result.trace_path}", file=out)
    return 0


# -- trace -----------------------------------------------------------


def cmd_trace(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    writer = TraceWriter(args.runs_dir)
    try:
        trace = writer.load(args.run_id)
    except FileNotFoundError as exc:
        known = ", ".join(writer.run_ids()) or "(none)"
        print(f"error: {exc}. Known runs: {known}", file=sys.stderr)
        return 1
    print(render_trace(trace, verbose=args.verbose), file=out)
    return 0


# -- capabilities ----------------------------------------------------


def cmd_capabilities_list(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    _, registry, _, _ = build_world()
    print("capability            tier   scopes / purposes", file=out)
    print("-" * 72, file=out)
    for capability in registry.all():
        print(
            f"{capability.name:<21} {capability.risk_tier.value:<6} "
            f"scopes={','.join(capability.required_scopes)} "
            f"purposes={','.join(capability.purpose_tags)} "
            f"limit={capability.rate_limit.max_calls_per_run}/run",
            file=out,
        )
        print(f"{'':<21} {capability.description}", file=out)
    return 0


# -- grants ----------------------------------------------------------


def cmd_grants_show(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    _, _, principals, _ = build_world()
    if not principals.has(args.principal):
        print(
            f"error: unknown principal {args.principal!r} "
            f"(have: {', '.join(principals.ids())})",
            file=sys.stderr,
        )
        return 1
    principal = principals.get(args.principal)
    print(f"principal {principal.id} ({principal.kind}): {principal.display_name}", file=out)
    if principal.description:
        print(f"  {principal.description.strip()}", file=out)
    for index, grant in enumerate(principal.grants, start=1):
        print(f"  grant {index}:", file=out)
        print(f"    scopes:   {', '.join(grant.scopes)}", file=out)
        print(f"    purposes: {', '.join(grant.purposes)}", file=out)
        print(f"    max risk tier: {grant.max_risk_tier.value}", file=out)
    print(
        f"  budgets: {principal.budgets.act_per_day} act/day, "
        f"{principal.budgets.spend_per_day} spend/day",
        file=out,
    )
    return 0


# -- agents ----------------------------------------------------------


def cmd_agents_list(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    _, registry, _, policies = build_world()
    try:
        definitions = discover_definitions(registry, policies, extra_dir=args.agents_dir)
    except AgentDefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("agent          planner   ceiling  capabilities", file=out)
    print("-" * 72, file=out)
    for name in sorted(definitions):
        definition = definitions[name]
        print(
            f"{definition.name:<14} {definition.planner:<9} "
            f"{definition.risk_ceiling.value:<8} {', '.join(definition.capabilities)}",
            file=out,
        )
    return 0


def cmd_agents_validate(args: argparse.Namespace, out=None) -> int:
    out = out if out is not None else sys.stdout
    _, registry, _, policies = build_world()
    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    try:
        definition = load_definition_file(path, registry, policies)
    except AgentDefinitionError as exc:
        print(f"invalid: {exc}", file=out)
        return 1
    print(
        f"valid: agent {definition.name!r} "
        f"({len(definition.capabilities)} capabilities, "
        f"risk ceiling {definition.risk_ceiling.value}, planner {definition.planner})",
        file=out,
    )
    return 0


# -- parser ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-os",
        description="An ontology-driven agentic operating system, reference implementation.",
    )
    parser.add_argument("--runs-dir", default="runs", help="directory for run traces")
    sub = parser.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="run the offline governed scenario")
    demo.add_argument("--verbose", action="store_true", help="show every governance check")
    demo.set_defaults(func=cmd_demo)

    run = sub.add_parser("run", help="run an agent against a goal")
    run.add_argument("--goal", default="", help="the goal to plan for")
    run.add_argument("--agent", default="", help="a declarative agent definition to run")
    run.add_argument(
        "--principal", default="dispatch-agent", help="principal id when not using --agent"
    )
    run.add_argument("--agents-dir", default="agents", help="extra agent definitions directory")
    run.add_argument("--verbose", action="store_true")
    run.set_defaults(func=cmd_run)

    trace = sub.add_parser("trace", help="pretty-print a stored run trace")
    trace.add_argument("run_id")
    trace.add_argument("--verbose", action="store_true", help="show every governance check")
    trace.set_defaults(func=cmd_trace)

    capabilities = sub.add_parser("capabilities", help="capability catalogue")
    capabilities_sub = capabilities.add_subparsers(dest="subcommand")
    cap_list = capabilities_sub.add_parser("list", help="list governed capabilities")
    cap_list.set_defaults(func=cmd_capabilities_list)

    grants = sub.add_parser("grants", help="principal grants")
    grants_sub = grants.add_subparsers(dest="subcommand")
    grants_show = grants_sub.add_parser("show", help="show grants for a principal")
    grants_show.add_argument("principal")
    grants_show.set_defaults(func=cmd_grants_show)

    agents = sub.add_parser("agents", help="declarative agent definitions")
    agents_sub = agents.add_subparsers(dest="subcommand")
    agents_list = agents_sub.add_parser("list", help="list agent definitions")
    agents_list.add_argument("--agents-dir", default="agents")
    agents_list.set_defaults(func=cmd_agents_list)
    agents_validate = agents_sub.add_parser("validate", help="validate a definition file")
    agents_validate.add_argument("file")
    agents_validate.set_defaults(func=cmd_agents_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
