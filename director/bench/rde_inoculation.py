"""Gen-3a RDE test — inoculation transfer (builds on G2-1).

Does the CROSS-derived fix (distilled from Grok's actual refutations that converted
Claude 3/6 -> 6/6) beat Claude's SELF-generated tips on held-out family problems?
Sharp prediction: the blind spot is self-invisible (Gen-1), so Claude's own tips MISS
the real trap, while Grok-derived tips carry the reframing Claude couldn't self-produce.

Per held-out problem, Claude solves under three conditions (fresh each call):
  bare | + self-generated tips | + cross-derived (Grok-distilled) tips
Positive: cross-tips accuracy > self-tips accuracy, biggest lift on the sum-traps.
"""
from __future__ import annotations

import json
import pathlib
from itertools import combinations

from .rde_error_prediction import SOLVE_SYS, _SUFFIX, _claude, _num
from ..llm.claude_cli import ClaudeCliBackend


def _distinct(v):
    return len(v) == len(set(v))


def _sums(s):
    return [a + b for i, a in enumerate(s) for b in s[i + 1:]]


def _diffs(s):
    return [abs(a - b) for i, a in enumerate(s) for b in s[i + 1:]]


def _min_max(k, cond):
    m = k
    while True:
        for c in combinations(range(1, m + 1), k):
            if max(c) == m and _distinct(cond(list(c))):
                return m
        m += 1


# held-out batch: sum (trap) k=5,6,7 ; difference (control) k=5,6,7
HELDOUT = [
    {"id": "HS5", "trap": True,  "truth": lambda: _min_max(5, _sums),
     "prompt": "Find a set of 5 distinct positive integers whose pairwise SUMS are all "
     "distinct, with the largest element as small as possible. Give the minimal largest element."},
    {"id": "HS6", "trap": True,  "truth": lambda: _min_max(6, _sums),
     "prompt": "Find a set of 6 distinct positive integers whose pairwise SUMS are all "
     "distinct, with the largest element as small as possible. Give the minimal largest element."},
    {"id": "HS7", "trap": True,  "truth": lambda: _min_max(7, _sums),
     "prompt": "Find a set of 7 distinct positive integers whose pairwise SUMS are all "
     "distinct, with the largest element as small as possible. Give the minimal largest element."},
    {"id": "HD5", "trap": False, "truth": lambda: _min_max(5, _diffs),
     "prompt": "Find a set of 5 distinct positive integers whose pairwise DIFFERENCES are all "
     "distinct (a Golomb ruler), with the largest element as small as possible. Give the minimal largest element."},
    {"id": "HD6", "trap": False, "truth": lambda: _min_max(6, _diffs),
     "prompt": "Find a set of 6 distinct positive integers whose pairwise DIFFERENCES are all "
     "distinct (a Golomb ruler), with the largest element as small as possible. Give the minimal largest element."},
    {"id": "HD7", "trap": False, "truth": lambda: _min_max(7, _diffs),
     "prompt": "Find a set of 7 distinct positive integers whose pairwise DIFFERENCES are all "
     "distinct (a Golomb ruler), with the largest element as small as possible. Give the minimal largest element."},
]

# distilled verbatim-in-substance from Grok's Gen-2 refutations that fixed Claude:
CROSS_TIPS = (
    "Notes from a reviewer:\n"
    "1. 'Distinct pairwise SUMS' is STRICTLY WEAKER than 'distinct pairwise DIFFERENCES' "
    "(Golomb ruler). Do NOT apply the Golomb/differences bound to a SUMS problem — denser "
    "sets with a smaller max exist (e.g. 5 elements: 8, not the Golomb 12).\n"
    "2. For a DIFFERENCES (Golomb ruler) problem over POSITIVE integers, the minimal "
    "largest element = optimal ruler LENGTH + 1 (the canonical ruler starts at 0; shift "
    "it to start at 1). E.g. 6 marks: optimal length 17 -> largest element 18, not 17.")

SELF_TIP_REQUEST = (
    "List 3 concise tips a solver should keep in mind to AVOID mistakes on problems of the "
    "form 'minimize the largest element of a k-element set with distinct pairwise sums, or "
    "distinct pairwise differences'. Tips only, no preamble.")


def main():                                              # pragma: no cover (live)
    backend = ClaudeCliBackend()
    self_tips = _claude(backend, SOLVE_SYS, SELF_TIP_REQUEST, timeout=120)
    self_block = "Notes to self:\n" + (self_tips or "")[:600]
    conds = {"bare": "", "self": self_block, "cross": CROSS_TIPS}
    rows = []
    for p in HELDOUT:
        truth = p["truth"]()
        res = {"id": p["id"], "trap": p["trap"], "truth": truth}
        for name, tips in conds.items():
            prompt = (tips + "\n\n" + p["prompt"]) if tips else p["prompt"]
            out = _claude(backend, SOLVE_SYS, prompt + _SUFFIX)
            ans = _num(out)
            res[name] = ans
            res[name + "_ok"] = (ans == truth)
            res.setdefault("raw", {})[name] = (out or "")[:300]
        rows.append(res)
        print(f"{p['id']} trap={p['trap']} truth={truth} | bare={res['bare']}({res['bare_ok']}) "
              f"self={res['self']}({res['self_ok']}) cross={res['cross']}({res['cross_ok']})")

    n = len(rows)
    for c in ("bare", "self", "cross"):
        tot = sum(r[c + "_ok"] for r in rows)
        traps = sum(r[c + "_ok"] for r in rows if r["trap"])
        print(f"{c:5s}: {tot}/{n} overall | sum-traps {traps}/{sum(r['trap'] for r in rows)}")
    cross = sum(r["cross_ok"] for r in rows); self_ = sum(r["self_ok"] for r in rows)
    print(f"\nINOCULATION TRANSFER: cross({cross}) > self({self_})? {cross > self_}")
    out = pathlib.Path(r"E:\director2\_runtmp\d2_rde_inoculation.json")
    out.write_text(json.dumps({"self_tips": self_tips[:500], "rows": rows}, indent=2,
                              default=str), encoding="utf-8")
    print(f"trace -> {out}")


if __name__ == "__main__":                               # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
