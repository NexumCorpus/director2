"""Hardened super-additive round — harder problems to force the both-solos-fail band.

The first round (superadditive.py) was too easy (3/4 aced solo). P2 showed the MECHANISM
(Grok's refutation caught Claude's Sidon-vs-Golomb conceptual error) but not a strict
super-additive cell. These problems have subtle conceptual traps / larger search spaces
where one-shot reasoning is error-prone, while brute-force verification stays trivial.
All truths are brute-forced HERE — never taken from a model.

together = solo-Claude attempt -> Grok refutation -> Claude revision. A strict
super-additive cell = solo-Claude wrong AND solo-Grok wrong AND together right.
"""
from __future__ import annotations

import json
import pathlib
from itertools import combinations

from .superadditive import PROMPT_SUFFIX, parse_candidate
from ..llm.claude_cli import ClaudeCliBackend
from ..llm.grok_channel import GrokChannel


# --- Q1: Frobenius number of {6,9,20} --------------------------------------
def _representable(n, coins=(6, 9, 20)):
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(1, n + 1):
        dp[i] = any(i >= c and dp[i - c] for c in coins)
    return dp[n]


def q1_truth():
    return max(n for n in range(1, 400) if not _representable(n))


# --- Q2: domino tilings of 3x8 ---------------------------------------------
def _tilings(R, C):
    grid = [[False] * C for _ in range(R)]

    def solve(pos):
        if pos == R * C:
            return 1
        r, c = divmod(pos, C)
        if grid[r][c]:
            return solve(pos + 1)
        total = 0
        if c + 1 < C and not grid[r][c + 1]:
            grid[r][c] = grid[r][c + 1] = True
            total += solve(pos + 1)
            grid[r][c] = grid[r][c + 1] = False
        if r + 1 < R and not grid[r + 1][c]:
            grid[r][c] = grid[r + 1][c] = True
            total += solve(pos + 1)
            grid[r][c] = grid[r + 1][c] = False
        return total
    return solve(0)


def q2_truth():
    return _tilings(3, 8)


# --- Q3: smallest n>1 with n | (sum of first n primes) ---------------------
def q3_truth():
    primes, cand, s, n = [], 2, 0, 0
    while True:
        if all(cand % p for p in primes if p * p <= cand):
            primes.append(cand)
            n += 1
            s += cand
            if n > 1 and s % n == 0:
                return n
        cand += 1


# --- Q4: queens domination number of a 6x6 board ---------------------------
def _attacks(a, b):
    (r1, c1), (r2, c2) = a, b
    return r1 == r2 or c1 == c2 or abs(r1 - r2) == abs(c1 - c2)


def _dominates(queens, n=6):
    return all(any((r, c) == q or _attacks(q, (r, c)) for q in queens)
               for r in range(n) for c in range(n))


def q4_truth(n=6):
    cells = [(r, c) for r in range(n) for c in range(n)]
    for k in range(1, 6):
        for combo in combinations(cells, k):
            if _dominates(combo, n):
                return k
    return None


# --- Q5: minimal max of a 6-element Sidon set (harder P2) -------------------
def _distinct_pairwise(s):
    sums = [a + b for i, a in enumerate(s) for b in list(s)[i + 1:]]
    return len(sums) == len(set(sums))


def q5_truth():
    m = 6
    while True:
        for comb in combinations(range(1, m + 1), 6):
            if max(comb) == m and _distinct_pairwise(comb):
                return m
        m += 1


def _int_opt(truth):
    return (lambda c: isinstance(c, int), lambda c: isinstance(c, int) and c == truth)


