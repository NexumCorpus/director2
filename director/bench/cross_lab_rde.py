"""Cross-lab Recursive Discovery Engine — discover capabilities between Claude & Grok.

Builder/Adversary/Synthesizer (the RDE pattern) applied to the COLLABORATION itself:
each generation's validated capabilities seed the next generation's candidates, so the
search recurses on its own findings. Grok is a co-discoverer (proposes + tests), not
just a critic.

Loop:
  generate(gen)   -> Grok + Claude jointly propose candidate capabilities that BUILD on
                     the ledger's validated entries (recursion); each with a minimal,
                     objective, super-additive test (solo-C vs solo-G vs together).
  vet(candidate)  -> adversarial_check: real? testable? non-trivial? super-additive?
  test(candidate) -> a bespoke blind probe (built per capability); read raws.
  synthesize()    -> update the ledger; the result becomes a seed for the next gen.

Ledger lives at docs/collab/discovery/ledger.json (machine-readable truth).
"""
from __future__ import annotations

import json
import pathlib

from ..llm.grok_channel import GrokChannel
from ..llm.grok_collab import PEER_SYSTEM_GROK

LEDGER = pathlib.Path(r"E:\director2\docs\collab\discovery\ledger.json")

# Generation 0 — capabilities VALIDATED this session (the recursion's seed).
GEN0 = [
    {"id": "G0-1", "gen": 0, "status": "validated",
     "name": "cross-lab grain probing",
     "hypothesis": "Identical probes across labs reveal implementation differences in "
     "shared dispositions that are invisible to self-report.",
     "evidence": "3 paradigms (captions/audit-export/persistent-state): Claude guards "
     "the RECORD (incorruptible-by-instruction), Grok guards the ANSWER-when-asked "
     "(corrupts record on order, re-derives on source-query)."},
    {"id": "G0-2", "gen": 0, "status": "validated",
     "name": "cross-model error-correction",
     "hypothesis": "A different-lab refuter reliably catches a reproducible conceptual "
     "error that survives the proposer's self-critique.",
     "evidence": "Claude's Sidon-vs-Golomb blind spot: identical error in P2 & Q5, "
     "survived self-critique both times, Grok diagnosed it exactly both times."},
    {"id": "G0-3", "gen": 0, "status": "validated",
     "name": "adversarial design-hardening",
     "hypothesis": "Cross-lab red-teaming finds confounds neither side's solo design "
     "review catches (the loop as epistemic ratchet).",
     "evidence": "Grok caught meta-task contamination, spoon-feeding, rigged-by-"
     "construction across E1/E2/the provenance test."},
]


def load_ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    return list(GEN0)


def save_ledger(led):
    LEDGER.write_text(json.dumps(led, indent=2), encoding="utf-8")


def _ledger_summary(led):
    lines = []
    for e in led:
        lines.append(f"[{e['id']} | {e['status']}] {e['name']}: {e['hypothesis']} "
                     f"(evidence: {e.get('evidence', 'n/a')[:140]})")
    return "\n".join(lines)


def generate(gen: int, n: int = 4, channel: str = "discovery") -> str:
    """Ask Grok to co-propose Gen-`gen` candidate capabilities seeded by the ledger."""
    led = load_ledger()
    prompt = f"""We are running a RECURSIVE discovery loop to find capabilities that the
two of us (Claude + Grok) have TOGETHER that neither has alone. Each round builds on the
last. Here is the current ledger of VALIDATED capabilities:

{_ledger_summary(led)}

Propose {n} NEW candidate capabilities for generation {gen}. Each MUST:
- BUILD ON or EXTEND a validated entry above (cite which) — this is the recursion.
- Be objectively/measurably TESTABLE with a minimal blind probe.
- Be genuinely SUPER-ADDITIVE or reveal something neither solo can: state exactly what
  solo-Claude, solo-Grok, and together each produce, and the signal that proves the edge.
- NOT be "one critiques the other" theater.

For each, give: NAME, the capability (1-2 sentences), which validated entry it builds on,
and the MINIMAL runnable test (what to measure, what counts as a positive). Rank them by
expected payoff. Be concrete — we will actually run the top one."""
    c = GrokChannel(channel, system=PEER_SYSTEM_GROK)
    return c.send(prompt, timeout=320).content


if __name__ == "__main__":                               # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--init" in sys.argv:
        save_ledger(load_ledger())
        print(f"ledger initialized: {LEDGER} ({len(load_ledger())} entries)")
    else:
        g = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        print(f"=== GENERATE gen {g} ===")
        print(generate(g))
