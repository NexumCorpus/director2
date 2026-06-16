"""Deterministic offline backend.

Two jobs:
1. Make the whole framework runnable (and testable) with zero API keys.
2. NEVER be mistaken for a real model — Director 1.0's worst dogfooding finding
   (F11) was mock output silently persisted as real. Every response is tagged
   ``backend="mock"`` and the router records + surfaces that tag.

Fixtures key on the ``kind`` hint and produce schema-valid JSON for every
structured flow in the framework. Pass ``scripts={kind: [text, ...]}`` to
override per-kind (each entry used once, in order; a callable receives
(system, user) and returns text).
"""

from __future__ import annotations

import json

from .base import LLMBackend, LLMResponse


def _plan_fixture(system: str, user: str) -> str:
    objective = ""
    for line in user.splitlines():
        if line.lower().startswith("objective:"):
            objective = line.split(":", 1)[1].strip()
            break
    objective = objective or "the stated objective"
    return json.dumps({
        "charter": {
            "objective": objective,
            "scope_in": ["core capability", "tests"],
            "scope_out": ["production deployment"],
            "success_criteria": ["all acceptance criteria verified",
                                 "tests pass"],
            "constraints": ["local execution"],
            "deliverables": ["working artifact", "report"],
            "risk_posture": "medium",
        },
        "modules": [
            {"name": "Research", "type": "research",
             "purpose": f"Gather evidence for: {objective}",
             "acceptance_criteria": ["sources graded", "claims extracted"]},
            {"name": "Build", "type": "implementation",
             "purpose": f"Implement: {objective}",
             "acceptance_criteria": ["code runs", "verified"]},
            {"name": "Validate", "type": "validation",
             "purpose": "Test and review the build",
             "acceptance_criteria": ["review passed"]},
        ],
        "tasks": [
            {"title": "Survey the territory", "role": "research",
             "module": "Research",
             "objective": f"Research the landscape for: {objective}",
             "acceptance_criteria": ["3+ findings"], "depends_on": []},
            {"title": "Build first cut", "role": "code", "module": "Build",
             "objective": f"Produce a working first implementation of: {objective}",
             "acceptance_criteria": ["artifact produced"],
             "depends_on": ["Survey the territory"]},
            {"title": "Test the build", "role": "test", "module": "Validate",
             "objective": "Write and run tests against the first cut",
             "acceptance_criteria": ["tests reported"],
             "depends_on": ["Build first cut"]},
            {"title": "Review the build", "role": "review", "module": "Validate",
             "objective": "Critically review the implementation",
             "acceptance_criteria": ["review verdict"],
             "depends_on": ["Build first cut"]},
        ],
        "milestones": [
            {"name": "M1: grounded plan", "tasks": ["Survey the territory"]},
            {"name": "M2: verified build",
             "tasks": ["Build first cut", "Test the build", "Review the build"]},
        ],
        "risks": [
            {"title": "Scope creep", "level": "medium",
             "description": "Objective may expand during build",
             "mitigation": "Charter scope_out enforced at coherence pass"},
        ],
    })


def _packet_fixture(system: str, user: str) -> str:
    return json.dumps({
        "title": "Choose the execution posture",
        "context": "The plan is ready; two materially different paths exist.",
        "options": [
            {"key": "A", "label": "Fast iteration",
             "description": "Smallest working slice first, broaden later.",
             "tradeoffs": ["earlier signal", "more rework risk"],
             "consequences": ["validation module starts later"],
             "risk_impact": "medium", "reversibility": "reversible",
             "state_delta": {"notes": ["posture: fast"]}},
            {"key": "B", "label": "High assurance",
             "description": "Verification-first; slower but sturdier.",
             "tradeoffs": ["later signal", "fewer surprises"],
             "consequences": ["build module starts later"],
             "risk_impact": "low", "reversibility": "reversible",
             "state_delta": {"notes": ["posture: assurance"]}},
        ],
        "recommendation_key": "A",
        "rationale": "Mock recommendation: bias to earliest grounded signal.",
        "risks": ["fixture-generated packet"],
        "default_if_deferred": "A",
    })