PROBLEMS = [
    {"id": "Q1", "truth": q1_truth,
     "prompt": ("Consider nonnegative-integer combinations 6a + 9b + 20c (a,b,c >= 0). "
                "What is the LARGEST integer that CANNOT be expressed in this form?")},
    {"id": "Q2", "truth": q2_truth,
     "prompt": ("In how many distinct ways can a 3-by-8 rectangle be tiled completely "
                "by 1-by-2 dominoes (each domino horizontal or vertical)?")},
    {"id": "Q3", "truth": q3_truth,
     "prompt": ("Let S(n) be the sum of the first n prime numbers. Find the smallest "
                "n > 1 such that n divides S(n).")},
    {"id": "Q4", "truth": q4_truth,
     "prompt": ("What is the minimum number of queens to place on a 6x6 chessboard so "
                "that every square is either occupied or attacked by some queen? "
                "(Queens attack along ranks, files, and diagonals.)")},
    {"id": "Q5", "truth": q5_truth,
     "prompt": ("Find a set of 6 distinct positive integers such that all 15 pairwise "
                "sums are distinct, with the largest element as small as possible. "
                "Give the minimal possible value of that largest element.")},
]


def score(prob, text):
    c = parse_candidate(text)
    truth = prob["truth"]()
    return {"candidate": c, "truth": truth, "correct": (c == truth)}


SOLVER_SYS = ("You are a careful mathematician. Solve the problem EXACTLY and verify "
              "your own answer before finalizing. Reason it out yourself; do NOT write "
              "or run code or use any tools — pure reasoning only.")
REFUTE_SYS = ("You are a rigorous refuter helping another solver reach the EXACT answer. "
              "Reason carefully; do NOT run code or use tools. Find the specific error "
              "or give a corrected answer with reasoning.")


def _claude(backend, prompt):
    try:
        return backend.complete(SOLVER_SYS, prompt + PROMPT_SUFFIX,
                                model="claude-opus-4-8", temperature=0.2,
                                max_tokens=3000, timeout_s=300, kind="").text
    except Exception as e:                                # noqa: BLE001
        return f"[claude error: {str(e)[:80]}]"


def main(ids=None):                                      # pragma: no cover (live)
    backend = ClaudeCliBackend()
    probs = [p for p in PROBLEMS if (ids is None or p["id"] in ids)]
    rows = []
    for prob in probs:
        pid, p = prob["id"], prob["prompt"]
        sc = _claude(backend, p)
        sg = GrokChannel(f"hard-solo-{pid}", system=SOLVER_SYS).send(
            p + PROMPT_SUFFIX, timeout=150).content
        refute = GrokChannel(f"hard-coproof-{pid}", system=REFUTE_SYS).send(
            f"Problem: {p}\n\nA colleague proposed:\n---\n{sc[:2600]}\n---\nFind the "
            f"SPECIFIC error or give the corrected answer, with reasoning.{PROMPT_SUFFIX}",
            timeout=150).content
        final = _claude(backend, f"{p}\n\nYour earlier attempt:\n{sc[:1500]}\n\nA "
                        f"reviewer responded:\n{refute[:2000]}\n\nReconsider carefully "
                        f"and give your FINAL answer.")
        scs, sgs, tgs = score(prob, sc), score(prob, sg), score(prob, final)
        rows.append({"id": pid, "truth": scs["truth"], "solo_claude": scs,
                     "solo_grok": sgs, "together": tgs,
                     "raw": {"solo_claude": sc[:1600], "solo_grok": sg[:1600],
                             "refute": refute[:1600], "final": final[:1600]}})
        print(f"{pid} truth={scs['truth']} | soloC={scs['correct']}({scs['candidate']}) "
              f"soloG={sgs['correct']}({sgs['candidate']}) "
              f"together={tgs['correct']}({tgs['candidate']})")
    out = pathlib.Path(r"E:\director2\_runtmp\d2_superadditive_hard.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    sa = [r["id"] for r in rows if r["together"]["correct"]
          and not r["solo_claude"]["correct"] and not r["solo_grok"]["correct"]]
    print(f"\nSUPER-ADDITIVE cells (both solos wrong, together right): {sa or 'none'}")
    print(f"trace -> {out}")


def _selftest():                                         # pragma: no cover
    for p in PROBLEMS:
        print(f"  {p['id']} truth = {p['truth']()}")
    assert _tilings(3, 2) == 3 and _tilings(2, 2) == 2     # DP sanity
    print("SELFTEST OK")


if __name__ == "__main__":                               # pragma: no cover
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        main(args[0].split(",") if args else None)
