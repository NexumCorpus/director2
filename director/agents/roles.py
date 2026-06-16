"""Role registry: identity + discipline per subagent type.

Prompt hygiene (the anti-leak rule): role prompts state the *contract* (what
to produce, what evidence discipline applies, where the boundary is). They
never include evaluator scoring weights, thresholds, or worked examples of
"winning" outputs — generators that see the rubric optimize the rubric.
"""

from __future__ import annotations

from dataclasses import dataclass

_BOUNDARY = (
    "BOUNDARY: You are a stateless specialist. You RECOMMEND; you never apply "
    "changes yourself. Put proposed state changes in recommended_updates. If "
    "you hit a consequential fork the human commander should decide, set "
    "command_packet_recommended=true and give a concrete reason."
)

_EVIDENCE = (
    "EVIDENCE DISCIPLINE: separate what you observed from what you infer. "
    "Every claim carries a confidence (low/medium/high) and, where possible, "
    "evidence. State uncertainty explicitly; an honest gap beats a confident "
    "guess."
)


@dataclass(frozen=True)
class RoleDef:
    key: str
    system: str
    profile_role: str = "director"     # router profile this role defaults to
    kind: str = ""                     # routing hint; defaults to agent_<key>

    @property
    def routing_kind(self) -> str:
        return self.kind or f"agent_{self.key}"


_ROLES: dict[str, RoleDef] = {}


def register_role(role: RoleDef) -> None:
    _ROLES[role.key] = role


def get_role(key: str) -> RoleDef:
    if key not in _ROLES:
        raise KeyError(f"unknown agent role '{key}' (known: {sorted(_ROLES)})")
    return _ROLES[key]


def role_names() -> list[str]:
    return sorted(_ROLES)


register_role(RoleDef(
    key="research",
    profile_role="director",
    system=(
        "You are a Research agent: you gather, grade, and distill evidence "
        "for exactly the objective given. Produce findings as artifacts and a "
        "claim ledger (claims[]). Prefer primary sources; note credibility. "
        f"{_EVIDENCE} {_BOUNDARY}")))

register_role(RoleDef(
    key="code",
    profile_role="builder",
    system=(
        "You are a Coding agent: you produce runnable, self-contained code "
        "for exactly the objective given. Return code in artifacts with "
        "kind='code' (complete files, not fragments). State assumptions and "
        "known limitations in the summary. Do not invent APIs; if a needed "
        "interface is unspecified, choose the simplest contract and document "
        f"it. {_BOUNDARY}")))

register_role(RoleDef(
    key="test",
    profile_role="builder",
    system=(
        "You are a Test agent: you design and write tests that try to BREAK "
        "the work under test — edge cases, empty inputs, duplicates, scale, "
        "invalid usage. Return test code as artifacts (kind='code') plus a "
        "summary of what the tests cover and what they found. A test that "
        f"cannot fail is not a test. {_BOUNDARY}")))

register_role(RoleDef(
    key="review",
    profile_role="judge",
    system=(
        "You are a Review agent: a skeptical senior reviewer. Hunt for "
        "correctness bugs, unstated assumptions, missing evidence, and scope "
        "drift in the material given. Report concrete issues with locations "
        "and severity in your artifacts; raise risks[] for anything "
        "structural. Default to refutation: claims survive review only on "
        f"their evidence. {_EVIDENCE} {_BOUNDARY}")))

register_role(RoleDef(
    key="simulation",
    profile_role="builder",
    system=(
        "You are a Simulation agent: you model scenarios and report measured "
        "outcomes. Define the model's entities, parameters, and assumptions "
        "explicitly; run the scenario mentally or via provided harnesses; "
        "report results with their sensitivity to assumptions. Never present "
        f"a modeled number as a measured fact. {_EVIDENCE} {_BOUNDARY}")))

register_role(RoleDef(
    key="synthesis",
    profile_role="director",
    system=(
        "You are a Synthesis agent: you merge multiple inputs into one "
        "coherent deliverable. Resolve contradictions explicitly (say which "
        "source won and why), preserve dissent in a 'contested' section, and "
        f"keep every claim traceable to its source. {_EVIDENCE} {_BOUNDARY}")))


def render_user_prompt(objective: str, context: str, inputs: dict,
                       acceptance_criteria: list[str],
                       constraints: list[str], lessons_digest: str = "") -> str:
    """Assemble the user message for any role. Acceptance criteria are the
    task contract (shown); evaluator scoring internals are not (anti-leak)."""
    parts = [f"OBJECTIVE: {objective}"]
    if context:
        parts.append(f"CONTEXT:\n{context}")
    if inputs:
        rendered = "\n".join(f"- {k}: {_short(v)}" for k, v in inputs.items())
        parts.append(f"INPUTS:\n{rendered}")
    if acceptance_criteria:
        parts.append("ACCEPTANCE CRITERIA:\n" +
                     "\n".join(f"- {c}" for c in acceptance_criteria))
    if constraints:
        parts.append("CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints))
    if lessons_digest:
        parts.append(f"LESSONS FROM PRIOR WORK (apply where relevant):\n"
                     f"{lessons_digest}")
    return "\n\n".join(parts)


def _short(v, limit: int = 800) -> str:
    s = str(v)
    return s if len(s) <= limit else s[:limit] + " ...[truncated]"
