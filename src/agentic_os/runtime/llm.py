"""LLM planner adapters for OpenAI and Anthropic.

Both adapters ask the model for a JSON plan against the capability
catalogue and the domain summary. They use the standard library HTTP
client, so the package has no provider SDK dependency. Everything else
in this repository runs offline; these adapters are the only code that
talks to a network, and only when an API key is present.
"""

from __future__ import annotations

import json
import os
import urllib.request

from agentic_os.runtime.planner import Plan, PlannedStep, PlanningContext


class LLMPlannerError(Exception):
    pass


PLAN_INSTRUCTIONS = """\
You plan work for a governed business agent. You cannot execute anything.
Propose a short plan as JSON with this shape:
{"steps": [{"capability": "...", "purpose": "...", "params": {...}, "rationale": "..."}]}

Rules:
- Only use capabilities from the catalogue below.
- Each step's purpose must be one of that capability's purpose_tags.
- Params must match the capability's input schema.
- Prefer read capabilities first to ground the plan.
- Return JSON only, no prose.
"""


def _build_prompt(goal: str, context: PlanningContext) -> str:
    catalogue = json.dumps(context.capability_catalogue, indent=2)
    return (
        f"{PLAN_INSTRUCTIONS}\n"
        f"Domain:\n{context.domain_summary}\n\n"
        f"Capability catalogue:\n{catalogue}\n\n"
        f"Working memory:\n{context.working_memory}\n\n"
        f"Goal: {goal}\n"
    )


def _parse_plan(goal: str, planner_name: str, text: str) -> Plan:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMPlannerError(f"model did not return valid JSON: {exc}") from exc
    steps = [PlannedStep.model_validate(step) for step in data.get("steps", [])]
    if not steps:
        raise LLMPlannerError("model returned an empty plan")
    return Plan(goal=goal, planner=planner_name, steps=steps)


def _post_json(url: str, headers: dict[str, str], payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAIPlanner:
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", timeout: float = 60.0) -> None:
        self.model = model
        self.timeout = timeout
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise LLMPlannerError("OPENAI_API_KEY is not set")

    def plan(self, goal: str, context: PlanningContext) -> Plan:
        body = _post_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "messages": [{"role": "user", "content": _build_prompt(goal, context)}],
                "temperature": 0,
            },
            self.timeout,
        )
        text = body["choices"][0]["message"]["content"]
        return _parse_plan(goal, self.name, text)


class AnthropicPlanner:
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-5", timeout: float = 60.0) -> None:
        self.model = model
        self.timeout = timeout
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise LLMPlannerError("ANTHROPIC_API_KEY is not set")

    def plan(self, goal: str, context: PlanningContext) -> Plan:
        body = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": _build_prompt(goal, context)}],
            },
            self.timeout,
        )
        text = "".join(
            block.get("text", "") for block in body.get("content", []) if block["type"] == "text"
        )
        return _parse_plan(goal, self.name, text)


def planner_from_environment():
    """Pick an LLM planner from available API keys. Anthropic wins ties."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicPlanner()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIPlanner()
    raise LLMPlannerError(
        "no API key found: set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        "or use 'agentic-os demo' which runs offline"
    )
