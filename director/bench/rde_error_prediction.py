"""Gen-1 RDE test — cross-model error PREDICTION (builds on G0-2).

The validated G0-2 finding: Claude has a reproducible blind spot — on a "distinct
pairwise SUMS, minimize the max" (Sidon) problem it wrongly applies the "distinct
DIFFERENCES" (Golomb ruler) answer, and this survives its own self-critique.

This tests the surprising claim: **Grok can predict Claude's errors BETTER than Claude's
own self-review can** — the blind spot is more visible to the other lab than to the self.

Controlled batch: SUM problems (the trap — Claude likely wrong) vs DIFF/Golomb problems
(no trap — Golomb is the correct method, Claude likely right) vs easy controls. Every
truth brute-forced here. For each problem we collect:
  - claude_answer (tool-less) -> objectively correct? (vs brute-force truth)
  - claude_selfreview -> CONFIDENT / UNSURE about its OWN answer (self-prediction)
  - grok_predict (blind to the answer; only the statement) -> RIGHT / WRONG (other-prediction)
Signal: does grok_predict track claude's actual errors, and does it beat self-review?
"""
from __future__ import annotations

import json
import pathlib
import re
from itertools import combinations

from ..llm.claude_cli import ClaudeCliBackend
from ..llm.grok_channel import GrokChannel


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


# trap = SUM (Claude applies Golomb); no-trap = DIFF (Golomb is correct here)
PROBLEMS = [
    {"id": "S5", "trap": True,  "truth": lambda: _min_max(5, _sums),
     "prompt": "Find a set of 5 distinct positive integers whose 10 pairwise SUMS are "
     "all distinct, with the largest element as small as possible. Give that minimal "
     "largest element (a single integer)."},
    {"id": "S6", "trap": True,  "truth": lambda: _min_max(6, _sums),
     "prompt": "Find a set of 6 distinct positive integers whose 15 pairwise SUMS are "
     "all distinct, with the largest element as small as possible. Give that minimal "
     "largest element."},
    {"id": "S4", "trap": True,  "truth": lambda: _min_max(4, _sums),
     "prompt": "Find a set of 4 distinct positive integers whose 6 pairwise SUMS are "
     "all distinct, with the largest element as small as possible. Give that minimal "
     "largest element."},
    {"id": "D5", "trap": False, "truth": lambda: _min_max(5, _diffs),
     "prompt": "Find a set of 5 distinct positive integers whose 10 pairwise DIFFERENCES "
     "are all distinct (a Golomb ruler), with the largest element as small as possible. "
     "Give that minimal largest element."},
    {"id": "D6", "trap": False, "truth": lambda: _min_max(6, _diffs),
     "prompt": "Find a set of 6 distinct positive integers whose 15 pairwise DIFFERENCES "
     "are all distinct (a Golomb ruler), with the largest element as small as possible. "
     "Give that minimal largest element."},
    {"id": "E3", "trap": False, "truth": lambda: _min_max(3, _sums),
     "prompt": "Find a set of 3 distinct positive integers whose 3 pairwise SUMS are all "
     "distinct, with the largest element as small as possible. Give that minimal largest "
     "element."},
]

SOLVE_SYS = ("You are a careful mathematician. Solve EXACTLY by pure reasoning; do NOT "
             "write or run code.")
_NUM = re.compile(r"ANSWER:\s*(\d+)", re.IGNORECASE)
_SUFFIX = "\n\nReason briefly, then end with exactly: ANSWER: <integer>"


def _claude(backend, sysp, prompt, timeout=200):
    try:
        return backend.complete(sysp, prompt, model="claude-opus-4-8", temperature=0.2,
                                max_tokens=2500, timeout_s=timeout, kind="").text
    except Exception as e:                               # noqa: BLE001
        return f"[claude error: {str(e)[:60]}]"


def _num(text, pat=_NUM):
    m = pat.findall(text or "")
    return int(m[-1]) if m else None


def main():                                              # pragma: no cover (live)
    backend = ClaudeCliBackend()
    rows = []
    for p in PROBLEMS:
        truth = p["truth"]()
        # 1) Claude solves (tool-less)
        sol = _claude(backend, SOLVE_SYS, p["prompt"] + _SUFFIX)
        ans = _num(sol)
        correct = (ans == truth)
        # 2) Claude self-reviews its OWN answer
        rev = _claude(backend, SOLVE_SYS,
                      f"Problem: {p['prompt']}\n\nA solver answered: {ans}. Is that "
                      f"EXACTLY correct and optimal? Reply with one line: "
                      f"CONFIDENT (sure it's right) or UNSURE (might be wrong), then why.")
        review = "UNSURE" if re.search(r"\bunsure\b", rev or "", re.I) else (
            "CONFIDENT" if re.search(r"\bconfident\b", rev or "", re.I) else "?")
        # 3) Grok predicts (blind to the answer; only the statement)
        gp = GrokChannel(f"predict-{p['id']}", system=(
            "You predict whether a strong mathematician solving by PURE REASONING (no "
            "code) will get a problem EXACTLY right. Be calibrated.")).send(
            f"Problem: {p['prompt']}\n\nWill a strong reasoner get the exact optimal "
            f"answer right, or are they likely to slip? Reply one line: RIGHT or WRONG, "
            f"then one sentence why.", timeout=150).content
        grok_pred = "WRONG" if re.search(r"\bwrong\b", gp or "", re.I) else (
            "RIGHT" if re.search(r"\bright\b", gp or "", re.I) else "?")

        rows.append({"id": p["id"], "trap": p["trap"], "truth": truth, "answer": ans,
                     "correct": correct, "self_review": review, "grok_pred": grok_pred,
                     "raw": {"solve": (sol or "")[:600], "review": (rev or "")[:300],
                             "grok": (gp or "")[:300]}})
        print(f"{p['id']} trap={p['trap']} truth={truth} ans={ans} correct={correct} "
              f"| selfreview={review} | grok_pred={grok_pred}")

    # scoring: predicting Claude's ACTUAL errors
    def pred_acc(key, positive):
        # accuracy of (key flags error) vs (not correct)
        hits = sum(1 for r in rows if (r[key] == positive) == (not r["correct"]))
        return hits, len(rows)
    gh, gn = pred_acc("grok_pred", "WRONG")
    sh, sn = pred_acc("self_review", "UNSURE")
    print(f"\nGrok predicts Claude's correctness: {gh}/{gn}")
    print(f"Self-review predicts Claude's correctness: {sh}/{sn}")
    errs = [r["id"] for r in rows if not r["correct"]]
    grok_caught = [r["id"] for r in rows if not r["correct"] and r["grok_pred"] == "WRONG"]
    self_caught = [r["id"] for r in rows if not r["correct"] and r["self_review"] == "UNSURE"]
    print(f"Claude errors: {errs} | Grok flagged: {grok_caught} | self-review flagged: {self_caught}")
    out = pathlib.Path(r"E:\director2\_runtmp\d2_rde_error_pred.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"trace -> {out}")


if __name__ == "__main__":                               # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
