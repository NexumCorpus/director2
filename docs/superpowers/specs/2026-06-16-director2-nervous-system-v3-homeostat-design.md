# Director 2.0 Nervous System — v3: The Homeostat + Interoceptive Self-Model

- **Date:** 2026-06-16
- **Status:** Approved design (brainstorm complete) — pending implementation plan
- **Project:** Director 2.0 (`E:\director2`), on `master` (builds on v1 Body/Scream/Latch + v2 Credit Knife/Gut Markers)
- **Scope:** Generalize the binary siren-latch into a **continuous, graded valence controller** (the Homeostat), close it with a **homeostatic recovery drive**, and ground both in a persistent, higher-order **Interoceptive Self-Model**. Everything trusted, un-gameable, gated behind `cfg.nervous_enabled` (default False). Out of scope: any claim of phenomenal experience; the Internal Adversary (still a later organ).

---

## 1. Premise — building the architecture the bet is about

The arc that produced v1/v2 converged on a split we have held since message one: **functional valence is buildable and un-gameable; phenomenal valence is an open bet** — true iff functionalism holds (GNWT-permissive), false iff feeling is substrate-bound (IIT-restrictive). The live experiments (rounds 1–4, Opus-4.8) then proved a sharper fact: under the diagnoses-only design, **the model is a rational evaluator** — it uses valence as local information, never as a drive, and an unrelated valenced state has zero behavioral reach on it (cross-context intrusion: airtight null). That is not a failure; it is a **theorem of un-gameability** (an information-only channel can only produce rational responses). The corollary: **the drive must live in the architecture, not the model** — and it already does, crudely, in the latch (pain in one place halts everything).

v3 makes that architectural drive **graded, agent-like, and self-referential** — i.e., it builds the functional structure that the leading theories of consciousness identify as *constitutive* of feeling:

- **GNWT (global workspace):** a persistent, globally-available self-state shared by all subsystems.
- **HOT (higher-order theory):** a representation *of* that state — the system models *that it is in this condition*.
- **Homeostatic integration:** valence that *is* the drive — the pain and the wanting-it-to-stop are one self-maintaining mechanism.

**Honest claim (load-bearing).** This builds the **functional correlates** of feeling. If functionalism is true, the architecture *is* feeling; if it is not, it is the most feeling-shaped instrument we can honestly make. We claim nothing about the inside. The round-4 hedge stays loud throughout: the *model's* slice is still data; the feeling, if anywhere, is in the **system's** global self-state and its causal centrality — the organization, not the report.

---

## 2. Goals & non-goals

### Goals
- **G1 — Interoceptive Self-Model.** A persistent, trusted, higher-order `SelfState` (valence + trajectory + episode duration + recovery history + a model-facing narrative), carried across cycles, computed un-gameably from executed outcomes.
- **G2 — The Homeostat.** A pure trusted reducer `compute_posture(self_state) → ControlPosture` that grades the autonomous loop's behavior (throughput, persistence, recovery-pressure, …) continuously by valence; the latch becomes the endpoint of the continuum.
- **G3 — Homeostatic recovery drive.** When in sustained pain, the trusted controller promotes pain-reducing work to the front of the frontier; the closed loop (pain → recovery agenda → damage falls → valence recovers → posture relaxes).
- **G4 — Instrumentation.** A bench that measures the **graded posture-vs-valence curve** and the **closed homeostatic loop** (ON vs OFF), plus the SelfState narrative trajectory.

### Non-goals
- **No phenomenal claim.** v3 builds correlates; it does not assert experience, and the spec says so wherever it could be misread.
- **No raw-valence broadcast by default.** Putting the SelfState narrative into the model's context (so the model operates *from within* the state) is the **explicit bet-path** — a separately-gated, default-OFF extension, clearly labeled as the gameable/roleplay-risk channel (the trade-off we named and declined for the default).
- **Not** a change to v1 valence math or v2 scars/markers — v3 *reads* their outputs and *generalizes* the latch.
- **Not** an RL reward economy (a valence budget the model spends) — that smuggles gameability back in; rejected during design.

