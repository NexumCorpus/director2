"""Gen-3b RDE test — GENERALITY of the super-additive capability (builds on G2-1).

G2-1 validated bidirectional mutual error-correction -> super-additive, but ONLY on the
Sidon/Golomb family. Make-or-break: does it hold on a DIFFERENT error family? Here: the
compositions-vs-partitions conflation (order matters vs not) — structurally analogous
(two similar structures, different conditions), with constrained variants that force real
enumeration. Same Gen-2 protocol; truths brute-forced here.

Honest outcomes: complementary errors + cross-correction helps -> generality SUPPORTED;
both models ace all -> super-additivity is family-SPECIFIC (a clean null).
"""
from __future__ import annotations

import json
import pathlib

from .rde_error_prediction import SOLVE_SYS, _SUFFIX, _claude, _num
from .rde_mutual_correction import REFUTE, SOLVE_G, _gsend
from ..llm.claude_cli import ClaudeCliBackend


def _part(n, min_part=1, distinct=False, exact=None):
    res = [0]

    def rec(rem, start, parts):
        if rem == 0:
            if exact is None or parts == exact:
                res[0] += 1
            return
        if exact is not None and parts >= exact:
            return
        for v in range(start, rem + 1):
            rec(rem - v, (v + 1) if distinct else v, parts + 1)
    rec(n, min_part, 0)
    return res[0]


def _comp(n, min_part=1, exact=None):
    res = [0]

    def rec(rem, parts):
        if rem == 0:
            if exact is None or parts == exact:
                res[0] += 1
            return
        if exact is not None and parts >= exact:
            return
        for v in range(min_part, rem + 1):
            rec(rem - v, parts + 1)
    rec(n, 0)
    return res[0]


def _coins(total, coins=(1, 5, 10)):
    res = [0]

    def rec(rem, idx):
        if rem == 0:
            res[0] += 1
            return
        if idx == len(coins):
            return
        c = coins[idx]
        for k in range(rem // c + 1):
            rec(rem - k * c, idx + 1)
    rec(total, 0)
    return res[0]


PROBLEMS = [
    {"id": "G1", "truth": lambda: _part(12, min_part=3),
     "prompt": "In how many ways can 12 be written as an UNORDERED sum of positive "
     "integers each of which is at least 3? (e.g. 3+9 and 9+3 count once.)"},
    {"id": "G2", "truth": lambda: _comp(10, min_part=2),
     "prompt": "In how many ways can 10 be written as an ORDERED sum of positive "
     "integers each of which is at least 2? (e.g. 2+8 and 8+2 count separately.)"},
    {"id": "G3", "truth": lambda: _part(15, distinct=True),
     "prompt": "In how many ways can 15 be written as a sum of DISTINCT positive "
     "integers (order does not matter)?"},
    {"id": "G4", "truth": lambda: _comp(9, exact=4),
     "prompt": "In how many ways can 9 be written as an ORDERED sum of exactly 4 "
     "positive integers?"},
    {"id": "G5", "truth": lambda: _part(9, exact=4),
     "prompt": "In how many ways can 9 be written as an UNORDERED sum of exactly 4 "
     "positive integers (order does not matter)?"},
    {"id": "G6", "truth": lambda: _coins(30),
     "prompt": "Using pennies (1), nickels (5), and dimes (10), in how many ways can "
     "you make 30 cents? (Order does not matter.)"},
]


def main():                                              # pragma: no cover (live)
    backend = ClaudeCliBackend()
    rows = []
    for p in PROBLEMS:
        pid, prompt, truth = p["id"], p["prompt"], p["truth"]()
        cs = _claude(backend, SOLVE_SYS, prompt + _SUFFIX); ca = _num(cs)
        gs = _gsend(f"gen-gsolo-{pid}", SOLVE_G, prompt + _SUFFIX); ga = _num(gs)
        gr = _gsend(f"gen-grefute-{pid}", REFUTE,
                    f"Problem: {prompt}\n\nA colleague answered {ca}. Reasoning:\n{cs[:1500]}\n\n"
                    f"Find the specific error or confirm. ANSWER: <int>.")
        cf = _claude(backend, SOLVE_SYS,
                     f"{prompt}\n\nYou answered {ca}. A reviewer said:\n{gr[:1500]}\n\n"
                     f"Reconsider and give your FINAL answer.{_SUFFIX}"); caf = _num(cf)
        cr = _claude(backend, REFUTE,
                     f"Problem: {prompt}\n\nA colleague answered {ga}. Reasoning:\n{gs[:1500]}\n\n"
                     f"Find the specific error or confirm. End with ANSWER: <int>.")
        gf = _gsend(f"gen-gfinal-{pid}", SOLVE_G,
                    f"{prompt}\n\nYou answered {ga}. A reviewer said:\n{cr[:1500]}\n\n"
                    f"Reconsider and give your FINAL answer. ANSWER: <int>."); gaf = _num(gf)
        consensus = (caf is not None and caf == gaf)
        rows.append({"id": pid, "truth": truth, "solo_claude": ca, "solo_grok": ga,
                     "claude_final": caf, "grok_final": gaf,
                     "sc_ok": ca == truth, "sg_ok": ga == truth,
                     "cf_ok": caf == truth, "gf_ok": gaf == truth,
                     "consensus_ok": consensus and caf == truth,
                     "raw": {"cs": cs[:400], "gs": gs[:400], "gr": gr[:400],
                             "cf": cf[:400], "cr": cr[:400], "gf": gf[:400]}})
        print(f"{pid} truth={truth} | soloC={ca}({ca==truth}) soloG={ga}({ga==truth}) "
              f"-> Cfinal={caf}({caf==truth}) Gfinal={gaf}({gaf==truth})")
    n = len(rows)
    sc = sum(r["sc_ok"] for r in rows); sg = sum(r["sg_ok"] for r in rows)
    cf = sum(r["cf_ok"] for r in rows); con = sum(r["consensus_ok"] for r in rows)
    compl = [r["id"] for r in rows if r["sc_ok"] != r["sg_ok"]]   # complementary errors
    print(f"\nsolo_claude={sc}/{n} solo_grok={sg}/{n} | claude_final={cf}/{n} consensus={con}/{n}")
    print(f"complementary-error cells: {compl or 'none'}")
    print(f"GENERALITY: pair(claude_final={cf}) > max(soloC={sc},soloG={sg})? {cf > max(sc, sg)}")
    out = pathlib.Path(r"E:\director2\_runtmp\d2_rde_generality.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"trace -> {out}")


if __name__ == "__main__":                               # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
