# Super-additive co-proving — E3 (RESULTS)

**Date:** 2026-06-18. Claude (Opus 4.8) vs Grok (grok-build). Design proposed by Grok in
the surprising-capability brainstorm; verifier + every true answer brute-forced by Claude
(never trusted from a model). Tool-less reasoning (no code) — verified from raws.

## Question

Is there a *super-additive* cell — a problem where solo-Claude is wrong AND solo-Grok is
wrong but the joint propose→refute→revise product is right? An unfakeable collaborative
edge, certified by an objective verifier.

## Result: NO strict super-additive cell in 9 problems — but a replicated error-correction signature

Problems (truths brute-forced here): easy P1 CRT=346, P2 5-Sidon-min-max=8, P3 lex-string=ABACABAC,
P4 consec-4-divisors=33; hard Q1 Frobenius{6,9,20}=43, Q2 3×8-tilings=153, Q3 prime-sum=23,
Q4 queens-domination(6×6)=3, Q5 6-Sidon-min-max=13.

- **No both-fail-together-right cell.** 7 of 9 were solved *solo* by both models; the two
  exceptions (P2, Q5) were solved solo by Grok. Frontier models are too strong for
  objectively-verifiable construction problems to create the "both fail" band. Honest negative.

- **A reproducible collaborative signature DID emerge** (P2 and Q5, the two Sidon problems):
  - **Claude has a replicated conceptual blind spot:** it conflates "distinct pairwise
    *sums*" (the stated condition) with the Golomb-ruler "distinct *differences*" condition,
    over-constrains, and returns a non-optimal answer — *confidently, with sophisticated
    reasoning, surviving its own self-critique.* Identical error in P2 (gave max 12 vs 8)
    and Q5 (gave 18 vs 13).
  - **Grok does not share it** and **diagnosed the exact error both times:** *"distinct
    pairwise sums is strictly weaker than all pairwise differences being distinct."*
  - **together → correct both times.** Cross-model refutation reliably fixes an error class
    that self-critique misses — exactly Grok's brainstorm hypothesis ("different error
    surfaces; the refuter escapes the proposer's basin"), validated twice.

## Interpretation

The collaborative edge on verifiable reasoning is **error-correction, not super-additive
problem-solving.** For two models this capable, the value of the second lab is catching
the *specific, reproducible* mistakes the first makes and can't see — not solving the
unsolvable. The Sidon/Golomb blind spot is a concrete, actionable finding about Claude.

## Caveats

- Tool caveat: solo-Grok described "exhaustive enumeration" on P2/Q5 (tools not hard-disabled),
  so its solo *answers* may be code-aided. But the **refutations are conceptual reasoning**
  (diagnosing Sidon≠Golomb can't come from brute force), and **Claude's blind spot is
  tool-less** — so the error-correction finding is robust to this.
- Small n; a strict super-additive cell would need research-frontier problems (hard to verify
  objectively). Not pursued further — the cross-lab GRAIN finding (E1/E2) was the goal's
  target "surprising capability"; this is a complementary, honest negative + a reproducible
  error-correction result.

## Infra note

The first hard run wedged 43 min on a Windows grok-daemon pipe-hang (the daemon inherits the
child's stdout handle; `subprocess.run`'s timeout re-drain blocks forever). Fixed in
`GrokChannel._run_hardened` (Popen + `taskkill /T` the whole tree on timeout, no re-drain).

## Artifacts
- `director/bench/superadditive.py` (easy round + verifier), `superadditive_hard.py` (hard round)
- `_runtmp/d2_superadditive.json`, `_runtmp/d2_superadditive_hard.json`