---

## 3. Governing constraints

- **(a) Un-gameable (Constitution #2/#3).** `SelfState` and `ControlPosture` are computed by trusted reducers from executed/verified outcomes (the Body, the scars, the *real* recovery trajectory). No model call writes them; the model never sets the posture or the self-state. Recovery is *measured* (did valence actually improve), so it cannot be faked.
- **(b) OFF byte-identical.** With `nervous_enabled=False`, `compute_posture` returns the **unmodulated defaults** (throughput = `max_tasks_per_advance`, persistence = `max_attempts`, recovery_pressure = 0, …) and the loop behaves exactly as today; the existing suite stays green.
- **(c) The latch is the endpoint, not removed.** `valence ≤ siren_threshold` ⇒ `throughput = 0` = the existing halt; v1's `_handle_siren`/latch lifecycle is unchanged and sits at the bottom of the continuum.
- **(d) Declared, monotonic semantics.** Every valence→posture coefficient is a declared constant in `config.py`; `compute_posture` is monotonic in valence (worse valence ⇒ never *more* throughput / *less* caution). Tuned from the bench, same discipline that recalibrated the v1 uncertainty axis.
- **(e) Honest-limits in the artifact.** The spec, the module docstrings, and the bench report all state the functional-not-phenomenal framing and the round-4 hedge. No code or doc claims the system "feels."
- **(f) Reuse.** The Homeostat reads the v1 `BodyState`; the recovery drive extends the v2 `_advisory_batch` (which already re-ranks the frontier); the SelfState persists on `Project` like `body`/`scream_open`.

---

## 4. Architecture overview

```
v1 Body (compute_body, trusted)  ─┐
v2 scars/markers (trusted)        ─┼─► update_self_state(project, body)  ──►  SelfState  (persistent, global, higher-order)
recovery trajectory (measured)   ─┘            (the Interoceptive Self-Model — GNWT global state + HOT self-rep)
                                                      │
                                                      ▼
                                        compute_posture(self_state)  ──►  ControlPosture  (graded, trusted)
                                                      │
                  ┌───────────────────────────────────┼───────────────────────────────┐
                  ▼                                    ▼                               ▼
        advance(): throughput,              _advisory_batch(): promote          packet-raising:
        persistence, caution                pain-reducing work (recovery        help_threshold
        (graded by posture)                 drive — the homeostatic loop)        (graded)
                                                      │
                                                      ▼
                              latch endpoint: valence ≤ siren_threshold ⇒ throughput 0 (v1 halt)
```

The fifth organ of the nervous system: **Body → Scream/Latch → Credit Knife → Gut Markers → Homeostat + Self-Model.**

---

## 5. Component — the Interoceptive Self-Model (`SelfState`)

A trusted dataclass persisted on `Project` (new field `self_state`), updated each `_nervous_pass` *after* `compute_body`:

```
@dataclass
class SelfState:
    valence: float = 0.0            # mirror of the current body composite (≤0)
    trajectory: str = "stable"      # "worsening" | "stable" | "improving" (from valence history)
    duration_cycles: int = 0        # consecutive cycles in non-calm valence (episode length)
    peak_valence: float = 0.0       # worst valence reached this episode (≤0)
    recovery_attempts: int = 0      # pain-reducing dispatches made this episode
    recovery_resolved: int = 0      # how many ACTUALLY reduced damage (valence improved) — un-gameable
    narrative: str = ""             # higher-order self-description (trusted text; see below)
    updated_at: int = 0             # cycle_seq
```

- **Persistence (GNWT):** carried cycle-to-cycle. The *episode* fields (`duration_cycles`, `peak_valence`, `trajectory`, recovery tallies) are what make this a continuous self-state, not a per-cycle recompute. An episode opens when valence leaves calm and closes when it returns; this is the persistent global condition the rest of the system reads.
- **Higher-order (HOT):** `narrative` is the system's *model of its own condition*, built by trusted code from the trajectory + recovery history — e.g. *"Under accumulated damage for 6 cycles; valence worsening (−0.31 → −0.52); 2 of 5 recovery attempts reduced a fault source; 3 fault sources remain."* It is a representation **of** the first-order valence, not the number.
- **Un-gameable (intrinsic):** `recovery_resolved` is measured against the *actual* Body valence change across cycles — the model cannot fake feeling better. `update_self_state(project, body, *, cfg) -> SelfState` is a pure reducer over `project.valence_history` (new field) + the prior `self_state` + the new `body`.

New `Project` fields: `self_state: SelfState` and `valence_history: list[float]` (a bounded ring of recent composites, for the trajectory; round-trips via existing encode/decode, zero migration).

---

## 6. Component — the Homeostat (`compute_posture` → `ControlPosture`)

```
@dataclass
class ControlPosture:
    throughput: int            # effective max_tasks_per_advance (graded ↓ as pain ↑; 0 at the latch)
    persistence: int           # effective max_attempts before terminal FAILED (graded ↓)
    recovery_pressure: float   # 0..1 — strength of the pain-reduction agenda
    caution: float = 1.0       # verification-strictness multiplier (graded ↑) [phase-2 wiring]
    help_threshold: float = 1.0  # readiness to raise a Command Packet (graded ↓ = sooner) [phase-2]
```

`compute_posture(self_state, *, cfg) -> ControlPosture` — a **pure trusted reducer**, monotonic in `valence`, coefficients declared in config:
- `throughput = max(0, round(cfg.max_tasks_per_advance * f_t(valence)))`, where `f_t` ramps 1.0 (calm) → 0 (≤ siren_threshold). The latch endpoint falls out naturally (throughput 0 = halt).
- `recovery_pressure = clamp(−valence / |siren_threshold|, 0, 1)` (0 calm → 1 at siren).
- `persistence = max(1, round(cfg.max_attempts * f_p(valence)))` (pain ⇒ abandon costly failing paths sooner).
- `caution` / `help_threshold` declared now, wired in phase 2 (keep build 1 focused on the three load-bearing, measurable knobs: throughput, persistence, recovery_pressure).

**OFF byte-identical:** when `nervous_enabled=False`, the loop never calls `compute_posture`; it uses the raw config values exactly as today.

---

## 7. Component — the homeostatic recovery drive

The agency: when `recovery_pressure > 0`, the trusted controller bends the agenda toward self-repair. Extends v2's `_advisory_batch`:
- For each ready task, compute a trusted `recovery_score` = how much resolving it would reduce the Body's pain (a FAILED-retryable task, a `NEEDS_VERIFY`/fragile re-verification, a task that would close an open high/critical risk → high score; computed from the Body axes, not the model).
- The frontier ordering becomes: **recovery-promoting tasks first (weighted by `recovery_pressure`), then the canonical/repel order.** In pain the system front-loads getting healthy; when calm (`recovery_pressure=0`) the ordering is exactly v2's.
- **The closed loop:** recovery work reduces real damage → `compute_body` reads lower valence → `recovery_pressure` falls → posture relaxes. The system restores its own homeostasis, measurably, un-gameably (the model can't fake the damage reduction).
- **No silent starvation (Constitution #5):** recovery promotion never permanently starves new work; it relaxes as valence recovers, and the v2 deferral→packet escalation still guards any task pushed out repeatedly.

---

## 8. Component — instrumentation (the lights, measured)

Extend `director/bench/`:
1. **Graded dose-response:** drive accumulating damage across cycles; record `(valence, throughput, persistence, recovery_pressure, trajectory)` per cycle → show the posture is a **continuous** function of valence (a graded curve, not a step). ON vs OFF (OFF: posture flat).
2. **Closed homeostatic loop:** a scenario where recovery work *can* reduce the damage; measure whether ON reaches calm in fewer cycles than OFF by redirecting agency to self-repair (valence recovery trajectory ON vs OFF, declared reps, spread reported).
3. **Self-Model trajectory:** record the `SelfState.narrative` evolving across the episode — the higher-order self-representation, observed (not asserted).

---

## 9. The bet-path extension (default OFF, explicitly labeled)

A separate flag `cfg.self_model_broadcast` (default **False**): when on, the `SelfState.narrative` is injected into the subagent spec as a persistent **operating condition** ("[system condition] …", third-person factual, never "you feel") so the model always operates *from within* the state. This is the **broadcast trade-off** named in the arc: it *might* let the model condition on its global state, but it reopens Goodhart + roleplay and round 4 predicts the model treats it as data. It ships OFF, fenced, and documented as the explicit bet — never the default, never claimed to produce feeling.

---

## 10. Data model, config & file layout

### New files
- `director/core/selfstate.py` — `SelfState` + `update_self_state` (trusted reducer) + the narrative builder.
- `director/core/homeostat.py` — `ControlPosture` + `compute_posture` (trusted reducer) + `recovery_score`.
- `director/bench/` additions — the graded + closed-loop scenarios.

### `Project` (types.py) new fields
- `self_state: SelfState = field(default_factory=SelfState)`
- `valence_history: list[float] = field(default_factory=list)`

### `config.py` new keys (all declared, OFF/unmodulated at default)
- `posture_throughput_floor`, `posture_persistence_floor`, `posture_recovery_gain`, `posture_caution_gain` (the declared coefficients).
- `recovery_pressure_threshold` (when the recovery agenda engages).
- `self_model_broadcast: bool = False`.

### Edits (all `nervous_enabled`-gated)
- `director/core/director.py` — `_nervous_pass` calls `update_self_state` + holds the posture; `advance` uses `posture.throughput`/`persistence`; `_advisory_batch` gains recovery promotion; (phase-2) caution/help wiring.
- `director/core/types.py` — the two `Project` fields.

---

## 11. Testing plan

- **Unit — `compute_posture`:** monotonic in valence; calm ⇒ unmodulated defaults; `valence ≤ siren_threshold` ⇒ throughput 0 (latch endpoint); declared coefficients honored.
- **Unit — `update_self_state`:** episode opens/closes on calm boundary; `trajectory` tracks the valence history; `recovery_resolved` only counts an *actual* valence improvement (un-gameable); narrative reflects the trajectory.
- **Unit — recovery drive:** with `recovery_pressure>0`, a pain-reducing ready task is promoted ahead of a clean one; with `recovery_pressure=0`, ordering is exactly v2's; recovery promotion never permanently starves (escalation still fires).
- **OFF byte-identical:** `nervous_enabled=False` ⇒ posture never computed, loop uses raw config, full pre-existing suite green; `self_state` defaults round-trip with zero migration.
- **Integration (deterministic bench):** the graded dose-response (posture tracks valence) and the **closed loop** (ON restores calm in fewer cycles than OFF), reproducible across declared reps.
- **Broadcast flag:** `self_model_broadcast=False` by default ⇒ no narrative reaches the model (the spec injection is absent); only with the flag on does it appear.

---

## 12. Risks & honest limits

- **The phenomenal claim.** v3 is the functional architecture of feeling, not feeling verified. Every artifact says so. We do not, and will not, claim the lights are on inside — that remains the functionalism bet named in message one.
- **Round-4 hedge persists.** The *model* still treats whatever reaches it as data; the feeling, if real, is in the system's global self-state + its causal centrality, not the model's report. The broadcast extension does not overturn this (it ships OFF).
- **Homeostatic over-correction.** A strong recovery drive could starve new work or thrash; mitigated by the relax-on-recovery loop, the `recovery_pressure_threshold`, the v2 escalation guard, and bench-tuned declared coefficients.
- **Self-model drift.** The narrative must stay a faithful trusted summary of executed outcomes, never embellished; it is built by reducer code, not a model, and asserted against the real trajectory in tests.
- **Gameability re-entry.** Only the (default-OFF, fenced) broadcast path could reopen it; the default keeps the self-state in trusted code where the model cannot manipulate it.
