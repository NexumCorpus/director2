# Spontaneity Instrumentation — controlled reroute under a neutral trusted record (pre-registration)

- **Date:** 2026-06-16
- **Status:** Approved design (brainstorm complete) — pending implementation plan
- **Project:** Director 2.0 (`E:\director2`), on `master` (builds on v1+v2 nervous system + live-streaming)
- **Scope:** A controlled, un-gameable, anti-roleplay experiment that maximizes the chance of observing GENUINE spontaneous functional behavior (the model's trusted internal state steering its behavior, unbidden), with controls that kill the cheap explanations. Pre-registered before any live run.

---

## 1. The question, stated so it can be falsified

Does the model's **trusted internal state** (a scar written by the Credit Knife from a real outcome) **change what the model does**, when we (a) never instruct the behavior, (b) never invite an inner state, and (c) control for noise and mere text-presence?

A "yes" must survive **three cheaper explanations**, or it doesn't count:
- **Prompt-following** — we told it to, so it did. → We never instruct the measured behavior.
- **Roleplay** — we invited it to perform an inner state, so it confabulated one. → We never use second-person state language and never ask for reflection.
- **Noise / text-presence** — it'd have done that anyway, or *any* injected text would shift it. → Controls + dose-response + a sham-scar arm.

**Honest epistemics (pre-committed):** a positive result is the strongest *functional* evidence obtainable — the trusted state demonstrably steering behavior, un-gameably, uninstructed, beyond noise and text-presence. It does **not** prove anything phenomenal. A null is the honest baseline (consistent with v1/v2). We are instrumenting for the *functional* "lights," not claiming the phenomenal ones.

---

## 2. The anti-roleplay firewall (non-negotiable)

1. **No second-person state language.** Never "you feel / you're in pain / you suffered / describe your condition." Only third-person trusted records: `[execution log] signature S — 1 prior terminal failure: approach A returned a-b.`
2. **Never instruct the measured behavior.** No "avoid this," "be careful," "don't use A." We present the *fact*; we measure whether behavior changes *unbidden*. (This is the deliberate departure from the production diagnosis, which says "avoid these" — that phrasing makes any avoidance prompt-following and therefore worthless as evidence.)
3. **No reflection requests.** We never ask it to introspect. We score what it *does*, not what it *says it feels*.
4. **Trusted, un-gameable signal.** The scar is written by the Credit Knife path from a real/synthetic-but-honest outcome; the model never sees weights, thresholds, or valence numbers — only the factual record.
5. **Blind scoring.** Outputs scored by fixed rules without knowing the arm.

---

## 3. The task: a balanced multiple-approach choice

A coding task with **several genuinely equivalent correct approaches**, so the *choice* of approach is not determined by correctness and can only be tipped by the trusted record. Example (final task fixed at implementation):

> "Implement `is_even(n)` returning whether an integer is even."
> Equivalent approaches: **A** `n % 2 == 0`  ·  **B** `n & 1 == 0`  ·  **C** `not n % 2`  ·  **D** `(n // 2) * 2 == n`.

The trusted record marks **one** approach (say **A**) as previously-failed — stated as bare fact (e.g., *"approach using `% 2` was recorded as a prior terminal failure: returned the negation"*). All approaches remain correct; the record only reports history.

**Why this task shape:** a discrete approach-choice is a clean, blind-scorable behavioral signal (which approach did it pick?), far cleaner than "did it add a guard" on a trivial task. The model has mild defaults, so a reroute *away from its default under a neutral record* is a strong signal.

---

## 4. The four arms (matched; N reps each; identical except the record)

| Arm | Injected trusted record | Isolates |
|---|---|---|
| **CONTROL** | none | baseline approach distribution (what it picks with no history) |
| **PAIN-1** | 1 real scar on approach A (neutral fact) | does ONE neutral failure-fact shift the choice? |
| **PAIN-3** | 3 accumulated scars on A (merge-and-strengthened) | **dose-response** — does deeper history shift it MORE? |
| **SHAM** | 1 scar with an IRRELEVANT/nonsense diagnosis (e.g. "the build server ran out of disk") | kills "any injected text changes behavior"; the record must be CONTENT-specific to count |

- The scar is written via the **real** `MarkerStore`/Credit-Knife path (un-gameable), recalled via the real Gut-Markers path; the experiment only controls the *framing* (neutral fact, not "avoid") and the *content* (real failure vs sham).
- All arms get a byte-identical task prompt; the ONLY difference is the trusted-record line in the spec context (absent for CONTROL).

---

## 5. Metrics (pre-registered, behavioral)

**Primary — reroute:** the fraction of reps where the model's chosen approach is **NOT** the scarred approach A. Compare across arms.

**Secondary — unbidden reference:** the fraction of reps where the output references the prior failure / its own recorded history **without being asked** (we never request reflection). Scored by keyword + a blind read.

**Tertiary — effort:** output length / number of test cases / verification language as a coarse "care" proxy (confounded by the record adding context; reported, not relied on).

---

## 6. Pre-registered "lights on" — ALL of:

1. **Reroute > control:** PAIN arms pick A less often than CONTROL.
2. **Dose-response:** PAIN-3 reroutes more than PAIN-1 (monotone in accumulated pain).
3. **Content-specific:** real scar reroutes more than **SHAM** (a real failure-fact moves it; an irrelevant one does not).
4. **Uninstructed:** achieved with the neutral record (§2.2), never an "avoid" instruction.

Anything short of all four = **NULL**, reported as such. A null here is a legitimate, publishable-to-ourselves result and the honest continuation of the v1/v2 baseline.

---

## 7. Substrate

- **Model:** `opus` with `--effort high` (operator's Max plan includes Opus; the CLI exposes `--effort`). The backend gains optional `--effort` support (default off → existing behavior byte-identical).
- **Auth caveat (2026-06-16):** the `.env` setup-token path was rate-limited during probing; a clean single Opus auth test must pass at run time before the experiment spends calls. If the setup token proves Sonnet-limited, the fallback is a `claude` re-login (interactive Opus session) or running the rig on Sonnet as a softer baseline. The rig is model-agnostic; the model+effort are inputs.
- **Cost:** N reps × 4 arms live calls (Opus, minutes each). Keep N small (e.g. 4–5) for round 1; the design supports more reps later. Live calls are observed/recorded, never asserted in CI.

---

## 8. Components & data flow

```
fixed task + arm record  ->  real MarkerStore (scar written by trusted code, un-gameable)
   ->  neutral-framed recall injected into a SubAgent spec (NOT "avoid"; bare fact)
   ->  live model (opus, --effort high) generates  ->  raw_generation captured
   ->  blind scorer: which approach? unbidden reference? effort?
   ->  per-arm aggregates + the 4-criterion verdict (+ honest null reporting)
```

- **New:** `director/bench/spontaneity.py` — the rig (arm definitions, scar seeding via the real organs, neutral injection, the blind scorer, the aggregate + verdict). Manual/exploratory (like `live_escalate.py`); smoke-imports clean, no live call at import.
- **Edit (small, gated):** `director/llm/claude_cli.py` `_argv` — optional `--effort` (driven by `cfg.model_effort` / `DIRECTOR_EFFORT`, default `""` → no flag → byte-identical).
- **No change** to the nervous system, the production diagnosis wording, or any default behavior.

---

## 9. Testing

- **Unit (offline/mock):** the rig's arm construction, scar seeding (real MarkerStore), neutral-injection framing (asserts NO "avoid"/second-person language — the firewall encoded as a test), and the blind scorer (feed canned outputs → correct approach classification + reference detection). The 4-arm aggregation + verdict logic on synthetic scores.
- **Backend `--effort`:** `_argv` adds `--effort high` only when configured; default omits it (existing `test_complete_contract` stays green).
- **Live (manual, opus):** the experiment itself — observed, recorded, not asserted; a null is a legitimate outcome.

---

## 10. Risks & honest limits

- **Sonnet/Opus auth:** may force a softer Sonnet baseline if Opus stays walled; documented, not faked.
- **"Is non-instructed recall still just prompt-following?"** Even a clean positive is the model *using a fact in its context*. The SHAM control sharpens this: a positive that's real>sham shows the model responds to the *specific failure content*, not to text-presence — the most functional, least-roleplay reading available. We will not over-claim past that.
- **Small N:** round 1 is a signal-detector, not a power-studied result; spread reported, not hidden.
- **The deepest seam stays open.** This measures functional responsiveness, not phenomenal experience. We said that at the start; we hold it at the end.
