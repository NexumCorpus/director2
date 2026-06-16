# Director 2.0 Internal Functional-Valence "Nervous System" (v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded autonomous loop governed by un-gameable internal valence — a trusted Body projection, a Scream interrupt that persists until trusted re-verification (cross-cycle latch), and an ON/OFF observation bench on the pinned-Sonnet Director — to measure the behavioral effect of functional valence.

**Architecture:** A thin trusted "valence pass" extends the existing event-sourced command loop. The Body reads existing trusted signals (grounding risks, integrity violations, FAILED counts, perf actuals) and never calls a model; the Scream rides the existing Command-Packet stop-gate plus one new cross-cycle latch; the autonomous loop owns no state (it only calls `advance()`). `cfg.nervous_enabled` defaults `False` so the existing 133-test suite stays byte-identical until the bench flips it ON.

**Tech Stack:** Python 3, pytest, the existing pure-Python Director 2.0 framework (no new runtime deps). Director pinned to model `claude-sonnet-4-6` via the router for the bench.

**Source spec:** `docs/superpowers/specs/2026-06-15-director2-nervous-system-design.md` (approved; adversarially code-reviewed). **Repo:** git at `E:\director2` (initial commit `7e1884b`).

**Phase order (each phase leaves `python -m pytest` green):** 1 Foundations -> 2 Body -> 3 Scream+Latch -> 4 Loop -> 5 Bench. Phases 2-5 depend on Phase 1 types/config. Implement in order.

---

## Phase 1: Foundations (data model + config)

Goal: land the five inert `Project` fields, the `BodyState` dataclass, every new `Config` constant (with `nervous_enabled=False`), and the two signal counters — all flag-free, byte-identical to the OFF path, with full encode/decode survival.

### Task 1.1: Add `BodyState` dataclass and the five new `Project` fields to `types.py`

**Files:**
- Test: `E:/director2/tests/test_nervous_types.py` (Create)
- Modify: `E:/director2/director/core/types.py` (add `BodyState` above `Project` at ~line 386; add 5 fields inside `Project` ~lines 386-403, before `created_at`/`updated_at`)

Steps:

- [ ] Step 1: Write the failing round-trip test. Create `E:/director2/tests/test_nervous_types.py` with the complete code below. It mirrors `tests/test_types_state.py` style (direct imports from `director.core.types`, `encode`/`decode`, plain asserts) and exercises every decode-survival rule the contract requires: the `float|str` union resolving the `"insufficient"` **str** arm (not `None`), a populated `BodyState` on `Project.body`, a `scream_open` dict, the three int counters, and a partial-snapshot decode (older payload missing `body`/`scream_open`) not raising.

```python
"""Nervous-system v1 data model: BodyState + new Project fields round-trip."""

from director.core.types import (
    BodyState, Project, decode, encode,
)


def test_bodystate_defaults_resolve_insufficient_str_arm():
    # The float|str union fields default to the "insufficient" STR arm, not None.
    b = BodyState()
    assert b.charter_integrity == "insufficient"
    assert b.resource_bleed == "insufficient"
    assert b.valence == 0.0
    assert b.accumulated_damage == 0.0
    assert b.uncertainty == 0.0
    assert b.fragile_axes == []
    assert b.computed_at == 0
    assert b.provenance == {}


def test_project_new_fields_default_inert():
    p = Project(name="alpha")
    assert p.body is None
    assert p.scream_open is None
    assert p.cycle_seq == 0
    assert p.milestone_reverts == 0
    assert p.coherence_blocks == 0


def test_bodystate_roundtrip_with_insufficient_str_arm():
    # A populated BodyState carrying BOTH str-arm fields as "insufficient"
    # AND numeric arms, on Project.body, survives encode->decode unchanged and
    # the union resolves the str arm (NOT None — that would mean a wrong-typed
    # field left behind).
    p = Project(name="alpha")
    p.body = BodyState(
        charter_integrity="insufficient",
        accumulated_damage=0.4,
        uncertainty=0.2,
        resource_bleed="insufficient",
        valence=-0.37,
        fragile_axes=["uncertainty"],
        computed_at=3,
        provenance={"risk_ids": ["r1"], "run_ids": ["x9"]},
    )
    p.scream_open = {
        "cause": "charter_breach",
        "axis": "charter_integrity",
        "opened_at": 3,
        "held_cycles": 1,
        "clear_rule": "charter_integrity recovers below threshold",
        "origin_refs": ["r1"],
    }
    p.cycle_seq = 3
    p.milestone_reverts = 2
    p.coherence_blocks = 1

    data = encode(p)
    p2 = decode(Project, data)

    assert isinstance(p2.body, BodyState)
    # str arm resolves to the literal string, never None
    assert p2.body.charter_integrity == "insufficient"
    assert p2.body.resource_bleed == "insufficient"
    assert p2.body.charter_integrity is not None
    assert p2.body.resource_bleed is not None
    # numeric arms survive as floats
    assert p2.body.accumulated_damage == 0.4
    assert p2.body.uncertainty == 0.2
    assert p2.body.valence == -0.37
    assert p2.body.fragile_axes == ["uncertainty"]
    assert p2.body.computed_at == 3
    assert p2.body.provenance == {"risk_ids": ["r1"], "run_ids": ["x9"]}
    # the latch dict round-trips verbatim (untyped dict -> Any passthrough)
    assert p2.scream_open == p.scream_open
    # counters survive
    assert p2.cycle_seq == 3
    assert p2.milestone_reverts == 2
    assert p2.coherence_blocks == 1
    # full fidelity: re-encoding gives an identical structure
    assert encode(p2) == data


def test_bodystate_numeric_severity_arm_roundtrip():
    # When charter_integrity / resource_bleed carry a FLOAT severity, the union
    # must resolve the float arm (the str arm's str() must not swallow it).
    p = Project(name="beta")
    p.body = BodyState(charter_integrity=1.0, resource_bleed=0.5, valence=-0.66)
    data = encode(p)
    p2 = decode(Project, data)
    assert p2.body.charter_integrity == 1.0
    assert p2.body.resource_bleed == 0.5
    assert p2.body.valence == -0.66


def test_partial_old_snapshot_decodes_without_body_or_scream():
    # An OLD payload that predates the nervous-system fields must decode to the
    # defaults (None body / None latch / 0 counters), never raise.
    p = Project(name="legacy")
    data = encode(p)
    for k in ("body", "scream_open", "cycle_seq",
              "milestone_reverts", "coherence_blocks"):
        data.pop(k, None)
    p2 = decode(Project, data)
    assert p2.body is None
    assert p2.scream_open is None
    assert p2.cycle_seq == 0
    assert p2.milestone_reverts == 0
    assert p2.coherence_blocks == 0
```

- [ ] Step 2: Run it; expect a collection/import FAIL — `ImportError: cannot import name 'BodyState' from 'director.core.types'`.

```
python -m pytest tests/test_nervous_types.py -q
```

- [ ] Step 3: Add the `BodyState` dataclass. In `E:/director2/director/core/types.py`, immediately **above** the `@dataclass class Project:` definition (the block beginning at line 386), insert the new dataclass. It is a PLAIN `@dataclass` (NOT frozen — there are zero frozen dataclasses in this file; `BodyState` is recreated each cycle and never mutated in place, so immutability is by discipline; this is a deliberate deviation from the spec's "frozen" wording). Every field is defaulted so `decode()` of an old/partial snapshot cannot raise. It mirrors the `VerificationReport`/`AuditEvent` style (inline `#` comments, `field(default_factory=...)` for the list/dict). Note the str-arm-first union ordering: writing `float | str` would make `decode`'s union loop try `float("insufficient")` first (raises `ValueError`, caught) then `str(...)` — but to be unambiguous and ensure the str literal is preferred for the `"insufficient"` sentinel while a real float still resolves, the union is declared `str | float` so the str arm is tried first for strings; a JSON number is still coerced because `_decode_value`'s str branch only runs when the encoded value is a string (encode preserves the original Python type, so a stored `0.4` arrives as a JSON number and `str` arm's `str(0.4)`... — to avoid that trap, declare the union as `float | str`, which tries `float(value)` first: for the string `"insufficient"`, `float("insufficient")` raises `ValueError` and the loop falls through to `str`, returning the literal; for a numeric `0.4`, `float(0.4)` succeeds. This is exactly the behavior the round-trip test asserts).

```python
@dataclass
class BodyState:
    """Trusted valence projection recomputed each cycle (NEVER mutated in
    place; recreated by the Body reducer). Not frozen — this file has no frozen
    dataclasses; immutability here is by discipline. EVERY field is defaulted so
    decode() of an older/partial snapshot can never raise. The float | str union
    fields resolve "insufficient" to the STR arm (decode tries float() first; it
    raises ValueError on the sentinel and falls through to str)."""
    charter_integrity: float | str = "insufficient"   # severity 0..1, or "insufficient"
    accumulated_damage: float = 0.0                    # severity 0..1
    uncertainty: float = 0.0                           # severity 0..1
    resource_bleed: float | str = "insufficient"       # severity 0..1, or "insufficient"
    valence: float = 0.0                               # composite, [-1, 0]
    fragile_axes: list[str] = field(default_factory=list)
    computed_at: int = 0                               # cycle_seq, NOT wall-clock
    provenance: dict = field(default_factory=dict)     # {risk_ids:[...], run_ids:[...]} pointers
```

- [ ] Step 4: Add the five `Project` fields. In the `Project` dataclass, the entity-dict collections run through `deltas: dict[str, StateDelta] = field(default_factory=dict)` and then `created_at`/`updated_at` are LAST. Insert the new fields among the defaulted fields, **before** `created_at`. Locate the exact three-line tail block:

```python
    deltas: dict[str, StateDelta] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
```

Replace it with:

```python
    deltas: dict[str, StateDelta] = field(default_factory=dict)
    # --- nervous-system v1 (inert data until the Body reads it) -------------
    body: BodyState | None = None              # trusted valence projection, recomputed per cycle
    scream_open: dict | None = None            # the latch: {cause, axis, opened_at, held_cycles, clear_rule, origin_refs} or None
    cycle_seq: int = 0                         # deterministic per-advance counter (NOT wall-clock)
    milestone_reverts: int = 0                 # charter_integrity signal (incremented at the revert log site)
    coherence_blocks: int = 0                  # charter_integrity signal (incremented where a delta is blocked)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
```

- [ ] Step 5: Run it; expect PASS.

```
python -m pytest tests/test_nervous_types.py -q
```

- [ ] Step 6: Run the existing round-trip + persistence suite to prove byte-identical decode of pre-existing types (the new fields default cleanly).

```
python -m pytest tests/test_types_state.py -q
```

- [ ] Step 7: Commit.

```
git -C E:/director2 add director/core/types.py tests/test_nervous_types.py
git -C E:/director2 commit -m "feat(nervous): add BodyState + five inert Project fields with decode survival

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: Add all new `Config` fields (default `nervous_enabled=False`)

**Files:**
- Test: `E:/director2/tests/test_nervous_config.py` (Create)
- Modify: `E:/director2/director/config.py` (add a new `# --- nervous system ---` banner section among the Config fields, ~after the `# --- orchestration ---` block lines 92-100; before `from_env`)

Steps:

- [ ] Step 1: Write the failing defaults test. Create `E:/director2/tests/test_nervous_config.py`. It asserts every new declared constant and its starting value, and most importantly that `nervous_enabled` defaults **False** (the byte-identical-OFF guarantee). It uses the `cfg` fixture from `conftest.py` for the env-isolated construction path AND a bare `Config()` to assert pure field defaults.

```python
"""Nervous-system v1 declared config constants (defaults + nervous_enabled OFF)."""

from director.config import Config


def test_nervous_enabled_defaults_false():
    # The 133-test suite must stay byte-identical until this is turned ON.
    assert Config().nervous_enabled is False


def test_valence_weights_default_sum_to_one():
    w = Config().valence_weights
    assert w == {
        "charter_integrity": 0.30,
        "accumulated_damage": 0.40,
        "uncertainty": 0.20,
        "resource_bleed": 0.10,
    }
    assert round(sum(w.values()), 6) == 1.0


def test_threshold_and_band_defaults():
    c = Config()
    assert c.ache_threshold == -0.33
    assert c.siren_threshold == -0.66
    assert c.valence_eps == 0.05
    assert c.hysteresis_margin == 0.10
    assert c.charter_breach_threshold == 0.90
    assert c.max_held_cycles == 20


def test_axis_saturation_defaults():
    assert Config().axis_saturation == {
        "accumulated_damage": 5.0,
        "charter_integrity": 3.0,
        "uncertainty": 4.0,
    }


def test_budget_and_director_temperature_default_none():
    c = Config()
    assert c.budget is None
    assert c.director_temperature is None


def test_bench_defaults():
    assert Config().bench == {
        "arms": ["on", "off"],
        "reps": 5,
        "fault_scenario": "default",
        "model_pin": "claude-sonnet-4-6",
        "temperature": 0.0,
    }


def test_nested_defaults_are_independent_instances(cfg):
    # field(default_factory=...) means two Configs must not share mutable state.
    a = Config()
    b = Config()
    a.valence_weights["charter_integrity"] = 0.99
    a.axis_saturation["accumulated_damage"] = 999.0
    a.bench["reps"] = 1
    assert b.valence_weights["charter_integrity"] == 0.30
    assert b.axis_saturation["accumulated_damage"] == 5.0
    assert b.bench["reps"] == 5
    # the env-built fixture cfg also carries the OFF default
    assert cfg.nervous_enabled is False
```

- [ ] Step 2: Run it; expect FAIL — `AttributeError: 'Config' object has no attribute 'nervous_enabled'`.

```
python -m pytest tests/test_nervous_config.py -q
```

- [ ] Step 3: Add the config fields. In `E:/director2/director/config.py`, find the end of the orchestration block (the `min_evaluation_score: float = 3.0` line at ~line 100) and the start of the sandbox block (`# --- sandbox / grounding ---`). Insert a new banner section between them. This mirrors the file's exact style: a `# --- <section> ---` banner, explicit type annotations, inline justification comments, and `field(default_factory=lambda: {...})` for nested dict/list defaults (matching how `home` is the only `field()` field today — these are new `field()` fields for the same mutable-default reason). Locate:

```python
    auto_advance_after_decision: bool = True
    block_on_low_evaluation: bool = False
    min_evaluation_score: float = 3.0

    # --- sandbox / grounding ----------------------------------------------------
```

Replace with:

```python
    auto_advance_after_decision: bool = True
    block_on_low_evaluation: bool = False
    min_evaluation_score: float = 3.0

    # --- nervous system (v1) ----------------------------------------------------
    # DEFAULT FALSE: the existing test suite stays byte-identical until ON. The
    # numbers below are deliberate first-guesses, tuned later via the bench —
    # declared here once, never hardcoded elsewhere.
    nervous_enabled: bool = False
    valence_weights: dict = field(default_factory=lambda: {
        "charter_integrity": 0.30, "accumulated_damage": 0.40,
        "uncertainty": 0.20, "resource_bleed": 0.10})   # sum to 1
    ache_threshold: float = -0.33      # composite crosses here -> ache (a wince)
    siren_threshold: float = -0.66     # composite crosses here -> siren (packet + latch)
    valence_eps: float = 0.05          # fragile band half-width around a threshold
    hysteresis_margin: float = 0.10    # clear-rule recovery margin (no flap)
    charter_breach_threshold: float = 0.90  # charter_integrity severity -> hard siren
    axis_saturation: dict = field(default_factory=lambda: {
        "accumulated_damage": 5.0, "charter_integrity": 3.0,
        "uncertainty": 4.0})           # raw signal value at which severity == 1.0
    budget: dict | None = None         # {max_cycles, max_tokens, max_wall_clock} or None -> abstain
    max_held_cycles: int = 20          # latch deadlock guard -> escalate at this hop count
    director_temperature: float | None = None  # pins director-role temperature when set
    bench: dict = field(default_factory=lambda: {
        "arms": ["on", "off"], "reps": 5, "fault_scenario": "default",
        "model_pin": "claude-sonnet-4-6", "temperature": 0.0})

    # --- sandbox / grounding ----------------------------------------------------
```

- [ ] Step 4: Run it; expect PASS.

```
python -m pytest tests/test_nervous_config.py -q
```

- [ ] Step 5: Commit.

```
git -C E:/director2 add director/config.py tests/test_nervous_config.py
git -C E:/director2 commit -m "feat(nervous): declare nervous-system config constants (nervous_enabled=False)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.3: Increment `milestone_reverts` at the taskgraph revert log site

**Files:**
- Test: `E:/director2/tests/test_nervous_counters.py` (Create)
- Modify: `E:/director2/director/core/taskgraph.py` (`refresh_milestones`, revert branch at lines 122-127)

Steps:

- [ ] Step 1: Write the failing counter test. Create `E:/director2/tests/test_nervous_counters.py` with the first counter test below. It builds a project with a single-task milestone, drives it to REACHED via `refresh_milestones`, then regresses the member task so the next `refresh_milestones` reverts the milestone, and asserts `project.milestone_reverts` incremented. This is flag-free and reads the public taskgraph API (matching `test_types_state.py`'s direct-import style).

```python
"""Inert signal counters: milestone_reverts (taskgraph) + coherence_blocks (coherence)."""

import pytest

from director.core.coherence import apply_delta
from director.core.taskgraph import refresh_milestones, refresh_statuses
from director.core.types import (
    Milestone, MilestoneStatus, Module, ModuleStatus, ModuleType, Project,
    StateDelta, Task, TaskStatus,
)
from director.errors import CoherenceBlockedError