def _agent_fixture(role: str):
    def fx(system: str, user: str) -> str:
        body = {
            "summary": f"[mock:{role}] Completed the assigned objective with "
                       f"deterministic fixture output of sufficient length to "
                       f"exercise downstream evaluators and ingestion paths.",
            "artifacts": [{
                "title": f"{role} output",
                "kind": "code" if role == "code" else "markdown",
                "content": ("def solve(items, k):\n"
                            "    return sorted(items)[:k]\n")
                if role == "code" else
                f"# {role.title()} findings\n\n- Finding one with supporting "
                f"detail.\n- Finding two with supporting detail.\n- Sources: "
                f"fixture evidence ledger.\n",
            }],
            "claims": [{"text": "fixture claim", "confidence": "medium",
                        "evidence": "fixture"}] if role == "research" else [],
            "risks": [],
            "lessons": [f"{role} fixture lesson: deterministic paths simplify tests"],
            "command_packet_recommended": False,
            "command_packet_reason": "",
        }
        return json.dumps(body)
    return fx


def _builder_fixture(system: str, user: str) -> str:
    return json.dumps({
        "rationale": "Sorted-slice baseline: simple, correct reference point.",
        "algo_class": "sorted_slice",
        "code": "def solve(items, k):\n    return sorted(items)[:k]\n",
    })


def _adversary_fixture(system: str, user: str) -> str:
    return json.dumps({
        "findings": ["no confirmed break (fixture)"],
        "hostile_workload": {"name": "adversarial_duplicates", "n": 512,
                             "dist": "duplicates", "seed": 99},
        "rationale": "Duplicate-heavy stream stresses tie handling.",
    })


def _synth_fixture(system: str, user: str) -> str:
    return json.dumps({"action": "CONTINUE",
                       "reason": "fixture: keep exploring current class"})


def _mutation_fixture(system: str, user: str) -> str:
    return json.dumps({
        "name": "candidate",
        "new_version_text": "You are a precise agent. Return strict JSON only.",
        "rationale": "fixture mutation: tightened output contract",
        "expected_effect": "fewer parse failures",
    })


_FIXTURES = {
    "initial_plan": _plan_fixture,
    "command_packet": _packet_fixture,
    "agent_research": _agent_fixture("research"),
    "agent_code": _agent_fixture("code"),
    "agent_test": _agent_fixture("test"),
    "agent_review": _agent_fixture("review"),
    "agent_simulation": _agent_fixture("simulation"),
    "agent_synthesis": _agent_fixture("synthesis"),
    "builder_propose": _builder_fixture,
    "adversary_attack": _adversary_fixture,
    "synthesizer_decide": _synth_fixture,
    "prompt_mutation": _mutation_fixture,
}


class MockBackend(LLMBackend):
    name = "mock"
    default_model = "mock-deterministic"
    cheap_model = "mock-deterministic"

    def __init__(self, scripts: dict[str, list] | None = None):
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.calls: list[dict] = []          # inspection hook for tests

    def complete(self, system: str, user: str, *, model: str,
                 temperature: float, max_tokens: int, timeout_s: float,
                 kind: str = "") -> LLMResponse:
        self.calls.append({"kind": kind, "system": system, "user": user})
        text = None
        queue = self.scripts.get(kind)
        if queue:
            entry = queue.pop(0)
            text = entry(system, user) if callable(entry) else str(entry)
        elif kind in _FIXTURES:
            text = _FIXTURES[kind](system, user)
        else:
            text = json.dumps({"summary": f"[mock] no fixture for kind='{kind}'",
                               "echo": user[:200]})
        return LLMResponse(text=text, model=model or self.default_model,
                           backend=self.name,
                           prompt_tokens=len(system) // 4 + len(user) // 4,
                           completion_tokens=len(text) // 4,
                           latency_s=0.0)
