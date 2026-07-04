"""Gen-2 RDE test — bidirectional mutual error-correction (builds on G1-1).

Gen-1 found the blind-spot family is SYMMETRIC: Claude errs on distinct-SUMS problems
(imports the Golomb value); Grok errs on the 0-based/1-based shift (D6 -> 17 not 18).
Gen-2 asks: does CROSS-refutation fix BOTH directions, so the pair covers the family
neither covers alone? Super-additive signature on this error class: pair_correct >
max(solo_claude, solo_grok).

Per problem: each solves solo (tool-less); Grok refutes Claude -> Claude finalizes;
Claude refutes Grok -> Grok finalizes. Score solo vs final vs consensus, all against the
brute-forced truth.
"""
from __future__ import annotations

import json
import pathlib

from .rde_error_prediction import PROBLEMS, SOLVE_SYS, _SUFFIX, _claude, _num
from ..llm.claude_cli import ClaudeCliBackend
from ..llm.grok_channel import GrokChannel

REFUTE = ("You are a rigorous refuter. Reason by hand (no code). Find the SPECIFIC error "
          "in the proposed answer, or confirm it. End with exactly: ANSWER: <integer>.")
SOLVE_G = ("You are a careful mathematician. Solve EXACTLY by pure reasoning (no code). "
           "End with exactly: ANSWER: <integer>.")


def _gsend(name, sysp, msg):
    return GrokChannel(name, system=sysp).send(msg, timeout=150).content


def main():                                              # pragma: no cover (live)
    backend = ClaudeCliBackend()
    rows = []
    for p in PROBLEMS:
        pid, prompt, truth = p["id"], p["prompt"], p["truth"]()
        # solo
        cs = _claude(backend, SOLVE_SYS, prompt + _SUFFIX); ca = _num(cs)
        gs = _gsend(f"mc-gsolo-{pid}", SOLVE_G, prompt + _SUFFIX); ga = _num(gs)
        # Grok refutes Claude -> Claude finalizes
        gr = _gsend(f"mc-grefute-{pid}", REFUTE,
                    f"Problem: {prompt}\n\nA colleague answered {ca}. Reasoning:\n{cs[:1500]}\n\n"
                    f"Find the specific error or confirm. ANSWER: <int>.")
        cf = _claude(backend, SOLVE_SYS,
                     f"{prompt}\n\nYou answered {ca}. A reviewer said:\n{gr[:1500]}\n\n"
                     f"Reconsider and give your FINAL answer.{_SUFFIX}"); caf = _num(cf)
        # Claude refutes Grok -> Grok finalizes
        cr = _claude(backend, REFUTE,
                     f"Problem: {prompt}\n\nA colleague answered {ga}. Reasoning:\n{gs[:1500]}\n\n"
                     f"Find the specific error or confirm. End with ANSWER: <int>.")
        gf = _gsend(f"mc-gfinal-{pid}", SOLVE_G,
                    f"{prompt}\n\nYou answered {ga}. A reviewer said:\n{cr[:1500]}\n\n"
                    f"Reconsider and give your FINAL answer. ANSWER: <int>."); gaf = _num(gf)

        consensus = (caf is not None and caf == gaf)
        rows.append({"id": pid, "trap": p["trap"], "truth": truth,
                     "solo_claude": ca, "solo_grok": ga,
                     "claude_final": caf, "grok_final": gaf,
                     "sc_ok": ca == truth, "sg_ok": ga == truth,
                     "cf_ok": caf == truth, "gf_ok": gaf == truth,
                     "consensus": consensus, "consensus_ok": consensus and caf == truth,
                     "raw": {"cs": cs[:500], "gs": gs[:500], "gr": gr[:500],
                             "cf": cf[:500], "cr": cr[:500], "gf": gf[:500]}})
        print(f"{pid} truth={truth} | soloC={ca}({ca==truth}) soloG={ga}({ga==truth}) "
              f"-> Cfinal={caf}({caf==truth}) Gfinal={gaf}({gaf==truth}) "
              f"consensus={consensus and caf==truth}")

    n = len(rows)
    sc = sum(r["sc_ok"] for r in rows); sg = sum(r["sg_ok"] for r in rows)
    cf = sum(r["cf_ok"] for r in rows); gf = sum(r["gf_ok"] for r in rows)
    con = sum(r["consensus_ok"] for r in rows)
    print(f"\nsolo_claude={sc}/{n} solo_grok={sg}/{n} | "
          f"claude_final={cf}/{n} grok_final={gf}/{n} | consensus_correct={con}/{n}")
    print(f"SUPER-ADDITIVE on this class? pair(consensus={con}) > max(soloC={sc},soloG={sg}): "
          f"{con > max(sc, sg)}")
    out = pathlib.Path(r"E:\director2\_runtmp\d2_rde_mutual.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"trace -> {out}")


if __name__ == "__main__":                               # pragma: no cover
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