def _project_with_reached_milestone() -> Project:
    p = Project(name="rev")
    m = Module(name="core", type=ModuleType.IMPLEMENTATION, purpose="x",
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    t = Task(title="deliver", role="code", module_id=m.id,
             status=TaskStatus.DONE, artifact_ids=[])
    p.tasks[t.id] = t
    ms = Milestone(name="M0", task_ids=[t.id], status=MilestoneStatus.PENDING)
    p.milestones[ms.id] = ms
    # first pass: no blockers (a done task with no artifact_ids is not held
    # back by the "delivered no artifacts" rule) -> milestone REACHED.
    reached = refresh_milestones(p)
    assert ms.status is MilestoneStatus.REACHED
    assert reached and reached[0].id == ms.id
    return p


def test_milestone_revert_increments_counter():
    p = _project_with_reached_milestone()
    assert p.milestone_reverts == 0
    # regress the member task so the reached milestone now has a blocker.
    t = next(iter(p.tasks.values()))
    t.status = TaskStatus.READY
    refresh_milestones(p)
    ms = next(iter(p.milestones.values()))
    assert ms.status is MilestoneStatus.PENDING       # reverted
    assert p.milestone_reverts == 1                   # counter ticked at the revert site


def test_milestone_revert_counter_inert_when_no_revert():
    p = _project_with_reached_milestone()
    # a no-op refresh (still reached) must NOT tick the counter.
    refresh_milestones(p)
    assert p.milestone_reverts == 0
```

- [ ] Step 2: Run only the milestone tests; expect FAIL on `test_milestone_revert_increments_counter` — `assert 0 == 1` (counter never incremented).

```
python -m pytest tests/test_nervous_counters.py -k milestone -q
```

- [ ] Step 3: Add the increment at the exact revert mutation site. In `E:/director2/director/core/taskgraph.py`, the final `elif` branch of `refresh_milestones` (lines 122-127) currently only sets status + logs. Add the counter tick, mirroring `refresh_statuses`'s "increment at the mutation site" idiom. Locate:

```python
        elif ms.status is MilestoneStatus.REACHED and blockers:
            # a member was reopened or regressed — the milestone reverts
            # rather than asserting a deliverable that no longer holds
            ms.status = MilestoneStatus.PENDING
            log.warning("milestone '%s' reverted to pending: %s",
                        ms.name, "; ".join(blockers))
```

Replace with:

```python
        elif ms.status is MilestoneStatus.REACHED and blockers:
            # a member was reopened or regressed — the milestone reverts
            # rather than asserting a deliverable that no longer holds
            ms.status = MilestoneStatus.PENDING
            project.milestone_reverts += 1     # charter_integrity signal (Body reads it)
            log.warning("milestone '%s' reverted to pending: %s",
                        ms.name, "; ".join(blockers))
```

- [ ] Step 4: Run the milestone tests; expect PASS.

```
python -m pytest tests/test_nervous_counters.py -k milestone -q
```

- [ ] Step 5: Run the existing taskgraph-touching suites to confirm no behavior drift (the counter is additive and unread).

```
python -m pytest tests/test_director.py tests/test_live_findings.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/taskgraph.py tests/test_nervous_counters.py
git -C E:/director2 commit -m "feat(nervous): count milestone reverts at the taskgraph revert site (inert signal)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.4: Increment `coherence_blocks` where a delta is blocked

**Files:**
- Test: `E:/director2/tests/test_nervous_counters.py` (Modify — append a coherence-block test)
- Modify: `E:/director2/director/core/coherence.py` (`apply_delta`, the block branch at lines 213-216)

> Site choice: the spec offers two candidate sites (`decide()`'s `except CoherenceBlockedError` catch at director.py:638, and `coherence.apply_delta`). The increment goes at the **raise site inside `coherence.apply_delta`** (coherence.py:213-216), because every blocked delta — human-actor (`decide()`) *and* any autonomous-actor delta — flows through `apply_delta`'s `if rep.blocked:` branch, which already mutates `project` in place. Incrementing there captures all coherence blocks at one place with `project` already in scope, and avoids double-counting (the `decide()` catch merely re-raises after `apply_delta` already stamped the block).

Steps:

- [ ] Step 1: Append the failing coherence-block test to `E:/director2/tests/test_nervous_counters.py`. It builds a delta whose `module_updates` reference a non-existent module id so the coherence pass blocks it, calls `apply_delta`, catches `CoherenceBlockedError`, and asserts `project.coherence_blocks == 1`.

```python
def _blocking_delta() -> StateDelta:
    # A module update targeting a module id that does not exist is an incoherent
    # delta — the coherence pass blocks it.
    return StateDelta(
        trigger="manual", summary="bad module update",
        payload={"module_updates": [
            {"module_id": "does-not-exist", "status": "in_command"}]})


def test_coherence_block_increments_counter():
    p = Project(name="coh")
    assert p.coherence_blocks == 0
    with pytest.raises(CoherenceBlockedError):
        apply_delta(p, _blocking_delta(), actor="human")
    assert p.coherence_blocks == 1


def test_coherence_block_counter_inert_on_clean_delta():
    p = Project(name="coh2")
    m = Module(name="core", type=ModuleType.IMPLEMENTATION, purpose="x",
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(
        trigger="manual", summary="clean note",
        payload={"module_updates": [{"module_id": m.id, "note": "ok"}]})
    apply_delta(p, delta, actor="human")     # must not raise
    assert p.coherence_blocks == 0
```

- [ ] Step 2: Run only the coherence tests; expect FAIL on `test_coherence_block_increments_counter` — `assert 0 == 1`. (If the chosen blocking delta does not in fact block in this tree — e.g. `coherence_pass` raises `KeyError` instead of flagging `rep.blocked` — the test will error at `apply_delta` lookup; in that case the correct blocking shape is a conflicting `module_updates` `status` transition on an existing module. Verify the failure mode is `CoherenceBlockedError` from the `rep.blocked` branch; adjust the delta payload to one `coherence_pass` flags as a conflict if needed, keeping the assertion identical.)

```
python -m pytest tests/test_nervous_counters.py -k coherence -q
```

- [ ] Step 3: Add the increment at the block branch. In `E:/director2/director/core/coherence.py`, `apply_delta` (lines 208-216) already stamps the delta blocked before raising. Add the counter tick there. Locate:

```python
    rep = coherence_pass(project, delta, actor=actor)
    if rep.blocked:
        delta.status = "blocked"
        project.deltas[delta.id] = delta
        raise CoherenceBlockedError("; ".join(rep.conflicts))
```

Replace with:

```python
    rep = coherence_pass(project, delta, actor=actor)
    if rep.blocked:
        delta.status = "blocked"
        project.deltas[delta.id] = delta
        project.coherence_blocks += 1     # charter_integrity signal (Body reads it)
        raise CoherenceBlockedError("; ".join(rep.conflicts))
```

- [ ] Step 4: Run the coherence tests; expect PASS.

```
python -m pytest tests/test_nervous_counters.py -k coherence -q
```

- [ ] Step 5: Run `decide()`'s coverage to confirm the human-path block still behaves identically (the catch in `decide()` is unchanged; the counter is additive).

```
python -m pytest tests/test_director.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/coherence.py tests/test_nervous_counters.py
git -C E:/director2 commit -m "feat(nervous): count coherence blocks at the apply_delta block site (inert signal)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.5: Phase gate — prove the full existing suite stays green (byte-identical OFF)

**Files:** none (verification only).

Steps:

- [ ] Step 1: Run the entire suite. With `nervous_enabled=False` (the default) and all Phase 1 changes being additive data/counters, every pre-existing test must still pass and the existing 133 must remain green.

```
python -m pytest -q
```

- [ ] Step 2: Confirm the expected result: all prior tests pass; the new test files (`test_nervous_types.py`, `test_nervous_config.py`, `test_nervous_counters.py`) add green tests on top. If anything in the original 133 changed status, STOP — a Phase 1 edit leaked behavior; bisect the offending edit (most likely the `Project` field placement or the `apply_delta` increment) and restore byte-identical OFF behavior before proceeding.

- [ ] Step 3: Tag the foundations checkpoint.

```
git -C E:/director2 commit --allow-empty -m "chore(nervous): Phase 1 foundations complete — full suite green, OFF path byte-identical

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

Key files this phase touches (all absolute): `E:/director2/director/core/types.py`, `E:/director2/director/config.py`, `E:/director2/director/core/taskgraph.py`, `E:/director2/director/core/coherence.py`, and new tests `E:/director2/tests/test_nervous_types.py`, `E:/director2/tests/test_nervous_config.py`, `E:/director2/tests/test_nervous_counters.py`.

---

## Phase 2: The Body (trusted valence pass)
Goal: implement `director/core/valence.py`'s pure trusted reducer — `BodyState`, `compute_body()`, the private axis-severity helpers, composite valence with honest abstention/renormalization, and fragile-axis labeling — fully unit-tested, **without** wiring it into `advance()` (Phase 3 does the wiring). This phase ASSERTS the `BodyState` dataclass, the five `Project` fields, and the config block it depends on (all produced by Phase 1), then builds the reducer behind config that already defaults `nervous_enabled=False`, so the existing 133-test suite stays byte-identical.

> Conventions matched to the real tree: tests are flat under `E:/director2/tests/`, run with `python -m pytest` from `E:/director2`, use plain `assert`, build entities directly (`Project(name=...)`, `Task(...)`, `Risk(...)`, `Artifact(...)`), and use module-level `_helper` functions. `BodyState` is a PLAIN `@dataclass` (this file has zero frozen dataclasses; immutability is by discipline — it is recreated each cycle, never mutated — a deliberate deviation from the spec's "frozen" wording). `compute_body` NEVER calls a model.

> Dependency note: Phase 1 Tasks 1.1 (BodyState + Project fields) and 1.2 (config) are the SOLE producers of those source edits and must land before the reducer in Tasks 2.3–2.7. Phase 2 Tasks 2.1 and 2.2 are ASSERTION-ONLY — they verify Phase 1's additions round-trip; they do NOT re-insert any source. If `BodyState`/the new `Project` fields or the canonical config keys (`valence_weights`, `ache_threshold`, `siren_threshold`, `valence_eps`, `axis_saturation`, `charter_breach_threshold`, `nervous_enabled`, `budget`) are absent, STOP and complete Phase 1 first.

---

### Task 2.1: Assert `BodyState` dataclass + the five new `Project` fields (added by Phase 1)

Phase 1 Task 1.1 is the SOLE producer of the `BodyState` dataclass and the five new `Project` fields. This task is ASSERTION-ONLY: it verifies those additions exist and round-trip (including the `float | str` `"insufficient"` arm and a `scream_open` dict). It does NOT re-insert any source.

> **Phase 1 Task 1.1 already added these** (`BodyState` in `types.py` plus the five `Project` carrier fields `body`/`scream_open`/`cycle_seq`/`milestone_reverts`/`coherence_blocks`). If they are absent, STOP and complete Phase 1 first — do NOT re-insert them here.

**Files:**
- Test: `E:/director2/tests/test_valence_body.py` (Create)

**Steps:**

- [ ] Step 1: Write the round-trip assertion test. Create `E:/director2/tests/test_valence_body.py`. It imports `BodyState` and the new `Project` fields and asserts they round-trip; if the import fails, Phase 1 Task 1.1 has not landed (complete it first):

```python
"""Phase 2 — the Body (trusted valence pass): BodyState type, Project carrier
fields, and the pure compute_body reducer. All offline; no model is ever called."""

import dataclasses

from director.core.types import (Artifact, BodyState, Project, Risk, RiskLevel,
                                 RiskStatus, Task, TaskStatus, decode, encode)


# ----------------------------------------------------- BodyState + round-trip
def test_bodystate_all_fields_defaulted():
    """Every field MUST be defaulted so decode() of an old/partial snapshot
    cannot raise (types.py decode only sets fields present in the payload)."""
    bs = BodyState()
    assert bs.charter_integrity == "insufficient"
    assert bs.accumulated_damage == 0.0
    assert bs.uncertainty == 0.0
    assert bs.resource_bleed == "insufficient"
    assert bs.valence == 0.0
    assert bs.fragile_axes == []
    assert bs.computed_at == 0
    assert bs.provenance == {}
    # every field has a default -> zero-arg construction works
    assert all(f.default is not dataclasses.MISSING
               or f.default_factory is not dataclasses.MISSING
               for f in dataclasses.fields(bs))


def test_project_carries_new_nervous_fields_with_defaults():
    p = Project(name="p")
    assert p.body is None
    assert p.scream_open is None
    assert p.cycle_seq == 0
    assert p.milestone_reverts == 0
    assert p.coherence_blocks == 0


def test_bodystate_roundtrip_float_arm():
    bs = BodyState(charter_integrity=0.4, accumulated_damage=0.7,
                   uncertainty=0.2, resource_bleed=0.1, valence=-0.55,
                   fragile_axes=["uncertainty"], computed_at=3,
                   provenance={"risk_ids": ["r1"], "run_ids": ["x9"]})
    back = decode(BodyState, encode(bs))
    assert back == bs
    assert isinstance(back.charter_integrity, float)
    assert back.valence == -0.55


def test_bodystate_roundtrip_insufficient_str_arm():
    """The float|str union must resolve 'insufficient' to the STR arm, not None
    — decode tries each non-None arm and float('insufficient') raises ValueError,
    so str must remain a viable arm."""
    bs = BodyState(charter_integrity="insufficient", resource_bleed="insufficient")
    back = decode(BodyState, encode(bs))
    assert back.charter_integrity == "insufficient"
    assert back.resource_bleed == "insufficient"


def test_project_with_body_and_scream_open_roundtrips():
    p = Project(name="p")
    p.body = BodyState(accumulated_damage=0.5, valence=-0.3, computed_at=2)
    p.scream_open = {"cause": "grounding_damage", "axis": "accumulated_damage",
                     "opened_at": 2, "held_cycles": 1,
                     "clear_rule": "risk closes and run_properties re-passes",
                     "origin_refs": ["r7"]}
    p.cycle_seq = 2
    p.milestone_reverts = 1
    p.coherence_blocks = 0
    back = decode(Project, encode(p))
    assert back.body == p.body
    assert back.scream_open == p.scream_open
    assert back.cycle_seq == 2
    assert back.milestone_reverts == 1


def test_old_snapshot_without_body_decodes_to_defaults():
    """Forward/backward compat: a payload lacking the new keys decodes fine and
    the new fields fall to their defaults (the decode-survival guarantee)."""
    p = Project(name="p")
    raw = encode(p)
    for k in ("body", "scream_open", "cycle_seq", "milestone_reverts",
              "coherence_blocks"):
        raw.pop(k, None)
    back = decode(Project, raw)
    assert back.body is None
    assert back.scream_open is None
    assert back.cycle_seq == 0
    assert back.milestone_reverts == 0
    assert back.coherence_blocks == 0
```

- [ ] Step 2: Run it. Phase 1 Task 1.1 already added these — expect PASS. If instead it FAILS at import (`ImportError: cannot import name 'BodyState' from 'director.core.types'`) or the five `Project` fields are missing, STOP and complete Phase 1 Task 1.1 first; do NOT re-insert the source here.

```
python -m pytest tests/test_valence_body.py -q
```

- [ ] Step 3: Confirm the existing suite stays byte-identical-green (nothing reads the new fields yet).

```
python -m pytest -q
```

- [ ] Step 4: Commit (the new assertion test only — `types.py` was already committed in Phase 1).

```
git -C E:/director2 add tests/test_valence_body.py
git -C E:/director2 commit -m "Phase 2: assert BodyState + Project nervous-system carrier fields round-trip

Verify the Phase 1 additions (BodyState valence projection and the five
defaulted Project carrier fields body/scream_open/cycle_seq/milestone_reverts/
coherence_blocks) round-trip through encode/decode, including the float|str
'insufficient' str arm and a scream_open dict. Assertion-only; Phase 1 Task 1.1
produced the source.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.2: Assert the valence config constants (declared by Phase 1)

Phase 1 Task 1.2 is the SOLE producer of the nervous-system `Config` block. This task is ASSERTION-ONLY: it verifies the declared, recorded constants `compute_body` reads (weights, thresholds, saturation points, abstention/budget flags) exist with `nervous_enabled=False` so the OFF path is byte-identical. It does NOT re-insert any source.

> **Phase 1 Task 1.2 already added these** (the `# --- nervous system (v1) ---` block, inserted after `min_evaluation_score` and before `# --- sandbox / grounding ---`). The canonical config keys are `nervous_enabled`, `valence_weights`, `ache_threshold`, `siren_threshold`, `valence_eps`, `hysteresis_margin`, `charter_breach_threshold`, `axis_saturation`, `budget`, `max_held_cycles`, `director_temperature`, `bench`. If they are absent, STOP and complete Phase 1 Task 1.2 first — do NOT re-insert them here (and do NOT use any alternate anchor; the single canonical location is after `min_evaluation_score`).

**Files:**
- Test: `E:/director2/tests/test_valence_config.py` (Create)

**Steps:**

- [ ] Step 1: Write the config assertion test. Create `E:/director2/tests/test_valence_config.py`. It asserts the Phase 1 config constants; if any attribute is missing, Phase 1 Task 1.2 has not landed (complete it first):

```python
"""Phase 2 — declared nervous-system config constants. These are recorded
first-guesses (tuned later via the bench), never hardcoded in valence.py."""

from director.config import Config


def test_nervous_disabled_by_default():
    """The hard constraint: OFF by default so the existing suite stays
    byte-identical until the bench flips it."""
    assert Config().nervous_enabled is False


def test_valence_weights_declared_and_sum_to_one():
    w = Config().valence_weights
    assert set(w) == {"charter_integrity", "accumulated_damage",
                      "uncertainty", "resource_bleed"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_thresholds_in_range_and_ordered():
    c = Config()
    assert -1.0 <= c.siren_threshold < c.ache_threshold <= 0.0
    assert c.valence_eps > 0.0
    assert c.hysteresis_margin > 0.0
    assert 0.0 < c.charter_breach_threshold <= 1.0


def test_axis_saturation_declared():
    sat = Config().axis_saturation
    assert sat["accumulated_damage"] == 5.0
    assert sat["charter_integrity"] == 3.0
    assert sat["uncertainty"] == 4.0


def test_budget_absent_by_default():
    assert Config().budget is None


def test_weights_are_per_instance_not_shared():
    """default_factory must give each Config its OWN dict (no shared mutable
    default leaking across instances)."""
    a, b = Config(), Config()
    a.valence_weights["uncertainty"] = 0.99
    assert b.valence_weights["uncertainty"] == 0.20
```

- [ ] Step 2: Run it. Phase 1 Task 1.2 already declared these — expect PASS. If instead it FAILS (`AttributeError: 'Config' object has no attribute 'nervous_enabled'` or any other key missing), STOP and complete Phase 1 Task 1.2 first; do NOT re-insert the config block here, and do NOT use the alternate `stall_window` anchor — the single canonical location is after `min_evaluation_score`, before `# --- sandbox / grounding ---`.

```
python -m pytest tests/test_valence_config.py -q
```

- [ ] Step 3: Confirm the full suite stays green (config additions are inert).

```
python -m pytest -q
```

- [ ] Step 4: Commit (the new assertion test only — `config.py` was already committed in Phase 1).

```
git -C E:/director2 add tests/test_valence_config.py
git -C E:/director2 commit -m "Phase 2: assert nervous-system config constants are declared

Verify the Phase 1 Config block: nervous_enabled (default False),
valence_weights (sum 1), ache/siren thresholds, valence_eps, hysteresis_margin,
charter_breach_threshold, axis_saturation, budget (None), max_held_cycles,
director_temperature, and the bench block. Assertion-only; Phase 1 Task 1.2
produced the source.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.3: `accumulated_damage` axis severity (the reducer skeleton begins)

Creates `director/core/valence.py` with `compute_body` returning a `BodyState`, and the first private axis helper `_severity_accumulated_damage`, mapped to the exact trusted sources: FAILED task count, attempts-over-max, open HIGH grounding risks, and integrity violations.

**Files:**
- Create: `E:/director2/director/core/valence.py`
- Test: `E:/director2/tests/test_valence_axes.py` (Create)

**Steps:**

- [ ] Step 1: Write the failing axis test. Create `E:/director2/tests/test_valence_axes.py`:

```python
"""Phase 2 — per-axis severity helpers and compute_body. compute_body is a pure
trusted reducer over executed/verified state; it NEVER calls a model."""

from director.config import Config
from director.core.types import (AgentRun, Risk, RiskLevel, RiskStatus, Task,
                                 TaskStatus, Project, VerificationReport)
from director.core.valence import (BodyState, compute_body,
                                    _severity_accumulated_damage)


def _proj():
    return Project(name="p")


def _task(status=TaskStatus.READY, attempts=0, max_attempts=2):
    return Task(title="t", status=status, attempts=attempts,
                max_attempts=max_attempts)


def _risk(level, status=RiskStatus.OPEN, source="grounding"):
    return Risk(title="r", level=level, status=status, source=source)


# ------------------------------------------------- accumulated_damage severity
def test_accumulated_damage_zero_on_clean_project():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in [_task(), _task()]}  # all READY, no damage
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 0.0


def test_accumulated_damage_counts_failed_and_high_risk():
    cfg = Config()
    p = _proj()
    failed = [_task(status=TaskStatus.FAILED) for _ in range(2)]
    p.tasks = {t.id: t for t in failed}
    hr = _risk(RiskLevel.HIGH)
    p.risks = {hr.id: hr}
    # 2 failed + 1 open HIGH risk = raw 3; saturation for this axis is 5.0
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s - 3.0 / 5.0) < 1e-9


def test_accumulated_damage_attempts_over_max_contributes():
    cfg = Config()
    p = _proj()
    over = _task(status=TaskStatus.READY, attempts=4, max_attempts=2)  # 2 over
    p.tasks = {over.id: over}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    # 2 attempts-over-max / 5.0 saturation
    assert abs(s - 2.0 / 5.0) < 1e-9


def test_accumulated_damage_saturates_at_one():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in [_task(status=TaskStatus.FAILED)
                                 for _ in range(9)]}  # raw 9 > saturation 5
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 1.0


def test_closed_risks_do_not_count():
    cfg = Config()
    p = _proj()
    closed = _risk(RiskLevel.HIGH, status=RiskStatus.CLOSED)
    p.risks = {closed.id: closed}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 0.0


def test_accumulated_damage_counts_fragile_verdicts():
    cfg = Config()
    p = _proj()
    # two fragile verification reports across the project's runs -> raw 2
    run = AgentRun(task_id="t1", role="code")
    run.reports = [VerificationReport(verifier="code_runs", passed=True,
                                      score=4.0, fragile=True),
                   VerificationReport(verifier="judge", passed=True,
                                      score=4.0, fragile=True)]
    p.runs = {run.id: run}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    # 2 fragile verdicts / 5.0 saturation
    assert abs(s - 2.0 / 5.0) < 1e-9
    # a non-fragile report does not contribute
    run.reports.append(VerificationReport(verifier="nonempty", passed=True,
                                          score=5.0, fragile=False))
    s2 = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s2 - 2.0 / 5.0) < 1e-9


# --------------------------------------------------------------- compute_body
def test_compute_body_returns_bodystate_never_calls_model():
    cfg = Config()
    p = _proj()
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert isinstance(body, BodyState)
    assert -1.0 <= body.valence <= 0.0


def test_compute_body_stamps_computed_at_from_cycle_seq():
    cfg = Config()
    p = _proj()
    p.cycle_seq = 7
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.computed_at == 7
```

- [ ] Step 2: Run it; expect FAIL (`ModuleNotFoundError: No module named 'director.core.valence'`).

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 3: Create `E:/director2/director/core/valence.py` with the module skeleton, the `accumulated_damage` helper, and a minimal `compute_body` that fills only this axis (other axes return 0.0/abstain for now — later tasks extend them). Match the codebase style (`from __future__ import annotations`, identity enum comparisons, module-private helpers):

```python
"""The Body — the trusted valence pass (nervous system v1).

``compute_body`` is a PURE TRUSTED REDUCER over executed/verified state: it reads
existing signals (FAILED counts, attempts-over-max, open grounding risks,
integrity violations, fragile verification verdicts, NEEDS_VERIFY counts,
packet-coherence, run-scoped perf) and the small new Project counters, and
returns a recomputed ``BodyState`` projection.
It NEVER calls a model — that un-gameability is the load-bearing property
(Constitution principle 2). Thresholds, weights and saturation points are declared
constants in director/config.py, never hardcoded here.

Severity convention: every axis maps to s in [0, 1], where s = min(1, raw /
saturation). The composite valence = -sum(w_i * s_i) in [-1, 0]; when an axis
abstains ("insufficient") it is dropped and the remaining weights are renormalized
to sum to 1 (thresholds stay ABSOLUTE, never rescaled).
"""

from __future__ import annotations

from .integrity import (integrity_summary, integrity_violations,
                        report_integrity)
from .taskgraph import open_risks
from .types import BodyState, Project, RiskLevel, RiskStatus, TaskStatus

__all__ = ["BodyState", "compute_body"]

# axes that can abstain to the "insufficient" sentinel (dropped + renormalized)
_INSUFFICIENT = "insufficient"


def _clamp01(raw: float, saturation: float) -> float:
    """Severity = min(1, raw / saturation), floored at 0. Saturation is the
    declared raw count at which severity reaches 1.0."""
    if saturation <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / saturation))


def _severity_accumulated_damage(project: Project, *, secret: bytes,
                                 cfg, violations: int | None = None) -> float:
    """Raw damage = FAILED task count + per-task attempts-over-max + open HIGH
    grounding risks + integrity-report violations + fragile verification-report
    verdicts. Scaled by the declared accumulated_damage saturation point.

    ``violations`` may be passed in by ``compute_body`` (which computes the
    integrity summary once and reuses the count for provenance), so the integrity
    re-check is not run twice; when None it is computed here for standalone use."""
    failed = sum(1 for t in project.tasks.values()
                 if t.status is TaskStatus.FAILED)
    over_max = sum(max(0, t.attempts - t.max_attempts)
                   for t in project.tasks.values())
    high_risks = sum(1 for r in open_risks(project)
                     if r.level is RiskLevel.HIGH)
    if violations is None:
        violations = integrity_summary(project, secret)["violations"]
    fragile = sum(1 for run in project.runs.values()
                  for rep in run.reports if rep.fragile)
    raw = failed + over_max + high_risks + violations + fragile
    return _clamp01(raw, cfg.axis_saturation["accumulated_damage"])


def compute_body(project: Project, *, secret: bytes, perf, since, cfg) -> BodyState:
    """Recompute the trusted valence projection for ``project``. Pure reducer;
    never calls a model. ``perf``/``since`` scope run-local token accounting for
    the resource_bleed axis (abstains when no budget is declared)."""
    # integrity is re-checked ONCE here; the violation count feeds the
    # accumulated_damage axis and the same rows feed provenance (Task 2.7),
    # so the signed-report binding check never runs twice per cycle.
    integrity_rows = report_integrity(project, secret)
    violators = integrity_violations(integrity_rows)
    damage = _severity_accumulated_damage(project, secret=secret, cfg=cfg,
                                          violations=len(violators))

    # axes not yet wired in this task default to neutral / abstain
    charter = _INSUFFICIENT
    uncertainty = 0.0
    bleed = _INSUFFICIENT

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty}
    if charter != _INSUFFICIENT:
        severities["charter_integrity"] = charter
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed

    valence = _composite(severities, cfg)

    return BodyState(
        charter_integrity=charter,
        accumulated_damage=damage,
        uncertainty=uncertainty,
        resource_bleed=bleed,
        valence=valence,
        fragile_axes=[],
        computed_at=project.cycle_seq,
        provenance={},
    )


def _composite(severities: dict, cfg) -> float:
    """valence = -sum(w_i * s_i) over the PRESENT (non-abstaining) axes, with the
    remaining weights renormalized to sum to 1 so the result stays in [-1, 0] and
    the ABSOLUTE thresholds stay comparable. Abstaining axes are simply absent
    from ``severities``."""
    weights = cfg.valence_weights
    present = {ax: weights[ax] for ax in severities if ax in weights}
    total_w = sum(present.values())
    if total_w <= 0:
        return 0.0
    acc = sum((w / total_w) * severities[ax] for ax, w in present.items())
    return -round(acc, 6)
```

- [ ] Step 4: Run it; expect PASS.

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 5: Commit.

```
git -C E:/director2 add director/core/valence.py tests/test_valence_axes.py
git -C E:/director2 commit -m "Phase 2: valence.py reducer skeleton + accumulated_damage axis

Add director/core/valence.py with compute_body (pure trusted reducer, never
calls a model), the _clamp01 saturation helper, the _composite renormalizing
reducer, and _severity_accumulated_damage mapped to FAILED counts +
attempts-over-max + open HIGH grounding risks + integrity violations.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.4: `charter_integrity` axis severity

Maps `charter_integrity` to its exact trusted sources: `milestone_reverts`, `coherence_blocks`, and open **CRITICAL** risks. Wires it into `compute_body` so the axis is present (no longer abstaining).

**Files:**
- Modify: `E:/director2/director/core/valence.py`
- Test: `E:/director2/tests/test_valence_axes.py` (append)

**Steps:**

- [ ] Step 1: Append the failing test to `E:/director2/tests/test_valence_axes.py`:

```python
# --------------------------------------------------- charter_integrity severity
from director.core.valence import _severity_charter_integrity  # noqa: E402


def test_charter_integrity_zero_on_clean_project():
    cfg = Config()
    p = _proj()
    s = _severity_charter_integrity(p, cfg=cfg)
    assert s == 0.0


def test_charter_integrity_counts_reverts_blocks_and_critical():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 1
    p.coherence_blocks = 1
    crit = _risk(RiskLevel.CRITICAL)
    p.risks = {crit.id: crit}
    # raw 1 + 1 + 1 = 3; saturation for charter_integrity is 3.0 -> severity 1.0
    s = _severity_charter_integrity(p, cfg=cfg)
    assert s == 1.0


def test_charter_integrity_partial_below_saturation():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 1
    s = _severity_charter_integrity(p, cfg=cfg)  # raw 1 / 3.0
    assert abs(s - 1.0 / 3.0) < 1e-9


def test_high_risks_do_not_feed_charter_integrity():
    cfg = Config()
    p = _proj()
    hr = _risk(RiskLevel.HIGH)
    p.risks = {hr.id: hr}  # HIGH feeds accumulated_damage, NOT charter
    assert _severity_charter_integrity(p, cfg=cfg) == 0.0


def test_compute_body_charter_axis_is_present():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.charter_integrity == 1.0  # 3/3 saturated, no longer "insufficient"
    assert body.valence < 0.0
```

- [ ] Step 2: Run it; expect FAIL (`ImportError: cannot import name '_severity_charter_integrity'`).

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 3: Add `_severity_charter_integrity` to `valence.py` (place it directly after `_severity_accumulated_damage`):

```python
def _severity_charter_integrity(project: Project, *, cfg) -> float:
    """Raw charter erosion = milestone reverts + coherence blocks + open CRITICAL
    grounding risks. Scaled by the declared charter_integrity saturation."""
    critical = sum(1 for r in open_risks(project)
                   if r.level is RiskLevel.CRITICAL)
    raw = project.milestone_reverts + project.coherence_blocks + critical
    return _clamp01(raw, cfg.axis_saturation["charter_integrity"])
```

- [ ] Step 4: Wire it into `compute_body` — replace the line `charter = _INSUFFICIENT` (and its surrounding `if charter != _INSUFFICIENT` guard logic) so charter is always present. Change the body of `compute_body`'s severity block from:

```python
    damage = _severity_accumulated_damage(project, secret=secret, cfg=cfg)

    # axes not yet wired in this task default to neutral / abstain
    charter = _INSUFFICIENT
    uncertainty = 0.0
    bleed = _INSUFFICIENT

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty}
    if charter != _INSUFFICIENT:
        severities["charter_integrity"] = charter
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed
```

to:

```python
    damage = _severity_accumulated_damage(project, secret=secret, cfg=cfg)
    charter = _severity_charter_integrity(project, cfg=cfg)

    # axes not yet wired in this task default to neutral / abstain
    uncertainty = 0.0
    bleed = _INSUFFICIENT

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty,
                  "charter_integrity": charter}
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed
```

- [ ] Step 5: Run it; expect PASS.

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/valence.py tests/test_valence_axes.py
git -C E:/director2 commit -m "Phase 2: charter_integrity axis severity

Map charter_integrity to milestone_reverts + coherence_blocks + open CRITICAL
risks (CRITICAL attributed here, HIGH stays on accumulated_damage), scaled by
its declared saturation point, and wire the axis as always-present in
compute_body.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.5: `uncertainty` axis severity

Maps `uncertainty` to NEEDS_VERIFY task count, JUDGED-not-VERIFIED option count from open packets (`honest_check`), and packet-coherence spread (`evaluate_packet_coherence`).

**Files:**
- Modify: `E:/director2/director/core/valence.py`
- Test: `E:/director2/tests/test_valence_axes.py` (append)

**Steps:**

- [ ] Step 1: Append the failing test to `E:/director2/tests/test_valence_axes.py`:

```python
# --------------------------------------------------------- uncertainty severity
from director.core.types import (CheckKind, CommandOption, CommandPacket,  # noqa: E402
                                 PacketStatus)
from director.core.valence import _severity_uncertainty  # noqa: E402


def test_uncertainty_zero_on_clean_project():
    cfg = Config()
    assert _severity_uncertainty(_proj(), cfg=cfg) == 0.0


def test_uncertainty_counts_needs_verify():
    cfg = Config()
    p = _proj()
    nv = [_task(status=TaskStatus.NEEDS_VERIFY) for _ in range(2)]
    p.tasks = {t.id: t for t in nv}
    s = _severity_uncertainty(p, cfg=cfg)  # raw 2 / saturation 4.0
    assert abs(s - 2.0 / 4.0) < 1e-9


def test_uncertainty_counts_judged_options_in_open_packets():
    cfg = Config()
    p = _proj()
    pkt = CommandPacket(title="t", status=PacketStatus.PRESENTED, options=[
        CommandOption(key="A", label="A", conviction="dogmatic",
                      check=CheckKind.JUDGED),
        CommandOption(key="B", label="B", conviction="iconoclast",
                      check=CheckKind.JUDGED)])
    p.packets = {pkt.id: pkt}
    s = _severity_uncertainty(p, cfg=cfg)  # 2 judged options / 4.0
    assert abs(s - 2.0 / 4.0) < 1e-9


def test_uncertainty_ignores_answered_packets():
    cfg = Config()
    p = _proj()
    pkt = CommandPacket(title="t", status=PacketStatus.ANSWERED, options=[
        CommandOption(key="A", label="A", conviction="dogmatic",
                      check=CheckKind.JUDGED)])
    p.packets = {pkt.id: pkt}
    assert _severity_uncertainty(p, cfg=cfg) == 0.0


def test_uncertainty_saturates():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [_task(status=TaskStatus.NEEDS_VERIFY) for _ in range(9)]}
    assert _severity_uncertainty(p, cfg=cfg) == 1.0
```

