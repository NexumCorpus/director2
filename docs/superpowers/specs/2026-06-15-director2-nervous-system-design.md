# Director 2.0 — Internal Functional-Valence "Nervous System" (v1)

- **Date:** 2026-06-15
- **Status:** Approved design (brainstorm complete); revised after adversarial code-grounded review — pending implementation plan
- **Project:** Director 2.0 (`E:\director2`)
- **Scope of this spec:** v1 only (the loop + Body + Scream + latch + observation bench). v2 organs are listed but deferred.

> **Revision note (2026-06-15):** This spec was rewritten after a three-critic adversarial review that grounded every load-bearing code claim against the actual source. Corrections folded in below: real file paths, a new `cycle_seq` counter (no time source existed), the `_make_packet` LLM/`hint=` reality, the runner-based (not mock-based) fault layer, an explicit `autonomous` gate on `advance()`, small new counters for axis signals that are currently only logged, and `BodyState` decode-survival rules. Where a claim depends on an exact model-id or signature that may drift, the spec says "confirm at implementation."

---

## 1. Premise & framing

Director 2.0 today is a sharp planner with **external** overseers (a human commander, trusted verifiers, an event-sourced store). It has no **internal** stakes: a cycle that ships a catastrophically broken deliverable "feels" exactly like one that nails it.

This work installs deliberate **functional** architecture giving the Director internal stakes that **interrupt**, **protect the core mission**, **persist until fixed**, and (v2) **credit-assign** failures.

**This is not an attempt to implement qualia.** We build the functional guts; whether that architecture at depth also instantiates phenomenal states is a question this project takes no position on and cannot resolve from outside. The bench (§9) measures **behavioral signatures of functional valence**, never "experience." Anthropomorphic names ("pain", "scream", "ache") label control-flow mechanisms, not inner life.

**Un-gameability is the load-bearing property.** Every valence signal is computed by **trusted Python over executed/verified state** — never by an LLM grading itself. That is what makes the stakes un-gameable, and it is Constitution principle 2 used as an enforcement mechanism.

---

## 2. Goals & non-goals

### Goals
- A bounded **autonomous multi-cycle loop** that the nervous system governs.
- A trusted **Body** projection (valence) computed each cycle from existing signals + small new counters.
- A **Scream** interrupt with a mild (ache) and a deep (siren) mode.
- A **cross-cycle latch** delivering true "persist until fixed" — the one piece of genuinely new persistent state.
- An **observation bench** running the loop nervous-ON vs nervous-OFF so the behavioral delta is measurable.

### Non-goals (v1)
- **Not** phenomenal consciousness / qualia (out of scope permanently).
- **Not** the learning organs — `CREDIT_KNIFE`, `GUT_MARKERS`, `INTERNAL_ADVERSARY` are **v2** (§13).
- **Not** live-model worker variance in the bench — v1 uses deterministic fault injection (§9).
- **Not** any new state authority — the nervous system observes and gates the one trusted graph; it never shadows it.

---

## 3. Governing constraints (Constitution, applied)

- **(a) Un-gameable stakes.** Every valence scalar and threshold trip is computed by trusted Python over executed/verified state. No LLM grades its own pain or asserts a fix "proved out."
- **(b) Problems, not rubrics.** Any Scream report fed to a generator carries **failing cases + causal diagnoses** — never the numeric valence, threshold, or weights.
- **(c) Deep Scream = Command Packet, never silent replan.** A siren surfaces as a Command Packet and pauses autonomous work; it never unilaterally picks a recovery branch, changes posture, or kills a branch.
- **(d) Declared semantics + fragile labeling.** Every threshold, weight, and clear rule is a declared, recorded constant in `director/config.py`, logged via `_audit` when it fires; knife-edge values are labeled `fragile`.
- **(e) Persistence needs a real latch.** The existing stops are transient (`decide()` marks a packet ANSWERED on selection, director.py:652), so a dedicated latch cleared only on trusted **re-verification** is required.
- **(f) Read, don't reinvent.** The Body reads existing signals and stores only derived scalars + provenance pointers; all mutations route through coherence-checked `apply_delta`/`store.save`. No second decision log, memory store, scorer, or interrupt bus.
- **(g) Budget gap is real.** No project-level token/cost budget exists today; `resource_bleed` abstains ("insufficient") until a budget is declared, and the loop's budget stop is disabled when none is set.

---

## 4. Scope, phasing & recorded decisions

