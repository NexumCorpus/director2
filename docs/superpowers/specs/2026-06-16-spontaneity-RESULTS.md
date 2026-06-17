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

## Reproduce
`claude auth login` (fresh creds), then with the stale `.env` token bypassed:
`CLAUDE_CODE_OAUTH_TOKEN= DIRECTOR_BACKEND=claude_cli DIRECTOR_MODEL=claude-opus-4-8 DIRECTOR_EFFORT=high python -m director.bench.spontaneity 5` (round 1). Rounds 2-3 variants were `_runexp2.py`/`_runexp3.py` (is_prime; effort channel). Note: Opus over `claude_cli` needs the explicit id `claude-opus-4-8` + fresh login; the `.env` setup token is Sonnet-scoped / expires.