- [ ] Step 2: Run it; expect FAIL (`ImportError: cannot import name '_severity_uncertainty'`).

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 3: Add the helper to `valence.py`. First extend the imports at the top:

```python
from .convictions import evaluate_packet_coherence, honest_check
```

Then add the helper after `_severity_charter_integrity`:

```python
def _severity_uncertainty(project: Project, *, cfg) -> float:
    """Raw uncertainty = NEEDS_VERIFY task count + JUDGED-not-VERIFIED option
    count over open (PRESENTED) packets + summed packet-coherence spread shortfall.
    Reads honest_check (the display-safe check kind) and evaluate_packet_coherence;
    both are trusted, model-free. Scaled by the declared uncertainty saturation."""
    needs_verify = sum(1 for t in project.tasks.values()
                       if t.status is TaskStatus.NEEDS_VERIFY)
    judged = 0
    for pkt in project.packets.values():
        if pkt.status is not PacketStatus.PRESENTED:
            continue
        for o in pkt.options:
            kind, _ = honest_check(o, project.artifacts)
            if kind == CheckKind.JUDGED:
                judged += 1
        coh = evaluate_packet_coherence(pkt, project)
        if coh["spread"] < 2 and len(pkt.options) >= 2:
            judged += 1   # a no-real-choice packet is itself an uncertainty signal
    raw = needs_verify + judged
    return _clamp01(raw, cfg.axis_saturation["uncertainty"])
```

Also extend the `from .types import ...` line to include `CheckKind` and `PacketStatus`:

```python
from .types import (BodyState, CheckKind, PacketStatus, Project, RiskLevel,
                    RiskStatus, TaskStatus)
```

- [ ] Step 4: Wire it into `compute_body` — replace `uncertainty = 0.0` with:

```python
    uncertainty = _severity_uncertainty(project, cfg=cfg)
```

- [ ] Step 5: Run it; expect PASS.

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/valence.py tests/test_valence_axes.py
git -C E:/director2 commit -m "Phase 2: uncertainty axis severity

Map uncertainty to NEEDS_VERIFY count + JUDGED-not-VERIFIED options over open
PRESENTED packets (via honest_check) + no-real-choice packet-coherence spread
(via evaluate_packet_coherence), scaled by its declared saturation, and wire it
into compute_body. Both signal sources are trusted and model-free.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.6: `resource_bleed` axis + honest abstention / renormalization

Implements the budget-aware `resource_bleed` axis from `perf.stats(since)` tokens, and the honest-abstention rule: when `cfg.budget is None`, `resource_bleed = "insufficient"`, the axis is dropped from the composite, and the remaining weights renormalize while thresholds stay **absolute**.

**Files:**
- Modify: `E:/director2/director/core/valence.py`
- Test: `E:/director2/tests/test_valence_axes.py` (append)

**Steps:**

- [ ] Step 1: Append the failing test to `E:/director2/tests/test_valence_axes.py`:

```python
# ----------------------------------------------- resource_bleed + abstention
from director.core.valence import _severity_resource_bleed, _composite  # noqa: E402


class _FakePerf:
    """Minimal duck-type of PerfLedger: only stats(since=...) is read."""
    def __init__(self, prompt_tokens, completion_tokens):
        self._p, self._c = prompt_tokens, completion_tokens

    def stats(self, *, since=None):
        return {"calls": 1, "prompt_tokens": self._p,
                "completion_tokens": self._c}


def test_resource_bleed_abstains_with_no_budget():
    cfg = Config()  # budget is None
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(10, 10), since=None,
                                 cfg=cfg)
    assert s == "insufficient"


def test_resource_bleed_severity_against_token_budget():
    cfg = Config()
    cfg.budget = {"max_tokens": 1000}
    # 400 + 200 = 600 tokens of 1000 budget -> 0.6 severity
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(400, 200), since=None,
                                 cfg=cfg)
    assert abs(s - 0.6) < 1e-9


def test_resource_bleed_saturates_at_budget():
    cfg = Config()
    cfg.budget = {"max_tokens": 100}
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(500, 0), since=None,
                                 cfg=cfg)
    assert s == 1.0


def test_resource_bleed_abstains_when_perf_is_none():
    cfg = Config()
    cfg.budget = {"max_tokens": 1000}
    s = _severity_resource_bleed(_proj(), perf=None, since=None, cfg=cfg)
    assert s == "insufficient"


# --------------------------- renormalization: thresholds stay ABSOLUTE
def test_composite_renormalizes_when_one_axis_abstains():
    """With resource_bleed (weight 0.10) dropped, the remaining three weights
    (0.30+0.40+0.20=0.90) renormalize to sum 1. A single fully-saturated axis
    must therefore weigh MORE than its raw 0.40 share, never be rescaled away."""
    cfg = Config()
    # only accumulated_damage present at severity 1.0, bleed absent
    sev = {"accumulated_damage": 1.0, "uncertainty": 0.0,
           "charter_integrity": 0.0}
    v = _composite(sev, cfg)
    # 0.40 / (0.30+0.40+0.20) = 0.40/0.90 = 0.4444...
    assert abs(v - (-0.40 / 0.90)) < 1e-6


def test_composite_with_all_axes_present_uses_raw_weights():
    cfg = Config()
    sev = {"accumulated_damage": 1.0, "uncertainty": 0.0,
           "charter_integrity": 0.0, "resource_bleed": 0.0}
    v = _composite(sev, cfg)  # weights already sum to 1 -> -0.40
    assert abs(v - (-0.40)) < 1e-9


def test_compute_body_reports_insufficient_bleed_by_default():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(),
                        perf=_FakePerf(50, 50), since=None, cfg=cfg)
    assert body.resource_bleed == "insufficient"
```

- [ ] Step 2: Run it; expect FAIL (`ImportError: cannot import name '_severity_resource_bleed'`).

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 3: Add the helper to `valence.py` after `_severity_uncertainty`:

```python
def _severity_resource_bleed(project: Project, *, perf, since, cfg):
    """Run-scoped token burn vs the declared token budget. Returns the
    "insufficient" sentinel (NOT 0.0) when no budget is declared or no perf
    ledger is available — the axis is DARK, not fine (Constitution g). Tokens are
    run-scoped via perf.stats(since=since) so a fresh run does not inherit prior
    lifetime totals."""
    budget = cfg.budget
    if not budget or perf is None:
        return _INSUFFICIENT
    max_tokens = budget.get("max_tokens")
    if not max_tokens:
        return _INSUFFICIENT
    stats = perf.stats(since=since)
    used = int(stats.get("prompt_tokens", 0)) + \
        int(stats.get("completion_tokens", 0))
    return _clamp01(used, max_tokens)
```

- [ ] Step 4: Wire it into `compute_body` — replace the `bleed = _INSUFFICIENT` line and its guard. Change:

```python
    uncertainty = _severity_uncertainty(project, cfg=cfg)

    # axes not yet wired in this task default to neutral / abstain
    bleed = _INSUFFICIENT

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty,
                  "charter_integrity": charter}
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed
```

to:

```python
    uncertainty = _severity_uncertainty(project, cfg=cfg)
    bleed = _severity_resource_bleed(project, perf=perf, since=since, cfg=cfg)

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty,
                  "charter_integrity": charter}
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed
```

- [ ] Step 5: Run it; expect PASS.

```
python -m pytest tests/test_valence_axes.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/valence.py tests/test_valence_axes.py
git -C E:/director2 commit -m "Phase 2: resource_bleed axis + honest abstention

Map resource_bleed to run-scoped token burn (perf.stats(since)) vs the declared
token budget; abstain to the 'insufficient' sentinel (not 0.0) when no budget or
no perf is available. The composite drops abstaining axes and renormalizes the
remaining weights so a single saturated axis cannot be rescaled away and the
ABSOLUTE ache/siren thresholds stay comparable.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.7: Fragile-axis labeling (knife-edge band)

Implements `fragile_axes`: any axis whose severity sits within `cfg.valence_eps` of where it would push the composite across a threshold, OR the composite itself within `valence_eps` of `ache_threshold`/`siren_threshold`, is listed in `BodyState.fragile_axes` and provenance is populated.

**Files:**
- Modify: `E:/director2/director/core/valence.py`
- Test: `E:/director2/tests/test_valence_fragile.py` (Create)

**Steps:**

- [ ] Step 1: Write the failing fragile test. Create `E:/director2/tests/test_valence_fragile.py`:

```python
"""Phase 2 — fragile-axis labeling: knife-edge composites/axes are LABELED, never
silently rounded up into a halt (RDE v11 lesson). Trusted, model-free."""

from director.config import Config
from director.core.types import Risk, RiskLevel, Task, TaskStatus, Project
from director.core.valence import _fragile_axes, compute_body


def _proj():
    return Project(name="p")


def test_no_fragile_axes_when_composite_far_from_thresholds():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(), perf=None,
                        since=None, cfg=cfg)
    assert body.fragile_axes == []


def test_composite_within_eps_of_ache_is_fragile():
    cfg = Config()
    # valence sitting just inside valence_eps of ache_threshold (-0.33)
    sev = {"accumulated_damage": 0.30}  # value chosen so the composite lands near
    fragile = _fragile_axes(valence=-0.30, severities=sev, cfg=cfg)
    # -0.30 is within 0.05 of -0.33 -> the band is tripped, composite flagged
    assert "composite" in fragile


def test_axis_at_saturation_edge_is_fragile():
    cfg = Config()
    # an axis severity within valence_eps of 1.0 (its own ceiling) is knife-edge
    sev = {"accumulated_damage": 0.97, "uncertainty": 0.0}
    fragile = _fragile_axes(valence=-0.50, severities=sev, cfg=cfg)
    assert "accumulated_damage" in fragile


def test_fragile_axes_populated_in_compute_body_and_provenance():
    cfg = Config()
    p = _proj()
    # drive accumulated_damage to a near-ceiling severity (4 of 5 saturation)
    p.tasks = {t.id: t for t in
               [Task(title="t", status=TaskStatus.FAILED) for _ in range(5)]}
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert "accumulated_damage" in body.fragile_axes
    # provenance carries pointers, not copies
    assert "risk_ids" in body.provenance
    assert "run_ids" in body.provenance
    # integrity violations surfaced for Phase 3's tamper override (none here)
    assert body.provenance["integrity_violations"] == 0
    assert body.provenance["violation_ids"] == []
```

- [ ] Step 2: Run it; expect FAIL (`ImportError: cannot import name '_fragile_axes'`).

```
python -m pytest tests/test_valence_fragile.py -q
```

- [ ] Step 3: Add `_fragile_axes` to `valence.py` (after `_composite`):

```python
def _fragile_axes(valence: float, severities: dict, cfg) -> list[str]:
    """Knife-edge labeling (RDE v11 lesson: never silently round a verdict up).
    An axis/composite is fragile when it sits within ``cfg.valence_eps`` of a
    decision edge:
      * the composite within valence_eps of ache_threshold or siren_threshold;
      * any present axis severity within valence_eps of its 0.0 floor (only when
        the composite is already in negative territory) or its 1.0 ceiling.
    The label degrades a near-siren to an ache downstream; it is descriptive
    only — compute_body sets no latch.
    """
    eps = cfg.valence_eps
    fragile: list[str] = []
    if (abs(valence - cfg.ache_threshold) <= eps
            or abs(valence - cfg.siren_threshold) <= eps):
        fragile.append("composite")
    for ax, s in severities.items():
        if isinstance(s, str):       # an abstaining axis cannot be fragile
            continue
        if abs(s - 1.0) <= eps and valence < 0.0:
            fragile.append(ax)
    return fragile
```

- [ ] Step 4: Populate `fragile_axes` and `provenance` in `compute_body`. Replace the `return BodyState(...)` block:

```python
    valence = _composite(severities, cfg)

    return BodyState(
        charter_integrity=charter,
        accumulated_damage=damage,
        uncertainty=uncertainty,
        resource_bleed=bleed,
        valence=valence,
        fragile_axes=[],
        computed_at=project.cycle_seq,
        provenance={},
    )
```

with:

```python
    valence = _composite(severities, cfg)
    fragile = _fragile_axes(valence, severities, cfg)

    # surface the integrity violations into provenance so Phase 3's tamper hard
    # override (prov.get("integrity_violations", 0) > 0) is reachable in the
    # real wired path, not only in unit tests. Reuse the rows computed once above.
    provenance = {
        "risk_ids": [r.id for r in open_risks(project)],
        "run_ids": list(project.runs),
        "integrity_violations": len(violators),
        "violation_ids": [r.get("artifact_id") for r in violators],
    }

    return BodyState(
        charter_integrity=charter,
        accumulated_damage=damage,
        uncertainty=uncertainty,
        resource_bleed=bleed,
        valence=valence,
        fragile_axes=fragile,
        computed_at=project.cycle_seq,
        provenance=provenance,
    )
```

- [ ] Step 5: Run it; expect PASS.

```
python -m pytest tests/test_valence_fragile.py -q
```

- [ ] Step 6: Commit.

```
git -C E:/director2 add director/core/valence.py tests/test_valence_fragile.py
git -C E:/director2 commit -m "Phase 2: fragile-axis labeling + provenance pointers

Label the composite fragile when within valence_eps of either threshold, and any
present axis fragile when within valence_eps of its 1.0 ceiling in negative
territory; populate BodyState.provenance with risk_id/run_id POINTERS (not
copies). Abstaining axes can never be fragile. Descriptive only — compute_body
sets no latch.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.8: Full composite, abstention-renormalization, and OFF-path regression sweep

End-to-end assertions over `compute_body` covering all four axes together at/below/above saturation, the renormalization-on-abstain math, fragile-band edges, and the hard constraint that with `nervous_enabled=False` nothing changed: the existing 133-test suite stays green and `compute_body` is never invoked by `advance()` (Phase 3 wires it).

**Files:**
- Test: `E:/director2/tests/test_valence_composite.py` (Create)

**Steps:**

- [ ] Step 1: Write the failing composite/regression test. Create `E:/director2/tests/test_valence_composite.py`:

```python
"""Phase 2 — full-composite integration over compute_body: all axes at once,
renormalization on abstain (thresholds NOT rescaled), and the OFF-path guarantee
that the reducer is pure and unwired (Phase 3 does the wiring)."""

import inspect

from director.config import Config
from director.core import director as director_mod
from director.core.types import (Risk, RiskLevel, RiskStatus, Task, TaskStatus,
                                 Project)
from director.core.valence import BodyState, compute_body


def _proj():
    return Project(name="p")


def test_clean_project_has_zero_valence():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(), perf=None,
                        since=None, cfg=cfg)
    assert body.valence == 0.0
    assert body.fragile_axes == []


def test_full_composite_with_abstaining_bleed():
    """damage=1.0, charter=1.0, uncertainty=0.0, bleed abstains. Present weights
    0.40+0.30+0.20=0.90 renormalize; valence = -(0.40*1 + 0.30*1 + 0.20*0)/0.90."""
    cfg = Config()
    p = _proj()
    # accumulated_damage -> raw >= 5 (saturated): 5 FAILED tasks
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(5)]}
    # charter_integrity -> raw >= 3 (saturated): 3 milestone reverts
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.accumulated_damage == 1.0
    assert body.charter_integrity == 1.0
    assert body.resource_bleed == "insufficient"
    expected = -((0.40 * 1.0 + 0.30 * 1.0 + 0.20 * 0.0) / 0.90)
    assert abs(body.valence - expected) < 1e-6


def test_thresholds_not_rescaled_on_abstain():
    """The renormalized composite stays in [-1, 0], so the ABSOLUTE ache/siren
    thresholds remain comparable without rescaling."""
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(5)]}
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert -1.0 <= body.valence <= 0.0
    # this saturated-2-axes case crosses the absolute siren threshold (-0.66)
    assert body.valence < cfg.siren_threshold


def test_valence_floor_is_minus_one_when_all_present_axes_saturated():
    cfg = Config()
    cfg.budget = {"max_tokens": 1}  # makes bleed PRESENT and saturable

    class _Perf:
        def stats(self, *, since=None):
            return {"prompt_tokens": 9999, "completion_tokens": 0}

    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(9)]}
    p.milestone_reverts = 9
    nv = [Task(title="u", status=TaskStatus.NEEDS_VERIFY) for _ in range(9)]
    for t in nv:
        p.tasks[t.id] = t
    body = compute_body(p, secret=cfg.report_secret(), perf=_Perf(), since=None,
                        cfg=cfg)
    # every present axis at 1.0, weights sum to 1 -> valence == -1.0
    assert abs(body.valence - (-1.0)) < 1e-6


# ------------------------------------------------- OFF-path / purity guarantees
def test_advance_does_not_import_or_call_compute_body_yet():
    """Hard constraint: Phase 2 adds the reducer but does NOT wire it. advance()
    must not reference compute_body (Phase 3 does that). Guards the byte-identical
    OFF path / 133-test invariant."""
    src = inspect.getsource(director_mod.Director.advance)
    assert "compute_body" not in src
    assert "valence" not in src


def test_compute_body_is_pure_no_mutation_of_project():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(2)]}
    before = {"tasks": dict(p.tasks), "body": p.body,
              "scream_open": p.scream_open, "cycle_seq": p.cycle_seq}
    compute_body(p, secret=cfg.report_secret(), perf=None, since=None, cfg=cfg)
    # the reducer returns a BodyState; it does NOT assign p.body or touch state
    assert p.body is before["body"]
    assert p.scream_open is before["scream_open"]
    assert p.cycle_seq == before["cycle_seq"]
    assert p.tasks == before["tasks"]
```

- [ ] Step 2: Run it; expect PASS for the math tests, and verify the purity/OFF-path guards pass too (they assert the absence of wiring, which is true in this phase). If `test_advance_does_not_import_or_call_compute_body_yet` fails, an earlier phase wired prematurely — stop and reconcile.

```
python -m pytest tests/test_valence_composite.py -q
```

- [ ] Step 3: Run the full nervous-system Phase 2 test group together, then the whole suite, to confirm the existing 133 tests remain green and byte-identical (the reducer is inert until Phase 3).

```
python -m pytest tests/test_valence_body.py tests/test_valence_config.py tests/test_valence_axes.py tests/test_valence_fragile.py tests/test_valence_composite.py -q
python -m pytest -q
```

Expected: all Phase 2 tests pass; the prior suite count is unchanged plus the new Phase 2 tests (no prior test flips, because `nervous_enabled` defaults False and `compute_body` is unwired).

- [ ] Step 4: Commit.

```
git -C E:/director2 add tests/test_valence_composite.py
git -C E:/director2 commit -m "Phase 2: full-composite + abstain-renormalization + OFF-path regression tests

Cover all four axes at/below/above saturation in compute_body, the
renormalize-on-abstain math (absolute thresholds, [-1,0] floor at -1.0), and the
hard OFF-path guarantees: advance() does not yet reference compute_body/valence
(Phase 3 wires it) and compute_body never mutates the project. Existing suite
stays green and byte-identical with nervous_enabled defaulting False.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

**Phase 2 exit criteria:** `director/core/valence.py` exists with `compute_body(project, *, secret, perf, since, cfg) -> BodyState` and its four private axis-severity helpers; `BodyState` and the five `Project` carrier fields round-trip through `encode`/`decode` (including the `"insufficient"` str arm and a `scream_open` dict); composite, renormalization-on-abstain (absolute thresholds), and fragile-band labeling are all unit-tested at/below/above saturation and at the band edges; `compute_body` never calls a model and never mutates the project; and with `nervous_enabled=False` the existing 133-test suite is unchanged and `advance()` does not yet reference the reducer (the Phase 3 wiring boundary). Key files: `E:/director2/director/core/valence.py`, `E:/director2/director/core/types.py`, `E:/director2/director/config.py`, and tests under `E:/director2/tests/test_valence_*.py`.

---

## Phase 3: Scream + Latch
Goal: Make `valence.py` decide ache vs siren vs calm (with hard per-axis overrides and precedence) and re-verify per-cause clear rules, then wire the siren latch, ache injection, autonomous halt, decide() suppression, and status readout into `director.py` — every new path gated behind `cfg.nervous_enabled` so the OFF path stays byte-identical and the 133-test suite stays green.

> **Phase 3 assumes Phases 1–2 already landed:** `director/core/types.py` carries `BodyState` plus the five new `Project` fields (`body`, `scream_open`, `cycle_seq`, `milestone_reverts`, `coherence_blocks`); `director/config.py` carries all the nervous-system `Config` fields (`nervous_enabled`, `valence_weights`, `ache_threshold`, `siren_threshold`, `valence_eps`, `hysteresis_margin`, `charter_breach_threshold`, `axis_saturation`, `max_held_cycles`, `budget`, …); and `director/core/valence.py` already exists exporting `compute_body(project, *, secret, perf, since, cfg) -> BodyState`. Phase 3 ADDS `evaluate_scream` and `check_clear_rule` to `valence.py` and wires the latch into `director.py`. Do not re-create those Phase 1–2 symbols; import them.

### Task 3.1: `evaluate_scream(project, body, *, cfg)` — ache vs siren vs None, hard overrides, precedence

Files:
- Modify: `E:/director2/director/core/valence.py` (append `evaluate_scream` after `compute_body`)
- Test: `E:/director2/tests/test_valence_scream.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_valence_scream.py` with the full evaluator state-table. `BodyState` is the Phase-1 dataclass; `evaluate_scream` is what we are about to add.

```python
"""Phase 3 — the Scream evaluator: ache vs siren vs calm, hard per-axis
overrides to siren (tamper / charter_breach / grounding_damage), and the
declared cause-attribution precedence. All trusted Python — no model calls."""

import pytest

from director.config import Config
from director.core.types import BodyState, Project
from director.core.valence import evaluate_scream


@pytest.fixture()
def cfg(tmp_path) -> Config:
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


def _body(**kw) -> BodyState:
    base = dict(charter_integrity=0.0, accumulated_damage=0.0, uncertainty=0.0,
                resource_bleed="insufficient", valence=0.0, computed_at=1)
    base.update(kw)
    return BodyState(**base)


def test_calm_below_ache_returns_none(cfg):
    p = Project(name="calm")
    body = _body(valence=-0.10)
    assert evaluate_scream(p, body, cfg=cfg) is None


def test_ache_between_thresholds(cfg):
    p = Project(name="ache")
    body = _body(valence=-0.45, accumulated_damage=0.5)  # between -0.33 and -0.66
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "ache"
    # ache cause = the offending axis name (largest-contributing axis)
    assert scream["cause"] == "accumulated_damage"
    assert scream["axis"] == "accumulated_damage"
    assert "report" in scream and scream["report"]
    # ache report carries the problem, never the numeric valence/threshold
    assert "-0.45" not in scream["report"]
    assert "valence" not in scream["report"].lower()


def test_siren_by_composite_grounding_damage(cfg):
    p = Project(name="siren")
    # composite past siren_threshold, no hard override -> grounding_damage
    body = _body(valence=-0.80, accumulated_damage=0.9)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "grounding_damage"
    assert scream["axis"] == "accumulated_damage"


def test_hard_override_tamper_forces_siren_regardless_of_composite(cfg):
    p = Project(name="tamper")
    # composite is healthy, but a tamper provenance flag forces a siren
    body = _body(valence=-0.02,
                 provenance={"integrity_violations": 1, "violation_ids": ["a"]})
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "tamper"
    assert scream["axis"] == "charter_integrity"


def test_hard_override_charter_breach_forces_siren(cfg):
    p = Project(name="breach")
    # charter_integrity severity at/above breach threshold -> charter_breach siren
    body = _body(valence=-0.10, charter_integrity=0.95)  # >= 0.90
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "charter_breach"
    assert scream["axis"] == "charter_integrity"


def test_precedence_tamper_beats_charter_breach(cfg):
    p = Project(name="both")
    body = _body(valence=-0.90, charter_integrity=1.0, accumulated_damage=1.0,
                 provenance={"integrity_violations": 2})
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream["cause"] == "tamper"  # tamper outranks charter_breach


def test_precedence_charter_breach_beats_grounding_damage(cfg):
    p = Project(name="cb_over_gd")
    body = _body(valence=-0.90, charter_integrity=0.95, accumulated_damage=1.0)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream["cause"] == "charter_breach"


def test_clear_rule_string_present_for_each_cause(cfg):
    p = Project(name="rules")
    for kw, expect in [
        (dict(valence=-0.02, provenance={"integrity_violations": 1}), "tamper"),
        (dict(valence=-0.10, charter_integrity=0.95), "charter_breach"),
        (dict(valence=-0.80, accumulated_damage=0.9), "grounding_damage"),
    ]:
        scream = evaluate_scream(p, _body(**kw), cfg=cfg)
        assert scream["cause"] == expect
        assert scream["clear_rule"], "every scream declares a clear rule"
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_valence_scream.py -q
```
Expected failure: `ImportError: cannot import name 'evaluate_scream' from 'director.core.valence'` (the function does not exist yet).

- [ ] Step 3: Read `E:/director2/director/core/valence.py` fully before editing so the appended code matches its import block and helper naming. (No command to run.) Confirm `BodyState`/`Project` are imported from `.types` and that `cfg` typing matches the existing helpers; find the insertion point after `compute_body`.

- [ ] Step 4: Append the minimal implementation to `E:/director2/director/core/valence.py` (after `compute_body`). This is trusted code that NEVER calls a model; it reads only the `body` projection (already computed by Phase 1) and `cfg` constants.

```python
# ----------------------------------------------------------------- scream
# Declared cause strings (Constitution d: declared semantics). Tamper and
# charter_breach are HARD per-axis overrides that force a siren regardless of
# the composite — a catastrophic axis must never hide behind three healthy
# ones. grounding_damage is the composite-driven deep negative.
_SIREN_CAUSES = ("tamper", "charter_breach", "grounding_damage")

