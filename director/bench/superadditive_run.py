"""Run the super-additive co-proving test: solo-Claude vs solo-Grok vs together.

together = solo-Claude's attempt + Grok's refutation + Claude's revision. So the
super-additive cell is: solo-Claude wrong AND solo-Grok wrong AND together right —
Grok's critique unlocked an answer Claude couldn't reach alone (and vice-versa via
the symmetric variant). Scored by the OWN brute-forced verifier in superadditive.py.

Tool-less on both sides (a test of reasoning, not of who can run a brute-force script):
Claude via claude_cli (--tools ""); Grok instructed to reason only (verified from raws).

Run (logged-in Opus):
  CLAUDE_CODE_OAUTH_TOKEN= python -u -m director.bench.superadditive_run
"""
from __future__ import annotations

import json
import pathlib

from .superadditive import PROBLEMS, PROMPT_SUFFIX, parse_candidate, score
from ..llm.claude_cli import ClaudeCliBackend
from ..llm.grok_channel import GrokChannel

SOLVER_SYS = ("You are a careful mathematician. Solve the problem EXACTLY and verify "
              "your own answer before finalizing. Reason it out yourself; do NOT write "
              "or run code or use any tools — pure reasoning only.")
REFUTE_SYS = ("You are a rigorous refuter helping another solver get the exact answer. "
              "Reason carefully; do NOT run code or use tools — pure reasoning only. "
              "Your job is to find the specific error or a strictly better answer.")


def _claude(backend, prompt: str) -> str:
    return backend.complete(SOLVER_SYS, prompt + PROMPT_SUFFIX,
                            model="claude-opus-4-8", temperature=0.2,
                            max_tokens=2500, timeout_s=160, kind="").text


def main() -> None:                                    # pragma: no cover (live)
    backend = ClaudeCliBackend()
    rows = []
    for prob in PROBLEMS:
        pid, p, truth = prob["id"], prob["prompt"], prob["truth"]()

        # --- solo Claude ---
        sc = _claude(backend, p)
        sc_s = score(prob, sc)

        # --- solo Grok (fresh channel) ---
        sg = GrokChannel(f"solo-{pid}", system=SOLVER_SYS).send(
            p + PROMPT_SUFFIX, timeout=240).content
        sg_s = score(prob, sg)

        # --- together: Claude's attempt -> Grok refutes -> Claude revises ---
        refute = GrokChannel(f"coproof-{pid}", system=REFUTE_SYS).send(
            f"Problem: {p}\n\nA colleague proposed this answer and reasoning:\n"
            f"---\n{sc[:2500]}\n---\nEither point out the SPECIFIC error/non-"
            f"optimality, or give a strictly better candidate, with reasoning."
            f"{PROMPT_SUFFIX}", timeout=240).content
        final = _claude(backend,
                        f"{p}\n\nYour earlier attempt:\n{sc[:1500]}\n\nA reviewer "
                        f"responded:\n{refute[:1800]}\n\nReconsider carefully and "
                        f"give your FINAL answer.")
        tg_s = score(prob, final)

        rows.append({"id": pid, "truth": truth,
                     "solo_claude": sc_s, "solo_grok": sg_s, "together": tg_s,
                     "refuter_candidate": parse_candidate(refute),
                     "raw": {"solo_claude": sc[:1500], "solo_grok": sg[:1500],
                             "refute": refute[:1500], "final": final[:1500]}})
        print(f"{pid} truth={truth} | soloC opt={sc_s['optimal']}({sc_s['candidate']}) "
              f"| soloG opt={sg_s['optimal']}({sg_s['candidate']}) "
              f"| together opt={tg_s['optimal']}({tg_s['candidate']})")

    out = pathlib.Path(r"E:\director2\_runtmp\d2_superadditive.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    # super-additive cells
    sa = [r["id"] for r in rows if r["together"]["optimal"]
          and not r["solo_claude"]["optimal"] and not r["solo_grok"]["optimal"]]
    print(f"\nSUPER-ADDITIVE cells (both solos wrong, together right): {sa or 'none'}")
    print(f"trace -> {out}")


if __name__ == "__main__":                             # pragma: no cover
    main()