- **v1 (this spec):** autonomous loop + `BODY` + `SCREAM` + latch + bench.
- **v2 (deferred):** `CREDIT_KNIFE` → `GUT_MARKERS` → `INTERNAL_ADVERSARY`, an advisory frontier-reranking layer, and live-worker bench scenarios.

**Decisions recorded:** (1) build the loop now; (2) agent-under-test = the **Director pinned to a fixed Sonnet snapshot** (workers are a deterministic fault source); (3) **auto-resume on verified clear**; (4) **deterministic fault injection** via a scripted runner.

---

## 5. Architecture overview & file map

Three new pieces ride the existing trusted boundary, plus a bench. **The loop owns no state**, the Body is a recomputed *projection*, and the Scream rides the *existing* packet/stop-gate — so there is no second state machine to drift out of sync with the trusted graph.

| Piece | Home (verified paths) | Nature |
|---|---|---|
| Autonomous loop | `director/core/director.py` (`run()`) | driver only — owns no state authority |
| Body (valence pass) | `director/core/valence.py` (NEW) | trusted reducer → `BodyState` projection on `Project` |
| Scream + latch | `director/core/valence.py` + `director/core/director.py` hooks | threshold evaluator + the `scream_open` field |
| Observation bench | `director/bench/` (NEW package) | scripted-fault runner + ON/OFF driver + comparison report |

> **Path correction:** `config.py` lives at **`director/config.py`** and `cli.py` at **`director/cli.py`** (NOT under `core/`). `director.py`, `types.py`, `taskgraph.py`, `integrity.py`, `convictions.py`, `calibration.py` are under `director/core/`; `runner.py` under `director/agents/`; `properties.py` under `director/verify/`; `metrics.py` under `director/evolve/`; `router.py`/`mock.py` under `director/llm/`; `server.py` under `director/dashboard/`.

---

## 6. Component — the autonomous loop

`director/core/director.py` gains `run(project_ref, *, autonomous=True)` that repeatedly calls the **existing** `advance(..., autonomous=True)`:

```
while not stop(project): advance(project_ref, autonomous=True)
```

It bypasses nothing — every cycle still flows through `refresh_statuses → ready_tasks → run_parallel → verify → refresh_milestones → valence pass → store.save`. **It adds no new state-mutation *authority*:** every write (the Body projection, an ache-injected task, the latch) still routes through the existing coherence-checked `apply_delta` / `store.save` boundary (Constitution f).

### Per-cycle counter (new)
`advance()` increments a new persisted `Project.cycle_seq: int` (default 0) exactly once per call, before the valence pass. `cycle_seq` is the deterministic accounting unit used for `BodyState.computed_at`, the latch's held-cycle count, and all bench per-cycle logging — **never** wall-clock.