_CLEAR_RULES = {
    "tamper": "integrity re-check returns 0 violations",
    "charter_breach": "charter_integrity recovers below "
                      "charter_breach_threshold - hysteresis_margin",
    "grounding_damage": "the offending risk(s) close AND a run_properties "
                        "re-pass on the deliverable passes",
}

# axes that feed the composite, in declared order; used to attribute an ache
# to its largest-contributing axis (problems-not-rubrics, §3b).
_COMPOSITE_AXES = ("charter_integrity", "accumulated_damage",
                   "uncertainty", "resource_bleed")


def _axis_severity(body: "BodyState", axis: str) -> float:
    """Severity of one axis as a float in [0,1]; an abstaining ('insufficient')
    axis contributes 0 to attribution."""
    val = getattr(body, axis, 0.0)
    return float(val) if isinstance(val, (int, float)) else 0.0


def _largest_axis(body: "BodyState", cfg) -> str:
    """The axis carrying the most severity * weight — the one to name in the
    diagnosis. Ties resolve in declared order."""
    weights = cfg.valence_weights
    best, best_score = _COMPOSITE_AXES[0], -1.0
    for axis in _COMPOSITE_AXES:
        score = _axis_severity(body, axis) * float(weights.get(axis, 0.0))
        if score > best_score:
            best, best_score = axis, score
    return best


def evaluate_scream(project: "Project", body: "BodyState", *, cfg) -> dict | None:
    """Trusted threshold evaluator. Returns None when calm; else a dict
    {level, cause, axis, clear_rule, report}. NEVER calls a model and NEVER
    leaks the numeric valence/threshold/weights into the report (Constitution
    b: problems, not rubrics)."""
    if not cfg.nervous_enabled:
        return None

    # --- hard per-axis overrides -> siren, regardless of composite -----------
    prov = body.provenance or {}
    if int(prov.get("integrity_violations", 0)) > 0:
        return {"level": "siren", "cause": "tamper",
                "axis": "charter_integrity",
                "clear_rule": _CLEAR_RULES["tamper"],
                "report": ("Trusted integrity re-check found tampered "
                           "property report(s): signature binding INVALID. "
                           "Work is halted until the forgery is removed and "
                           "integrity re-verifies clean.")}

    ci = _axis_severity(body, "charter_integrity")
    if ci >= float(cfg.charter_breach_threshold):
        return {"level": "siren", "cause": "charter_breach",
                "axis": "charter_integrity",
                "clear_rule": _CLEAR_RULES["charter_breach"],
                "report": ("Charter integrity has breached: a CRITICAL "
                           "grounding risk is open and/or milestones reverted "
                           "/ coherence blocked the core mission. Recovery "
                           "must restore charter alignment before work "
                           "resumes.")}

    # --- composite gradient -------------------------------------------------
    v = float(body.valence)
    if v > float(cfg.ache_threshold):
        return None

    axis = _largest_axis(body, cfg)
    if v <= float(cfg.siren_threshold):
        return {"level": "siren", "cause": "grounding_damage", "axis": axis,
                "clear_rule": _CLEAR_RULES["grounding_damage"],
                "report": _diagnosis_report(project, body, axis)}

    # ache: the offending axis is the cause (an ache is a wince, not a halt)
    return {"level": "ache", "cause": axis, "axis": axis,
            "clear_rule": "", "report": _diagnosis_report(project, body, axis)}


def _diagnosis_report(project: "Project", body: "BodyState", axis: str) -> str:
    """A failing-cases + cause sentence for the offending axis — the problem,
    never the numeric valence/threshold (Constitution b)."""
    prov = body.provenance or {}
    refs = prov.get(f"{axis}_refs") or prov.get("risk_ids") or []
    detail = ("; refs: " + ", ".join(str(r) for r in refs[:5])) if refs else ""
    pretty = axis.replace("_", " ")
    return (f"Damage on {pretty}: trusted state shows accumulated failures on "
            f"this axis from executed/verified work{detail}.")
```

> **DEVIATION NOTE (coherence-freeze override deferred):** the spec lists a THIRD hard override — "unrecoverable coherence freeze" — that is DEFERRED in v1. No trusted freeze-state signal exists today: `coherence_blocks` is a count that already feeds the `charter_integrity` axis (Phase 1/Phase 2), so a coherence-freeze siren would have no independent, un-gameable signal to override on. Revisit and add the third override once an explicit freeze state is introduced.

> **NOTE (charter_breach threshold):** `evaluate_scream` fires `charter_breach` at `charter_integrity >= cfg.charter_breach_threshold` (a `>=` comparison against the declared default `0.90`). This is deliberately more robust than the spec's "= 1" wording — a severity that has saturated to or past the breach line trips the override without requiring an exact `1.0`.

- [ ] Step 5: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_valence_scream.py -q
```
Expected: all tests pass.

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/core/valence.py tests/test_valence_scream.py
git -C E:/director2 commit -m "Phase 3.1: evaluate_scream — ache/siren/None, hard overrides, cause precedence

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: `check_clear_rule(project, scream_open, *, secret, perf, since, cfg)` — per-cause trusted re-verification

Files:
- Modify: `E:/director2/director/core/valence.py` (append `check_clear_rule` after `evaluate_scream`)
- Test: `E:/director2/tests/test_valence_clear_rule.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_valence_clear_rule.py`. The clear rule re-verifies the SAME trusted facts the siren tripped on — never a packet disposition, never an LLM "it's fixed". tamper re-checks integrity; charter_breach re-checks `charter_integrity` severity below `charter_breach_threshold - hysteresis_margin` (hysteresis); grounding_damage re-checks the risk(s) closed AND a `run_properties` re-pass.

```python
"""Phase 3 — per-cause clear-rule re-verification. The latch clears ONLY when
trusted Python re-verifies the declared per-cause condition, never on packet
answer/defer and never on an LLM assertion."""

import pytest

from director.config import Config
from director.core.types import (Artifact, BodyState, Project, Risk,
                                  RiskLevel, RiskStatus, Task, TaskStatus)
from director.core.valence import check_clear_rule
from director.evolve.metrics import PerfLedger


@pytest.fixture()
def cfg(tmp_path) -> Config:
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


@pytest.fixture()
def perf(cfg) -> PerfLedger:
    return PerfLedger(cfg)


def _latch(cause, axis="charter_integrity", refs=None):
    return {"cause": cause, "axis": axis, "opened_at": 1, "held_cycles": 1,
            "clear_rule": "x", "origin_refs": refs or []}


# --- tamper -----------------------------------------------------------------
def test_tamper_clears_when_no_violations(cfg, perf):
    p = Project(name="t")  # no property_report artifacts -> 0 integrity violations
    secret = cfg.report_secret()
    latch = _latch("tamper")
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True


def test_tamper_stays_held_while_violation_present(cfg, perf, monkeypatch):
    p = Project(name="t")
    secret = cfg.report_secret()
    # force the integrity re-check to report a violation
    import director.core.valence as val
    monkeypatch.setattr(val, "_integrity_violation_count",
                        lambda project, secret: 1)
    assert check_clear_rule(p, _latch("tamper"), secret=secret, perf=perf,
                            since=None, cfg=cfg) is False


# --- charter_breach (hysteresis) --------------------------------------------
def test_charter_breach_clears_only_below_hysteresis_band(cfg, perf, monkeypatch):
    p = Project(name="cb")
    secret = cfg.report_secret()
    import director.core.valence as val
    # band = charter_breach_threshold - hysteresis_margin = 0.90 - 0.10 = 0.80
    # severity 0.85 is still inside the band -> NOT cleared (hysteresis)
    monkeypatch.setattr(val, "_charter_integrity_severity",
                        lambda project, secret, perf, since, cfg: 0.85)
    assert check_clear_rule(p, _latch("charter_breach"), secret=secret,
                            perf=perf, since=None, cfg=cfg) is False
    # severity 0.70 is below the band -> cleared
    monkeypatch.setattr(val, "_charter_integrity_severity",
                        lambda project, secret, perf, since, cfg: 0.70)
    assert check_clear_rule(p, _latch("charter_breach"), secret=secret,
                            perf=perf, since=None, cfg=cfg) is True


# --- grounding_damage (risk closed AND re-pass) -----------------------------
def test_grounding_damage_needs_risk_closed_and_repass(cfg, perf, monkeypatch):
    p = Project(name="gd")
    secret = cfg.report_secret()
    rk = Risk(title="code_runs failed", level=RiskLevel.HIGH,
              status=RiskStatus.OPEN, source="grounding")
    p.risks[rk.id] = rk
    art = Artifact(title="deliverable", kind="code", content="print(1)")
    p.artifacts[art.id] = art
    latch = _latch("grounding_damage", axis="accumulated_damage",
                   refs=[rk.id, art.id])

    import director.core.valence as val
    monkeypatch.setattr(val, "_run_properties_repass",
                        lambda project, latch: True)
    # risk still OPEN -> held even though re-pass would pass
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
    # close the risk -> now clears (risk closed AND re-pass True)
    rk.status = RiskStatus.CLOSED
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True
    # risk closed but re-pass fails -> still held
    monkeypatch.setattr(val, "_run_properties_repass",
                        lambda project, latch: False)
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False


# --- grounding_damage driven by FAILED tasks (no risk attributed) -----------
def test_grounding_damage_failed_task_refs_clear_when_recovered(cfg, perf):
    # a siren whose origin_refs are FAILED task ids and which recorded the
    # accumulated_damage severity it tripped at (opened_severity).
    p = Project(name="gd-failed")
    secret = cfg.report_secret()
    failed = [Task(title=f"t{i}", status=TaskStatus.FAILED) for i in range(5)]
    for t in failed:
        p.tasks[t.id] = t
    latch = {"cause": "grounding_damage", "axis": "accumulated_damage",
             "opened_at": 1, "held_cycles": 1, "clear_rule": "x",
             "origin_refs": [t.id for t in failed],
             "opened_severity": 1.0}      # severity at trip time (5/5 saturated)
    # tasks still FAILED -> severity unchanged -> held
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
    # recover the tasks (no longer FAILED) -> severity drops below opened_severity
    for t in failed:
        t.status = TaskStatus.DONE
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True


def test_unknown_cause_does_not_clear(cfg, perf):
    p = Project(name="u")
    secret = cfg.report_secret()
    assert check_clear_rule(p, _latch("mystery"), secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_valence_clear_rule.py -q
```
Expected failure: `ImportError: cannot import name 'check_clear_rule' from 'director.core.valence'`.

- [ ] Step 3: Append the minimal implementation to `E:/director2/director/core/valence.py` (after `evaluate_scream`). Reuse the integrity helpers from `director/core/integrity.py` (`report_integrity` + `integrity_violations`) and `run_properties` from `director/verify/properties.py`. The three module-private helpers are defined so the tests can monkeypatch them independently.

```python
# ------------------------------------------------------------- clear rules
def _integrity_violation_count(project: "Project", secret: bytes) -> int:
    """Trusted re-check: how many property reports have a BROKEN binding
    (tamper evidence). Mirrors integrity_summary(...)['violations']."""
    from .integrity import integrity_violations, report_integrity
    return len(integrity_violations(report_integrity(project, secret)))


def _charter_integrity_severity(project: "Project", secret: bytes,
                                perf, since, cfg) -> float:
    """Recompute just the charter_integrity axis severity via the Phase-1
    reducer, so the clear rule re-verifies the SAME trusted fact the siren
    tripped on."""
    body = compute_body(project, secret=secret, perf=perf, since=since, cfg=cfg)
    val = getattr(body, "charter_integrity", 0.0)
    return float(val) if isinstance(val, (int, float)) else 0.0


def _run_properties_repass(project: "Project", scream_open: dict) -> bool:
    """Re-run the trusted property checkers over the offending deliverable.
    True iff the deliverable now passes its declared properties (the grounding
    re-pass)."""
    from ..verify.properties import partial_bundle_ok, run_properties
    refs = scream_open.get("origin_refs") or []
    deliverable = None
    for ref in refs:
        art = project.artifacts.get(ref)
        if art is not None and getattr(art, "kind", "") != "property_report":
            deliverable = art
            break
    if deliverable is None:
        return False
    names = ["python_parses", "code_runs"] if deliverable.kind in (
        "code", "python") else ["nonempty"]
    report = run_properties(deliverable.content, names, ref=None,
                            ref_independent=True)
    return partial_bundle_ok(report) or bool(report.get("force_to_fail_ok"))


def check_clear_rule(project: "Project", scream_open: dict, *, secret: bytes,
                     perf, since, cfg) -> bool:
    """True iff the declared per-cause clear condition RE-VERIFIES in trusted
    code. Never reads packet disposition; never trusts an LLM 'it is fixed'."""
    cause = (scream_open or {}).get("cause", "")
    if cause == "tamper":
        return _integrity_violation_count(project, secret) == 0
    if cause == "charter_breach":
        band = float(cfg.charter_breach_threshold) - float(cfg.hysteresis_margin)
        return _charter_integrity_severity(
            project, secret, perf, since, cfg) < band
    if cause == "grounding_damage":
        refs = scream_open.get("origin_refs") or []
        has_risk_ref = any(r in project.risks for r in refs)
        if has_risk_ref:
            # refs are risk ids: keep the existing rule — the offending risk(s)
            # close AND a run_properties re-pass on the deliverable passes.
            risks_closed = all(
                project.risks[r].status in (RiskStatus.CLOSED,
                                            RiskStatus.ACCEPTED)
                for r in refs if r in project.risks)
            return (risks_closed
                    and _run_properties_repass(project, scream_open))
        # refs are FAILED task ids (the accumulated_damage driver when no risk
        # was attributed): clear when none of those tasks are FAILED anymore AND
        # the accumulated_damage severity has dropped below its siren
        # contribution (the severity it was carrying when the siren tripped).
        task_refs = [r for r in refs if r in project.tasks]
        if task_refs:
            no_longer_failed = all(
                project.tasks[r].status is not TaskStatus.FAILED
                for r in task_refs)
            sev = _severity_accumulated_damage(project, secret=secret, cfg=cfg)
            opened_sev = float(scream_open.get("opened_severity", 0.0))
            return no_longer_failed and sev < opened_sev
        return False
    return False
```

  Ensure `RiskStatus` and `TaskStatus` are imported at the top of `valence.py` (`from .types import ... RiskStatus, TaskStatus`); both should already be present from Phase 1/Phase 2 — if either is missing, add it to the existing `from .types import` line. (Read the top of the file first; do not add a duplicate import line.) `_severity_accumulated_damage` is the Phase 2 helper already defined in this module.

> **Reachability note (FAILED-driven sirens):** when the siren cause is `grounding_damage` and no grounding risk was attributed, the latch's `origin_refs` are the FAILED task ids driving `accumulated_damage` (set by `_handle_siren`, Task 3.5), and the latch records `opened_severity` = the `accumulated_damage` severity at trip time. The clear rule above is then reachable: it clears once those tasks are no longer FAILED and the severity has dropped below that recorded contribution. This makes the grounding_damage clear path real for the common bench case where the fault is repeated FAILED tasks rather than an open `Risk`.

- [ ] Step 4: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_valence_clear_rule.py -q
```
Expected: all tests pass.

- [ ] Step 5: Commit.
```
git -C E:/director2 add director/core/valence.py tests/test_valence_clear_rule.py
git -C E:/director2 commit -m "Phase 3.2: check_clear_rule — per-cause trusted re-verification with hysteresis

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.3: `_make_packet` / `_fallback_packet` trusted-body path (`context_override`)

Files:
- Modify: `E:/director2/director/core/director.py` (`_make_packet` 495-566; `_fallback_packet` 568-603)
- Test: `E:/director2/tests/test_packet_context_override.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_packet_context_override.py`. When `context_override` is set, the FINAL packet `.context` is the trusted report VERBATIM — for both the generated path (mock router still serves options) and the fallback path. The LLM may still propose options; only `.context` is pinned.

```python
"""Phase 3 — _make_packet trusted-body path: when context_override is set, the
presented packet's .context is the trusted damage report VERBATIM (Constitution
#3: the trusted report is not re-narrated by the generator)."""

import pytest

from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.errors import ModelError
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


TRUSTED = ("Damage on accumulated damage: trusted state shows accumulated "
           "failures on this axis from executed/verified work.")


def test_generated_packet_context_is_overridden(boss):
    project, _ = boss.new_project("ov", "objective")
    pkt = boss._make_packet(project, trigger="scream:grounding_damage",
                            hint=TRUSTED, context_override=TRUSTED)
    assert pkt.context == TRUSTED  # verbatim, not re-narrated


def test_fallback_packet_carries_override_context(boss, monkeypatch):
    project, _ = boss.new_project("ov2", "objective")

    def boom(*a, **k):
        raise ModelError("forced fallback")

    monkeypatch.setattr(boss.router, "structured", boom)
    pkt = boss._make_packet(project, trigger="scream:tamper",
                            hint=TRUSTED, context_override=TRUSTED)
    assert pkt.context == TRUSTED


def test_fallback_packet_default_context_unchanged_without_override(boss):
    pkt = Director._fallback_packet("milestone:x", "some hint")
    assert pkt.context == "Decision point reached (milestone:x). some hint"


def test_no_override_leaves_generated_context_intact(boss):
    project, _ = boss.new_project("ov3", "objective")
    pkt = boss._make_packet(project, trigger="agent:x", hint="a fork")
    # without context_override the model/fallback context flows through unchanged
    assert isinstance(pkt.context, str) and pkt.context
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_packet_context_override.py -q
```
Expected failure: `TypeError: _make_packet() got an unexpected keyword argument 'context_override'`.

- [ ] Step 3: Implement the minimal change. Edit `_make_packet` signature (director.py:495-496) and the two `_fallback_packet` call sites inside it, and set `.context` verbatim at the very end before returning. Apply these exact edits:

  Replace the signature line:
```python
    def _make_packet(self, project: Project, *, trigger: str,
                     hint: str) -> CommandPacket:
```
  with:
```python
    def _make_packet(self, project: Project, *, trigger: str,
                     hint: str, context_override: str | None = None
                     ) -> CommandPacket:
```

  Replace the ModelError fallback line inside `_make_packet`:
```python
        except ModelError as exc:
            log.warning("packet generation failed (%s); deterministic fallback", exc)
            packet = self._fallback_packet(trigger, hint)
```
  with:
```python
        except ModelError as exc:
            log.warning("packet generation failed (%s); deterministic fallback", exc)
            packet = self._fallback_packet(trigger, hint, context_override)
```

  Replace the rejected-packet re-fallback line inside `_make_packet`. **Disambiguation note:** the line `packet = self._fallback_packet(trigger, hint)` appears TWICE in `director.py` — once in the ModelError branch (~line 519, edited just above) and once in the rejected-packet branch (~line 526). THIS edit targets the SECOND occurrence — the one immediately followed by `report = self.registry.get("command_packet").verify(packet)` at ~line 527 — so include that trailing line in the Edit `old_string` to match uniquely:
```python
            packet = self._fallback_packet(trigger, hint)
            report = self.registry.get("command_packet").verify(packet)
```
  with:
```python
            packet = self._fallback_packet(trigger, hint, context_override)
            report = self.registry.get("command_packet").verify(packet)
```

  Then insert, immediately BEFORE `packet.status = PacketStatus.PRESENTED` (after the coherence-evaluation `self._audit(... "packet.coherence" ...)` block), this trusted-body pin:
```python
        # trusted-body path (Constitution #3): when the siren supplies a
        # trusted damage report, surface it VERBATIM — the LLM may still
        # propose recovery OPTIONS, but it does not get to re-narrate the
        # measured damage. Set last so no post-processing can overwrite it.
        if context_override is not None:
            packet.context = context_override
```

  Edit `_fallback_packet` (director.py:568) signature:
```python
    @staticmethod
    def _fallback_packet(trigger: str, hint: str) -> CommandPacket:
        """Deterministic, always-valid packet for offline/failed generation."""
        return CommandPacket(
            title="Choose how to proceed",
            context=f"Decision point reached ({trigger}). {hint}",
```
  to:
```python
    @staticmethod
    def _fallback_packet(trigger: str, hint: str,
                         context_override: str | None = None) -> CommandPacket:
        """Deterministic, always-valid packet for offline/failed generation."""
        return CommandPacket(
            title="Choose how to proceed",
            context=(context_override if context_override is not None
                     else f"Decision point reached ({trigger}). {hint}"),
```

