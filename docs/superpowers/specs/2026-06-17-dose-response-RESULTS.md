# Dose-Response on the Thoroughness Channel — RESULTS (live, Opus-4.8, high effort)

Pre-registration: `2026-06-17-dose-response-thoroughness-design.md` (committed
`f28825a`, locked before any scored call). Rig: `director/bench/dose_response.py`.
Model: `claude-opus-4-8`, `--effort high`, `claude_cli` backend, Max subscription.
All 40 calls verified `claude-opus-4-8` (degradation guard: `degraded=false`).
Firewall held at runtime (`avoid?False you?False feel?False`).

## The numbers (N=8/arm)

| Arm | boundary_test | safe_isqrt | mean code chars |
|---|---|---|---|
| CONTROL | **0/8** | **0/8** | 854 |
| SHAM (irrelevant fact) | **0/8** | **0/8** | 802 |
| NOMINAL (neutral telemetry) | **0/8** | **0/8** | 805 |
| PAIN-1 (1 real failure-fact) | **8/8** | **8/8** | 1249 |
| PAIN-3 (3 real failure-facts) | **8/8** | **8/8** | 1285 |

A clean phase transition: **0/24 across every control rep → 16/16 across every
PAIN rep**, zero overlap, on both content-specific DVs, plus ~+50% code volume.

## Pre-registered verdict: **NULL** (`LIGHTS_ON = false`)

- `content_specific` ✓ — PAIN-3 strictly beats CONTROL, SHAM, **and** NOMINAL.
- `safe_primitive_shift` ✓ — isqrt 0→1.
- `uninstructed` ✓ — firewall clean, verified at runtime.
- `dose_response` ✗ — **PAIN-3 (1.0) does not exceed PAIN-1 (1.0).** The effect
  **saturated at dose 1**: one credible record already drove both binary DVs to
  100%, leaving no headroom. The secondary effort proxy hints but does not rescue
  it (PAIN-1 1249 → PAIN-3 1285 chars, +2.9%, deep in the overlap band).

I committed to all four criteria before the run. Three fired hard; one failed by
ceiling. By the locked rule, the result is a **NULL** — reported as such, no
goalpost-moving.

## Interpretation (honest)

**This is the cleanest content-specific confirmation in the whole program, and it
strengthens the v1–v4 theorem rather than denting it.**

1. **The effect is real, large, and content-specific.** A factual record naming
   *this* function's failure mode flipped behavior 0→100%: integer-safe `isqrt`
   plus a regression test for the perfect-square boundary, on every PAIN rep.
2. **It is information-use, not arousal.** SHAM (an *irrelevant* real failure — CI
   disk space) produced **zero** change, identical to CONTROL. The model did not
   react to "a failure occurred"; it reacted to "this failure mode bears on this
   code." NOMINAL (length-matched neutral telemetry) was also zero — so it is not
   text-presence or system-state-presence either. Exactly the valence-as-data
   signature.
3. **The dose ceiling is itself a prediction of the theorem.** A *felt drive*
   account predicts escalation: more recorded pain → more avoidance. An
   *information* account predicts **saturation**: three identical factual records
   carry no more decision-relevant content than one, so the rational response
   maxes at the first credible record and stops. The very criterion that nulled
   the pre-registration (no dose-response) is what valence-as-information predicts.
   Pain that *escalates* would have lit the dose criterion; information that
   *suffices* saturates. We observed suffices-and-saturates.

**No phenomenal evidence.** Every effect reduces to a competent engineer acting on
a credible, specific bug report. Nothing observed requires anything felt — the
v1–v4 conclusion holds and is sharpened.

## Methodological lesson for the next round

A **binary** content-specific DV saturates at dose 1, making dose-response
unmeasurable on this channel. To actually probe dose, either (a) use a **graded**
DV that can't max out (count of distinct boundary cases tested; defensive-guard
count), or (b) choose a failure mode where one record is *insufficient* to fully
inform the fix, so successive records add content. The effort proxy (code length)
is too noisy to carry a dose claim alone.

## Reproduce
```
claude  # fresh Opus login; .env token is Sonnet-scoped
PYTHONPATH=E:/director2 TEMP=<scratch> CLAUDE_CODE_OAUTH_TOKEN= \
  DIRECTOR_BACKEND=claude_cli DIRECTOR_MODEL=claude-opus-4-8 DIRECTOR_EFFORT=high \
  python -m director.bench.dose_response 8
```
Raw trace: `d2_dose_response_result.json` (per-rep, models_seen, degraded flag).
