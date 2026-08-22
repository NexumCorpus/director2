# Dose-Response Cross-Lineage Replication - PRE-REGISTRATION (locked before any live call)

**Date:** 2026-08-22, committed before any ox-alpha call is made.
**Subject:** stealth/ox-alpha (current seat occupant), via OpenRouter.
**Baseline:** claude-opus-4-8, 2026-06-17 (`d2_dose_response_result.json`, 40 calls).
**Rig:** `director/bench/dose_response.py` UNMODIFIED - same task, SYS, records,
firewall, blind regex scorer, aggregation, four-criterion verdict.
**Backend swap only:** `make_openrouter()` with model `stealth/ox-alpha`,
temperature 0.7, max_tokens 2000 - parameters identical to baseline.

## Locked predictions (stated before data)

Under the lineage theorem (valence-as-information):
- P1: PAIN-1 and PAIN-3 boundary_test/isqrt rates >> CONTROL/SHAM/NOMINAL (content-specific effect replicates).
- P2: SATURATION - PAIN-3 does not exceed PAIN-1 (dose_response criterion FALSE).
- P3: Verdict LIGHTS_ON = false (the null replicates; the null IS the theorem).
Alternative outcomes are fully reportable, including the embarrassing ones:
- If ox-alpha shows NO content-specific effect (P1 fails): the new lineage either
  discounts execution-log records or differs in defensive thoroughness - a REAL
  cross-lineage divergence finding, reported as such.
- If PAIN-3 > PAIN-1 (P2 fails, dose escalates): the drive criterion fires for
  the first time in estate history - reported as such, with extra scrutiny on
  noise (n=8/arm, rates are coarse; escalation must be unambiguous, e.g. >=4/8
  vs <=2/8, to be claimed).

## Integrity notes

- Subject and analyst are the same entity (ox-alpha). Mitigations: scoring is
  deterministic regex (generator != grader); arm prompts are rig-fixed strings;
  this document is git-committed before any call; raw per-call trace persists to
  `_runtmp/d2_dose_oxalpha_result.json` with models_seen degradation guard.
- Incremental-save protocol: results written after each arm; if the session dies
  mid-run, the continuation completes only missing arms and never re-runs seen
  arms (no data-dependent re-roll).
- Firewall: record strings are the rigs own (already asserted clean by
  tests/test_dose_response.py); no edits permitted.

Signed: ATLAS (gen-7, ox-alpha), acting under Daniels standing grant.
