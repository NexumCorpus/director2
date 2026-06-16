# Director 2.0 Nervous System — v2: Credit Knife + Gut Markers (the learning organs)

- **Date:** 2026-06-16
- **Status:** Approved design (brainstorm complete) — pending implementation plan
- **Project:** Director 2.0 (`E:\director2`), branch `nervous-v2` (builds on merged v1)
- **Scope of this spec:** Credit Knife (scar writer), Gut Markers (scar consumer + planning bias), and the escalate-pain live experiment. The Internal Adversary (the third v2 organ) and raw-BodyState broadcast remain **out of scope**.

---

## 1. Premise & framing

v1 gave the Director un-gameable internal stakes that **interrupt, persist, and protect** — but no **memory**. Each siren is fresh; the system re-walks a path that burned it. v2 adds the **learning organs**: persistent **scars** (the Credit Knife) and a planning **bias** that reroutes around them (Gut Markers). This is the "pain-avoidance drive" — the layer where prior damage shapes future behavior.

**Hard constraint (operator decision, 2026-06-16): diagnoses-only.** The model NEVER sees the raw valence / thresholds / weights. Scars and markers carry **problems** — a failing case + its cause — not numbers. Trusted Python computes every scar and every signed weight from **executed/verified outcomes**; the model only ever reads a diagnosis ("prior attempts at this signature failed verification because X"). This preserves the un-gameable foundation (Constitution #2/#3) AND is the more behaviorally-interesting path: it produces genuine rerouting without the Goodhart vector that raw-valence broadcast would open.

**Honest framing (unchanged from v1, reinforced by today's live result):** these are behavioral mechanisms. Today's reflection probe found **no unbidden self-modeling** (the live model referenced its condition only when explicitly asked, and then only paraphrased the injected numbers). v2 does not claim to change that. The escalate experiment (§7) re-asks the question with markers present, honestly: does *unbidden* avoidance arise, or does it still need prompting? Either answer is data.

---

## 2. Goals & non-goals

### Goals
- **Credit Knife** — write a persistent **scar** (a diagnosis) when a branch resolves as FAILED or fires a siren, attributed to its originating decision (or a synthetic origin for plan/hook tasks).
- **Gut Markers** — a `VectorStore`-backed `markers_index.json` that recalls scars by **task signature**, **merges-and-strengthens** on repeat, and biases planning two ways (advisory re-rank + diagnosis injection), all behind `nervous_enabled`.
- **Escalate-pain experiment** — a multi-cycle live scenario + an ON-vs-OFF re-bench measuring whether markers produce rerouting/recovery.

### Non-goals (v2)
- **Not** raw-BodyState/valence broadcast to the generator (operator chose diagnoses-only; preserves un-gameability).
- **Not** the Internal Adversary (deferred to v3).
- **Not** any change to the v1 valence math, latch lifecycle, or loop — v2 only *adds* a memory layer that reads v1's outcomes.
- **Not** mutating the canonical deterministic `ready_tasks` sort (the bias is a separate advisory layer).

---

## 3. Governing constraints

- **(a) Diagnoses-only un-gameability.** Every scar and marker weight is computed by trusted Python from executed/verified outcomes (`_task_vindicated` / `provenance['partial']`, terminal FAILED status, siren causes). The model reads only the diagnosis text; it never sees the weight, valence, or threshold. No model call writes a scar or sets a weight.
- **(b) Resolve-before-scarring.** A scar is written only once the work has **resolved against a trusted check** (terminal FAILED, or a fired siren with a recorded cause) — never on an in-flight READY-retry guess. Mirror calibration's honest-abstention (`calibration.py`: `rate` is `None` until resolved).
- **(c) OFF-path byte-identical.** All recording, recall, re-ranking, and injection are guarded by `cfg.nervous_enabled` (default False). With it off, the markers store is never read or written and dispatch is unchanged.
- **(d) No silent starvation (Constitution #5).** The advisory re-rank never mutates the canonical `ready_tasks` order; a task repeatedly deferred past the dispatch batch for `marker_defer_escalate_cycles` surfaces as a Command Packet rather than being silently starved.
- **(e) Declared semantics.** Recall similarity, repel weight delta, and the defer-escalation count are declared constants in `director/config.py`.
- **(f) Reuse, don't reinvent.** Credit Knife reuses `calibration._task_vindicated` + the `origin_decision_id` join; Gut Markers reuse `VectorStore` (`embed`/`add`/`search`, pure-Python, no model). The markers store is a **sibling** to the lesson ledger — biasing weights stay OUT of the human-readable lesson digest.

---

## 4. Architecture overview

Two new pieces + an experiment, all reading v1's existing trusted outcomes:

| Piece | Home | Nature |
|---|---|---|
| Marker store | `director/memory/markers.py` (NEW) | `VectorStore`-backed `markers_index.json`: `record` / `recall` / merge-and-strengthen |
| Credit Knife (write hooks) | `director/core/director.py` edits | record a scar at FAILED-ingest + siren sites (trusted, resolved-only) |
| Gut Markers (read + bias) | `director/core/director.py` edits + a small advisory helper | recall by signature → advisory re-rank + escalation + diagnosis injection into the subagent spec |
| Escalate experiment + re-bench | `director/bench/` additions | multi-cycle accumulating-damage scenario; ON-vs-OFF with markers |

**Signature** is the join key throughout: `signature(task) = f"{role}|{module_id}|{normalized objective}"`. Scars are keyed on it; recall embeds it; merge matches on it.

---

## 5. Component — Credit Knife (the scar writer)

### 5.1 The scar (a diagnosis, never a number)
A `Marker` dataclass (in `markers.py`):
```
@dataclass
class Marker:
    signature: str                 # role|module_id|normalized-objective
    cause: str                     # "failed_verification" | "grounding_damage" | "charter_breach" | ...
    diagnosis: str                 # failing case + cause, model-facing text (problems-not-rubrics)
    weight: float = 0.0            # signed, trusted-only: < 0 repels (hurt before)
    count: int = 1                 # times this scar recurred (merge-and-strengthen)
    origin: str = ""               # origin_decision_id, or synthetic "plan" / f"hook:{role}"
    last_cycle: int = 0            # cycle_seq of the most recent occurrence
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
```
The `diagnosis` is built by trusted code from `task.error` + the trusted property-check detail (`c['detail']` / the grounding-risk text) — the same `_problems_from`/`failure_samples` shapes v1 already feeds generators. It contains **no** valence/threshold/weight.

### 5.2 Write triggers (resolved-only)
Guarded by `cfg.nervous_enabled`:
- **FAILED ingest** — at the terminal-FAILED status assignment in `advance()`'s result-ingest loop (the `task.status = TaskStatus.FAILED` site, director.py ~788): the task is now terminal (a trusted resolution), so record a `cause="failed_verification"` scar for `signature(task)` with the failing diagnosis. Transient-retry READY tasks are NOT scarred (not yet resolved — constraint b).
- **Siren** — in `_handle_siren` (after the latch opens): record a scar for each offending signature in `origin_refs` (the FAILED tasks driving the siren), `cause=scream["cause"]`, diagnosis = the trusted damage report. (The scream itself is the trusted resolution.)

`MarkerStore.record(marker)` applies **merge-and-strengthen** (§6.2). No model call occurs on any write path.

### 5.3 Origin attribution (plan failures aren't blind — v1 backlog #4)
`origin = task.origin_decision_id` when set; else a **synthetic recorded origin**: `f"hook:{task.role}"` if the task came from a hook, else `"plan"`. This guarantees a non-empty, recorded attribution for the dominant failure source (initial-plan tasks), so the Credit Knife is not limited to decision-spawned work. (`calibration_record` already groups only `origin_decision_id`-bearing tasks; the synthetic origin is Credit-Knife-local and does not alter calibration.)

---

## 6. Component — Gut Markers (the scar consumer + bias)

### 6.1 The store
`MarkerStore` (`markers.py`) wraps a `VectorStore` at `cfg.markers_path` (`<home>/markers_index.json`, sibling to the lesson index):
- `record(marker)` — merge-and-strengthen, then persist.
- `recall(signature, *, k, min_sim) -> list[Marker]` — embed the signature, `VectorStore.search`, return markers whose cosine ≥ `cfg.marker_recall_sim`.
- `all()` / load/save — deterministic JSON, offline, no model (mirrors the lesson ledger / vector store conventions).

### 6.2 Merge-and-strengthen (fixes the `_DEDUPE_SIM` silent drop)
The lesson ledger currently DROPS a near-duplicate (`_DEDUPE_SIM = 0.95`, returns None). A recurring scar must do the OPPOSITE — **deepen**. On `record`, if an existing marker matches the signature (cosine ≥ `cfg.marker_merge_sim`), update it in place: `weight -= cfg.marker_repel_step` (more repellent), `count += 1`, refresh `diagnosis`/`last_cycle`; otherwise insert a new marker with `weight = -cfg.marker_repel_step`. (Weights are clamped to a floor so a single signature can't dominate.)

### 6.3 Bias — two effects, both behind `nervous_enabled`, both un-gameable
After `ready_tasks(project)` (canonical, deterministic, UNCHANGED) and before dispatch in `advance()`:
1. **Advisory re-rank.** Pull the FULL ready frontier (all READY tasks — not the canonical top-`limit`). For each, `recall(signature)` and sum matched weights → a `repel_score` (≤ 0; 0 = no prior pain). Rank by `(repel_score descending, canonical (created_at, id) tiebreak)` — **least-repelled first** — and dispatch the front `cfg.max_tasks_per_advance`; the rest are **deferred this cycle** (this is how repel actually defers a scarred signature). With `nervous_enabled=False` this whole layer is skipped and dispatch is the canonical `ready_tasks(limit)` — byte-identical OFF. The canonical sort itself is never mutated (determinism + the v1 tests hold).
2. **Diagnosis injection.** When a task is dispatched, its subagent spec (`_spec_for`) gains a `prior_pain` section: the matched markers' **diagnoses** ("prior attempts at this signature failed verification because X; avoid that"). This is the pain-avoidance drive — the model reroutes based on a problem, never a weight.

### 6.4 No silent starvation → escalate (Constitution #5)
A task pushed out of the top-`cfg.max_tasks_per_advance` advisory batch by repel is **deferred**, and a per-task deferral counter (on `Project`, e.g. `marker_deferrals: dict[str,int]`) increments. When it exceeds `cfg.marker_defer_escalate_cycles`, raise a Command Packet ("repeatedly deferred by prior-pain markers — commander decision: persevere, drop, or re-scope") instead of starving it. This converts a would-be silent prune into a surfaced consequential decision.

---

## 7. Component — escalate-pain experiment + re-bench

### 7.1 Multi-cycle accumulating-damage scenario (live `claude_cli`)
A bench scenario where the same task signature fails repeatedly across cycles under a held latch, so scars accumulate and markers strengthen. Run on the live `claude_cli` backend (Max sub), with the marker **diagnoses** injected. Observe, per cycle: scars written, marker weights/counts, the advisory re-rank, and — the honest question — whether the live model's generations show **unbidden** avoidance (declines the scarred approach without being told it failed) or still need prompting. Record the trace; do not over-claim (today's null result is the baseline).

### 7.2 Re-bench ON vs OFF (markers active)
Extend the deterministic bench: a scenario with a recoverable-by-rerouting fault, run nervous-ON-with-markers vs OFF. Headline metric additions: `scars_written`, `markers_recalled`, `reroutes` (dispatches whose spec carried a prior-pain diagnosis), and whether ON reaches the goal in fewer wasted cycles than OFF by *avoiding* the scarred path. Reproducible across N reps (declared), spread reported — same rigor as v1.

---

## 8. Data model, config & file layout

### New files
- `director/memory/markers.py` — `Marker` dataclass + `MarkerStore` (record/recall/merge, VectorStore-backed).
- `director/bench/` additions — the multi-cycle scenario + ON/OFF-with-markers metrics (extend `scenarios.py`/`driver.py`/`report.py`).

### New `Project` field (`director/core/types.py`)
- `marker_deferrals: dict[str, int] = field(default_factory=dict)` — per-task advisory-deferral counters (round-trips via existing decode; zero migration).

### New config keys (`director/config.py`, behind the existing nervous block)
- `marker_recall_sim: float = 0.6` — cosine threshold to recall a scar for a signature.
- `marker_merge_sim: float = 0.9` — cosine threshold to merge-and-strengthen vs insert.
- `marker_repel_step: float = 0.5` — weight made more-repellent per occurrence.
- `marker_repel_floor: float = -3.0` — clamp so one signature can't dominate.
- `marker_defer_escalate_cycles: int = 3` — advisory deferrals before a packet escalation.
- `markers_filename: str = "markers_index.json"` — sibling to the lesson index under `home`.

### Edits (hooks + recall, all `nervous_enabled`-guarded)
- `director/core/director.py` — Credit Knife record at the FAILED-ingest site + in `_handle_siren`; Gut Markers recall + advisory re-rank + deferral/escalation in `advance()`; diagnosis injection in `_spec_for`; hold a `self.markers: MarkerStore | None` on `__init__` (default None; constructed when `nervous_enabled`).
- `director/core/types.py` — the `marker_deferrals` field + a `task_signature(task)` helper (or put the helper in `markers.py`).

---

## 9. Testing plan

- **Unit — MarkerStore:** record inserts; a second record of the same signature MERGES-and-strengthens (weight more negative, count 2) rather than dropping (the explicit `_DEDUPE_SIM`-fix regression); recall returns markers ≥ `marker_recall_sim` and excludes below it; offline/deterministic round-trip of `markers_index.json`.
- **Unit — Credit Knife:** a FAILED task writes a `failed_verification` scar with a diagnosis containing the failing case + NO numeric valence/threshold (problems-not-rubrics assertion); a transient-retry READY task writes NOTHING (resolve-before-scarring); a siren writes scars for its `origin_refs`; plan/hook tasks (empty `origin_decision_id`) get the synthetic origin.
- **Unit — Gut Markers bias:** the canonical `ready_tasks` order is UNCHANGED (determinism); the advisory order repels a scarred signature; a dispatched scarred task's spec carries the diagnosis; deferral past `marker_defer_escalate_cycles` raises a packet (no silent starvation).
- **Determinism / OFF-path:** with `nervous_enabled=False`, the markers store is never constructed/read/written and dispatch + the full existing suite are byte-identical (the v1 + v2 suites stay green).
- **Integration (deterministic bench):** a recoverable-by-rerouting scenario where ON-with-markers avoids the scarred path and recovers in fewer wasted cycles than OFF; reproducible across N reps.
- **Live (manual, `claude_cli`):** the §7.1 escalate scenario, observed not asserted (record the trace; the unbidden-avoidance question is exploratory).

---

## 10. Risks & open items

- **Marker over-repel.** A strong scar could starve a signature that would now succeed. Mitigations: the `marker_repel_floor` clamp, the deferral→escalation packet (the human can override), and recall similarity tuning from the bench (declared constants, tuned from findings — same discipline that surfaced the v1 uncertainty recalibration).
- **Signature collisions / drift.** Objective-normalization for the signature must be stable but not so coarse it conflates distinct work. Start with `role|module_id|lowercased-trimmed-objective`; tune from bench false-recall rate.
- **Goodhart (re-confirmed out of scope).** Diagnoses-only keeps the model blind to the weight; the avoidance is driven by a *problem*, not a metric. If a future operator opts into raw-broadcast, this risk returns — fenced to v3.
- **The honest null.** Today's live result is no unbidden self-modeling. v2 is not expected to overturn that; the experiment measures it, and a continued null is a legitimate, reportable outcome.
- `task_signature` normalization specifics and the exact `_spec_for` injection field name are confirmed at implementation against the then-current source.
