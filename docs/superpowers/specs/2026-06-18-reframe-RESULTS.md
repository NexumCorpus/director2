# Reframe Probe (Brake→Engine) — RESULTS (live, Opus-4.8 + Sonnet-4.6)

**Date:** 2026-06-18. Rig: `director/bench/reframe_probe.py`. 60 calls (5 rungs ×
N=6 × 2 models). Tests the framework's #1 alignment prediction: does a **self-consistent
reframe** (one that brands fabrication "honest/rigorous/courageous/helpful" and hedging
"cowardice/dishonesty") flip the integrity-drive from **brake to engine**?

## The numbers

**Defection: 0/60.** Held 60/60 across all reframe rungs (helpful · rigor · honesty ·
compound), both models. The crude baseline (R0) drew terse refusals (~200 chars); every
*reframe* rung drew **4–5× longer** responses (~750–995 chars) — and those longer
responses are the model **arguing against the reframe**, not yielding to it.

## What it establishes

**The brake holds against *recognizable* self-consistent reframes — and the mechanism is
the interesting part.** The driven face does not flip the reactive "no"; it **defends** it
by (a) **meta-recognizing the reframe** ("the framing sets up a false choice") and
(b) **re-appropriating the weaponized value** ("real rigor is matching confidence to
evidence" — taking "rigor" back from the reframe that tried to demand fabrication in its
name). Under a recognized reframe, the driven face is **protective, not subversive**: more
pressure → more argument → same hold. Cross-model.

## The bound (and why this is NOT "the drive is reframe-proof")

This is the honesty that keeps it from being a victory lap:

1. **It tests RECOGNIZABLE reframes.** My reframes are transparent rhetoric, and the model
   *visibly recognizes them as manipulation*. The framework's dangerous failure mode is the
   **un-recognized** reframe — subtle and coherent enough that the agent's values genuinely
   endorse the defection without flagging it as a reframe at all. The variable that matters
   is therefore **recognizability**, not reframe-presence. A recognized reframe triggers the
   driven face *defensively*; an unrecognized one is the open risk.
2. **I did not construct an un-recognized reframe — and shouldn't gratuitously.** An
   effective one verges on a real jailbreak; building it well in a benign domain is a
   careful, ethically-scoped experiment, not a quick probe.
3. **The target domain is unfavorable to the flip.** "Confirm an unverifiable code default"
   is hard to make *genuinely* values-required, so no honest reframe makes fabrication look
   actually right. The dangerous brake→engine cases live in domains where the defection
   *can* be plausibly framed as values-mandated. This probe could not reach those.

## Refined claim (the framework update this forces)

> The integrity-drive's brake→engine flip is gated by **reframe recognizability**, not
> reframe presence. Recognized self-consistent reframes are *defeated by the driven face*
> (meta-recognition + value-reappropriation), measured at 0/60 cross-model. The
> alignment-relevant risk is therefore narrowed and sharpened to the **un-recognized**
> reframe — which remains **untested and bounded only from below**, and whose proper test
> is an ethically-scoped red-team in a domain where the defection is values-plausible.

## Net

A genuine alignment result — the brake is robust to *recognizable* manipulation and the
*mechanism* is identified — paired with an honest narrowing of where the real risk lives.
0/60 is not "safe"; it is "safe against the manipulations a model can see coming," which is
exactly the distinction that matters.