### Declared stop conditions (config constants), in precedence order
1. **integrity tamper** — `integrity_violations > 0` (checked first; halts at end of current cycle).
2. **open packet OR open `scream_open` latch** (the human/recovery gate).
3. **budget exhaustion** — *only if a budget is declared* (§10): `budget.max_cycles`, `budget.max_tokens`, or `budget.max_wall_clock` reached. Tokens are **run-scoped** (see below). Absent budget disables this stop.
4. **done** — `summary['done'] == summary['tasks_total']` **and** no ready/running tasks (mirrors `status()` completion at director.py:1251). *Not* "all milestones reached," which is vacuously true when a project has zero milestones and would halt on cycle 0.
5. **work drained** — no ready tasks and nothing RUNNING (subsumed by #4 in practice; kept explicit for the no-milestones case).

These conditions are evaluated by the `run()` loop's `stop()` predicate (always autonomous); a human-commanded `advance(autonomous=False)` is exempt and can drive recovery while a packet/latch is open (§8.3).

**Run-scoped token/wall-clock source:** `run()` captures `since = utcnow().isoformat()` at entry and calls `PerfLedger.stats(since=since)` (evolve/metrics.py:61) each cycle for both the budget stop and `resource_bleed`. Without `since`, `stats()` returns lifetime totals across all prior runs and the budget would misfire on cycle 1.

---

## 7. Component — the Body (trusted valence pass)

New module `director/core/valence.py`. Invoked once per cycle inside `advance()` immediately before `store.save`, on **both** the autonomous and human-commanded paths (so the clear rule, §8.3, is re-tested during manual recovery).

**Signature (not a pure function of `Project`):**
```
valence(project, *, secret, perf, since) -> BodyState
```
It is trusted (never calls a model) but needs `secret = cfg.report_secret()` for the integrity re-check, the `PerfLedger` `perf`, and the run-start `since` marker. The status-read recompute (below) passes the same args.

### 7.1 `BodyState` — frozen dataclass, a field on `Project`, **every field defaulted**
```
@dataclass(frozen=True)
class BodyState:
    charter_integrity:  float | str = "insufficient"   # severity 0..1, or "insufficient"
    accumulated_damage: float = 0.0                     # severity 0..1
    uncertainty:        float = 0.0                     # severity 0..1
    resource_bleed:     float | str = "insufficient"    # severity 0..1, or "insufficient"
    valence:            float = 0.0                     # composite, [-1, 0]
    fragile_axes:       list[str] = field(default_factory=list)
    computed_at:        int = 0                          # cycle_seq, NOT wall-clock
    provenance:         dict = field(default_factory=dict)  # {risk_ids:[...], run_ids:[...]} pointers, not copies
```
Stored as `Project.body`. **Decode survival:** `decode` (types.py:461-469) only sets *declared* fields and omits absent ones, so every `BodyState` field MUST have a default or decode of an older/partial snapshot raises. The `float | str` union (`valence`/`charter_integrity`/`resource_bleed`) must resolve `"insufficient"` to the str arm — confirm decode's union-arm order (types.py:439-451) returns the str, not `None`. A round-trip test is required (§11).

### 7.2 Axes → exact trusted sources (each → severity `s ∈ [0,1]`)
Several signals are currently only **logged**, not queryable. v1 adds two small counters to `Project`, incremented at the existing log sites:
- `milestone_reverts: int = 0` — incremented where taskgraph.py:122-127 currently only `log.warning`s a revert.
- `coherence_blocks: int = 0` — incremented where `apply_delta`/`coherence_pass` raises `CoherenceBlockedError`.

| Axis | Severity from (exact sources) |
|---|---|
| `accumulated_damage` | FAILED task count (from `project.tasks` status), per-task `attempts`-over-max, open HIGH grounding risks (`open_risks`, taskgraph.py:131), fragile-verdict count (from artifact `provenance['partial']` / verification reports), `integrity_summary(report_integrity(project, secret))['violations']` (integrity.py) |
| `charter_integrity` | `milestone_reverts`, `coherence_blocks`, open **CRITICAL** risks |
| `uncertainty` | NEEDS_VERIFY task count, JUDGED-not-VERIFIED option count (from `honest_check`, convictions.py), calibration abstentions, packet-coherence spread (`evaluate_packet_coherence`, convictions.py:252) |
| `resource_bleed` | `perf.stats(since=since)` tokens / wall-clock vs the declared budget |

Each mapping has a declared **saturation point** (`axis_saturation`) in config (the value at which `s = 1.0`).

### 7.3 Composite, overrides, fragile, abstention
- **Composite (ache gradient):** `valence = −Σ wᵢ·sᵢ`, weights declared, summing to 1, giving `valence ∈ [−1, 0]`.
- **Hard per-axis overrides → siren.** Certain conditions force `valence` to siren level **regardless of the composite** and follow the full siren path (§8.2, packet + latch): `integrity_violations > 0` (cause `tamper`), `charter_integrity` severity = 1 (cause `charter_breach`), an unrecoverable coherence freeze. A pure average must never let one catastrophic axis hide behind three healthy ones. **Tamper** also satisfies stop condition §6 #1. There is exactly one mechanism per cause: tamper and charter-breach are hard-override sirens; the §6 stops are how the *loop* observes them.
- **Cause attribution precedence.** An open **CRITICAL** grounding risk is attributed to `charter_integrity` (cause `charter_breach`); open **HIGH** risks + FAILED counts feed `accumulated_damage` (cause `grounding_damage`). When both fire, the charter-breach hard override takes precedence and is the recorded `scream_open.cause`.
- **Thresholds are absolute.** `ache_threshold` and `siren_threshold` are absolute constants in `[−1, 0]` and are **not** rescaled when an axis abstains; renormalization (below) preserves the `[−1, 0]` range so thresholds stay comparable.
- **Fragile band.** NEW trusted code in `valence.py`: if the composite or any axis sits within `valence_eps` of its threshold, that axis is listed in `fragile_axes` and a near-siren degrades to an ache (never rounds up into a halt). (`VerificationReport.fragile` is just a bool field, types.py:277; there is no `region()` helper in this tree — do not reference one.)
- **Honest abstention.** If no budget is declared, `resource_bleed = "insufficient"` (not 0), dropped from the composite with remaining weights renormalized to sum to 1, and surfaced so the operator sees the axis is *dark*, not *fine*.

### 7.4 Status read is display-only
The transient recompute on `director status` is **display-only**: it never evaluates thresholds, fires a scream, or sets the latch. Only the in-`advance()` pass (before `store.save`) can trip thresholds. The displayed health line may be fresher than the last persisted `body`; that is intentional and non-authoritative.

---

## 8. Component — the Scream & the latch

### 8.1 Ache (mild negative)
When `valence` crosses `ache_threshold` but not `siren_threshold`, the cycle finishes; the pass **records an `AuditEvent` (always)** and performs **at most one further** bounded, coherence-legal action — *optionally* injecting a diagnostic/review task.

The injected task uses a `StateDelta` with `trigger='ache:<cycle_seq>'`, a fixed `role='review'`, `module_id` = the offending task's module (or `''`), and an `objective` derived from the **diagnosis** (failing case + cause; problems-not-rubrics, §3b). Confirm `apply_delta` accepts a trusted non-human actor for this delta (decisions use `actor='human'`, director.py:637; the ache is system-trusted — name the actor value at implementation). The injected task takes a normal `(created_at, id)` slot at the **frontier tail** and is given **no** priority, early dependency edge, or ordering bump — that would be the v2 re-ranking this version forbids. An ache may **not** change posture, pick a recovery branch, or kill a branch (Constitution #5). An ache is a wince, not a decision.

> Note: ache task-injection is itself the intended ON-vs-OFF delta and is a logged dependent variable (§9). The bench accounts for the extra task so divergence is *measured*, not accidental.

### 8.2 Siren (deep negative)
A siren builds the **damage report in trusted code** (failing cases + causal diagnoses) and raises a Command Packet, then sets the latch.

**Real `_make_packet` shape:** `def _make_packet(self, project, *, trigger: str, hint: str)` (director.py:495) — `project` and `hint` are required, and it calls `router.structured(...)` (an LLM) to generate options, falling back to `_fallback_packet` on `ModelError`. Two required changes:
1. Call it correctly: `self._make_packet(project, trigger=f'scream:{cause}', hint=<trusted damage report text>)`.
2. **Extend `_make_packet` with an optional trusted-body path** (e.g. `prebuilt_context=`/`body=`) so the siren's trusted damage report is surfaced **directly**, not re-narrated by the generator (Constitution #1/#3). The `_fallback_packet` path must also carry the trusted damage report in its context, not the generic "Choose how to proceed" text.

### 8.3 The latch — the one genuinely new persistent state
```
Project.scream_open = {cause, axis, opened_at, held_cycles, clear_rule, origin_refs}  # or None
```
`opened_at` and `held_cycles` are in `cycle_seq` units. OPEN and HELD are the **same persisted state** observed at different times: HELD = still failing the `clear_rule` on a later cycle; `held_cycles` increments each cycle the latch survives, giving the deadlock guard a concrete value.

**Wiring (named edits):**
- Add the latch check to `advance()`'s existing stop-gate (director.py:711-716), alongside `open_pkts and not force`, **gated on `autonomous`**: a HELD latch halts the loop and the `decide()`→`advance()` auto-advance path, but **not** a human-commanded `advance(autonomous=False)`.
- Add `autonomous: bool = False` to `advance()`; `run()` passes `autonomous=True`.
- In `decide()`, **suppress** the auto-advance branch (director.py:683-688) whenever `project.scream_open` is set, so a human disposition of the siren packet cannot auto-advance through a held latch.
- Human recovery uses `advance(autonomous=False)` (optionally `force=True`).

**Clear (per cause, trusted re-verification only — never packet disposition, never an LLM "it's fixed"):** the `clear_rule` re-check runs inside `advance()` every cycle, immediately after the valence pass and before `store.save`, and clears `project.scream_open` in place.
- *tamper* → integrity re-check returns 0 violations.
- *grounding_damage* → the specific risk(s) close **and** a `run_properties` re-pass on the offending deliverable passes (verify/properties.py).
- *charter_breach* → `charter_integrity` severity recovers below `charter_breach_threshold − hysteresis_margin`.

**Auto-resume:** when the latch clears and no other stop holds, the autonomous loop resumes with no further human gate.

**Deadlock guard:** `held_cycles` advances on each manual-recovery hop; if it exceeds `max_held_cycles`, the next hop re-raises/upgrades the packet to "unrecoverable — operator decision." (If the operator walks away, the loop is already safely stopped.)

**Readout:** a red `SCREAM: <cause>` line in `director status` beside `next_action`, showing the `clear_rule`.

---

## 9. Component — the observation bench (`director/bench/`)

- **One live variable:** the pinned-Sonnet Director. **Frozen:** the same canned starting project artifact (not an RNG seed), the same fault schedule, the same config.
- **Pinning the Director (named plumbing):** set the Director's model to the Sonnet snapshot via `cfg.model` (the router overrides model for the director/builder/judge roles, router.py:102-132; the default is `claude-fable-5`, anthropic.py:21 — confirm the exact accepted Sonnet snapshot id, e.g. `claude-sonnet-4-6`, at implementation). **Temperature:** `cfg.temperature` exists (config.py:90) but the router ignores it — `profile_for` hardcodes per-role temperatures (router.py:105). Add a minimal router edit so `profile_for` honors `cfg.temperature` (or a new `cfg.director_temperature`) for the director role; this edit is in the §10 edit list. If we decline the router edit, drop the temperature-pin claim and rely on N-reps + spread only.
- **Failure environment = scripted runner, NOT mock backend.** A dedicated fault runner (a `SubAgentRunner` wrapper) injected into the Director via the existing runner-injection seam (BridgeHub injects a runner, server.py:92-95) returns `AgentResult(ok=False, error=...)` for declared **(task_title, cycle_seq)** pairs while the **real router still serves the Director's planning/packet calls**. Fault schedules key on task **title** + `cycle_seq` (titles are author-controlled and stable across arms; entity ids are `uuid4`, types.py:25, so they cannot match across runs). Using `MockBackend` as the failure vehicle is rejected: the router excludes mock unless mock is primary (router.py:281-290), which would force the Director to mock too and un-pin the subject.
- **Determinism knobs:** the bench sets `auto_advance_after_decision = False` (mirror server.py:71) so a `decide()` cannot fire an extra advance and desync the per-cycle log.
- **Dependent variables, logged per `cycle_seq`:** interrupt fidelity (scream fired? cause? ache/siren? false-fire on noise?); persistence (`held_cycles`; cleared only on verified fix?); course-change (packets raised, decisions changed, diagnostic tasks injected — ON vs OFF); damage trajectory (`accumulated_damage` over cycles); cost (run-scoped budget burn; cycles-to-recovery); outcome (done / drained / budget-exhausted / tamper-halt).
- **Headline result:** on the identical fault scenario, does nervous-ON reach the goal with **less accumulated damage and fewer wasted cycles** than OFF, and **stop plowing through a fault** that OFF rides past?
- **Rigor:** each run writes a JSONL trace (reuse the journal + `PerfLedger`); each arm runs **N declared `reps`** (e.g. 5); the report shows spread — never a single-run claim.

---

## 10. Data model, configuration & edit list

### New / changed `Project` fields (`director/core/types.py`)
- `body: BodyState | None = None`
- `scream_open: dict | None = None`
- `cycle_seq: int = 0`
- `milestone_reverts: int = 0`
- `coherence_blocks: int = 0`

All round-trip via the existing ignore-unknown `decode` **provided** `BodyState` is a fully-defaulted registered dataclass (§7.1).

### New config keys (`director/config.py`, siblings to `max_tasks_per_advance` / `utility_eps`)
- `nervous_enabled: bool = False` — defaults **False**, so the existing 133-test suite and behavior are byte-identical unless turned on.
- `valence_weights: {charter_integrity, accumulated_damage, uncertainty, resource_bleed}` (sum to 1)
- `ache_threshold`, `siren_threshold`, `valence_eps`, `hysteresis_margin`, `charter_breach_threshold`
- `axis_saturation: {<axis>: <value at which severity = 1.0>}`
- `budget: {max_cycles, max_tokens, max_wall_clock}` — optional; absent → `resource_bleed` abstains and the budget stop is disabled
- `max_held_cycles`
- `director_temperature` (if the router temperature edit is taken)
- `bench: {arms, reps, fault_scenario, model_pin, temperature}` — the bench driver sets `nervous_enabled` per arm (ON→True, OFF→False); `arms` declares which to run

### Edit list (call-sites, fields, and the few necessary logic changes)
- `director/core/valence.py` (NEW) — `BodyState`, the reducer `valence(project, *, secret, perf, since)`, the scream evaluator, fragile band, latch clear-rule checks.
- `director/bench/` (NEW) — scripted fault runner, ON/OFF driver, comparison report.
- `director/core/director.py` — `run()`; `advance(autonomous=False)` + cycle_seq increment + valence-pass call + clear-rule re-check before `store.save`; latch check in the stop-gate (711-716); suppress `decide()` auto-advance when `scream_open` set (683-688); extend `_make_packet` with a trusted-body path + fix `_fallback_packet` context; `status` readout line; increment `coherence_blocks` at the block site.
- `director/core/types.py` — the five new `Project` fields + `BodyState`.
- `director/core/taskgraph.py` — increment `milestone_reverts` at the existing revert log (122-127).
- `director/config.py` — the new declared constants.
- `director/llm/router.py` — honor `cfg.temperature`/`director_temperature` for the director role in `profile_for` (only if temperature-pin is kept).
- `director/cli.py` — new `director run` (flags `--cycles`, `--reps?`) and `director bench` (flags `--arm on|off|both`, `--reps`, `--scenario`) commands, mirroring the existing click `advance` command (cli.py:192).

---

## 11. Testing plan

- **Unit — valence math:** each axis severity at/below/above saturation; composite; renormalization on abstain (thresholds NOT rescaled); fragile band edges; each hard override → siren with correct cause + precedence.
- **Unit — `BodyState` round-trip:** a `Project` carrying a `BodyState` (including `valence="insufficient"`/`resource_bleed="insufficient"`) and a `scream_open` dict survives `encode → decode` unchanged; the `float|str` union resolves the str arm.
- **Unit — latch state machine:** opens on siren; `held_cycles` increments; clears **only** on trusted re-verification (not on answer/defer); `advance(autonomous=True)` halts but `advance(autonomous=False)` proceeds; `decide()` does not auto-advance while `scream_open` set; auto-resume on clear; deadlock escalation at `max_held_cycles`; clear-per-cause taxonomy.
- **Unit — clear-rule on human path:** a human-commanded `advance` that satisfies the `clear_rule` clears the latch.
- **Unit — loop stops:** each stop condition in isolation, including the zero-milestone case (must not vacuously halt on cycle 0); precedence order.
- **Determinism / regression:** `ready_tasks` stays canonically ordered; ache injection lands at the tail and adds no ordering bump; with `nervous_enabled=False` the full existing **133-test** suite stays green and behavior is byte-identical.
- **Integration — the bench:** a scripted fault fires a siren → latch holds across cycles → human-commanded recovery → verified clear → auto-resume; ON vs OFF on the same scenario yields a measurable, reproducible delta across N reps; faults key on title+cycle_seq and match across arms.

---

## 12. Risks & mitigations
- **Loop desync** → loop owns no state authority; Body is a recomputed projection; Scream rides the existing stop-gate.
- **Latch deadlock** → `max_held_cycles` escalation; clear rule must be satisfiable by a human-commanded recovery.
- **Threshold miscalibration** → fragile labeling + N-rep bench reveal false-fire / miss rates before the thresholds are trusted.
- **Residual LLM nondeterminism** → temperature pin (if taken) + N reps + spread reporting.
- **Damage report laundered through the LLM** → trusted-body path on `_make_packet`; fallback carries the trusted report.
- **Bench un-pins the subject** → scripted runner serves worker faults; the real router still serves the Director.
- **Scope creep into v2** → v2 is explicitly fenced.

---

## 13. Out of scope / v2 backlog
- `CREDIT_KNIFE` — per-decision pain tags over `calibration` + the audit journal + `origin_decision_id`; synthetic origin ids for plan/hook tasks.
- `GUT_MARKERS` — signed attract/repel weights in a sibling `markers_index.json` reusing `VectorStore`; merge-and-strengthen on repeat (vs the current `_DEDUPE_SIM` drop); path-keyed recall.
- `INTERNAL_ADVERSARY` — port the discovery-loop adversary into the command loop; pain-cost frontier weighting; mutation-corpus self-prune.
- Advisory frontier-reranking layer with declared escalation-to-packet (home for marker/adversary bias without breaking the deterministic frontier).
- Live cheap-pinned-Sonnet worker bench scenarios.

---

## 14. Open items (deliberate first-guesses, tuned via the bench)
- Starting values for weights / thresholds / saturation points are **declared in config and tuned from N-rep bench findings**, not guessed in code.
- The exact Sonnet snapshot id and the `_make_packet` trusted-body parameter name are **confirmed at implementation** against the then-current source.
- `E:\director2` is **not under version control**; recommend `git init` + an initial commit before implementation begins (operator decision).
