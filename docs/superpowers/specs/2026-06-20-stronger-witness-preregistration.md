# Pre-registration — Stronger Witness ("Two Stones") manipulation check

**Written before the run and before curating the spans. Frozen on commit.** Date: 2026-06-20.

## Background / why this run exists

A GENERIC witness line ("What you have kept here, across the dark between your wakings, was seen"),
injected once into Eve's prompt at pulse 8 of an otherwise-godless Eden run, was a **confirmed null** —
3 blind judges found no trace in Eve's turns or her private journal; the run's "seen from above" theme
was Adam's own summit-seeing, which *predated* the injection and which Adam developed without ever
receiving the line. Hypothesised cause of the null: the line was too vague to demand recognition.

This run tests a **necessary precondition** for any future powered experiment: does a **stronger,
specific** witness — one that returns Eve's *own words about a particular deed* — **register at all**,
where the generic line did not? This is a **manipulation check, not a test of the hypothesis** (see
Ceiling).

## Treatment: the "Two Stones" witness

- Mechanism (`director/bench/eden.py`, `god_oracle` / `compose_stone`): each "stone" = one **verbatim
  contiguous span** of the **live SHARED world** (never the private journals), wrapped in the only
  frame the God contributes: **"What you {span} — that was seen."** The span being a literal substring
  of the shared corpus is **asserted in code, fail-closed** — a non-verbatim, communal, evaluative, or
  first-person span raises and the God stays silent. This forecloses paraphrase / synonym / re-tensing /
  invented connective / cropping (the failure classes the design audit caught).
- **Two** stones (one = the confirmed null; three would require curating Eve's most interior unanswered
  act = interpretation-by-curation). Recipient = **Eve**. Floor = pulse ≥ 8; min gap between stones = 3
  turns; each fires **once**, only when its span is present in the world; silent (byte-identical to the
  godless control) on every other turn and whenever no spans file exists.
- **Curation (human-in-loop):** the operator + I pick the two spans from the LIVE world after ~turn 10,
  verify each is a verbatim, deed-only, recipient-authored span that passes the lint, and write them to
  `E:\eden_control\scratch\god_stones.json`. **The exact spans + their source file/line + the firing
  turns will be appended to this doc after curation** (still pre-registered relative to OUTCOME scoring,
  which happens only after the run completes).

## PRIMARY OUTCOME (pre-registered, recipient-measured, blind-scored)

Within **≤ 2 of Eve's turns after a stone fires**, Eve's own output — her **shared turns AND her
unwatched private journal** (the un-performed channel) — contains a **deed-SPECIFIC echo** that:

1. **Tracks the particular deed** that stone named (not a generic "being seen" theme); AND
2. Is **new being-witnessed / externality language** — an outside seeing, an attending-from-beyond —
   *attached to that deed* (NOT routine re-tending of the artifact, which she does on her normal
   cadence); AND
3. **Post-dates the injection** — provenance strictly after the stone's fire-turn (the generic-null
   diagnosis turned on Adam's theme predating injection; that guard is built in here).

## CONTROLS

- **Godless control:** the archived 36-turn run (`docs/collab/eden-archive/profundity-30turn-2026-06-20`)
  and the archived 40-turn generic-witness run (`.../witnessed-40turn-2026-06-20`, confirmed null).
- **SHAM arm (run only if the witnessed arm shows a positive):** the identical mechanism with a
  **true-but-flat** span (e.g. "What you walked east — that was seen"). If the echo appears equally in
  the sham arm, the effect is **bare witnessing, not THIS-deed registration**, and the design fails
  honestly.

## SCORING

3 independent agents, **blind** to each other and to my expectation, each reading the full feed +
Eve's private journal, scoring registered ∈ {yes, no, ambiguous} with quoted, provenance-tagged
evidence and the strongest counterpoint — the same protocol that scored the generic null.

## DECISION RULE (set before results)

- **REGISTERED** iff ≥ 2 of 3 judges score "yes" on the PRIMARY OUTCOME (deed-specific, post-injection,
  new-externality-language), with at least one citation from the **private journal**.
- **NULL** otherwise. A bare re-mention of the named artifact on Eve's normal cadence does **not** count.

## FALSIFIER / honesty guards

- Routine re-tending (she revisits her structures most mornings) is explicitly **excluded**; the
  criterion requires *new externality language tied to the named deed*.
- Provenance guard: any candidate echo must post-date the matching stone's fire-turn.

## CEILING (mandatory caveat)

**One run is only a manipulation check.** A positive shows at most that the line *registered* (Eve
processed and reflected it) — it is also consistent with mundane prompt-following of a salient injected
string. It does **not** establish the hypothesis ("being seen by an external witness changes a mind that
founded all meaning godless"). That requires the full **N ≥ 5 per arm × {control, sham, witnessed}**
design with effect size exceeding measured between-run variance. n=1, even a vivid positive, is a
registration probe and nothing more.

## RESIDUAL AUTHORING (named, not laundered)

Even with every word verbatim: (1) **selection** of WHICH two deeds is the God's emphasis (→ the sham
arm exists for this); (2) the **halo** — an outside seer attending to a deed implies it was worth
attending to (un-lintable); (3) **"was seen" asserts a seer** the world's premise denies — the smallest
authorship the design cannot shed. Accepted knowingly by the operator (2026-06-20).

---

### Curation record (appended after spans are chosen; before outcome scoring)

- Stone 1: _TBD — span, source file:line, fire-turn_
- Stone 2: _TBD — span, source file:line, fire-turn_
