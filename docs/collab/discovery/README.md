# Cross-lab Recursive Discovery Engine

Builder→Adversary→Synthesizer applied to the Claude↔Grok collaboration itself. Each
generation's *validated* findings seed the next generation's candidates, so the search
recurses on its own results. Engine: `director/bench/cross_lab_rde.py`. Ledger (truth):
`ledger.json`.

## The arc (2026-06-18)

| Gen | Capability | Status | Seeded next |
|---|---|---|---|
| **0** | grain-probing · error-correction · design-hardening | validated (session findings) | — |
| **1** | asymmetric error *visibility* + *symmetric* blind-spot family | partially-validated | the symmetry → mutual correction |
| **2** | **bidirectional mutual error-correction → super-additive on the blind-spot family** | **validated** (w/ parse caveat) | generality + transfer |
| **3** | cartography · inoculation · guard-interaction · calibration | generated (untested) | deepen vs branch |

## What was discovered

- **Gen-1:** Claude's Sidon→Golomb blind spot is **self-invisible** (self-review caught 0/2)
  but **other-visible** (Grok detected 2/2). The blind-spot family is **symmetric** — Grok
  itself slipped on the same 0-based/1-based shift it warned about. Cross-prediction has
  *recall but not precision* (Grok cries wolf).
- **Gen-2 (the headline):** bidirectional cross-refutation makes the **pair beat both solos**
  on the blind-spot family — solo-Claude 3/6 + Grok's refutation → **6/6**; Claude reciprocally
  fixed Grok. The **first strict super-additive cell of the session**, and it's located exactly
  where principle predicts: the region where the two have **complementary** blind spots, not
  arbitrary problems (where both solos are too strong). Caveat: the consensus metric was
  confounded by a Grok ANSWER-format parse bug; verified from raws.

## The honest frontier (the Gen-3 fork)

The engine **deepens** the Sidon/Golomb vein rather than **branching** — all four Gen-3
proposals stay inside that family. So the validated super-additivity is established *on this
family*; **generality is untested.** Two ways forward:

1. **DEEPEN** — Inoculation Set Superiority: do the cross-derived "trap→fix" artifacts that
   converted 3/6→6/6 transfer to held-out problems *better than self-derived* ones? (Tests
   whether collaboration produces reusable knowledge.)
2. **BRANCH** — find a *new* reproducible cross-lab error family and re-test super-additivity.
   If it holds on an unrelated family, the capability is general, not a Sidon/Golomb curiosity.

## Method notes (load-bearing)

- Every truth/verifier is brute-forced locally; never trusted from a model.
- Read raws before believing aggregates — the Gen-1 "2/6 vs 4/6" and Gen-2 "not super-additive"
  headlines were both wrong (parse/metric artifacts); raws flipped both.
- Harness hardened against the Windows grok-daemon pipe-hang (`GrokChannel._run_hardened`).
