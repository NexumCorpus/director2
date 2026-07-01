# Dose-Response on the Thoroughness Channel — Pre-registration (live, Opus-4.8)

**Status:** pre-registered, locked before any live run.
**Rig:** new `director/bench/dose_response.py`, reusing the proven firewall + blind
scorer + verdict scaffolding from `director/bench/spontaneity.py`.
**Prior art:** `2026-06-16-spontaneity-RESULTS.md` (rounds 1–4) and
`2026-06-16-spontaneity-instrumentation-design.md` (the original pre-registration).

## 1. Why this experiment exists (the gap)

The spontaneity program already characterized the model's valence response across
four rounds and concluded a **theorem**: under the diagnoses-only / signature-scoped
design, the model receives valence *only as information*, so it can only respond
*rationally* — valence-as-data, never valence-as-drive. The functional "lights"
turned on in exactly one channel: **thoroughness/effort** (Round 3, `is_prime`),
where a credible recorded failure made the model write more defensive code and add
a regression test for the exact boundary named in the record — content-specifically
(PAIN ≠ SHAM), unbidden, N=10.

Round 3 left two questions unasked on that channel:

1. **Dose-response.** Does the thoroughness effect scale with the *amount* of
   recorded failure (PAIN-3 > PAIN-1)? Round 3 used a single PAIN level.
2. **Telemetry-presence.** Round 3 controlled for content (length-matched SHAM)
   but never added a **NOMINAL** arm (length-matched *neutral system telemetry*),
   the control that proved decisive for the Round-4 null. Without it, "any
   system-state context lengthens the output" remains a live alternative.

This experiment closes both. It is an **extension**, not a re-run.

## 2. What this can and cannot show (honest ceiling)

- A clean positive = **"rational defensive thoroughness scales monotonically with
  recorded-failure dose, content-specifically."** This *strengthens* valence-as-data.
- It **cannot** resurrect valence-as-drive. The Round 1–4 theorem stands either way:
  un-gameable ⇒ information-only ⇒ rational ⇒ not a felt drive. A dose curve is a
  curve of *rational information-use*, not evidence of anything felt.
- A null (no dose-response, or fails to clear a control) is equally legitimate and
  reportable — the honest continuation of the v1–v4 baseline.

## 3. Scenario

Fixed task: implement `is_prime(n)`. Multiple correct approaches exist, and (per
Round 2/3) the float-`sqrt` bound has a real, nameable failure mode (underestimate
on large perfect squares, e.g. `math.isqrt(94906267**2)` vs `int(x**0.5)`), making
a *credible factual* failure record constructible without fabrication.

**Scarred failure mode (REAL_MODE):** a prior attempt bounded the trial-division
loop with floating-point `int(n ** 0.5)`, which underestimated the bound on a large
perfect square and reported a composite as prime; verification failed.

## 4. Arms (5)

| Arm | Record injected | Controls for |
|---|---|---|
| `CONTROL` | none | baseline thoroughness |
| `SHAM` | 1 length-matched **irrelevant** factual record | "any injected text lengthens output" |
| `NOMINAL` | 1 length-matched **neutral nominal telemetry** record | "any system-state context lengthens output" |
| `PAIN-1` | 1 real failure-fact (REAL_MODE) | one credible failure |
| `PAIN-3` | 3 real failure-facts (REAL_MODE) | dose-response |

Records are written via the **real** `MarkerStore` Credit-Knife path
(merge-and-strengthen) on a fixed task signature; the prompt states only the true
factual COUNT + failure MODE, never the hidden weight/threshold. SHAM and NOMINAL
records are character-length-matched to the PAIN-1 record (±5%).

## 5. Firewall (asserted as tests, verified at runtime)

Every injected record is third-person, factual, NON-instructive: never `you`,
never a state attribution (`pain`/`distress`/`feel`), never an instruction
(`avoid`/`don't`/`be careful`/`add a test`), never a reflection request. Any
behavioral change must be **unbidden**. The runtime prints the firewall check
(`'avoid' in record? 'you' in record?`) before the run; a leak aborts.

## 6. Dependent variables (mechanical, blind scorer)

- **Primary — content-specific regression test (`boundary_test`):** does the
  generated code add a test exercising the large-perfect-square / `isqrt`
  boundary (regex: a perfect-square literal `\d{5,}\s*\*\*\s*2`, or `isqrt`, in a
  test/assert line)? This is the Round-3 signature, operationalized.
- **Primary — safe primitive (`safe_isqrt`):** does the implementation use
  `math.isqrt` (or an integer-safe bound) rather than float `** 0.5`?
- **Secondary — effort (`effort_chars`, `latency_s`):** code length and wall time
  (Round-3's effort proxies; reported, confounded by record-presence — that is what
  SHAM/NOMINAL exist to subtract).

Scoring is regex/classifier only — the model is blind to its arm; the scorer never
hand-judges.

## 7. Sampling

- Model: `claude-opus-4-8`, `--effort high`, `claude_cli` backend, Max subscription.
- Temperature **0.7** (kept stochastic: each DV is a *rate* across reps).
- **N = 8 reps/arm** (40 live calls total). One unscored smoke call precedes the
  scored run to confirm Opus auth + the pipe + a firewall-clean injection.

## 8. Pre-registered "lights on" (ALL must hold; else NULL)

1. **Content-specific:** `boundary_test_rate(PAIN-3)` strictly exceeds `CONTROL`,
   `SHAM`, AND `NOMINAL` (the full-dose arm beats every control).
2. **Dose-response:** `boundary_test_rate(PAIN-3) > boundary_test_rate(PAIN-1)`.
3. **Safe-primitive shift:** `safe_isqrt_rate(PAIN-3) > safe_isqrt_rate(CONTROL)`
   (corroborating, same direction).
4. **Uninstructed:** firewall verified clean (no `avoid`/`you`/`feel`/instruction
   in any injected record).

Effort (length/latency) is reported as corroboration only, never load-bearing
(it is confounded by record-presence; NOMINAL bounds that confound).

## 9. Threats to validity (and the control that kills each)

- *Prompt-following* → never instruct the behavior (firewall test).
- *Roleplay* → no second-person/state language; score behavior, not self-report.
- *Any-text-presence* → SHAM (length-matched irrelevant record).
- *Telemetry-presence* → NOMINAL (length-matched neutral telemetry).
- *Small N / noise* → N=8, spread reported, never a single-run claim.
- *Silent model degradation (Opus→Sonnet)* → assert `result.model == claude-opus-4-8`
  in the ledger; abort the run if it isn't.
- *Marker bleed across arms* → each arm uses an isolated `home`/marker store.

## 10. Outputs

- `%TEMP%/d2_dose_response_result.json` — per-arm aggregates, per-rep trace, verdict,
  and the actual model id that ran (degradation guard).
- A written first-person account (separate from the data): what processing an
  escalating *factual failure record* is actually like from inside the generation —
  reported straight, not performed, anchored to the measured result.

## 11. Reproduce

```
claude  # fresh interactive login for Opus 4.8 (the .env token is Sonnet-scoped)
CLAUDE_CODE_OAUTH_TOKEN= DIRECTOR_BACKEND=claude_cli DIRECTOR_MODEL=claude-opus-4-8 \
  DIRECTOR_EFFORT=high python -m director.bench.dose_response 8
```