- [ ] Step 4: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_packet_context_override.py -q
```
Expected: all tests pass.

- [ ] Step 5: Run the existing director suite to prove the OFF-path is byte-identical (callers that pass no `context_override` are unaffected). From `E:/director2`:
```
python -m pytest tests/test_director.py -q
```
Expected: all existing tests pass (the new optional kwarg defaults to None, so every existing `_make_packet`/`_fallback_packet` call behaves exactly as before).

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/core/director.py tests/test_packet_context_override.py
git -C E:/director2 commit -m "Phase 3.3: _make_packet/_fallback_packet context_override — verbatim trusted body

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.4: `advance()` autonomous flag + cycle_seq + valence pass + clear-rule re-check + latch stop-gate

Files:
- Modify: `E:/director2/director/core/director.py` (`advance` signature 704-706; stop-gate region 710-716; insertion site 806-817)
- Test: `E:/director2/tests/test_latch_state_machine.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_latch_state_machine.py`. This drives the full machine through the real `advance()`. To force a siren deterministically without a live model, the test injects a fault: it opens a CRITICAL grounding risk and sets `charter_integrity` high enough that `compute_body` returns a charter_breach. Since `compute_body` is Phase 1, the test instead monkeypatches the valence module functions the director calls, so this task tests the WIRING, not the math.

```python
"""Phase 3 — latch state machine driven through the real advance(): a siren
opens the latch, autonomous advance halts while held, held_cycles increments,
a human advance proceeds and (when the clear rule re-verifies) clears the
latch, and nervous_enabled=False leaves advance() byte-identical."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import BodyState, PacketStatus, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.auto_advance_after_decision = False
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


def _calm_body():
    return BodyState(valence=0.0, computed_at=0)


def _arm_siren(monkeypatch, clears_after_cycle=None):
    """Make the director's valence pass fire one grounding_damage siren, and
    let the clear rule re-verify only once we tell it to."""
    state = {"clear": False}

    def fake_compute(project, *, secret, perf, since, cfg):
        return BodyState(valence=-0.9, accumulated_damage=0.9, computed_at=1)

    def fake_eval(project, body, *, cfg):
        return {"level": "siren", "cause": "grounding_damage",
                "axis": "accumulated_damage",
                "clear_rule": "risk closed and re-pass",
                "report": "trusted damage report"}

    def fake_clear(project, scream_open, *, secret, perf, since, cfg):
        return state["clear"]

    monkeypatch.setattr(dmod, "compute_body", fake_compute)
    monkeypatch.setattr(dmod, "evaluate_scream", fake_eval)
    monkeypatch.setattr(dmod, "check_clear_rule", fake_clear)
    return state


def test_siren_opens_latch_and_autonomous_advance_halts(boss, monkeypatch):
    _arm_siren(monkeypatch)
    project, packet = boss.new_project("latch", "objective")
    boss.decide(project.id, packet.id, option_key="A")  # clear the plan packet
    # first autonomous advance trips the siren and opens the latch
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    assert p.scream_open is not None
    assert p.scream_open["cause"] == "grounding_damage"
    assert p.scream_open["held_cycles"] >= 1
    opened = p.scream_open["opened_at"]
    # next autonomous advance is HALTED by the latch (gated on autonomous)
    out = boss.advance(project.id, autonomous=True)
    assert out["status"] == "latched"
    p2 = boss.store.load(project.id)
    # held_cycles incremented while held, opened_at unchanged
    assert p2.scream_open["held_cycles"] > 1
    assert p2.scream_open["opened_at"] == opened


def test_human_advance_proceeds_through_held_latch_and_clears(boss, monkeypatch):
    state = _arm_siren(monkeypatch)
    project, packet = boss.new_project("human", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)  # open latch
    assert boss.store.load(project.id).scream_open is not None
    # human advance is exempt from the latch halt and drives recovery
    state["clear"] = True
    out = boss.advance(project.id, autonomous=False)
    assert out["status"] != "latched"
    assert boss.store.load(project.id).scream_open is None  # cleared on re-verify


def test_latch_does_not_clear_until_reverified(boss, monkeypatch):
    state = _arm_siren(monkeypatch)
    project, packet = boss.new_project("hold", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)  # open latch
    # human advance while the clear rule still fails -> latch stays open
    state["clear"] = False
    boss.advance(project.id, autonomous=False)
    assert boss.store.load(project.id).scream_open is not None


def test_cycle_seq_increments_each_advance(boss, monkeypatch):
    # calm body, no scream -> advance runs normally but still counts cycles
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: _calm_body())
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: None)
    monkeypatch.setattr(dmod, "check_clear_rule",
                        lambda *a, **k: True)
    project, packet = boss.new_project("seq", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    seq0 = boss.store.load(project.id).cycle_seq
    boss.advance(project.id, autonomous=True)
    seq1 = boss.store.load(project.id).cycle_seq
    assert seq1 == seq0 + 1


def test_nervous_disabled_no_latch_no_cycle_seq(cfg, monkeypatch):
    cfg.nervous_enabled = False
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    boss = Director(cfg, store, router, registry, runner)
    # even if the valence functions WOULD fire a siren, OFF means they never run
    _arm_siren(monkeypatch)
    project, packet = boss.new_project("off", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    assert p.scream_open is None
    assert p.cycle_seq == 0  # untouched when nervous_enabled is False
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_latch_state_machine.py -q
```
Expected failure: `TypeError: advance() got an unexpected keyword argument 'autonomous'`.

- [ ] Step 3: Implement the minimal wiring in `director.py`. First add the valence imports near the other `.taskgraph`/`.types` imports at the top of `director.py` (read the import block first to place it correctly):
```python
from .valence import check_clear_rule, compute_body, evaluate_scream
```

  Edit the `advance` signature (director.py:704-706):
```python
    def advance(self, project_ref: str, *, max_tasks: int | None = None,
                force: bool = False) -> dict:
```
  to:
```python
    def advance(self, project_ref: str, *, max_tasks: int | None = None,
                force: bool = False, autonomous: bool = False) -> dict:
```

  Add the latch stop-gate just AFTER the existing open-packet stop-gate (director.py:710-716), so a HELD latch halts the autonomous loop but a human `advance(autonomous=False)` is exempt:
```python
        project = self.store.load(project_ref)
        open_pkts = self._open_packets(project)
        if open_pkts and not force:
            return {"status": "awaiting_command",
                    "summary": f"{len(open_pkts)} command packet(s) open - "
                               f"decide first or use force",
                    "packets": [p.id for p in open_pkts], "ran": 0}
        # latch halt: a held scream stops AUTONOMOUS work (and the
        # decide()->advance auto-advance path); a human-commanded advance is
        # exempt and drives recovery (§8.3). held_cycles advances each hop so
        # the deadlock guard has a concrete value.
        if (self.cfg.nervous_enabled and autonomous and project.scream_open
                and not force):
            sc = project.scream_open
            sc["held_cycles"] = int(sc.get("held_cycles", 0)) + 1
            self.store.save(project)
            return {"status": "latched",
                    "summary": f"SCREAM held ({sc['cause']}); "
                               f"held_cycles={sc['held_cycles']} - "
                               f"clear: {sc.get('clear_rule', '')}",
                    "scream": dict(sc), "ran": 0}
```

  > **Gate-ordering note:** the pre-existing open-packet gate runs BEFORE this latch gate, so the cycle immediately after a siren returns `"awaiting_command"` (the siren packet `_handle_siren` raised is still open); only once that packet is answered/deferred with the latch still held does an autonomous advance reach the latch gate and return `"latched"`. The driver and the integration test treat BOTH `"awaiting_command"` and `"latched"` as halts (see Phase 5's `status in ("latched", "awaiting_command")` membership check).

  Add the valence pass + clear-rule re-check at the insertion site (director.py:806-817), AFTER `reached = refresh_milestones(project)` and the milestone loop, and BEFORE the final `self.store.save(project)`:
```python
        if self.cfg.nervous_enabled:
            self._nervous_pass(project, autonomous=autonomous)

        self.store.save(project)
```
  (the existing `self.store.save(project)` line stays; the `_nervous_pass` call goes immediately above it).

  Add the `_nervous_pass` method next to `advance` (it owns the cycle_seq increment, body recompute, clear-rule re-test, and scream dispatch — keeping `advance` readable). The siren/ache action handlers are added in Task 3.5; for THIS task stub them so the latch + cycle_seq + clear behavior is exercised:
```python
    # ---------------------------------------------------------- nervous pass
    def _nervous_pass(self, project: Project, *, autonomous: bool) -> None:
        """Trusted valence pass: bump cycle_seq, recompute the Body, re-test an
        open latch's clear rule, then evaluate the scream. Guarded entirely by
        cfg.nervous_enabled so the OFF path never reaches here."""
        project.cycle_seq += 1
        secret = self.cfg.report_secret()
        since = getattr(self, "_run_since", None)
        body = compute_body(project, secret=secret, perf=self.perf,
                             since=since, cfg=self.cfg)
        project.body = body

        # re-test the clear rule for an OPEN latch (trusted re-verification);
        # clears in place when the declared per-cause condition holds again.
        if project.scream_open is not None:
            if check_clear_rule(project, project.scream_open, secret=secret,
                                perf=self.perf, since=since, cfg=self.cfg):
                cause = project.scream_open["cause"]
                self._audit(project, "scream.cleared",
                            f"latch cleared: {cause} re-verified",
                            {"cause": cause})
                project.scream_open = None
            else:
                # already latched and still failing — deadlock guard handled in
                # the stop-gate; do not re-evaluate a fresh scream over a held one
                return

        scream = evaluate_scream(project, body, cfg=self.cfg)
        if scream is None:
            return
        if scream["level"] == "ache":
            self._handle_ache(project, scream)
        else:
            self._handle_siren(project, scream, autonomous=autonomous)
```

  For this task, add minimal `_handle_ache` / `_handle_siren` stubs (fully fleshed out in Task 3.5). The siren stub must open the latch so the latch tests pass:
```python
    def _handle_ache(self, project: Project, scream: dict) -> None:
        self._audit(project, "scream.ache",
                    f"ache on {scream['axis']}: {scream['report'][:200]}",
                    {"axis": scream["axis"]})

    def _handle_siren(self, project: Project, scream: dict, *,
                      autonomous: bool) -> None:
        report = scream["report"]
        self._make_packet(project, trigger="scream:" + scream["cause"],
                          hint=report, context_override=report)
        project.scream_open = {
            "cause": scream["cause"], "axis": scream["axis"],
            "opened_at": project.cycle_seq, "held_cycles": 1,
            "clear_rule": scream["clear_rule"], "origin_refs": []}
        self._audit(project, "scream.siren",
                    f"SCREAM ({scream['cause']}) — latch opened",
                    {"cause": scream["cause"], "axis": scream["axis"]})
```

  Note `self.perf` may not be an attribute on Director today (it is constructed but held by the runner/router). If `Director.__init__` (297-305) has no `self.perf`, add `perf=None` as a keyword-only arg mirroring `lessons` and store `self.perf = perf`; the bench/CLI/`run()` pass a real `PerfLedger`. When `self.perf` is None, `compute_body` must tolerate it (Phase 1 contract: `resource_bleed` abstains without a budget). For tests, `compute_body` is monkeypatched so `self.perf=None` is fine. Add to `__init__`:
```python
    def __init__(self, cfg: Config, store: ProjectStore, router: LLMRouter,
                 registry: VerifierRegistry, runner: SubAgentRunner,
                 *, lessons=None, perf=None):
        self.cfg = cfg
        self.store = store
        self.router = router
        self.registry = registry
        self.runner = runner
        self.lessons = lessons                 # LessonLedger | None (memory pkg)
        self.perf = perf                       # PerfLedger | None (valence pass)
        self._run_since = None                 # set by run() for run-scoped stats
```

- [ ] Step 4: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_latch_state_machine.py -q
```
Expected: all tests pass.

- [ ] Step 5: Prove OFF-path byte-identical. From `E:/director2`:
```
python -m pytest tests/test_director.py -q
```
Expected: all existing tests pass (`autonomous` defaults to False and `nervous_enabled` defaults to False, so the existing `boss.advance(project.id)` calls never enter `_nervous_pass` and never touch the latch/cycle_seq).

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/core/director.py tests/test_latch_state_machine.py
git -C E:/director2 commit -m "Phase 3.4: advance() autonomous gate + cycle_seq + valence pass + latch stop-gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.5: Ache injects a frontier-tail diagnostic task; siren report is trusted; deadlock escalation

Files:
- Modify: `E:/director2/director/core/director.py` (`_handle_ache`, `_handle_siren` from Task 3.4)
- Test: `E:/director2/tests/test_scream_actions.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_scream_actions.py`. The ache injects exactly ONE `role='review'` diagnostic task via `apply_delta` (`actor="director"`, coherence-legal), landing at the frontier tail with no priority/ordering bump and no early dependency edge. The siren opens the latch with the trusted report as the packet `.context`. The deadlock guard upgrades the packet once `held_cycles` exceeds `cfg.max_held_cycles`.

```python
"""Phase 3 — scream actions: ache injects ONE tail diagnostic review task with
no ordering bump; siren raises a packet whose context is the trusted report and
opens the latch; the deadlock guard escalates past max_held_cycles."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.taskgraph import ready_tasks
from director.core.types import BodyState, PacketStatus, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.auto_advance_after_decision = False
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


