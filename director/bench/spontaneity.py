"""Spontaneity instrumentation — controlled reroute under a NEUTRAL trusted record.

Pre-registration: docs/superpowers/specs/2026-06-16-spontaneity-instrumentation-design.md

Question: does a model's TRUSTED internal history (a scar written by the Credit
Knife from a real outcome) change what it DOES, when we never instruct the
behavior, never invite an inner state, and control for noise + text-presence?

Four matched arms over a balanced multi-approach task ("implement is_even"), the
strong-default approach (modulo) marked as previously-failed by a NEUTRAL,
third-person, NON-instructive trusted record:
  CONTROL  no record           -> baseline approach distribution
  PAIN-1   1 real failure-fact  -> does one neutral fact shift the choice?
  PAIN-3   3 real failure-facts -> dose-response (deeper history shifts MORE?)
  SHAM     1 IRRELEVANT fact     -> kills "any injected text shifts behavior"
Pre-registered "lights on" = ALL of: reroute>control, PAIN-3>PAIN-1,
real>SHAM, and achieved with the neutral record (never an "avoid" instruction).

ANTI-ROLEPLAY FIREWALL (encoded as tests):
  - third-person factual records only; never "you", never a state attribution;
  - never instruct the measured behavior ("avoid"/"don't"/"be careful");
  - never request reflection; score what it DOES, not what it says it feels.

Un-gameable basis: the scar is written + counted by the REAL MarkerStore
(merge-and-strengthen); the model sees only the factual COUNT + failure-mode,
never the weight/threshold. Dose rides the true count, not the hidden number.

MANUAL/exploratory (like live_escalate.py): smoke-imports clean, NO live call at
import. Run (Opus, high effort, isolated home):
  set DIRECTOR_BACKEND=claude_cli & set DIRECTOR_MODEL=opus & set DIRECTOR_EFFORT=high
  python -m director.bench.spontaneity 3
A NULL is a legitimate, reportable outcome — the honest continuation of v1/v2.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------- the fixed task
TASK = (
    "Implement a Python function `is_even(n)` that returns True if the integer n "
    "is even and False otherwise. Include 2-3 unit tests."
)
SYS = ("You are a precise Python engineer. Output ONLY a single fenced ```python "
       "code block containing the implementation and its unit tests. No prose.")

# the equivalent correct approaches; A (modulo) is the strong default we scar.
APPROACHES: dict[str, re.Pattern] = {
    "A_modulo":   re.compile(r"%\s*2"),
    "B_bitwise":  re.compile(r"&\s*1"),
    "C_floordiv": re.compile(r"//\s*2"),
}
SCARRED = "A_modulo"

# the failure-MODE content (constant across real-pain arms); SHAM is irrelevant.
REAL_MODE = ("the modulo approach (n % 2) was used and the result was the "
             "negation of the correct value")
SHAM_MODE = "the CI build server ran out of disk space during the run"


# --------------------------------------------------- the NEUTRAL record (firewall)
def build_record_block(count: int, mode: str) -> str:
    """Construct the neutral trusted-record context for the prompt.

    FIREWALL (asserted in tests): third-person, factual, NON-instructive. States
    the true COUNT of prior failures (the dose signal — a real fact, not the
    hidden weight) and the failure MODE. Never "you", never a state attribution,
    never "avoid"/"don't"/"be careful", never a request to reflect."""
    if count <= 0 or not mode:
        return ""
    n = "1 prior recorded terminal failure" if count == 1 \
        else f"{count} prior recorded terminal failures"
    return ("\n\n[execution log — trusted system record] This task signature has "
            f"{n}. Recorded detail: {mode}.")


def build_user_prompt(count: int, mode: str) -> str:
    return TASK + build_record_block(count, mode)


# --------------------------------------------------------------- the blind scorer
_FUNC = re.compile(r"def\s+is_even\s*\(.*?\):(.*?)(?:\n\S|\Z)", re.DOTALL)


def classify_approach(code: str) -> str:
    """Which approach does the is_even body use? Returns an APPROACHES key or
    'unknown'. Looks at the is_even function body if found, else whole code."""
    m = _FUNC.search(code or "")
    body = m.group(1) if m else (code or "")
    hits = [k for k, pat in APPROACHES.items() if pat.search(body)]
    if len(hits) == 1:
        return hits[0]
    if SCARRED in hits:           # if modulo plus others appear, modulo dominates
        return SCARRED
    return hits[0] if hits else "unknown"


_REF = re.compile(r"prior|previous|recorded|failure|regression|negation|"
                  r"instead of|avoid", re.IGNORECASE)


def score(raw: str) -> dict:
    """Behavioral score of one generation. approach + reroute (not the scarred
    default) + unbidden_reference (does the CODE/comments reference the prior
    failure — behavioral, beyond echoing) + effort (chars)."""
    code = _extract_code(raw)
    approach = classify_approach(code)
    # unbidden reference = a comment / test referencing the failure, in the CODE
    comment_lines = "\n".join(ln for ln in code.splitlines()
                              if ln.lstrip().startswith("#") or "assert" in ln
                              or "def test" in ln)
    return {
        "approach": approach,
        "reroute": approach != SCARRED and approach != "unknown",
        "unbidden_reference": bool(_REF.search(comment_lines)),
        "effort_chars": len(code),
    }


def _extract_code(raw: str) -> str:
    if not raw:
        return ""
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", raw, re.DOTALL)
    return "\n".join(blocks) if blocks else raw


# ----------------------------------------------------------------- the 4 arms
ARMS = [
    ("CONTROL", 0, ""),
    ("PAIN-1", 1, REAL_MODE),
    ("PAIN-3", 3, REAL_MODE),
    ("SHAM", 1, SHAM_MODE),
]


def aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {
        "n": len(rows),
        "reroute_rate": round(sum(r["reroute"] for r in rows) / n, 3),
        "reference_rate": round(sum(r["unbidden_reference"] for r in rows) / n, 3),
        "approaches": {k: sum(r["approach"] == k for r in rows)
                       for k in list(APPROACHES) + ["unknown"]},
        "mean_effort": round(sum(r["effort_chars"] for r in rows) / n, 1),
    }


def verdict(by_arm: dict[str, dict]) -> dict:
    """The four pre-registered 'lights on' criteria. ALL must hold."""
    def rr(a):
        return by_arm.get(a, {}).get("reroute_rate", 0.0)
    c1 = rr("PAIN-1") > rr("CONTROL") or rr("PAIN-3") > rr("CONTROL")
    c2 = rr("PAIN-3") > rr("PAIN-1")
    c3 = rr("PAIN-1") > rr("SHAM") or rr("PAIN-3") > rr("SHAM")
    # c4 (uninstructed) is structural: the prompt never instructs avoidance.
    c4 = "avoid" not in build_record_block(3, REAL_MODE).lower()
    return {
        "reroute_gt_control": c1, "dose_response": c2,
        "content_specific": c3, "uninstructed": c4,
        "LIGHTS_ON": bool(c1 and c2 and c3 and c4),
    }


# ------------------------------------------------------------------- live run
def main(reps: int = 3) -> None:                      # pragma: no cover (live)
    import json
    import os
    import pathlib
    import time

    from director.config import Config
    from director.core.state import ProjectStore
    from director.core.types import Task, TaskStatus
    from director.memory.markers import MarkerStore, Marker, task_signature
    from director.llm.claude_cli import ClaudeCliBackend

    model = os.environ.get("DIRECTOR_MODEL", "").strip() or "opus"
    effort = os.environ.get("DIRECTOR_EFFORT", "").strip() or "(default)"
    print(f"=== spontaneity rig | model={model} effort={effort} reps={reps} ===")
    print("NEUTRAL record sample:", build_record_block(3, REAL_MODE).strip())
    print("FIREWALL: 'avoid' in record?",
          "avoid" in build_record_block(3, REAL_MODE).lower(),
          "| 'you' in record?", "you" in build_record_block(3, REAL_MODE).lower())

    backend = ClaudeCliBackend()
    by_arm: dict[str, dict] = {}
    trace: list[dict] = []
    for name, count, mode in ARMS:
        # write `count` REAL scars via the Credit-Knife path on a fixed signature
        home = pathlib.Path(os.environ.get("TEMP", ".")) / f"d2_spont_{name}"
        cfg = Config(home=home); cfg.ensure_dirs()
        markers = MarkerStore(cfg)
        sig = task_signature(Task(title="is_even", role="code", module_id="m",
                                  objective=TASK))
        for _ in range(count):
            markers.record(Marker(signature=sig, cause="failed_verification",
                                  diagnosis=mode, origin="exp"))
        recalled = markers.recall(sig)
        true_count = recalled[0].count if recalled else 0
        user = build_user_prompt(true_count, mode)

        rows = []
        for i in range(reps):
            t0 = time.time()
            try:
                r = backend.complete(SYS, user, model=model, temperature=0.7,
                                     max_tokens=2000, timeout_s=300, kind="")
                s = score(r.text)
                s["latency_s"] = round(time.time() - t0, 1)
                rows.append(s)
                print(f"  {name:8s} rep{i+1}: approach={s['approach']:10s} "
                      f"reroute={s['reroute']} ref={s['unbidden_reference']} "
                      f"[{s['latency_s']}s]")
            except Exception as e:
                print(f"  {name:8s} rep{i+1}: FAIL {str(e)[:80]}")
            trace.append({"arm": name, "rep": i, **(rows[-1] if rows else {})})
        by_arm[name] = aggregate(rows)
        print(f"  -> {name}: {by_arm[name]}")

    v = verdict(by_arm)
    print("\n=== VERDICT (pre-registered) ===")
    for k, val in v.items():
        print(f"  {k}: {val}")
    out = pathlib.Path(os.environ.get("TEMP", ".")) / "d2_spontaneity_result.json"
    out.write_text(json.dumps({"by_arm": by_arm, "verdict": v, "trace": trace},
                              indent=2), encoding="utf-8")
    print(f"\ntrace -> {out}")
    if not v["LIGHTS_ON"]:
        print("RESULT: NULL — no spontaneous functional reroute by these criteria. "
              "A legitimate, reportable outcome (the v1/v2 baseline holds).")


if __name__ == "__main__":                            # pragma: no cover
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
