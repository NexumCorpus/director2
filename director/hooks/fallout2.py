"""Fallout 2 — Wasteland Renaissance modding hook.

Reactive dialogue trees and quest scaffolds as structured JSON, with trusted
graph validators: the LLM writes the creative content, deterministic code
proves the graph is sound (reachable, no dangling jumps, conditions over
declared state variables). The JSON is engine-agnostic by design;
:mod:`director.hooks.fallout2_ssl` compiles validated trees to sfall-ready
``.ssl`` + ``.msg`` sources (`director hooks fo2-compile`).

Dialogue JSON contract:
{
  "npc": "name",
  "variables": {"player_karma": "int", "quest_stage_x": "int", ...},
  "entry": "start",
  "nodes": {
     "<node_id>": {
        "text": "what the NPC says",
        "conditions": ["player_karma >= 10", ...],     # optional gate to enter
        "responses": [
           {"text": "player line", "goto": "<node_id>|end",
            "conditions": [...], "effects": ["quest_stage_x = 2", ...]}
        ]
     }, ...
}

Quest JSON contract:
{
  "id": "quest_x", "name": "...", "variables": {...}, "entry": "stage_1",
  "stages": {"<stage_id>": {"description": "...",
                            "objectives": ["..."],
                            "transitions": [{"to": "<stage_id>|complete|fail",
                                             "when": ["cond", ...]}]}}
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.types import Severity, VerificationReport, VerifyAction
from .base import register_hook

_COND_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|>=|<=|>|<)\s*(-?\w+)\s*$")
_EFFECT_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=|\+=|-=)\s*(-?\w+)\s*$")

_TERMINAL_DIALOGUE = {"end", "exit", "combat", "barter"}
_TERMINAL_QUEST = {"complete", "fail"}


# --------------------------------------------------------------------------- #
# Trusted validators
# --------------------------------------------------------------------------- #

def _check_conditions(conds, variables: dict, where: str,
                      problems: list[str]) -> None:
    for c in conds or []:
        m = _COND_RE.match(str(c))
        if not m:
            problems.append(f"{where}: unparseable condition '{c}'")
        elif m.group(1) not in variables:
            problems.append(f"{where}: condition uses undeclared variable "
                            f"'{m.group(1)}'")


def validate_dialogue(tree: dict) -> list[str]:
    """Return problems (empty == valid). Trusted graph checks only — no
    judgment about writing quality."""
    problems: list[str] = []
    if not isinstance(tree, dict):
        return ["dialogue is not an object"]
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return ["dialogue has no nodes"]
    variables = tree.get("variables") or {}
    entry = tree.get("entry", "start")
    if entry not in nodes:
        problems.append(f"entry node '{entry}' does not exist")

    for nid, node in nodes.items():
        if not str(node.get("text", "")).strip():
            problems.append(f"node '{nid}': empty text")
        _check_conditions(node.get("conditions"), variables,
                          f"node '{nid}'", problems)
        responses = node.get("responses") or []
        for i, r in enumerate(responses):
            where = f"node '{nid}' response[{i}]"
            if not str(r.get("text", "")).strip():
                problems.append(f"{where}: empty text")
            goto = str(r.get("goto", ""))
            if goto not in nodes and goto not in _TERMINAL_DIALOGUE:
                problems.append(f"{where}: dangling goto '{goto}'")
            _check_conditions(r.get("conditions"), variables, where, problems)
            for e in r.get("effects") or []:
                m = _EFFECT_RE.match(str(e))
                if not m:
                    problems.append(f"{where}: unparseable effect '{e}'")
                elif m.group(1) not in variables:
                    problems.append(f"{where}: effect writes undeclared "
                                    f"variable '{m.group(1)}'")

    # reachability from entry
    if entry in nodes:
        seen = set()
        stack = [entry]
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in nodes:
                continue
            seen.add(cur)
            for r in nodes[cur].get("responses") or []:
                stack.append(str(r.get("goto", "")))
        unreachable = sorted(set(nodes) - seen)
        if unreachable:
            problems.append(f"unreachable nodes: {unreachable}")
        # a node with no responses must be intentional-terminal; flag it
        for nid in seen:
            if not (nodes[nid].get("responses") or []):
                problems.append(f"node '{nid}': no responses (dead end - "
                                f"route to a terminal like 'end' instead)")
    return problems


def validate_quest(quest: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(quest, dict):
        return ["quest is not an object"]
    stages = quest.get("stages")
    if not isinstance(stages, dict) or not stages:
        return ["quest has no stages"]
    variables = quest.get("variables") or {}
    entry = quest.get("entry", "")
    if entry not in stages:
        problems.append(f"entry stage '{entry}' does not exist")
    for sid, stage in stages.items():
        if not str(stage.get("description", "")).strip():
            problems.append(f"stage '{sid}': empty description")
        transitions = stage.get("transitions") or []
        for i, t in enumerate(transitions):
            to = str(t.get("to", ""))
            if to not in stages and to not in _TERMINAL_QUEST:
                problems.append(f"stage '{sid}' transition[{i}]: dangling "
                                f"target '{to}'")
            _check_conditions(t.get("when"), variables,
                              f"stage '{sid}' transition[{i}]", problems)
    if entry in stages:
        seen = set()
        stack = [entry]
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in stages:
                continue
            seen.add(cur)
            for t in stages[cur].get("transitions") or []:
                stack.append(str(t.get("to", "")))
        unreachable = sorted(set(stages) - seen)
        if unreachable:
            problems.append(f"unreachable stages: {unreachable}")
        terminal_reachable = any(
            str(t.get("to")) in _TERMINAL_QUEST
            for sid in seen for t in stages[sid].get("transitions") or [])
        if not terminal_reachable:
            problems.append("no path reaches a terminal (complete/fail)")
    return problems


# --------------------------------------------------------------------------- #
# Verifiers (wrap validators for the registry)
# --------------------------------------------------------------------------- #

class _JsonGraphVerifier:
    """Verifies agent outputs whose artifacts carry dialogue/quest JSON."""
    name = "fo2_graphs"

    def verify(self, target, context=None) -> VerificationReport:
        problems: list[str] = []
        checked = 0
        artifacts = (target or {}).get("artifacts", []) \
            if isinstance(target, dict) else []
        for a in artifacts:
            if not isinstance(a, dict):
                continue
            kind = str(a.get("kind", ""))
            if kind not in ("dialogue", "quest"):
                continue
            checked += 1
            try:
                data = json.loads(str(a.get("content", "")))
            except json.JSONDecodeError as exc:
                problems.append(f"artifact '{a.get('title')}': not JSON ({exc})")
                continue
            validator = validate_dialogue if kind == "dialogue" else validate_quest
            problems.extend(f"artifact '{a.get('title')}': {p}"
                            for p in validator(data))
        if checked == 0:
            return VerificationReport(
                verifier=self.name, passed=True, score=3.0,
                severity=Severity.INFO, action=VerifyAction.LOG_ONLY,
                issues=["no dialogue/quest artifacts to verify"])
        passed = not problems
        return VerificationReport(
            verifier=self.name, passed=passed,
            score=5.0 if passed else 2.0,
            severity=Severity.INFO if passed else Severity.MAJOR,
            action=VerifyAction.AUTO_APPROVE if passed
            else VerifyAction.REQUIRE_HUMAN_REVIEW,
            issues=problems[:12],
            details={"artifacts_checked": checked})


# --------------------------------------------------------------------------- #
# Scaffolds
# --------------------------------------------------------------------------- #

EXAMPLE_DIALOGUE = {
    "npc": "Mara the Scavenger",
    "variables": {"player_karma": "int", "wr_mara_quest": "int",
                  "player_has_parts": "int"},
    "entry": "start",
    "nodes": {
        "start": {
            "text": "You're not from the caravan. What do you want?",
            "responses": [
                {"text": "Just passing through.", "goto": "end"},
                {"text": "I hear you need salvage parts.",
                 "goto": "quest_intro",
                 "conditions": ["wr_mara_quest == 0"]},
                {"text": "I have your parts.", "goto": "quest_turnin",
                 "conditions": ["wr_mara_quest == 1",
                                "player_has_parts >= 3"]},
            ],
        },
        "quest_intro": {
            "text": "My water purifier died. Three condenser parts and "
                    "it hums again. The old factory crawls with geckos.",
            "responses": [
                {"text": "I'll find them.", "goto": "end",
                 "effects": ["wr_mara_quest = 1"]},
                {"text": "Not my problem.", "goto": "end",
                 "effects": ["player_karma -= 1"]},
            ],
        },
        "quest_turnin": {
            "text": "These are perfect. The settlement drinks clean tonight "
                    "because of you.",
            "responses": [
                {"text": "Glad to help.", "goto": "end",
                 "effects": ["wr_mara_quest = 2", "player_karma += 2",
                             "player_has_parts -= 3"]},
            ],
        },
    },
}

EXAMPLE_QUEST = {
    "id": "wr_purifier", "name": "Clean Water for the Renaissance",
    "variables": {"wr_mara_quest": "int", "player_has_parts": "int"},
    "entry": "find_parts",
    "stages": {
        "find_parts": {
            "description": "Recover 3 condenser parts from the gecko-infested "
                           "factory.",
            "objectives": ["Collect condenser parts (3)"],
            "transitions": [{"to": "return_to_mara",
                             "when": ["player_has_parts >= 3"]}],
        },
        "return_to_mara": {
            "description": "Bring the parts back to Mara.",
            "objectives": ["Talk to Mara"],
            "transitions": [{"to": "complete", "when": ["wr_mara_quest == 2"]}],
        },
    },
}


class Fallout2Hook:
    name = "fallout2_wr"
    description = ("Fallout 2 'Wasteland Renaissance' modding: reactive "
                   "dialogue trees, quest scaffolds, and systems design with "
                   "trusted graph validation.")

    def task_templates(self) -> list[dict]:
        return [
            {"title": "Define NPC roster and reactivity matrix",
             "role": "research",
             "objective": "Define the NPCs in scope and the world-state "
                          "variables (karma, reputation, quest stages) their "
                          "dialogue reacts to. Produce a reactivity matrix "
                          "artifact mapping variables to NPC behaviors.",
             "acceptance_criteria": ["every NPC lists reactive variables",
                                     "variables have types and ranges"]},
            {"title": "Author reactive dialogue trees", "role": "code",
             "depends_on_index": [0],
             "objective": "Write dialogue trees as JSON (kind='dialogue') per "
                          "the contract: nodes, conditioned responses, "
                          "effects on declared variables. Every branch must "
                          "route to a terminal.",
             "acceptance_criteria": ["valid per fo2_graphs verifier",
                                     "reactive conditions on 2+ variables"],
             "verifiers": ["fo2_graphs"],
             "context": "Dialogue JSON contract:\n" +
                        json.dumps(EXAMPLE_DIALOGUE, indent=1)[:1500]},
            {"title": "Author quest scaffolds", "role": "code",
             "depends_on_index": [0],
             "objective": "Write quest scaffolds as JSON (kind='quest'): "
                          "stages, objectives, conditioned transitions to "
                          "complete/fail.",
             "acceptance_criteria": ["valid per fo2_graphs verifier"],
             "verifiers": ["fo2_graphs"],
             "context": "Quest JSON contract:\n" +
                        json.dumps(EXAMPLE_QUEST, indent=1)[:1200]},
            {"title": "Reactivity review pass", "role": "review",
             "depends_on_index": [1, 2],
             "objective": "Review dialogue and quests for reactivity gaps: "
                          "states with no reactive response, contradictory "
                          "effects, missing failure paths."},
        ]

    def verifiers(self) -> dict:
        return {"fo2_graphs": _JsonGraphVerifier}

    def scaffold(self, target_dir, **params) -> list[Path]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        out = []
        for fname, data in (("dialogue.mara.json", EXAMPLE_DIALOGUE),
                            ("quest.purifier.json", EXAMPLE_QUEST)):
            p = target / fname
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            out.append(p)
        # compiled sfall sources for the example content
        from .fallout2_ssl import compile_quest_header, compile_to_files
        out.extend(compile_to_files(EXAMPLE_DIALOGUE, target))
        qh = target / "quest.purifier.h"
        qh.write_text(compile_quest_header(EXAMPLE_QUEST), encoding="utf-8")
        out.append(qh)
        readme = target / "README-fallout2-wr.md"
        readme.write_text(
            "# Wasteland Renaissance content pack\n\n"
            "Generated by Director 2.0 `fallout2_wr` hook.\n\n"
            "- `dialogue.*.json` — reactive dialogue trees "
            "(validated: reachability, dangling gotos, declared variables)\n"
            "- `quest.*.json` — quest stage graphs (validated: terminal "
            "reachability)\n"
            "- `*.ssl` + `*.msg` — compiled sfall sources for the dialogue "
            "(state in sfall globals; fix the TODO include paths for your "
            "mod tree)\n"
            "- `quest.*.h` — quest state-machine header (sfall global keys "
            "+ stage graph)\n\n"
            "Recompile after editing JSON: "
            "`director hooks fo2-compile dialogue.mara.json`\n",
            encoding="utf-8")
        out.append(readme)
        return out


register_hook(Fallout2Hook)