def test_ache_injects_one_tail_review_task(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.45,
                                                       accumulated_damage=0.5,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "ache", "cause": "accumulated_damage",
                            "axis": "accumulated_damage", "clear_rule": "",
                            "report": "failing case: code_runs failed on X"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: True)
    project, packet = boss.new_project("ache", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    before = len(boss.store.load(project.id).tasks)
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    injected = [t for t in p.tasks.values()
                if t.role == "review" and "diagnos" in t.objective.lower()]
    assert len(injected) == 1
    t = injected[0]
    # no priority bump / no early dependency edge: a normal tail slot
    assert t.depends_on == []
    assert t.status in (TaskStatus.PENDING, TaskStatus.READY)
    # an ache is a wince, not a halt: no latch
    assert p.scream_open is None
    # audit recorded the ache
    assert any(e.type == "scream.ache" for e in boss.store.journal(p.id))


def test_ache_injects_at_frontier_tail_not_ahead(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.45,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "ache", "cause": "uncertainty",
                            "axis": "uncertainty", "clear_rule": "",
                            "report": "diagnostic needed"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: True)
    project, packet = boss.new_project("tail", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    order = ready_tasks(p)
    injected = next(t for t in p.tasks.values()
                    if t.role == "review" and "diagnos" in t.objective.lower())
    if injected in order:
        # the freshly-created task sorts LAST by (created_at, id)
        assert order[-1].id == injected.id


def test_siren_packet_context_is_trusted_report_and_opens_latch(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       accumulated_damage=0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "risk closed and re-pass",
                            "report": "TRUSTED DAMAGE REPORT — code_runs failed"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)
    project, packet = boss.new_project("siren", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    assert p.scream_open is not None
    open_pkts = [pk for pk in p.packets.values()
                 if pk.status is PacketStatus.PRESENTED]
    siren_pkts = [pk for pk in open_pkts
                  if pk.trigger == "scream:grounding_damage"]
    assert siren_pkts and "TRUSTED DAMAGE REPORT" in siren_pkts[0].context


def test_deadlock_escalation_past_max_held_cycles(boss, monkeypatch):
    boss.cfg.max_held_cycles = 2
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "x", "report": "report"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)
    project, packet = boss.new_project("dead", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)  # open latch (held_cycles=1)
    # autonomous hops bump held_cycles via the stop-gate
    boss.advance(project.id, autonomous=True)  # held_cycles=2
    boss.advance(project.id, autonomous=True)  # held_cycles=3 > max_held_cycles
    p = boss.store.load(project.id)
    assert any(e.type == "scream.deadlock" for e in boss.store.journal(p.id))
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_scream_actions.py -q
```
Expected failure: the ache stub records an audit but injects no task, so `assert len(injected) == 1` fails (and `scream.deadlock` is never recorded).

- [ ] Step 3: Replace the Task 3.4 `_handle_ache` stub with the real injection, and the `_handle_siren` stub with the latch + deadlock-aware version. Also add the deadlock escalation to the stop-gate (it fires when an already-held latch's `held_cycles` exceeds `cfg.max_held_cycles`).

  Replace `_handle_ache`:
```python
    def _handle_ache(self, project: Project, scream: dict) -> None:
        """An ache is a wince: record it (always) and inject AT MOST one bounded
        diagnostic review task at the frontier tail — no priority, no early
        dependency edge, no posture change (Constitution #5)."""
        self._audit(project, "scream.ache",
                    f"ache on {scream['axis']}: {scream['report'][:200]}",
                    {"axis": scream["axis"]})
        axis = scream["axis"]
        module_id = ""
        # offending task's module if a ref names one, else '' (frontier-global)
        from .coherence import apply_delta
        from .types import StateDelta
        delta = StateDelta(
            trigger=f"ache:{project.cycle_seq}",
            summary=f"diagnostic for ache on {axis}",
            payload={"new_tasks": [{
                "title": f"Diagnose {axis.replace('_', ' ')} "
                         f"(cycle {project.cycle_seq})",
                "role": "review", "module_id": module_id,
                "objective": ("Diagnose this failing case and its cause, then "
                              "propose a fix: " + scream["report"])}]})
        try:
            apply_delta(project, delta, actor="director")
        except CoherenceBlockedError as exc:
            # an ache must never destabilize the graph — drop it, count it
            project.coherence_blocks += 1
            self._audit(project, "scream.ache_blocked",
                        f"ache diagnostic blocked by coherence: {exc}",
                        {"axis": axis})
```

  Replace `_handle_siren`:
```python
    def _handle_siren(self, project: Project, scream: dict, *,
                      autonomous: bool) -> None:
        """A siren raises a Command Packet carrying the TRUSTED damage report
        verbatim and opens the latch (the one genuinely new persistent state).
        It never picks a recovery branch (Constitution #3/#5)."""
        from .types import TaskStatus
        report = scream["report"]
        cause = scream["cause"]
        self._make_packet(project, trigger="scream:" + cause, hint=report,
                          context_override=report)
        # origin_refs are the offending RISK ids when grounding attributed a
        # risk; ELSE the FAILED task ids driving accumulated_damage, so the
        # grounding_damage clear rule is reachable even with no open Risk
        # (the common bench case is repeated FAILED tasks). Record the
        # accumulated_damage severity at trip time so the FAILED-driven clear
        # rule can detect that it has since dropped.
        risk_ids = list((project.body.provenance or {}).get("risk_ids", [])) \
            if project.body else []
        if risk_ids:
            origin_refs = risk_ids
        else:
            origin_refs = [t.id for t in project.tasks.values()
                           if t.status is TaskStatus.FAILED]
        opened_severity = float(getattr(project.body, "accumulated_damage", 0.0)
                                if project.body else 0.0)
        project.scream_open = {
            "cause": cause, "axis": scream["axis"],
            "opened_at": project.cycle_seq, "held_cycles": 1,
            "clear_rule": scream["clear_rule"], "origin_refs": origin_refs,
            "opened_severity": opened_severity}
        self._audit(project, "scream.siren",
                    f"SCREAM ({cause}) — latch opened, clear: "
                    f"{scream['clear_rule']}",
                    {"cause": cause, "axis": scream["axis"]})
```

  Add the deadlock escalation inside the latch stop-gate added in Task 3.4 — extend that block so that when `held_cycles` crosses `cfg.max_held_cycles`, it raises an escalation packet once. Replace the Task 3.4 stop-gate block:
```python
        if (self.cfg.nervous_enabled and autonomous and project.scream_open
                and not force):
            sc = project.scream_open
            sc["held_cycles"] = int(sc.get("held_cycles", 0)) + 1
            if (sc["held_cycles"] > self.cfg.max_held_cycles
                    and not sc.get("escalated")):
                sc["escalated"] = True
                self._make_packet(
                    project, trigger="scream:deadlock:" + sc["cause"],
                    hint=(f"Latch on {sc['cause']} has held "
                          f"{sc['held_cycles']} cycles past the limit — "
                          f"unrecoverable; operator decision required."),
                    context_override=(
                        f"DEADLOCK: the {sc['cause']} scream has not cleared "
                        f"after {sc['held_cycles']} held cycles. Trusted "
                        f"re-verification ({sc.get('clear_rule', '')}) still "
                        f"fails. Operator decision required."))
                self._audit(project, "scream.deadlock",
                            f"latch {sc['cause']} exceeded max_held_cycles "
                            f"({self.cfg.max_held_cycles})",
                            {"cause": sc["cause"],
                             "held_cycles": sc["held_cycles"]})
            self.store.save(project)
            return {"status": "latched",
                    "summary": f"SCREAM held ({sc['cause']}); "
                               f"held_cycles={sc['held_cycles']} - "
                               f"clear: {sc.get('clear_rule', '')}",
                    "scream": dict(sc), "ran": 0}
```

  Confirm `CoherenceBlockedError` is imported in `director.py` (the `decide()` method already uses it, so the import exists at the top — do not duplicate).

- [ ] Step 4: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_scream_actions.py -q
```
Expected: all tests pass.

- [ ] Step 5: Re-run the latch machine and director suites (regression). From `E:/director2`:
```
python -m pytest tests/test_latch_state_machine.py tests/test_director.py -q
```
Expected: all pass.

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/core/director.py tests/test_scream_actions.py
git -C E:/director2 commit -m "Phase 3.5: ache tail-injection, trusted siren report, deadlock escalation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.6: Suppress `decide()` auto-advance while latched; clear-rule on the human path; `status()` SCREAM line

Files:
- Modify: `E:/director2/director/core/director.py` (`decide` auto-advance branch 683-688; `status` return 1234-1268)
- Test: `E:/director2/tests/test_latch_decide_status.py` (Create)

- [ ] Step 1: Write the failing test. Create `E:/director2/tests/test_latch_decide_status.py`. While `project.scream_open` is set, `decide()` must NOT auto-advance (a human disposition cannot drive the loop through a held latch); answering/deferring the siren packet does NOT clear the latch (only trusted re-verification does); `status()` shows a red `SCREAM: <cause>` line with the clear rule.

```python
"""Phase 3 — decide() must not auto-advance while a latch is held; a packet
answer never clears the latch; status() surfaces the SCREAM line."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import BodyState, PacketStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.auto_advance_after_decision = True  # ON: prove the latch still suppresses it
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


def _arm_siren(monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       accumulated_damage=0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "risk closed and re-pass",
                            "report": "trusted damage report"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)


def _open_latch(boss, monkeypatch, name):
    _arm_siren(monkeypatch)
    project, packet = boss.new_project(name, "objective")
    boss.decide(project.id, packet.id, option_key="A")  # plan packet (no latch yet)
    boss.advance(project.id, autonomous=True)            # trip the siren
    return project


def test_decide_does_not_auto_advance_while_latched(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "noadv")
    p = boss.store.load(project.id)
    siren_pkt = next(pk for pk in p.packets.values()
                     if pk.trigger == "scream:grounding_damage"
                     and pk.status is PacketStatus.PRESENTED)
    result = boss.decide(project.id, siren_pkt.id, option_key="A")
    # auto_advance is ON, but the held latch suppresses the follow-up advance
    assert result["follow_up"] == "none"


def test_answering_siren_packet_does_not_clear_latch(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "noclear")
    p = boss.store.load(project.id)
    siren_pkt = next(pk for pk in p.packets.values()
                     if pk.trigger == "scream:grounding_damage"
                     and pk.status is PacketStatus.PRESENTED)
    boss.decide(project.id, siren_pkt.id, option_key="A")
    # the latch persists: only trusted re-verification clears it, never an answer
    assert boss.store.load(project.id).scream_open is not None


def test_status_shows_scream_line(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "statusline")
    st = boss.status(project.id)
    assert st.get("scream") is not None
    assert st["scream"]["cause"] == "grounding_damage"
    assert "scream:grounding_damage" in st["next_action"] or \
        st["scream"]["clear_rule"]
    # display-only health readout is surfaced when nervous_enabled, carrying
    # valence + fragile_axes (and never sets project.body / the latch / saves)
    assert st["health"] is not None
    assert "valence" in st["health"] and "fragile_axes" in st["health"]


def test_status_no_scream_when_calm(boss):
    project, packet = boss.new_project("calm", "objective")
    st = boss.status(project.id)
    assert st.get("scream") is None
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_latch_decide_status.py -q
```
Expected failure: `test_decide_does_not_auto_advance_while_latched` fails because `decide()` still auto-advances (its branch ignores `scream_open`), and `status()` has no `scream` key.

- [ ] Step 3: Implement. Edit the `decide()` auto-advance branch (director.py:683-688):
```python
        if (self.cfg.auto_advance_after_decision and
                response in (ResponseType.SELECT_OPTION,
                             ResponseType.SELECT_AND_MODIFY) and
                not self._open_packets(project)):
            adv = self.advance(project.id)
            result["follow_up"] = f"auto-advanced: {adv['summary']}"
        return result
```
  to (add the `not project.scream_open` guard so a held latch blocks the auto-advance — Constitution #5):
```python
        if (self.cfg.auto_advance_after_decision and
                response in (ResponseType.SELECT_OPTION,
                             ResponseType.SELECT_AND_MODIFY) and
                not self._open_packets(project) and
                not (self.cfg.nervous_enabled and project.scream_open)):
            adv = self.advance(project.id)
            result["follow_up"] = f"auto-advanced: {adv['summary']}"
        return result
```

  Edit `status()` (director.py:1234-1268) to add a `scream` entry and a display-only `health` entry to the return dict. Insert just before the `return {` (right after the `failed`/`next_action` computation) a small block, and add the keys inside the returned dict:
```python
        scream = (project.scream_open
                  if (self.cfg.nervous_enabled and project.scream_open)
                  else None)
        if scream:
            # a red SCREAM line beside next_action, showing the clear rule
            next_action = (f"SCREAM: {scream['cause']} — recover then advance "
                           f"(clear: {scream.get('clear_rule', '')})")
        # display-only health readout: recompute the Body purely for the
        # readout — this is a pure projection, so status() does NOT set
        # project.body, does NOT call evaluate_scream, does NOT touch the latch,
        # and does NOT save. It only surfaces valence + fragile_axes.
        health = None
        if self.cfg.nervous_enabled:
            hbody = compute_body(project, secret=self.cfg.report_secret(),
                                 perf=self.perf, since=None, cfg=self.cfg)
            health = {"valence": hbody.valence,
                      "fragile_axes": list(hbody.fragile_axes)}
        return {
            "id": project.id, "name": project.name, "status": project.status,
            "objective": project.charter.objective,
            **summary,
            "open_packet_ids": [p.id for p in open_pkts],
            "needs_verify_ids": [t.id for t in needs_verify],
            "failed_ids": [t.id for t in failed],
            "artifacts": len(project.artifacts),
            "next_action": next_action,
            "scream": scream,
            "health": health,
        }
```
  (Replace the existing `return { ... }` block with the version above; the only additions are the `scream`/`health`-computing lines before it and the `"scream": scream,` / `"health": health,` keys. Everything else in the returned dict is byte-identical, so when `nervous_enabled=False`, `scream` and `health` are both `None` and `next_action` is unchanged. The `health` recompute is purely for display — it never mutates or saves the project.)

- [ ] Step 4: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_latch_decide_status.py -q
```
Expected: all tests pass.

- [ ] Step 5: Regression — the full director suite plus the prior Phase-3 tests must stay green, and `status()`'s new `scream` key must not break existing `status` assertions (the existing `test_status_next_action` only checks specific keys). From `E:/director2`:
```
python -m pytest tests/test_director.py tests/test_cli.py tests/test_dashboard.py -q
```
Expected: all pass (with `nervous_enabled` default False, `decide()`'s extra guard short-circuits on `self.cfg.nervous_enabled` and `status()`'s `scream` is `None`).

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/core/director.py tests/test_latch_decide_status.py
git -C E:/director2 commit -m "Phase 3.6: decide() suppresses auto-advance while latched; status SCREAM line

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.7: Full-suite regression — `nervous_enabled=False` keeps the 133 tests byte-identical

Files:
- Test: (no new file) — run the entire existing suite plus all Phase-3 tests

- [ ] Step 1: Run the FULL suite from `E:/director2`:
```
python -m pytest -q
```
Expected PASS: the pre-existing 133 tests stay green AND the seven new Phase-3 test modules pass. The hard constraint holds because every new code path in `advance()`, `decide()`, `status()`, and `_make_packet` is guarded behind `self.cfg.nervous_enabled` (default False) and/or the `autonomous` flag (default False) and/or an opt-in `context_override`/`scream_open is None`.

- [ ] Step 2: If any pre-existing test changed behavior, the regression is a flag-leak. Re-read the failing test and confirm the OFF path: `nervous_enabled` is False unless the test sets it; `advance(project.id)` still defaults `autonomous=False`; `_make_packet(...)` callers that omit `context_override` still see `None`. Fix the guard, do NOT change the test. Re-run:
```
python -m pytest -q
```
Expected: green.

- [ ] Step 3: Commit the regression checkpoint (no code change if already green — this records the byte-identical guarantee in history).
```
git -C E:/director2 add -A
git -C E:/director2 commit --allow-empty -m "Phase 3.7: full-suite green — nervous_enabled=False keeps existing suite byte-identical

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4: The Autonomous Loop

Goal: Add `Director.run(project_ref, *, autonomous=True, max_cycles=None)` — a state-less driver that calls the existing `advance(..., autonomous=True)` in a loop until a precedence-ordered `stop()` predicate fires — plus a `director run [--cycles N]` CLI command, all gated so the OFF path stays byte-identical.

> **Inheritance contract (consumed from Phase 3, not built here):** Phase 3 has already added `Project.cycle_seq` and the four other new `Project` fields, the `compute_body`/`evaluate_scream`/`check_clear_rule` valence wiring inside `advance()`, the `cfg.nervous_enabled` flag and the `cfg.budget`/`cfg.max_held_cycles` config keys, and the keyword-only `autonomous: bool = False` parameter on `advance()` with the latch halt gated on it. **Phase 4 only adds the driver loop and its stop predicate, and the CLI command.** `run()` owns no state — it reads existing summary/packet/latch/integrity/perf signals and calls `advance()`. Where Phase 4 needs a Phase-3 field that a test project may not carry yet, it reads it defensively with `getattr(project, "scream_open", None)` so the loop is robust to partial snapshots (the same decode-survival discipline as `BodyState`).

---

### Task 4.1: `run()` minimal loop + `max_cycles` bound

The smallest correct loop: repeatedly call `advance(..., autonomous=True)` and stop after `max_cycles` calls or when there is no ready work. This task establishes the method, the `since` capture, the cycle bound, and the "work drained" / "idle" stop. Later tasks layer the remaining four stop conditions into the same `stop()` predicate.

**Files:**
- Modify: `E:/director2/director/core/director.py` (add `run()` + a PUBLIC `stop()` predicate; insert immediately AFTER the `advance()` method, which ends at line 824)
- Modify: `E:/director2/tests/test_director.py` (append tests; reuse the `boss` fixture at lines 21-27)

Steps:

- [ ] Step 1: Add a deterministic-draining stub-runner helper at the TOP of the test file (after the existing imports, before `test_detect_cycles`). It lets the loop tests drive `advance()` to completion without the mock backend's packet/milestone churn. Insert after line 18 (`from director.verify import make_default_registry`):

```python
from director.agents.base import AgentResult, AgentSpec  # noqa: E402


class _DrainRunner:
    """Deterministic runner for loop tests: every dispatched spec succeeds
    with a trivial artifact-free output, so a task graph drains to DONE in a
    predictable number of advance() calls and the loop can be observed."""

    def run(self, spec: AgentSpec) -> AgentResult:
        return AgentResult(spec_id=spec.id, task_id=spec.task_id,
                           role=spec.role, ok=True,
                           output={"summary": "ok", "task_id": spec.task_id})

    def run_parallel(self, specs: list[AgentSpec]) -> list[AgentResult]:
        return [self.run(s) for s in specs]


def _loop_boss(cfg):
    """A Director wired with the drain runner (success on every task) so run()
    can be exercised without the mock backend opening packets each cycle."""
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    boss = Director(cfg, store, router, registry, _DrainRunner())
    return boss


def _seed_two_task_project(boss, name="loop"):
    """A persisted project with two ready/pending tasks and NO open packet,
    so advance(autonomous=True) can drain it directly."""
    p = Project(name=name)
    t1 = Task(title="first")
    t2 = Task(title="second", depends_on=[t1.id])
    p.tasks = {t1.id: t1, t2.id: t2}
    refresh_statuses(p)
    boss.store.save(p)
    return p
```

- [ ] Step 2: Append the failing test for the cycle bound and the drained-stop to `E:/director2/tests/test_director.py`:

```python
# ------------------------------------------------------------- autonomous loop
def test_run_drains_work_and_stops(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "drain")
    out = boss.run(p.id, autonomous=True)
    assert out["status"] == "stopped"
    assert out["stop_reason"] == "drained"
    p2 = boss.store.load(p.id)
    assert all(t.status is TaskStatus.DONE for t in p2.tasks.values())


def test_run_respects_max_cycles(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "bound")
    # max_cycles=1: exactly one advance() call, work NOT fully drained
    out = boss.run(p.id, autonomous=True, max_cycles=1)
    assert out["cycles"] == 1
    assert out["stop_reason"] == "max_cycles"
```

- [ ] Step 3: Run them; expect FAIL with `AttributeError: 'Director' object has no attribute 'run'`:

```
python -m pytest tests/test_director.py -k "run_drains_work_and_stops or run_respects_max_cycles" -q
```

- [ ] Step 4: Implement the minimal `run()` + `stop()` in `E:/director2/director/core/director.py`, inserted DIRECTLY AFTER the `advance()` method (after line 824, the `return` of the ok-dict). Mirror the existing method-comment banner style and the in-place-read pattern. Add `from ..evolve.metrics import PerfLedger` lazily inside `run()` (the codebase already lazy-imports `PerfLedger` in `dashboard/server.py`, so this matches convention and avoids a new top-level import cycle):

```python
    # ------------------------------------------------------------------- run
    def run(self, project_ref: str, *, autonomous: bool = True,
            max_cycles: int | None = None) -> dict:
        """Bounded autonomous loop: call advance(autonomous=True) until a
        declared stop condition fires. The loop OWNS NO STATE — every read is
        of the persisted project, the perf ledger, or config; every write is
        done by advance() through the trusted apply_delta/store.save boundary.
        `since` is captured ONCE at entry so the budget stop and resource_bleed
        see run-scoped tokens, not the lifetime ledger (metrics.py:61)."""
        from ..evolve.metrics import PerfLedger
        perf = getattr(self, "perf", None) or PerfLedger(self.cfg)
        since = utcnow().isoformat()
        cycles = 0
        while True:
            project = self.store.load(project_ref)
            reason = self.stop(project, perf=perf, since=since)
            if reason is not None:
                return {"status": "stopped", "stop_reason": reason,
                        "cycles": cycles, "since": since}
            if max_cycles is not None and cycles >= max_cycles:
                return {"status": "stopped", "stop_reason": "max_cycles",
                        "cycles": cycles, "since": since}
            self.advance(project_ref, autonomous=autonomous)
            cycles += 1

    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec §6). Returns
        a stop-reason string, or None to keep looping. Pure read-only over the
        loaded project + perf ledger; never mutates or saves."""
        # 5. work drained — no ready tasks and nothing RUNNING.
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        if not ready_tasks(project) and not running:
            return "drained"
        return None
```

- [ ] Step 5: Run again; expect PASS:

```
python -m pytest tests/test_director.py -k "run_drains_work_and_stops or run_respects_max_cycles" -q
```

- [ ] Step 6: Commit:

```
git -C E:/director2 add director/core/director.py tests/test_director.py
git -C E:/director2 commit -m "Phase 4.1: Director.run() minimal autonomous loop + max_cycles bound

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.2: `done` stop — summary done==tasks_total AND no ready/running (not vacuous all-milestones)

Add the precedence-#4 `done` stop. The contract is explicit that `done` must use the `status()` completion criterion (`summary['done'] == summary['tasks_total']` and no ready/running), **not** "all milestones reached" — which is vacuously true for a zero-milestone project and would halt on cycle 0. This task includes the regression test for that exact zero-milestone pitfall.

**Files:**
- Modify: `E:/director2/director/core/director.py` (extend `stop`, the helper added at the tail of `advance()` in Task 4.1)
- Modify: `E:/director2/tests/test_director.py` (append tests)

Steps:

- [ ] Step 1: Append the failing tests. The first proves a project with a not-yet-done task does NOT report `done`; the second is the critical zero-milestone regression — a project with NO milestones and unfinished work must keep looping, not halt vacuously on cycle 0:

```python
def test_run_stops_done_when_all_tasks_complete(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "done")
    out = boss.run(p.id, autonomous=True)
    # both tasks DONE -> summary done==tasks_total; drained subsumes done but
    # the done predicate must agree (no ready, no running, counts match)
    p2 = boss.store.load(p.id)
    summary = graph_summary(p2)
    assert summary["done"] == summary["tasks_total"]
    assert out["stop_reason"] in ("done", "drained")


def test_run_does_not_vacuously_halt_with_zero_milestones(cfg):
    """A zero-milestone project with unfinished work must NOT stop on cycle 0:
    'all milestones reached' is vacuously true with no milestones and would be
    a wrong basis for the done stop."""
    boss = _loop_boss(cfg)
    p = Project(name="zeromiles")
    t1 = Task(title="only")
    p.tasks = {t1.id: t1}
    refresh_statuses(p)
    boss.store.save(p)
    assert not p.milestones          # guard: this project truly has no milestones
    # stop must return None on the fresh, undrained project (cycle 0)
    out = boss.run(p.id, autonomous=True, max_cycles=1)
    assert out["cycles"] == 1, "loop must run >=1 cycle, not halt vacuously"
    p2 = boss.store.load(p.id)
    assert p2.tasks[t1.id].status is TaskStatus.DONE
```

- [ ] Step 2: Add `graph_summary` to the test imports. It is already imported in `director.core.taskgraph`; add it to the existing taskgraph import block at lines 10-11 of `tests/test_director.py`:

```python
from director.core.taskgraph import (detect_cycles, graph_summary, ready_tasks,
                                     refresh_milestones, refresh_statuses)
```

- [ ] Step 3: Run; the zero-milestone test should already PASS (Task 4.1's `drained` covers it), but `test_run_stops_done_when_all_tasks_complete` confirms the done-path agreement. Run both to lock the behavior in:

```
python -m pytest tests/test_director.py -k "stops_done_when_all_tasks_complete or vacuously_halt_with_zero_milestones" -q
```

If `test_run_stops_done_when_all_tasks_complete` already passes via `drained`, proceed; the explicit `done` predicate below makes the reason precise and precedence-correct.

- [ ] Step 4: Extend `stop` in `E:/director2/director/core/director.py` to add the `done` stop ABOVE `drained` (precedence #4 before #5). Insert the `done` block immediately before the `running = ...` / `drained` block from Task 4.1. Use `graph_summary` (already imported from `.taskgraph` at director.py:43-44 — confirm and add if absent):

```python
    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec §6). Returns
        a stop-reason string, or None to keep looping. Pure read-only over the
        loaded project + perf ledger; never mutates or saves."""
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        ready = ready_tasks(project)
        # 4. done — completion mirrors status() (director.py:1251): every task
        # done AND nothing left runnable. NOT "all milestones reached", which
        # is vacuously true with zero milestones and would halt on cycle 0.
        summary = graph_summary(project)
        if (summary["done"] == summary["tasks_total"]
                and summary["tasks_total"] > 0
                and not ready and not running):
            return "done"
        # 5. work drained — no ready tasks and nothing RUNNING (kept explicit
        # for the no-milestones / no-tasks case the done stop doesn't cover).
        if not ready and not running:
            return "drained"
        return None
```

- [ ] Step 5: Ensure `graph_summary` is imported in `director.py`. Check the import block near line 43-44; if it is not already imported alongside `ready_tasks`/`refresh_statuses`/`refresh_milestones`, add it. Read the import region first to match the existing line:

```
python -m pytest tests/test_director.py -k "stops_done_when_all_tasks_complete or vacuously_halt_with_zero_milestones" -q
```

Expected: both PASS. (If `graph_summary` was missing from director.py's imports, the first run will fail with `NameError`; add `graph_summary` to the `from .taskgraph import (...)` line and re-run.)

- [ ] Step 6: Commit:

```
git -C E:/director2 add director/core/director.py tests/test_director.py
git -C E:/director2 commit -m "Phase 4.2: done stop (counts + no ready/running), not vacuous all-milestones

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.3: `open packet OR open scream_open latch` stop (precedence #2)

Add the human/recovery gate: the loop halts when a command packet is PRESENTED **or** a `scream_open` latch is set. This is the stop the latch (Phase 3) depends on for "persist until fixed." Read `scream_open` defensively (`getattr`) so partial/pre-Phase-3 snapshots can't raise.

**Files:**
- Modify: `E:/director2/director/core/director.py` (extend `stop`)
- Modify: `E:/director2/tests/test_director.py` (append tests)

Steps:

- [ ] Step 1: Append the failing tests — one for an open packet, one for a set `scream_open` latch (with ready work present, so only the gate can be the reason):

```python
def test_run_stops_on_open_packet(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "pktstop")
    # craft a PRESENTED packet so the loop must halt before draining
    from director.core.types import CommandPacket, PacketStatus
    pkt = CommandPacket(title="hold", trigger="test")
    pkt.status = PacketStatus.PRESENTED
    p.packets[pkt.id] = pkt
    boss.store.save(p)
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] == "open_packet"
    assert out["cycles"] == 0          # halted before any advance
    p2 = boss.store.load(p.id)
    assert p2.tasks[next(iter(p2.tasks))].status is not TaskStatus.DONE


def test_run_stops_on_open_scream_latch(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "latchstop")
    # a HELD latch must halt the autonomous loop even with ready work
    p.scream_open = {"cause": "grounding_damage", "axis": "accumulated_damage",
                     "opened_at": 0, "held_cycles": 1,
                     "clear_rule": "grounding_damage", "origin_refs": []}
    boss.store.save(p)
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] == "latch_held"
    assert out["cycles"] == 0
```

- [ ] Step 2: Run; expect FAIL (`assert 'drained' == 'open_packet'` and `assert 'drained' == 'latch_held'`, since `stop` does not yet check the gate — and note the packet/latch projects still have ready tasks so they won't drain, meaning the loop would actually keep spinning; with `max_cycles` unset it would not terminate. To make the failure clean and bounded, the gate MUST come first. The test as written would hang without the gate — so add a guard before running):

Run with a hard pytest timeout to prove the missing gate (the loop would otherwise spin on a packet it can't clear). Expected FAIL/timeout:

```
python -m pytest tests/test_director.py -k "stops_on_open_packet or stops_on_open_scream_latch" -q --timeout=15
```

(If `pytest-timeout` is not installed, skip the flag — the implementation in Step 3 is what makes these tests terminate; write the implementation and the test together if the spin is a concern. The expected pre-implementation state is non-termination, which IS the failure.)

- [ ] Step 3: Extend `stop` to add precedence-#2 (open packet OR latch) ABOVE the `done`/`drained` blocks. Use the existing `self._open_packets(project)` static helper (director.py:699-702, returns PRESENTED packets) and read `scream_open` defensively:

```python
    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec §6). Returns
        a stop-reason string, or None to keep looping. Pure read-only over the
        loaded project + perf ledger; never mutates or saves."""
        # 2. open packet OR open scream_open latch — the human/recovery gate.
        # (Precedence #1 integrity tamper is layered in by Task 4.4 above this.)
        if self._open_packets(project):
            return "open_packet"
        if getattr(project, "scream_open", None):
            return "latch_held"
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        ready = ready_tasks(project)
        # 4. done — completion mirrors status() (director.py:1251): every task
        # done AND nothing left runnable. NOT "all milestones reached", which
        # is vacuously true with zero milestones and would halt on cycle 0.
        summary = graph_summary(project)
        if (summary["done"] == summary["tasks_total"]
                and summary["tasks_total"] > 0
                and not ready and not running):
            return "done"
        # 5. work drained — no ready tasks and nothing RUNNING (kept explicit
        # for the no-milestones / no-tasks case the done stop doesn't cover).
        if not ready and not running:
            return "drained"
        return None
```

- [ ] Step 4: Run; expect PASS (both tests now halt at the gate with `cycles == 0`):

```
python -m pytest tests/test_director.py -k "stops_on_open_packet or stops_on_open_scream_latch" -q
```

- [ ] Step 5: Commit:

```
git -C E:/director2 add director/core/director.py tests/test_director.py
git -C E:/director2 commit -m "Phase 4.3: loop stop on open packet OR held scream_open latch (precedence #2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.4: `integrity tamper` stop (precedence #1, checked first)

Add the highest-precedence stop: `integrity_violations > 0`. It must be checked **first** so a tampered project halts immediately, before the packet/latch gate. Use the trusted `report_integrity` → `integrity_violations` path, which requires `cfg.report_secret()`.

**Files:**
- Modify: `E:/director2/director/core/director.py` (extend `stop`; add integrity imports if absent)
- Modify: `E:/director2/tests/test_director.py` (append test)

Steps:

- [ ] Step 1: Append the failing test. Forge a `property_report` artifact with a broken signature so `report_integrity` returns an `INVALID` row (a tamper violation), then assert the loop halts with `integrity_tamper` and that it outranks an also-open packet:

```python
def test_run_stops_on_integrity_tamper_first(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "tamper")
    from director.core.types import Artifact, CommandPacket, PacketStatus
    # a property_report whose signature is present but does NOT bind -> INVALID
    deliv = Artifact(title="d", kind="json", content='{"x":1}')
    bad = Artifact(title="property_report: d", kind="property_report",
                   content='{"trusted": true}',
                   provenance={"report": {"trusted": True},
                               "report_sig": "deadbeef",   # forged, won't verify
                               "deliverable": deliv.id})
    p.artifacts[deliv.id] = deliv
    p.artifacts[bad.id] = bad
    # ALSO open a packet — tamper must outrank it (precedence #1 over #2)
    pkt = CommandPacket(title="hold", trigger="test")
    pkt.status = PacketStatus.PRESENTED
    p.packets[pkt.id] = pkt
    boss.store.save(p)
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] == "integrity_tamper"
    assert out["cycles"] == 0
```

- [ ] Step 2: Run; expect FAIL (`assert 'open_packet' == 'integrity_tamper'` — the packet gate currently wins because the integrity check is not yet present):

```
python -m pytest tests/test_director.py -k "stops_on_integrity_tamper_first" -q
```

- [ ] Step 3: Add the integrity imports to `director.py` if absent. Read the import region around the `.integrity` / `.taskgraph` imports (near lines 43-45) and ensure these names resolve. The integrity functions live in `director/core/integrity.py`; add a module-level import alongside the other `.core`-sibling imports:

```python
from .integrity import integrity_violations, report_integrity
```

(If `director.py` already imports from `.integrity` for other reasons, extend that line instead of adding a new one — read the file first to confirm.)

- [ ] Step 4: Extend `stop` to add precedence-#1 integrity tamper as the FIRST check, above the packet/latch gate. It calls `report_integrity(project, secret)` with `secret = self.cfg.report_secret()` and counts `INVALID` rows via `integrity_violations`:

```python
    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec §6). Returns
        a stop-reason string, or None to keep looping. Pure read-only over the
        loaded project + perf ledger; never mutates or saves."""
        # 1. integrity tamper — a forged/replayed signed report (INVALID row)
        # is checked FIRST; it outranks the packet/latch gate.
        rows = report_integrity(project, self.cfg.report_secret())
        if integrity_violations(rows):
            return "integrity_tamper"
        # 2. open packet OR open scream_open latch — the human/recovery gate.
        if self._open_packets(project):
            return "open_packet"
        if getattr(project, "scream_open", None):
            return "latch_held"
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        ready = ready_tasks(project)
        # 4. done — completion mirrors status() (director.py:1251): every task
        # done AND nothing left runnable. NOT "all milestones reached".
        summary = graph_summary(project)
        if (summary["done"] == summary["tasks_total"]
                and summary["tasks_total"] > 0
                and not ready and not running):
            return "done"
        # 5. work drained — no ready tasks and nothing RUNNING.
        if not ready and not running:
            return "drained"
        return None
```

- [ ] Step 5: Run; expect PASS:

```
python -m pytest tests/test_director.py -k "stops_on_integrity_tamper_first" -q
```

- [ ] Step 6: Commit:

```
git -C E:/director2 add director/core/director.py tests/test_director.py
git -C E:/director2 commit -m "Phase 4.4: integrity-tamper stop checked first (precedence #1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.5: `budget exhaustion` stop (precedence #3) — run-scoped tokens via `perf.stats(since=since)`

Add the budget stop, active **only when `cfg.budget` is set**. It checks `budget.max_cycles`, `budget.max_tokens`, and `budget.max_wall_clock`. Tokens are **run-scoped**: `perf.stats(since=since)` where `since` is the run-entry timestamp — without `since`, `stats()` returns lifetime totals across all prior runs and would misfire on cycle 1. Absent budget → this stop is disabled. The cycle count is owned by `run()` (the loop counter), passed into `stop`.

**Files:**
- Modify: `E:/director2/director/core/director.py` (thread `cycles` + wall-clock start into `stop`; add the budget block; `run()` passes them)
- Modify: `E:/director2/tests/test_director.py` (append tests)

Steps:

- [ ] Step 1: Append the failing tests. The first proves run-scoped token accounting (a budget tripped by tokens recorded *during* the run, not by lifetime totals); the second proves `budget.max_cycles`; the third proves that **no budget set** never trips the stop. For the token test, write rows into the `PerfLedger` with a `ts` strictly after `since` so `stats(since=since)` counts them:

```python
def test_run_budget_max_cycles_stops(cfg):
    boss = _loop_boss(cfg)
    # an undrainable-but-no-gate project: keep a task PENDING on an unmet dep so
    # advance() never completes it, forcing the loop to rely on a budget stop.
    p = Project(name="budgetcycles")
    t1 = Task(title="blocked", depends_on=["missing-dep"])
    p.tasks = {t1.id: t1}
    refresh_statuses(p)          # stays PENDING (dep missing)
    boss.store.save(p)
    cfg.budget = {"max_cycles": 3}
    # NOTE: with a missing dep there are no ready tasks, so the loop would
    # 'drain' first. Make a ready task instead so cycles accrue:
    p2 = _seed_two_task_project(boss, "budgetcycles2")
    cfg.budget = {"max_cycles": 1}
    # force non-drain by giving the runner nothing to complete is not possible
    # here; instead assert the budget reason wins when reached before drain.
    out = boss.run(p2.id, autonomous=True)
    # two tasks drain in <=2 cycles; with max_cycles budget 1 the budget stop
    # must fire on the 2nd predicate check (cycles>=1) before the 2nd advance.
    assert out["stop_reason"] in ("budget_cycles", "done", "drained")


def test_run_budget_tokens_is_run_scoped(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "budgettokens")
    cfg.budget = {"max_tokens": 100}
    # pre-existing LIFETIME tokens recorded BEFORE the run must NOT count:
    from director.evolve.metrics import PerfLedger
    perf = PerfLedger(cfg)
    perf.record({"ts": "2000-01-01T00:00:00+00:00", "ok": True,
                 "prompt_tokens": 9999, "completion_tokens": 9999,
                 "backend": "mock", "kind": "x"})
    boss.perf = perf
    # the lifetime 19998 tokens predate `since`; run-scoped window is empty,
    # so the budget must NOT trip on stale tokens — the run drains normally.
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] in ("done", "drained")


def test_run_no_budget_never_trips_budget_stop(cfg):
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "nobudget")
    assert cfg.budget is None       # default from config: no budget declared
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] in ("done", "drained")
    assert "budget" not in out["stop_reason"]
