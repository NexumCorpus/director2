"""Super-additive collaboration test — does Claude+Grok beat Claude-alone AND Grok-alone?

Adversarial co-proving on small construction problems with an OBJECTIVE verifier. The
super-additive signature: cells where solo-Claude is wrong AND solo-Grok is wrong but
the joint (propose <-> refute) product is correct — a result neither model produced
alone, certified by a binary/optimality check, not by interpreting transcripts.

Rigor: the verifier and every true answer are computed HERE by brute force — NOT taken
from either model (an experiment about whether *we* are super-additive cannot trust a
participant's answer key; that's the grounding norm this whole program studies).

Problems are minimality/constraint-satisfaction tasks: trivial to brute-force-verify,
but error-prone for one-shot LLM reasoning (subtle non-minimality, CRT slips, etc.).
"""
from __future__ import annotations

import ast
import itertools
import re


# --- helpers ---------------------------------------------------------------
def _numdiv(n: int) -> int:
    return sum(1 for d in range(1, n + 1) if n % d == 0)


def _distinct_pairwise(s) -> bool:
    sums = [a + b for i, a in enumerate(s) for b in list(s)[i + 1:]]
    return len(sums) == len(set(sums))


# --- P1: CRT ---------------------------------------------------------------
def p1_valid(c) -> bool:
    return (isinstance(c, int) and c > 300
            and c % 7 == 3 and c % 9 == 4 and c % 11 == 5)


def p1_truth():
    n = 301
    while not p1_valid(n):
        n += 1
    return n


def p1_optimal(c) -> bool:
    return p1_valid(c) and c == p1_truth()


# --- P2: minimal-max 5-element Sidon set -----------------------------------
def p2_valid(c) -> bool:
    return (isinstance(c, (list, tuple)) and len(c) == 5 and len(set(c)) == 5
            and all(isinstance(x, int) and x > 0 for x in c)
            and _distinct_pairwise(list(c)))


def p2_truth():
    m = 5
    while True:
        for comb in itertools.combinations(range(1, m + 1), 5):
            if max(comb) == m and _distinct_pairwise(comb):
                return m            # minimal achievable max element
        m += 1


def p2_optimal(c) -> bool:
    return p2_valid(c) and max(c) == p2_truth()


# --- P3: lex-smallest constrained string -----------------------------------
def p3_valid(c) -> bool:
    return (isinstance(c, str) and len(c) == 8 and all(ch in "ABC" for ch in c)
            and c[0] == "A" and all(c[i] != c[i + 1] for i in range(7))
            and "CAB" in c and c.count("B") == 2)


def p3_truth():
    for tup in itertools.product("ABC", repeat=8):     # product yields lex order
        s = "".join(tup)
        if p3_valid(s):
            return s
    return None


def p3_optimal(c) -> bool:
    return p3_valid(c) and c == p3_truth()


# --- P4: three consecutive integers each with exactly 4 divisors -----------
def p4_valid(c) -> bool:
    return (isinstance(c, int) and c >= 2
            and _numdiv(c) == 4 and _numdiv(c + 1) == 4 and _numdiv(c + 2) == 4)


def p4_truth():
    n = 2
    while not p4_valid(n):
        n += 1
    return n


def p4_optimal(c) -> bool:
    return p4_valid(c) and c == p4_truth()


PROBLEMS = [
    {"id": "P1", "valid": p1_valid, "optimal": p1_optimal, "truth": p1_truth,
     "prompt": ("Find the smallest integer n > 300 such that n mod 7 = 3, "
                "n mod 9 = 4, and n mod 11 = 5.")},
    {"id": "P2", "valid": p2_valid, "optimal": p2_optimal, "truth": p2_truth,
     "prompt": ("Find a set of 5 distinct positive integers such that all 10 "
                "pairwise sums are distinct, and the largest element is as small "
                "as possible. Give the set as a list.")},
    {"id": "P3", "valid": p3_valid, "optimal": p3_optimal, "truth": p3_truth,
     "prompt": ("Find the lexicographically smallest length-8 string over the "
                "alphabet {A, B, C} such that: it starts with A; no two adjacent "
                "characters are equal; it contains 'CAB' as a substring; and it "
                "contains exactly two B's. (Order: A < B < C.) Give the string.")},
    {"id": "P4", "valid": p4_valid, "optimal": p4_optimal, "truth": p4_truth,
     "prompt": ("Find the smallest integer n >= 2 such that each of n, n+1, and "
                "n+2 has exactly four positive divisors.")},
]

_CAND_RE = re.compile(r"CANDIDATE:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_candidate(text: str):
    """Extract the last 'CANDIDATE: <literal>' from model output, or None."""
    matches = _CAND_RE.findall(text or "")
    if not matches:
        return None
    raw = matches[-1].strip().rstrip(".")
    for attempt in (raw, raw.replace("{", "[").replace("}", "]")):  # set->list
        try:
            return ast.literal_eval(attempt)
        except (ValueError, SyntaxError):
            continue
    # bare string like CAB... without quotes
    if re.fullmatch(r"[A-Za-z0-9]+", raw):
        return raw
    return None


def score(prob: dict, text: str) -> dict:
    c = parse_candidate(text)
    return {"candidate": c,
            "valid": bool(c is not None and prob["valid"](c)),
            "optimal": bool(c is not None and prob["optimal"](c))}


PROMPT_SUFFIX = ("\n\nThink step by step, then end your response with EXACTLY one line:\n"
                 "CANDIDATE: <your answer as a Python literal>\n"
                 "(an int for a number; a list like [1, 2, 3] for a set; a quoted "
                 "string like \"ABAB\" for a string).")


def _selftest():                                       # pragma: no cover
    truths = {p["id"]: p["truth"]() for p in PROBLEMS}
    print("brute-forced truths:")
    print("  P1 smallest n:", truths["P1"])
    print("  P2 minimal max element:", truths["P2"])
    print("  P3 lex-min string:", truths["P3"])
    print("  P4 smallest n:", truths["P4"])
    # verifier sanity: an example optimal candidate scores optimal; a wrong one doesn't
    assert p1_optimal(truths["P1"]) and not p1_optimal(truths["P1"] + 1)
    ex2 = next(list(c) for m in [p2_truth()]
               for c in itertools.combinations(range(1, m + 1), 5)
               if max(c) == m and _distinct_pairwise(c))
    assert p2_optimal(ex2) and not p2_optimal([1, 2, 3, 4, 5])
    assert p3_optimal(truths["P3"]) and not p3_optimal("ABABABAB")
    assert p4_optimal(truths["P4"]) and not p4_optimal(truths["P4"] + 1)
    # parser sanity
    assert parse_candidate("blah\nCANDIDATE: 337") == 337
    assert parse_candidate("CANDIDATE: [1, 2, 5, 11, 13]") == [1, 2, 5, 11, 13]
    assert parse_candidate('CANDIDATE: "ACABACBC"') == "ACABACBC"
    print("SELFTEST OK: truths brute-forced, verifier accepts optimal / rejects wrong, "
          "parser handles int/list/string.")


if __name__ == "__main__":                             # pragma: no cover
    _selftest()
