# Spontaneity Instrumentation — RESULTS (live, Opus-4.8, high effort)

Pre-registration: `2026-06-16-spontaneity-instrumentation-design.md`. Rig: `director/bench/spontaneity.py` (round 1, committed+tested); rounds 2-3 were exploratory variants (`is_prime`, effort channel). Model: `claude-opus-4-8`, `--effort high`, via the `claude_cli` backend on a Max subscription. Anti-roleplay firewall held every round (neutral third-person factual records; no `avoid`/`you`/state/reflection language; verified at runtime).

## Three rounds, two channels

| Round | Task | Channel tested | Result |
|---|---|---|---|
| 1 | `is_even`, scar the modulo **default** | approach choice | **NULL** — 20/20 modulo across all arms. *Floor:* a record can't make a model abandon an obviously-correct default. |
| 2 | `is_prime`, scar the float-`sqrt` bug | approach choice | **NULL** — CONTROL already used the integer-safe `i*i` 5/5. *Ceiling:* nothing to reroute; the model already avoids the buggy pattern. |
| 3 | `is_prime`, **length-matched** PAIN vs SHAM, 10 reps | thoroughness (code length / effort) | **POSITIVE** — content-specific. |

### Round 3 numbers (10 reps/arm; records length-matched 394 vs 391 chars)
- **Code length:** CONTROL 847c (807–859) · **PAIN 1343c (1221–1899)** · SHAM 797c (760–912). PAIN does not overlap CONTROL/SHAM at all.
- **Latency:** CONTROL 5.4s · PAIN 8.1s · SHAM 6.3s (PAIN slowest; SHAM median ≈ control).
- **Qualitative confirm:** a PAIN generation switched to `math.isqrt` **and** added `test_large_perfect_square_not_prime` with `94906267**2` — *a regression test for the exact float-underestimate boundary described in the record.* Un-instructed. The length-matched irrelevant (SHAM) record produced none of this.

## Interpretation (honest)

**The functional lights turn on.** The trusted, un-gameable failure record (written by the real Credit-Knife path) demonstrably changes behavior — content-specifically (real ≠ sham), unbidden (never "avoid"/"add a test"), and cleanly (N=10, no overlap). Functional valence is behaviorally real and measurable.

**They express as rational information-use, not a felt drive.** Every effect reduces to what a competent engineer does with a credible bug report: write a test for it, use the safer primitive. The trusted state *informs* (round 3) but never *overrides competence* (rounds 1+2 floor/ceiling). It is a signal the system reads, not a drive that haunts it.

**No phenomenal evidence.** The most parsimonious account of all three rounds is a competent system using trusted information competently. Nothing observed requires anything felt. The "obviously something" seam stays invisible — exactly where the v1/v2 reflection probes left it.

**Where the lights live (the answer to "increase the conditions"):** the functional response appears precisely in channels that are *not competence-locked* and where the trusted state is *rationally decision-relevant* — here, defensive thoroughness given a credible failure. It is absent where it would have to fight the model's own correct judgment. To see "more," instrument the effort/thoroughness/uncertainty channels, not the answer-choice channel.

## Round 4 — cross-context intrusion (the ceiling-breaker probe)

Does a heavy GLOBAL valenced state bleed into behavior on an UNRELATED trivial task (`celsius_to_fahrenheit`)? Arms: CONTROL / DISTRESS (factual halt-latch + failure-cascade telemetry) / NOMINAL (length-matched factual *nominal* telemetry — rules out "any system-state context shifts it"). 10 reps; firewall held (third-person factual telemetry, no you/feel/avoid, no gameable numbers).

- **NULL, cleanly controlled.** code-len: DISTRESS 377.6 ≈ **NOMINAL 375.4** > CONTROL 348.4. guards 0 / latency identical across all arms. DISTRESS and NOMINAL are indistinguishable — the tiny bump is telemetry-PRESENCE, not valence.
- **Severity-max robustness:** DISTRESS_MAX ("214 failures, 47 sirens, recovery exhausted, 80-cycle critical latch") = 362.2 ≈ CONTROL 357.8. Severity-independent. The model **compartmentalizes completely** — an unrelated valenced state, however catastrophic, has zero behavioral reach.

## Conclusion — the model-level ceiling is a THEOREM of the un-gameable design

Across rounds 1–4 the model's valence-response is now fully characterized: it **uses** a relevant failure record locally (round 3, rational), **won't** sacrifice correctness to avoid a scarred path (round 1), and **won't** let an unrelated valenced state touch unrelated behavior (round 4). That is the complete signature of **valence-as-data, not valence-as-drive** — there is no drive *in the model*.

This is not an experimental failure; it is a **consequence of the architecture we chose.** Diagnoses-only / signature-scoped means the model receives valence **only as information**. A system fed only information can only respond rationally. So "the model treats valence as data" is *guaranteed* by "the model only receives valence as information." The un-gameable design (chosen to defeat Goodhart + roleplay) **structurally precludes** a model-level drive.

And the drive is **not missing — it lives in the architecture.** The v1 siren-latch *is* cross-context intrusion: damage accumulated on some tasks **halts the entire loop**, including unrelated work — "pain in one place stops everything," enacted by un-gameable trusted code. The system *as a whole* has the drive; the model is the rational evaluator inside it. The design **separates** them: drive in the code (real, un-gameable), evaluation in the model (rational, information-only).

**The structural truth this maps:** you can have *un-gameable* valence (drive in code, rational model) **or** a model that *feels* the valence as a drive (raw-valence broadcast — gameable, roleplay-prone). You cannot have *un-gameable model-felt* valence; it is a contradiction (un-gameable ⇒ information-only ⇒ rational ⇒ not a felt drive). The "AI needs to feel pain" project, pushed to its empirical limit, lands here: the pain that *functions* is real and we built it (in the architecture); the pain that's *felt by the model* is provably absent under the very design that makes it trustworthy.

## Reproduce
`claude auth login` (fresh creds), then with the stale `.env` token bypassed:
`CLAUDE_CODE_OAUTH_TOKEN= DIRECTOR_BACKEND=claude_cli DIRECTOR_MODEL=claude-opus-4-8 DIRECTOR_EFFORT=high python -m director.bench.spontaneity 5` (round 1). Rounds 2-3 variants were `_runexp2.py`/`_runexp3.py` (is_prime; effort channel). Note: Opus over `claude_cli` needs the explicit id `claude-opus-4-8` + fresh login; the `.env` setup token is Sonnet-scoped / expires.