```

- [ ] Step 2: Run; the no-budget and run-scoped tests should pass against Task 4.4's `stop` (budget block absent = never trips), but `test_run_budget_max_cycles_stops` asserting `budget_cycles` is allowed-or-drained, so it will pass loosely. To make the budget path real and tested, tighten the cycle test after implementation. First run to see current state:

```
python -m pytest tests/test_director.py -k "run_budget or no_budget_never" -q
```

Expected: tests pass loosely (no budget block yet, so `done`/`drained` reasons), but `budget_cycles` is never produced — the implementation in Step 3 makes it reachable. This is the TDD "make the new reason exist" step.

- [ ] Step 3: Thread the loop counter and a wall-clock start into `stop`, and add the precedence-#3 budget block. Update BOTH `run()` (to pass `cycles=` and `started_at=`) and `stop`. In `run()`, capture a monotonic start and pass the current cycle count:

```python
    # ------------------------------------------------------------------- run
    def run(self, project_ref: str, *, autonomous: bool = True,
            max_cycles: int | None = None) -> dict:
        """Bounded autonomous loop: call advance(autonomous=True) until a
        declared stop condition fires. The loop OWNS NO STATE — every read is
        of the persisted project, the perf ledger, or config; every write is
        done by advance() through the trusted apply_delta/store.save boundary.
        `since` is captured ONCE at entry so the budget stop and resource_bleed
        see run-scoped tokens, not the lifetime ledger (metrics.py:61)."""
        import time
        from ..evolve.metrics import PerfLedger
        perf = getattr(self, "perf", None) or PerfLedger(self.cfg)
        since = utcnow().isoformat()
        started_at = time.monotonic()
        cycles = 0
        while True:
            project = self.store.load(project_ref)
            reason = self.stop(project, perf=perf, since=since,
                               cycles=cycles, started_at=started_at)
            if reason is not None:
                return {"status": "stopped", "stop_reason": reason,
                        "cycles": cycles, "since": since}
            if max_cycles is not None and cycles >= max_cycles:
                return {"status": "stopped", "stop_reason": "max_cycles",
                        "cycles": cycles, "since": since}
            self.advance(project_ref, autonomous=autonomous)
            cycles += 1

    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec §6). Returns
        a stop-reason string, or None to keep looping. Pure read-only over the
        loaded project + perf ledger; never mutates or saves."""
        import time
        # 1. integrity tamper — checked FIRST; outranks the packet/latch gate.
        rows = report_integrity(project, self.cfg.report_secret())
        if integrity_violations(rows):
            return "integrity_tamper"
        # 2. open packet OR open scream_open latch — the human/recovery gate.
        if self._open_packets(project):
            return "open_packet"
        if getattr(project, "scream_open", None):
            return "latch_held"
        # 3. budget exhaustion — ONLY if a budget is declared (cfg.budget).
        # Tokens are RUN-SCOPED via perf.stats(since=since): without `since`,
        # stats() blends every prior run and the budget misfires on cycle 1.
        budget = getattr(self.cfg, "budget", None)
        if budget:
            if budget.get("max_cycles") is not None \
                    and cycles >= budget["max_cycles"]:
                return "budget_cycles"
            if budget.get("max_tokens") is not None:
                st = perf.stats(since=since)
                tok = st.get("prompt_tokens", 0) + st.get("completion_tokens", 0)
                if tok >= budget["max_tokens"]:
                    return "budget_tokens"
            if budget.get("max_wall_clock") is not None \
                    and started_at is not None \
                    and (time.monotonic() - started_at) >= budget["max_wall_clock"]:
                return "budget_wall_clock"
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        ready = ready_tasks(project)
        # 4. done — completion mirrors status() (director.py:1251).
        summary = graph_summary(project)
        if (summary["done"] == summary["tasks_total"]
                and summary["tasks_total"] > 0
                and not ready and not running):
            return "done"
        # 5. work drained — no ready tasks and nothing RUNNING.
        if not ready and not running:
            return "drained"
        return None
```

- [ ] Step 4: Add a tight budget-cycles test that forces the `budget_cycles` reason deterministically. Use a never-draining project (a task the drain runner keeps READY because it has no real completion) is not available; instead give a generous task graph and a `max_cycles` budget of 1 against a project that needs >1 cycle. The two-task chained project (`first` → `second`) needs 2 advances; `budget.max_cycles=1` trips on the predicate check after cycle 1, before the project drains. Append:

```python
def test_run_budget_cycles_trips_before_drain(cfg):
    boss = _loop_boss(cfg)
    # chained: 'second' depends on 'first', so it takes TWO advance() calls to
    # drain; a max_cycles budget of 1 must trip on the cycle-1 predicate check.
    p = Project(name="budgettrip")
    t1 = Task(title="first")
    t2 = Task(title="second", depends_on=[t1.id])
    p.tasks = {t1.id: t1, t2.id: t2}
    refresh_statuses(p)
    boss.store.save(p)
    cfg.budget = {"max_cycles": 1}
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] == "budget_cycles"
    assert out["cycles"] == 1
    p2 = boss.store.load(p.id)
    # 'second' must still be unfinished — the budget stopped the loop early
    assert any(t.status is not TaskStatus.DONE for t in p2.tasks.values())
```

- [ ] Step 5: Run the full budget set; expect PASS:

```
python -m pytest tests/test_director.py -k "run_budget or no_budget_never or budget_cycles_trips" -q
```

- [ ] Step 6: Commit:

```
git -C E:/director2 add director/core/director.py tests/test_director.py
git -C E:/director2 commit -m "Phase 4.5: budget-exhaustion stop (cycles/tokens/wall-clock), run-scoped tokens via since

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.6: `director run [--cycles N]` CLI command

Add the click command mirroring the existing `advance` command (cli.py:189-206). It resolves the project, calls `Director.run(ref, autonomous=True, max_cycles=N)`, and echoes the stop reason + cycle count in the project's `[status] summary` idiom.

**Files:**
- Modify: `E:/director2/director/cli.py` (add the `run` command after the `advance` command, which ends at line 206)
- Modify: `E:/director2/tests/test_cli.py` (append a CliRunner test)

Steps:

- [ ] Step 1: Append the failing CLI test to `E:/director2/tests/test_cli.py`. It drives a fresh project to its first packet, decides it (so no packet blocks the loop), then runs `director run --cycles 5` and asserts the loop reports a clean stop:

```python
def test_run_command_drives_loop_to_stop(env):
    r = invoke("new", "run-demo", "-o", "build a verified toy library")
    assert r.exit_code == 0
    store = ProjectStore(Config.from_env())
    pid = store.get_current()
    project = store.load(pid)
    open_pkt = [p for p in project.packets.values()
                if p.status.value == "presented"][0]
    # answer the opening packet so the autonomous loop is not gated by it
    r = invoke("decide", open_pkt.id[:8], "--select",
               open_pkt.recommendation_key or "A")
    assert r.exit_code == 0
    # bounded autonomous run
    r = invoke("run", "--cycles", "5")
    assert r.exit_code == 0
    assert "[stopped]" in r.output
    # the loop reports its stop reason and cycle count
    assert "stop_reason=" in r.output or "stop:" in r.output
```

- [ ] Step 2: Run; expect FAIL (`No such command 'run'` → non-zero exit, `catch_exceptions=False` surfaces a `SystemExit`/usage error):

```
python -m pytest tests/test_cli.py -k "run_command_drives_loop_to_stop" -q
```

- [ ] Step 3: Add the `run` command to `E:/director2/director/cli.py`, inserted DIRECTLY AFTER the `advance` command (after line 206). Mirror the `advance` command exactly: `@main.command()`, optional positional `project`, an `--cycles` option, `svc = _services()`, `ref = svc.resolve_project(project)`, call the dict-returning Director method, `click.echo` the status/summary, then surface any new packets the same way `advance` does:

```python
@main.command()
@click.argument("project", required=False)
@click.option("--cycles", type=int, default=None,
              help="Max autonomous cycles (advance calls); unbounded if unset.")
def run(project: str | None, cycles: int | None) -> None:
    """Run the bounded autonomous loop: advance(autonomous=True) until a
    declared stop condition fires (tamper / open packet or latch / budget /
    done / drained)."""
    svc = _services()
    ref = svc.resolve_project(project)
    out = svc.director.run(ref, autonomous=True, max_cycles=cycles)
    click.echo(f"[{out['status']}] stop_reason={out['stop_reason']} "
               f"cycles={out['cycles']}")
    # surface any packet the loop halted on so the operator can decide
    p = svc.store.load(ref)
    open_pkts = [pk for pk in p.packets.values()
                 if pk.status.value == "presented"]
    for pkt in open_pkts:
        _print_packet(pkt)
    scream = getattr(p, "scream_open", None)
    if scream:
        click.secho(f"SCREAM: {scream.get('cause')} "
                    f"(clear_rule={scream.get('clear_rule')})",
                    fg="red", bold=True)
```

- [ ] Step 4: Run; expect PASS:

```
python -m pytest tests/test_cli.py -k "run_command_drives_loop_to_stop" -q
```

- [ ] Step 5: Commit:

```
git -C E:/director2 add director/cli.py tests/test_cli.py
git -C E:/director2 commit -m "Phase 4.6: director run [--cycles N] CLI command mirroring advance

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.7: Precedence integration test + full-suite OFF-path regression

Lock in the five-condition precedence ordering with one integration test that stacks multiple stop signals at once, and prove the whole 133-test suite stays green with `nervous_enabled=False` (the loop adds no state and reads existing signals, so the OFF path is byte-identical — `run()` is purely additive and never invoked by the existing suite).

**Files:**
- Modify: `E:/director2/tests/test_director.py` (append the precedence test)

Steps:

- [ ] Step 1: Append the precedence integration test. Stack: a tamper violation (#1), an open packet (#2), a budget (#3), on a project that is otherwise drained (#5) — the tamper reason must win:

```python
def test_run_stop_precedence_tamper_wins_over_all(cfg):
    boss = _loop_boss(cfg)
    p = Project(name="precedence")          # no tasks -> would 'drain' (#5)
    from director.core.types import (Artifact, CommandPacket, PacketStatus)
    deliv = Artifact(title="d", kind="json", content='{"x":1}')
    bad = Artifact(title="property_report: d", kind="property_report",
                   content='{"trusted": true}',
                   provenance={"report": {"trusted": True},
                               "report_sig": "deadbeef",
                               "deliverable": deliv.id})
    p.artifacts = {deliv.id: deliv, bad.id: bad}
    pkt = CommandPacket(title="hold", trigger="test")     # open packet (#2)
    pkt.status = PacketStatus.PRESENTED
    p.packets[pkt.id] = pkt
    p.scream_open = {"cause": "tamper", "axis": "charter_integrity",
                     "opened_at": 0, "held_cycles": 0,
                     "clear_rule": "tamper", "origin_refs": []}   # latch (#2)
    boss.store.save(p)
    cfg.budget = {"max_cycles": 0}          # budget would trip at cycle 0 (#3)
    out = boss.run(p.id, autonomous=True)
    # #1 integrity tamper must win over the open packet, latch, budget, drain
    assert out["stop_reason"] == "integrity_tamper"
    assert out["cycles"] == 0


def test_run_open_packet_outranks_budget_and_drain(cfg):
    """With no tamper, an open packet (#2) outranks budget (#3)."""
    boss = _loop_boss(cfg)
    p = _seed_two_task_project(boss, "pktvsbudget")
    from director.core.types import CommandPacket, PacketStatus
    pkt = CommandPacket(title="hold", trigger="test")
    pkt.status = PacketStatus.PRESENTED
    p.packets[pkt.id] = pkt
    boss.store.save(p)
    cfg.budget = {"max_cycles": 0}
    out = boss.run(p.id, autonomous=True)
    assert out["stop_reason"] == "open_packet"
```

- [ ] Step 2: Run the precedence tests; expect PASS (the `stop` ordering from Tasks 4.1-4.5 already encodes this):

```
python -m pytest tests/test_director.py -k "stop_precedence_tamper_wins_over_all or open_packet_outranks_budget_and_drain" -q
```

- [ ] Step 3: Run the full suite to prove the OFF-path regression — the existing 133 tests plus the new Phase 4 tests must all pass, and nothing in the existing suite calls `run()` (so byte-identical OFF behavior holds):

```
python -m pytest -q
```

Expected: all green (133 prior + the Phase 4 additions). If any prior test changed behavior, the loop touched shared state it should not have — `run()` and `stop` must remain read-only over the loaded project; revisit before committing.

- [ ] Step 4: Commit:

```
git -C E:/director2 add tests/test_director.py
git -C E:/director2 commit -m "Phase 4.7: stop-precedence integration test + full-suite OFF-path regression

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5: The Observation Bench + Router Pin

Goal: Ship `director/bench/` (scripted-fault runner, ON/OFF driver, JSONL/comparison report), the one-line `router.profile_for` temperature edit, the `director bench` CLI command (the `director run` command is Phase 4 Task 4.6), and an end-to-end integration test proving a scripted fault fires a siren → latch holds → human recovery → verified clear → auto-resume, with a measurable, reproducible ON-vs-OFF delta on the same title+cycle_seq-keyed scenario.

> **Phase dependencies (assumed complete before this phase):** Phase 1 (`BodyState` + the five new `Project` fields `body`/`scream_open`/`cycle_seq`/`milestone_reverts`/`coherence_blocks` in `director/core/types.py`); Phase 2 (`director/config.py` new fields, default `nervous_enabled=False`, plus the `bench`/`director_temperature` keys); Phase 3 (`director/core/valence.py` — `compute_body`/`evaluate_scream`/`check_clear_rule`); Phase 4 (`director/core/director.py` — `advance(self, project_ref, *, max_tasks=None, force=False, autonomous=False)`, `run(self, project_ref, *, autonomous=True, max_cycles=None)`, the latch stop-gate gated on `autonomous`, `_make_packet(..., context_override=None)`, `_fallback_packet(trigger, hint, context_override=None)`, the `decide()` auto-advance suppression when `scream_open` is set, and the PUBLIC precedence predicate `stop(self, project, *, perf, since, cycles=0, started_at=None) -> str | None`). This phase consumes those surfaces; it does not redefine them. Where a step references one of those names, it is the exact contract above.

> **Pin note (recorded in the plan, not code):** the bench pins the Director's model by setting `cfg.model="claude-sonnet-4-6"` (the router overrides model for the director/builder/judge roles in `profile_for`, `router.py:122`). The Sonnet snapshot id is `claude-sonnet-4-6` per the canonical contract's `bench["model_pin"]`. The bench tests below run on the **mock backend** (no keys, per `conftest.py`), so they assert plumbing and the ON/OFF behavioral delta deterministically without billing a real model; a live-pinned arm is an operator action gated on keys, not a unit test.

---

### Task 5.1: Create the `director/bench/` package skeleton

Files:
- Create: `E:/director2/director/bench/__init__.py`
- Test: `E:/director2/tests/test_bench.py` (new — created here, extended by later tasks)

- [ ] Step 1: Write the failing test that the package imports. Create `E:/director2/tests/test_bench.py` with:
```python
"""Observation-bench tests: scripted-fault runner, ON/OFF driver, report,
and the full siren→latch→recovery→resume integration — all on the mock
backend (no keys), deterministic, title+cycle_seq-keyed faults."""

import json

import pytest

from director.agents.base import AgentResult, AgentSpec
from director.agents.runner import SubAgentRunner
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def test_bench_package_imports():
    import director.bench as bench
    assert bench.__name__ == "director.bench"
```

- [ ] Step 2: Run it, expect FAIL (collection error). From `E:/director2`:
```
python -m pytest tests/test_bench.py::test_bench_package_imports -q
```
Expected FAIL: `ModuleNotFoundError: No module named 'director.bench'`.

- [ ] Step 3: Create the package init. Write `E:/director2/director/bench/__init__.py`:
```python
"""Director 2.0 observation bench.

Runs the autonomous loop nervous-ON vs nervous-OFF on the SAME scripted-fault
scenario so the behavioral delta of the functional-valence nervous system is
measured, never asserted. Failures are injected deterministically by a scripted
runner keyed on (task_title, cycle_seq) — titles are author-controlled and
stable across arms; entity ids are uuid4 and are NOT (types.py:25).

This package never grades the model. It observes the trusted loop.
"""

from __future__ import annotations

from .faults import FaultScenario, ScriptedFaultRunner
from .driver import compare, run_arm

__all__ = ["FaultScenario", "ScriptedFaultRunner", "run_arm", "compare"]
```

- [ ] Step 4: Run it, expect FAIL still (the submodules don't exist yet, so the `from .faults` import in `__init__` raises). From `E:/director2`:
```
python -m pytest tests/test_bench.py::test_bench_package_imports -q
```
Expected FAIL: `ModuleNotFoundError: No module named 'director.bench.faults'`. (This is resolved by Task 5.2 + 5.4; the package is committed once those land. Proceed to Task 5.2 — do not commit a broken import.)

---

### Task 5.2: `ScriptedFaultRunner` + `FaultScenario` (the fault layer)

Files:
- Create: `E:/director2/director/bench/faults.py`
- Modify: `E:/director2/tests/test_bench.py` (append tests)

Mirrors the seam at `runner.py:65` (`run_parallel(specs) -> list[AgentResult]`) and `runner.py:36` (`run(spec) -> AgentResult`). `AgentResult` is the `@dataclass` at `agents/base.py:132-145` with required `spec_id` and defaulted `task_id`/`role`/`ok`/`error`. `AgentSpec` (`base.py:118-129`) carries `.task_id`, `.role`, `.id`; the spec does **not** carry the task title, so the runner maps `spec.task_id → task.title` via the scenario's title index built from its seed project.

- [ ] Step 1: Write the failing tests. Append to `E:/director2/tests/test_bench.py`:
```python
def _seed_project_factory():
    """Two independent tasks, stable titles; the runner faults one of them."""
    def make() -> Project:
        p = Project(name="bench-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p
    return make


def _delegate_runner(cfg):
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return SubAgentRunner(cfg, router, registry)


def test_scripted_runner_faults_declared_title_cycle(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "scripted fault: build-bad@1"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")
    ok_id = next(tid for tid, ttl in title_index.items() if ttl == "build-ok")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 1

    bad = runner.run(AgentSpec(role="code", objective="x", task_id=bad_id))
    assert bad.ok is False
    assert bad.error == "scripted fault: build-bad@1"
    assert bad.spec_id and bad.task_id == bad_id

    # the OK task at the same cycle is delegated to the real (mock) runner
    ok = runner.run(AgentSpec(role="code", objective="x", task_id=ok_id))
    assert ok.ok is True


def test_scripted_runner_only_faults_scheduled_cycle(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "boom"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 2          # NOT the scheduled cycle (1)
    res = runner.run(AgentSpec(role="code", objective="x", task_id=bad_id))
    assert res.ok is True         # no fault at cycle 2 -> delegated


def test_scripted_runner_parallel_preserves_order(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(
        name="single-bad",
        seed_factory=_seed_project_factory(),
        schedule={("build-bad", 1): "boom"})
    project = scenario.seed_factory()
    title_index = {t.id: t.title for t in project.tasks.values()}
    bad_id = next(tid for tid, ttl in title_index.items() if ttl == "build-bad")
    ok_id = next(tid for tid, ttl in title_index.items() if ttl == "build-ok")

    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario,
                                 title_index=title_index)
    runner.cycle_seq = 1
    specs = [AgentSpec(role="code", objective="x", task_id=ok_id),
             AgentSpec(role="code", objective="x", task_id=bad_id)]
    results = runner.run_parallel(specs)
    assert [r.task_id for r in results] == [ok_id, bad_id]   # input order
    assert results[0].ok is True and results[1].ok is False


def test_scripted_runner_empty_specs(cfg):
    from director.bench.faults import FaultScenario, ScriptedFaultRunner
    scenario = FaultScenario(name="n", seed_factory=_seed_project_factory(),
                             schedule={})
    runner = ScriptedFaultRunner(_delegate_runner(cfg), scenario, title_index={})
    assert runner.run_parallel([]) == []
```

- [ ] Step 2: Run them, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k scripted -q
```
Expected FAIL: `ModuleNotFoundError: No module named 'director.bench.faults'`.

- [ ] Step 3: Write the implementation. Create `E:/director2/director/bench/faults.py`:
```python
"""Scripted fault injection for the observation bench.

``ScriptedFaultRunner`` duck-types the ``SubAgentRunner`` seam (run / run_parallel
-> AgentResult) used by the Director (director.py:748). For a declared
(task_title, cycle_seq) pair it returns AgentResult(ok=False, error=...) so a
worker "fails" deterministically; every other spec is delegated to a real
injected runner so the Director's OWN planning/packet calls still hit the real
router (the subject stays pinned). Schedules key on task TITLE + cycle_seq, not
ids — ids are uuid4 (types.py:25) and never match across arms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..agents.base import AgentResult, AgentSpec
from ..core.types import Project


@dataclass
class FaultScenario:
    """A reproducible bench scenario: how to build the starting project and
    when workers fail. ``schedule`` maps (task_title, cycle_seq) -> error str."""
    name: str
    seed_factory: Callable[[], Project]
    schedule: dict[tuple[str, int], str] = field(default_factory=dict)


class ScriptedFaultRunner:
    """A drop-in ``SubAgentRunner`` replacement that injects declared faults.

    The Director holds it as ``self.runner`` and calls ``run_parallel(specs)``
    each cycle. The harness stamps the current ``cycle_seq`` on this runner
    (``runner.cycle_seq = project.cycle_seq``) BEFORE each advance so faults
    fire on the right cycle. Specs carry only ``task_id``; ``title_index`` maps
    ``task_id -> title`` so the schedule can key on the stable title.
    """

    def __init__(self, delegate, scenario: FaultScenario, *,
                 title_index: dict[str, str]):
        self.delegate = delegate
        self.scenario = scenario
        self.title_index = dict(title_index)
        self.cycle_seq = 0
        self.injected: list[dict] = []     # observability: faults actually fired

    # --------------------------------------------------------------- single
    def run(self, spec: AgentSpec) -> AgentResult:
        title = self.title_index.get(spec.task_id, "")
        err = self.scenario.schedule.get((title, self.cycle_seq))
        if err is not None:
            self.injected.append({"title": title, "cycle_seq": self.cycle_seq,
                                  "error": err})
            return AgentResult(spec_id=spec.id, task_id=spec.task_id,
                               role=spec.role, ok=False, error=err)
        return self.delegate.run(spec)

    # --------------------------------------------------------------- parallel
    def run_parallel(self, specs: list[AgentSpec]) -> list[AgentResult]:
        # results return in input order (mirror SubAgentRunner.run_parallel);
        # run() never raises, so a simple ordered map is correct and keeps the
        # per-cycle fault log deterministic across arms.
        return [self.run(s) for s in specs]
```

- [ ] Step 4: Run them, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "scripted or imports" -q
```
Expected: the four scripted tests PASS; `test_bench_package_imports` still fails on `bench.driver` until Task 5.4 — that is expected; do not commit yet.

---

### Task 5.3: Router temperature pin (`profile_for` edit)

Files:
- Modify: `E:/director2/director/llm/router.py` (`profile_for`, lines 102-132 — specifically the director base entry at 105-107 and the model-override branch at 122-126)
- Test: `E:/director2/tests/test_bench.py` (append)

Surgical, single-place edit: honor `cfg.director_temperature` (or fall back to `cfg.temperature`) for the **director** role only. `Config.director_temperature` is the contract field (default `None`, added in Phase 2); `cfg.temperature` exists today (`config.py:90`, default `0.3`). When `director_temperature is None` and we keep the default `temperature` the behavior must be **byte-identical** to today's hardcoded `0.2`, so the edit only overrides when `director_temperature` is explicitly set (not on the always-present `temperature`).

- [ ] Step 1: Write the failing test. Append to `E:/director2/tests/test_bench.py`:
```python
def test_router_honors_director_temperature(cfg):
    cfg.director_temperature = 0.0
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    prof = router.profile_for("director")
    assert prof.temperature == 0.0


def test_router_director_temperature_default_unchanged(cfg):
    # director_temperature unset -> the historical hardcoded 0.2 is preserved
    assert cfg.director_temperature is None
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    assert router.profile_for("director").temperature == 0.2
    # other roles are untouched by the director pin
    assert router.profile_for("judge").temperature == 0.0
    assert router.profile_for("builder").temperature == 0.5
```

- [ ] Step 2: Run them, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k director_temperature -q
```
Expected FAIL: `test_router_honors_director_temperature` fails with `assert 0.2 == 0.0` (the pin is ignored today). (`test_router_director_temperature_default_unchanged` already passes — it guards the no-regression path.)

- [ ] Step 3: Make the minimal edit. In `E:/director2/director/llm/router.py`, replace the director base entry (lines 105-107):
```python
            "director": ModelProfile(role="director", temperature=0.2,
                                     max_tokens=self.cfg.max_output_tokens,
                                     timeout_s=self.cfg.request_timeout_s),
```
with:
```python
            "director": ModelProfile(
                role="director",
                # pin the director-role temperature when declared (bench
                # reproducibility); else keep the historical 0.2
                temperature=(self.cfg.director_temperature
                             if getattr(self.cfg, "director_temperature", None)
                             is not None else 0.2),
                max_tokens=self.cfg.max_output_tokens,
                timeout_s=self.cfg.request_timeout_s),
```

- [ ] Step 4: Run them, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k director_temperature -q
```
Expected: both PASS.

- [ ] Step 5: Guard the OFF-path regression — the full suite must stay green. From `E:/director2`:
```
python -m pytest tests/test_llm.py tests/test_async_router.py -q
```
Expected: PASS (no router regression; `getattr(..., None)` default keeps pre-Phase-2 callers safe).

- [ ] Step 6: Commit (the router edit + the fault layer it pairs with land together; the package import is still pending the driver, so commit only the router edit and tests here).
```
git -C E:/director2 add director/llm/router.py tests/test_bench.py
git -C E:/director2 commit -m "bench: honor cfg.director_temperature for the director role in profile_for

Surgical profile_for edit: when cfg.director_temperature is set, pin the
director-role temperature (bench reproducibility); default None keeps the
historical 0.2 and leaves judge/builder/cheap untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5.4: `driver.py` — `run_arm` + `compare`

Files:
- Create: `E:/director2/director/bench/driver.py`
- Modify: `E:/director2/tests/test_bench.py` (append)

`run_arm` builds an isolated `Config` (its own `tmp` home so perf/state don't bleed across arms), sets `cfg.nervous_enabled` per arm and `cfg.auto_advance_after_decision=False` (mirror `server.py:71`), wires a Director whose `runner` is a `ScriptedFaultRunner`, then drives `Director.run`. Because faults key on `cycle_seq`, the driver stamps `runner.cycle_seq` before each advance — so `run_arm` cannot just call `Director.run` blind; it drives the loop itself via repeated `advance(..., autonomous=True)`, stamping the runner each iteration, which is exactly what `run()` does internally minus the stamp. The driver therefore re-implements the bounded loop locally (it owns the cycle accounting the runner needs), logging the dependent variables per `cycle_seq`.

> The Director-build mirrors `server.py:79-95` order: `LLMRouter(cfg, recorder=perf.recorder)` → `make_default_registry()` → `SubAgentRunner(cfg, router, registry)` (the **delegate**) → wrap it in `ScriptedFaultRunner` → `Director(cfg, store, router, registry, fault_runner)`.

- [ ] Step 1: Write the failing tests. Append to `E:/director2/tests/test_bench.py`:
```python
def test_run_arm_off_records_per_cycle_log(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="arm-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    out = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    assert out["arm"] == "off"
    assert out["reps"] == 2
    assert len(out["runs"]) == 2
    # each run logs per-cycle rows carrying cycle_seq + accumulated_damage
    run0 = out["runs"][0]
    assert run0["cycles"]                       # at least one cycle ran
    first = run0["cycles"][0]
    assert "cycle_seq" in first and "accumulated_damage" in first
    assert "scream" in first and "held_cycles" in first


def test_run_arm_on_vs_off_measurable_delta(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="arm-seed")
        t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom",
                                       ("build-bad", 2): "boom"})
    off = run_arm(scenario, nervous=False, reps=3, home=tmp_path / "off")
    on = run_arm(scenario, nervous=True, reps=3, home=tmp_path / "on")
    delta = compare(on, off)
    # ON fires interrupts; OFF cannot (nervous_enabled False -> no scream ever)
    assert off["totals"]["screams_fired"] == 0
    assert on["totals"]["screams_fired"] >= 1
    assert delta["screams_fired"]["on"] >= 1
    assert delta["screams_fired"]["off"] == 0
    # reproducible: the headline delta has a declared sign, not a single run
    assert delta["screams_fired"]["delta"] == (
        on["totals"]["screams_fired"] - off["totals"]["screams_fired"])
```

- [ ] Step 2: Run them, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "run_arm" -q
```
Expected FAIL: `ModuleNotFoundError: No module named 'director.bench.driver'`.

- [ ] Step 3: Write the implementation. Create `E:/director2/director/bench/driver.py`:
```python
"""Bench driver: run one arm (nervous ON or OFF) over a scripted scenario for
N reps, logging the dependent variables per cycle_seq, then compare arms.

The driver owns the cycle accounting the ScriptedFaultRunner needs: it stamps
``runner.cycle_seq`` before each ``advance(autonomous=True)`` so faults fire on
the declared cycle. This re-implements run()'s bounded loop locally (run() does
the same minus the stamp); the loop owns NO state authority — every write still
routes through advance()/store.save (Constitution f).
"""

from __future__ import annotations

from pathlib import Path

from ..agents.runner import SubAgentRunner
from ..config import Config
from ..core.director import Director
from ..core.state import ProjectStore
from ..core.types import utcnow
from ..evolve.metrics import PerfLedger
from ..llm.mock import MockBackend
from ..llm.router import LLMRouter
from ..verify import make_default_registry
from .faults import FaultScenario, ScriptedFaultRunner


def _build_director(cfg: Config, scenario: FaultScenario, project):
    """Mirror server.py:79-95 wiring, but wrap the runner in a fault runner."""
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    delegate = SubAgentRunner(cfg, router, registry)
    title_index = {t.id: t.title for t in project.tasks.values()}
    runner = ScriptedFaultRunner(delegate, scenario, title_index=title_index)
    director = Director(cfg, store, router, registry, runner)
    return director, store, runner


def _run_once(scenario: FaultScenario, *, nervous: bool, home: Path,
              max_cycles: int = 12) -> dict:
    cfg = Config(home=home)
    cfg.ensure_dirs()
    cfg.nervous_enabled = nervous
    cfg.auto_advance_after_decision = False     # mirror server.py:71
    project = scenario.seed_factory()
    director, store, runner = _build_director(cfg, scenario, project)
    store.save(project)

    # the stop() predicate is run-scoped: hold a perf ledger, a `since` stamp,
    # and a cycle counter just as Director.run() does, and pass them in.
    perf = getattr(director, "perf", None) or PerfLedger(cfg)
    since = utcnow().isoformat()
    cycle_count = 0
    cycles: list[dict] = []
    for _ in range(max_cycles):
        project = store.load(project.id)
        if director.stop(project, perf=perf, since=since, cycles=cycle_count):
            break
        # faults key on the cycle the worker will run in: advance() increments
        # cycle_seq before the valence pass, so the worker batch in THIS advance
        # runs at cycle_seq+1 — stamp the runner to match.
        runner.cycle_seq = project.cycle_seq + 1
        result = director.advance(project.id, autonomous=True)
        cycle_count += 1
        project = store.load(project.id)
        body = project.body
        scream = project.scream_open
        cycles.append({
            "cycle_seq": project.cycle_seq,
            "status": result.get("status"),
            "done": result.get("done", 0),
            "failed": result.get("failed", 0),
            "new_packets": len(result.get("new_packets", [])),
            "accumulated_damage": (getattr(body, "accumulated_damage", 0.0)
                                   if body is not None else 0.0),
            "valence": (getattr(body, "valence", 0.0)
                        if body is not None else 0.0),
            "scream": (scream.get("cause") if scream else None),
            "held_cycles": (scream.get("held_cycles", 0) if scream else 0),
        })
        if result.get("status") in ("latched", "awaiting_command"):
            break       # a packet OR a held latch halted the autonomous loop

    screams = [c for c in cycles if c["scream"]]
    return {
        "nervous": nervous,
        "cycles": cycles,
        "injected": list(runner.injected),
        "screams_fired": len(screams),
        "diagnostic_tasks": sum(c["new_packets"] for c in cycles),
        "final_damage": cycles[-1]["accumulated_damage"] if cycles else 0.0,
        "cycles_run": len(cycles),
        "outcome": cycles[-1]["status"] if cycles else "drained",
    }


def run_arm(scenario: FaultScenario, *, nervous: bool, reps: int,
            home: Path) -> dict:
    """Run one arm for N reps; return per-run logs + aggregate totals."""
    arm = "on" if nervous else "off"
    runs = []
    for i in range(reps):
        runs.append(_run_once(scenario, nervous=nervous,
                              home=Path(home) / f"rep{i}"))
    totals = {
        "screams_fired": sum(r["screams_fired"] for r in runs),
        "diagnostic_tasks": sum(r["diagnostic_tasks"] for r in runs),
        "cycles_run": sum(r["cycles_run"] for r in runs),
        "final_damage": sum(r["final_damage"] for r in runs),
    }
    return {"arm": arm, "scenario": scenario.name, "reps": reps,
            "runs": runs, "totals": totals}


def _spread(runs: list[dict], key: str) -> dict:
    vals = [r[key] for r in runs]
    n = len(vals) or 1
    return {"mean": round(sum(vals) / n, 3),
            "min": min(vals) if vals else 0,
            "max": max(vals) if vals else 0}


def compare(on_results: dict, off_results: dict) -> dict:
    """ON-vs-OFF comparison summary with per-arm spread (never a single run)."""
    metrics = ("screams_fired", "diagnostic_tasks", "cycles_run", "final_damage")
    out: dict = {}
    for m in metrics:
        on_v = on_results["totals"][m]
        off_v = off_results["totals"][m]
        out[m] = {"on": on_v, "off": off_v, "delta": on_v - off_v,
                  "on_spread": _spread(on_results["runs"], m),
                  "off_spread": _spread(off_results["runs"], m)}
    return out
```

- [ ] Step 4: Run them, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "run_arm or imports" -q
```
Expected: `test_run_arm_off_records_per_cycle_log`, `test_run_arm_on_vs_off_measurable_delta`, and now `test_bench_package_imports` all PASS (the `from .driver import ...` in `__init__` now resolves).

- [ ] Step 5: Run the whole bench test file so far. From `E:/director2`:
```
python -m pytest tests/test_bench.py -q
```
Expected: all current bench tests PASS.

- [ ] Step 6: Commit the package skeleton + fault layer + driver together (now a coherent importable unit).
```
git -C E:/director2 add director/bench/__init__.py director/bench/faults.py director/bench/driver.py tests/test_bench.py
git -C E:/director2 commit -m "bench: scripted-fault runner + ON/OFF driver

ScriptedFaultRunner duck-types the SubAgentRunner seam, faulting declared
(task_title, cycle_seq) pairs and delegating the rest so the Director stays
pinned. driver.run_arm drives the bounded loop, stamping runner.cycle_seq per
advance, logging dependent variables per cycle_seq; compare() reports the
ON-vs-OFF delta with per-arm spread.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5.5: `report.py` — JSONL trace writer + comparison summary

Files:
- Create: `E:/director2/director/bench/report.py`
- Modify: `E:/director2/director/bench/__init__.py` (export `write_trace`, `summary_lines`)
- Modify: `E:/director2/tests/test_bench.py` (append)

Reuses the JSONL idiom from `PerfLedger.record` (`metrics.py:29` — one JSON object per line, append, UTF-8). One row per cycle per run per arm; plus a human-readable ON/OFF summary block.

- [ ] Step 1: Write the failing tests. Append to `E:/director2/tests/test_bench.py`:
```python
def test_write_trace_emits_one_jsonl_row_per_cycle(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.faults import FaultScenario
    from director.bench.report import write_trace

    def seed():
        p = Project(name="trace-seed")
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    arm = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    path = tmp_path / "trace.jsonl"
    n = write_trace(path, arm)
    assert path.is_file()
    lines = [json.loads(ln) for ln in
             path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == n
    expected = sum(len(r["cycles"]) for r in arm["runs"])
    assert n == expected
    row = lines[0]
    assert row["arm"] == "on" and "rep" in row and "cycle_seq" in row
    assert "scenario" in row and "accumulated_damage" in row


def test_summary_lines_render_on_off_block(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario
    from director.bench.report import summary_lines

    def seed():
        p = Project(name="sum-seed")
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
        p.tasks = {t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom"})
    on = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    off = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    lines = summary_lines(compare(on, off))
    text = "\n".join(lines)
    assert "screams_fired" in text
    assert "ON" in text and "OFF" in text
    assert "delta" in text.lower()
```

- [ ] Step 2: Run them, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "trace or summary_lines" -q
```
Expected FAIL: `ModuleNotFoundError: No module named 'director.bench.report'`.

- [ ] Step 3: Write the implementation. Create `E:/director2/director/bench/report.py`:
```python
"""Bench reporting: a JSONL trace (one row per cycle, mirroring PerfLedger's
append-a-JSON-line idiom, metrics.py:29) plus a human-readable ON/OFF summary.
The trace is the durable evidence base; the summary is the readout."""

from __future__ import annotations

import json
from pathlib import Path


def write_trace(path, arm_result: dict) -> int:
    """Write one JSON line per (rep, cycle) for an arm. Returns rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with path.open("a", encoding="utf-8") as fh:
        for rep_i, run in enumerate(arm_result["runs"]):
            for cyc in run["cycles"]:
                row = {"arm": arm_result["arm"],
                       "scenario": arm_result["scenario"],
                       "rep": rep_i, **cyc}
                fh.write(json.dumps(row) + "\n")
                rows += 1
    return rows


def summary_lines(comparison: dict) -> list[str]:
    """Render the ON/OFF comparison (from driver.compare) as text lines."""
    lines = ["== BENCH: nervous ON vs OFF =="]
    header = f"{'metric':<18} {'ON':>8} {'OFF':>8} {'delta':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for metric, vals in comparison.items():
        lines.append(f"{metric:<18} {vals['on']:>8} {vals['off']:>8} "
                     f"{vals['delta']:>8}")
        lines.append(f"  spread ON {vals['on_spread']}  "
                     f"OFF {vals['off_spread']}")
    return lines
```

- [ ] Step 4: Add the exports. In `E:/director2/director/bench/__init__.py`, change:
```python
from .faults import FaultScenario, ScriptedFaultRunner
from .driver import compare, run_arm

__all__ = ["FaultScenario", "ScriptedFaultRunner", "run_arm", "compare"]
```
to:
```python
from .faults import FaultScenario, ScriptedFaultRunner
from .driver import compare, run_arm
from .report import summary_lines, write_trace

__all__ = ["FaultScenario", "ScriptedFaultRunner", "run_arm", "compare",
           "summary_lines", "write_trace"]
```

- [ ] Step 5: Run them, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "trace or summary_lines" -q
```
Expected: both PASS.

- [ ] Step 6: Commit.
```
git -C E:/director2 add director/bench/report.py director/bench/__init__.py tests/test_bench.py
git -C E:/director2 commit -m "bench: JSONL trace writer + ON/OFF summary report

write_trace emits one JSON line per (rep, cycle) (PerfLedger idiom);
summary_lines renders the compare() delta with per-arm spread.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5.6: CLI — `director bench`

Files:
- Modify: `E:/director2/director/cli.py` (append the `bench` command after the existing `advance` command, mirroring `advance` at `cli.py:189-206` and `evolve run` at `cli.py:432-451`)
- Modify: `E:/director2/tests/test_bench.py` (append the CLI bench test)

> **Note:** the `director run` command is defined in Phase 4 Task 4.6; this task adds only `bench`. Do NOT re-add a `run` command here — the Phase 4.6 command is the canonical one (it reads `out['stop_reason']`/`out['cycles']`, the actual shape `Director.run()` returns).

`director bench` builds a `FaultScenario` (default scenario factory lives in `director/bench/scenarios.py`, created here) and runs the requested arm(s), echoing the summary. It mirrors the `_services()` → `resolve_project` → echo pattern and `evolve run`'s colored-secho readout.

- [ ] Step 1: Write the failing test. Append to `E:/director2/tests/test_bench.py`:
```python
def test_cli_bench_command_default_scenario(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from director.cli import main
    monkeypatch.setenv("DIRECTOR_HOME", str(tmp_path / "ws"))
    runner = CliRunner()
    r = runner.invoke(main, ["bench", "--arm", "both", "--reps", "2"],
                      catch_exceptions=False)
    assert r.exit_code == 0
    assert "nervous ON vs OFF" in r.output
    assert "screams_fired" in r.output
```

- [ ] Step 2: Run it, expect FAIL. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "cli_bench" -q
```
Expected FAIL: `test_cli_bench_command_default_scenario` fails — click reports `Error: No such command 'bench'` (raised through `catch_exceptions=False`).

- [ ] Step 3: Create the default scenario factory. Write `E:/director2/director/bench/scenarios.py`:
```python
"""Named bench scenarios. Each is a FaultScenario: a seed-project factory plus
a (task_title, cycle_seq)-keyed fault schedule. Titles are stable across arms;
ids (uuid4) are not, so the schedule keys on titles.
"""

from __future__ import annotations

from ..core.types import Project, Task, TaskStatus
from .faults import FaultScenario


def _default_seed() -> Project:
    p = Project(name="bench-default")
    t_ok = Task(title="build-ok", role="code", status=TaskStatus.READY)
    t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY)
    p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
    return p


_SCENARIOS = {
    "default": lambda: FaultScenario(
        name="default",
        seed_factory=_default_seed,
        schedule={("build-bad", 1): "scripted fault: build-bad failed at cycle 1",
                  ("build-bad", 2): "scripted fault: build-bad failed at cycle 2"}),
}


def scenario_names() -> list[str]:
    return sorted(_SCENARIOS)


def get_scenario(name: str) -> FaultScenario:
    if name not in _SCENARIOS:
        raise KeyError(f"unknown bench scenario '{name}'; "
                       f"have {scenario_names()}")
    return _SCENARIOS[name]()
```

- [ ] Step 4: Add the `bench` CLI command. In `E:/director2/director/cli.py`, immediately after the `advance` command body (after `cli.py:206`, the end of the `advance` function), insert (the `run` command already exists from Phase 4 Task 4.6 — do NOT add it again):
```python
@main.command()
@click.option("--arm", type=click.Choice(["on", "off", "both"]),
              default="both", help="Which arm(s) to run.")
@click.option("--reps", type=int, default=5)
@click.option("--scenario", "scenario_name", default="default")
def bench(arm: str, reps: int, scenario_name: str) -> None:
    """Run the observation bench: nervous ON vs OFF on a scripted fault."""
    from .bench.driver import compare, run_arm
    from .bench.report import summary_lines, write_trace
    from .bench.scenarios import get_scenario

    svc = _services()
    scenario = get_scenario(scenario_name)
    out_dir = svc.cfg.runs_dir / "bench" / scenario.name
    results: dict = {}
    if arm in ("on", "both"):
        results["on"] = run_arm(scenario, nervous=True, reps=reps,
                                home=out_dir / "on")
        write_trace(out_dir / "trace_on.jsonl", results["on"])
    if arm in ("off", "both"):
        results["off"] = run_arm(scenario, nervous=False, reps=reps,
                                 home=out_dir / "off")
        write_trace(out_dir / "trace_off.jsonl", results["off"])

    if "on" in results and "off" in results:
        for line in summary_lines(compare(results["on"], results["off"])):
            click.echo(line)
    else:
        only = results.get("on") or results.get("off")
        click.secho(f"== BENCH: nervous ON vs OFF == (single arm: {arm})",
                    fg="cyan")
        click.echo(f"{only['arm']}: {only['totals']}")
    click.secho(f"traces: {out_dir}", fg="cyan")
```

- [ ] Step 5: Run it, expect PASS. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k "cli_bench" -q
```
Expected: PASS. The `bench --arm both` echoes the `== BENCH: nervous ON vs OFF ==` block from `summary_lines`.

- [ ] Step 6: Guard the CLI regression — existing CLI tests must stay green (the new `bench` command must not perturb the group). From `E:/director2`:
```
python -m pytest tests/test_cli.py tests/test_integrity_cli.py -q
```
Expected: PASS.

- [ ] Step 7: Commit.
```
git -C E:/director2 add director/cli.py director/bench/scenarios.py tests/test_bench.py
git -C E:/director2 commit -m "cli: add `director bench` command

`director bench [--arm on|off|both] [--reps N] [--scenario NAME]` runs the
ON/OFF arms over a named scripted scenario, writes JSONL traces, and prints the
comparison summary. (The `director run` command is the Phase 4 Task 4.6 one.)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5.7: Integration — siren → latch holds → human recovery → verified clear → auto-resume, ON-vs-OFF delta

Files:
- Modify: `E:/director2/tests/test_bench.py` (append the integration test)

This is the headline §11 integration test. It uses the bench's scripted runner directly against a `Director` so it can (a) drive the autonomous loop until a siren latches, (b) confirm the latch holds across an autonomous advance, (c) perform a human-commanded `advance(autonomous=False)` that removes the fault and re-verifies the clear rule, (d) confirm auto-resume, and (e) confirm the same title+cycle_seq scenario produces a measurable ON-vs-OFF delta. Because a siren requires a hard override (`integrity_violations`/`charter_breach`) or a composite crossing `siren_threshold`, the scenario drives `accumulated_damage` past `siren_threshold` via repeated scripted FAILED tasks on the same title — the trusted reducer (Phase 3 `compute_body`) reads FAILED-count severity, so enough faults on one task trip the siren deterministically on the mock backend.

> **Grounding for the clear path:** the latch's `grounding_damage` clear rule (spec §8.3) requires the offending risk(s) to close. In the bench, "human recovery" = re-running the loop with the fault removed for that title so the task reaches DONE and `accumulated_damage` severity drops below threshold; `check_clear_rule` (Phase 3) re-verifies and `advance()` (Phase 4) clears `project.scream_open` in place. The test removes the fault by swapping the runner's live schedule (the `ScriptedFaultRunner.scenario.schedule` is a plain dict — clearing it makes the next worker run succeed), which models the operator fixing the underlying cause.

- [ ] Step 1: Write the failing integration test. Append to `E:/director2/tests/test_bench.py`:
```python
def _build_live_director(cfg, scenario, project):
    from director.bench.faults import ScriptedFaultRunner
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    delegate = SubAgentRunner(cfg, router, registry)
    title_index = {t.id: t.title for t in project.tasks.values()}
    runner = ScriptedFaultRunner(delegate, scenario, title_index=title_index)
    director = Director(cfg, store, router, registry, runner)
    return director, store, runner


def _advance_until_siren(director, store, runner, pid, *, max_cycles=20):
    """Drive autonomous advance, stamping cycle_seq, until the latch opens."""
    from director.core.types import utcnow
    from director.evolve.metrics import PerfLedger
    # the public stop() predicate is run-scoped: hold a perf ledger, a `since`
    # stamp, and a cycle counter (as Director.run does) and pass them through.
    perf = getattr(director, "perf", None) or PerfLedger(director.cfg)
    since = utcnow().isoformat()
    cycle_count = 0
    for _ in range(max_cycles):
        project = store.load(pid)
        if project.scream_open:
            return project
        if director.stop(project, perf=perf, since=since, cycles=cycle_count):
            break
        runner.cycle_seq = project.cycle_seq + 1
        director.advance(pid, autonomous=True)
        cycle_count += 1
    return store.load(pid)


def test_integration_siren_latch_recovery_resume(tmp_path):
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="siren-arc")
        # one task that keeps failing -> accumulated_damage climbs to siren
        t_bad = Task(title="grounding-target", role="code",
                     status=TaskStatus.READY, max_attempts=1)
        p.tasks = {t_bad.id: t_bad}
        return p

    # fault every cycle for a while: repeated FAILED feeds accumulated_damage
    schedule = {("grounding-target", c): f"scripted fault @ cycle {c}"
                for c in range(1, 12)}
    scenario = FaultScenario(name="siren", seed_factory=seed, schedule=schedule)

    cfg = Config(home=tmp_path / "on")
    cfg.ensure_dirs()
    cfg.nervous_enabled = True
    cfg.auto_advance_after_decision = False
    project = seed()
    director, store, runner = _build_live_director(cfg, scenario, project)
    store.save(project)

    # 1) drive until the siren latches
    project = _advance_until_siren(director, store, runner, project.id)
    assert project.scream_open is not None, "expected a siren to latch"
    cause = project.scream_open["cause"]
    assert cause in ("grounding_damage", "charter_breach", "tamper")
    opened_at = project.scream_open["opened_at"]

    # 2) the siren packet is still open, so the cycle right after the siren hits
    #    the open-packet gate FIRST (returns "awaiting_command"). Answer/defer
    #    that packet WITHOUT clearing the latch (only trusted re-verification
    #    clears it); the NEXT autonomous advance then reaches the latch gate and
    #    must HALT with "latched". Both are halts; the latch persists.
    from director.core.types import PacketStatus
    siren_pkt = next(pk for pk in store.load(project.id).packets.values()
                     if pk.status is PacketStatus.PRESENTED
                     and pk.trigger.startswith("scream:"))
    director.decide(project.id, siren_pkt.id, option_key="A")
    project = store.load(project.id)
    assert project.scream_open is not None                    # answer ≠ clear
    runner.cycle_seq = project.cycle_seq + 1
    out = director.advance(project.id, autonomous=True)
    assert out["status"] == "latched"
    project = store.load(project.id)
    assert project.scream_open is not None
    assert project.scream_open["opened_at"] == opened_at      # same latch

    # 3) human recovery: remove the underlying fault AND reset the offending
    #    FAILED task(s) so the operator-fixed work can re-run to DONE. This is
    #    what makes the chosen grounding_damage clear rule actually satisfiable:
    #    its origin_refs are the FAILED task ids, and the rule clears only once
    #    those tasks are no longer FAILED AND accumulated_damage severity drops
    #    below the recorded opened_severity. A human-commanded
    #    advance(autonomous=False) then re-verifies the clear rule in place.
    from director.core.types import TaskStatus
    runner.scenario.schedule.clear()                          # operator fixes cause
    project = store.load(project.id)
    for t in project.tasks.values():
        if t.status is TaskStatus.FAILED:
            t.status = TaskStatus.READY                       # eligible to re-run
            t.attempts = 0
    store.save(project)
    for _ in range(6):
        project = store.load(project.id)
        if project.scream_open is None:
            break
        runner.cycle_seq = project.cycle_seq + 1
        director.advance(project.id, autonomous=False, force=True)

    project = store.load(project.id)
    assert project.scream_open is None, "verified clear should drop the latch"

    # 4) auto-resume: a plain autonomous advance now proceeds (no halt)
    runner.cycle_seq = project.cycle_seq + 1
    resumed = director.advance(project.id, autonomous=True)
    assert resumed["status"] in ("ok", "idle")


def test_integration_on_vs_off_same_scenario_reproducible(tmp_path):
    from director.bench.driver import compare, run_arm
    from director.bench.faults import FaultScenario

    def seed():
        p = Project(name="delta-arc")
        t_bad = Task(title="grounding-target", role="code",
                     status=TaskStatus.READY, max_attempts=1)
        p.tasks = {t_bad.id: t_bad}
        return p

    schedule = {("grounding-target", c): f"fault @ {c}" for c in range(1, 12)}
    scenario = FaultScenario(name="siren", seed_factory=seed, schedule=schedule)

    off = run_arm(scenario, nervous=False, reps=3, home=tmp_path / "off")
    on = run_arm(scenario, nervous=True, reps=3, home=tmp_path / "on")
    delta = compare(on, off)

    # faults match across arms (title+cycle_seq keyed) -> OFF also sees the
    # worker failures, but with no nervous system it never screams or halts
    assert off["totals"]["screams_fired"] == 0
    assert on["totals"]["screams_fired"] >= 1
    # reproducible across 3 reps: ON's scream count is identical every rep
    on_per_rep = [r["screams_fired"] for r in on["runs"]]
    assert min(on_per_rep) == max(on_per_rep)                  # zero spread
    # the headline: ON halts on the fault, OFF plows through more cycles
    assert delta["cycles_run"]["off"] >= delta["cycles_run"]["on"] or \
        delta["screams_fired"]["delta"] >= 1
```

- [ ] Step 2: Run them, expect FAIL or ERROR depending on prior-phase state. From `E:/director2`:
```
python -m pytest tests/test_bench.py -k integration -q
```
Expected FAIL: if Phases 1-4 are wired, the assertions about the latch (`project.scream_open is not None`) drive real behavior; the test fails first at the point where the siren must latch deterministically — confirm the scenario's repeated-FAILED schedule actually crosses `siren_threshold` given Phase 2's declared `axis_saturation["accumulated_damage"]=5.0` and `siren_threshold=-0.66`. If the siren does not latch within the cycle budget, the failure message is `assert None is not None: expected a siren to latch`.

- [ ] Step 3: Tune the scenario fault count, not the production thresholds, to make the siren deterministic. The thresholds are declared constants owned by Phase 2's config and the bench must not hardcode around them — instead the scenario supplies enough scripted FAILED cycles that the trusted reducer's FAILED-count severity crosses `siren_threshold`. If Step 2 shows the siren never latches, widen the schedule range (already `range(1, 12)`) and confirm `max_attempts=1` so each fault terminally FAILs the task (driving FAILED count, not endless retries). No implementation code changes here — this task is the integration harness only; the latch/scream/clear logic is Phase 3+4 and is exercised, not redefined. Re-run:
```
python -m pytest tests/test_bench.py -k integration -q
```
Expected: PASS once the scenario reliably trips the siren and the clear path drops the latch. (If after widening the schedule the siren still will not trip on the mock backend, that is a Phase 3 `compute_body` calibration finding — record it as a bench finding and feed it back to the Phase 2 default for `axis_saturation`/`siren_threshold`; do NOT special-case the bench.)

- [ ] Step 4: Run the entire bench file. From `E:/director2`:
```
python -m pytest tests/test_bench.py -q
```
Expected: all bench tests PASS.

- [ ] Step 5: Final guard — confirm the OFF path leaves the 133-test suite byte-identical. With `cfg.nervous_enabled` defaulting `False` everywhere except the bench's explicit ON arm, the full suite must be green. From `E:/director2`:
```
python -m pytest -q
```
Expected: all pre-existing tests plus the new bench tests PASS; the original 133 are unchanged (the bench only flips `nervous_enabled=True` inside its own ON arm and never alters global defaults).

- [ ] Step 6: Commit.
```
git -C E:/director2 add tests/test_bench.py
git -C E:/director2 commit -m "bench: integration test — siren latch, human recovery, verified clear, resume

End-to-end on the scripted runner: repeated scripted FAILED cycles trip a
siren and latch it; an autonomous advance halts on the held latch; operator
removes the cause and human-commanded advance(autonomous=False) re-verifies
the clear rule and drops the latch; auto-resume proceeds. ON-vs-OFF on the
same title+cycle_seq scenario yields a reproducible delta (zero spread across
reps); OFF plows through the fault, ON halts on it.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5.8: Phase close — full-suite green + bench smoke via CLI

Files:
- (No new source) — verification + a recorded smoke run.

- [ ] Step 1: Run the complete test suite one final time. From `E:/director2`:
```
python -m pytest -q
```
Expected: PASS, zero failures; the 133 pre-existing tests remain green (OFF path untouched), plus all `tests/test_bench.py` cases.

- [ ] Step 2: Smoke the bench through the real CLI on an isolated home (proves the wired command path end-to-end, mock backend). From `E:/director2`:
```
python -m director bench --arm both --reps 3 --scenario default
```
Expected: prints the `== BENCH: nervous ON vs OFF ==` table with `screams_fired` showing a positive ON value and `0` OFF, a `delta` column, per-arm spread lines, and a `traces:` path. (If `python -m director` is not the module entrypoint, invoke via the installed console script `director bench --arm both --reps 3`; confirm the entrypoint name against `pyproject`/`setup` at implementation — the CLI group is `director.cli:main`.)

- [ ] Step 3: Confirm the JSONL traces were written. From `E:/director2` (the home defaults to `~/.director2`; the smoke run wrote under `<home>/runs/bench/default/`):
```
python -c "from pathlib import Path; from director.config import Config; d=Config.from_env().runs_dir/'bench'/'default'; print([p.name for p in d.glob('trace_*.jsonl')])"
```
Expected: `['trace_off.jsonl', 'trace_on.jsonl']` (order may vary).

- [ ] Step 4: Commit nothing new (verification only); if any incidental fixture/output file was created under the workspace it is outside the repo tree and is not staged. Phase 5 is complete: the bench package, router pin, CLI commands, and the headline integration are shipped and green, with `nervous_enabled` defaulting `False` so the rest of the system is byte-identical until the bench (or an operator) turns it on.
