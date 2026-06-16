# Director 2.0 Nervous System v2 — Credit Knife + Gut Markers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Director persistent, un-gameable memory of failure: trusted-code **scars** (Credit Knife) written from resolved outcomes, and a `VectorStore`-backed **marker** store (Gut Markers) that recalls them by task signature and reroutes planning around prior pain — diagnoses-only, behind `nervous_enabled`.

**Architecture:** A new `director/memory/markers.py` (`Marker` + `MarkerStore`, reusing the pure-Python `VectorStore`). `director.py` gains write hooks (Credit Knife: at the FAILED-ingest site and in `_handle_siren`, resolved-only) and read+bias (Gut Markers: an advisory re-rank of the full ready frontier with packet-escalation, plus diagnosis injection into `_spec_for`'s `AgentSpec.context`). The model NEVER sees the numeric weight/valence — only the diagnosis text. Everything is guarded by `cfg.nervous_enabled` so v1 and the existing suite stay byte-identical.

**Tech Stack:** Python 3, pytest, the existing Director 2.0 framework (no new deps). Source spec: `docs/superpowers/specs/2026-06-16-director2-nervous-system-v2-design.md`. Branch `nervous-v2` (HEAD has the recalibration; full suite 396 green).

**Phase order (each leaves `python -m pytest` from E:\director2 green):** 1 Foundations → 2 Credit Knife → 3 Gut Markers → 4 Experiment + re-bench.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `director/memory/markers.py` | `Marker` dataclass, `task_signature()`, `MarkerStore` (record/recall/merge-and-strengthen over a `VectorStore`) | Create |
| `director/config.py` | `marker_*` tuning constants (after the `bench` field) | Modify |
| `director/core/types.py` | `Project.marker_deferrals` field | Modify |
| `director/core/director.py` | `self.markers` on `__init__`; Credit Knife scar hooks; Gut Markers advisory re-rank + escalation + diagnosis injection | Modify |
| `director/cli.py` | construct `MarkerStore` and inject when `nervous_enabled` | Modify |
| `director/bench/driver.py` | inject markers in the ON arm; scenario + metrics | Modify |
| `director/bench/scenarios.py` | a repeated-failure scenario | Modify |
| `tests/test_markers.py`, `tests/test_credit_knife.py`, `tests/test_gut_markers.py` | unit + integration | Create |

**Un-gameability invariant (assert it in tests):** every scar/marker `weight` is set by trusted code; the only marker field that reaches a generator is `diagnosis`, which contains no numeric valence/threshold/weight.

---

## Phase 1: Foundations — MarkerStore, config, Project field

### Task 1.1: `Marker` + `task_signature` + `MarkerStore` (merge-and-strengthen)

**Files:**
- Create: `E:/director2/director/memory/markers.py`
- Test: `E:/director2/tests/test_markers.py`

- [ ] **Step 1: Write the failing test.** Create `E:/director2/tests/test_markers.py`:

```python
"""Gut Markers store: signature recall + merge-and-strengthen (the explicit fix
for the lesson ledger's silent _DEDUPE_SIM drop). Offline, deterministic, no model."""

import pytest

from director.config import Config
from director.core.types import Task
from director.memory.markers import Marker, MarkerStore, task_signature


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    return c


def test_task_signature_is_role_module_objective():
    t = Task(title="Build add()", role="code", module_id="m1",
             objective="Implement add(a, b)")
    assert task_signature(t) == "code|m1|implement add(a, b)"
    # falls back to the title when objective is empty
    t2 = Task(title="Build It", role="code", module_id="m1")
    assert task_signature(t2) == "code|m1|build it"


def test_record_inserts_then_recall_returns_it(cfg):
    store = MarkerStore(cfg)
    m = store.record(Marker(signature="code|m1|implement add",
                            cause="failed_verification",
                            diagnosis="add() returned a-b not a+b", last_cycle=1))
    assert m.weight == pytest.approx(-cfg.marker_repel_step)
    assert m.count == 1
    hits = store.recall("code|m1|implement add")
    assert len(hits) == 1
    assert hits[0].diagnosis == "add() returned a-b not a+b"
    assert hits[0].weight < 0


def test_record_merges_and_strengthens_on_repeat(cfg):
    # a recurring scar DEEPENS (more negative weight, count++) — NOT a silent drop.
    store = MarkerStore(cfg)
    store.record(Marker(signature="code|m1|implement add",
                        cause="failed_verification", diagnosis="first", last_cycle=1))
    m2 = store.record(Marker(signature="code|m1|implement add",
                             cause="grounding_damage", diagnosis="again", last_cycle=2))
    assert m2.count == 2
    assert m2.weight == pytest.approx(-2 * cfg.marker_repel_step)
    assert m2.diagnosis == "again"          # diagnosis refreshed to the latest
    # only ONE marker exists for that signature (merged, not duplicated)
    assert len(store.recall("code|m1|implement add")) == 1


def test_weight_clamped_at_floor(cfg):
    store = MarkerStore(cfg)
    for i in range(50):
        store.record(Marker(signature="code|m1|x", cause="failed_verification",
                            diagnosis="d", last_cycle=i))
    assert store.recall("code|m1|x")[0].weight >= cfg.marker_repel_floor


def test_recall_excludes_below_similarity(cfg):
    store = MarkerStore(cfg)
    store.record(Marker(signature="code|m1|implement add",
                        cause="failed_verification", diagnosis="d", last_cycle=1))
    # an unrelated signature recalls nothing above the recall threshold
    assert store.recall("research|m9|write a market analysis report") == []


def test_persists_across_instances(cfg):
    MarkerStore(cfg).record(Marker(signature="code|m1|implement add",
                                   cause="failed_verification", diagnosis="d",
                                   last_cycle=1))
    assert len(MarkerStore(cfg).recall("code|m1|implement add")) == 1
```

- [ ] **Step 2: Run it; expect FAIL** (`ModuleNotFoundError: director.memory.markers`).

```
python -m pytest tests/test_markers.py -q
```

- [ ] **Step 3: Implement** `E:/director2/director/memory/markers.py`:

```python
"""Gut Markers — persistent, un-gameable memory of failure (nervous-system v2).

A ``Marker`` is a SCAR: a diagnosis (failing case + cause) plus a trusted-only
signed ``weight`` (< 0 repels). Trusted code computes the weight from executed
outcomes; the only field a generator ever reads is ``diagnosis`` (problems, not
numbers — Constitution #3). The store reuses the pure-Python ``VectorStore`` (no
model) as a SIBLING to the lesson ledger, and MERGES-and-strengthens a recurring
scar instead of the lesson ledger's silent ``_DEDUPE_SIM`` drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core.types import new_id, utcnow
from .vector import VectorStore


def task_signature(task) -> str:
    """Stable recall key: role | module | normalized objective (or title)."""
    obj = (task.objective or task.title or "").strip().lower()
    return f"{task.role}|{task.module_id}|{obj}"


@dataclass
class Marker:
    signature: str
    cause: str = "failed_verification"   # failed_verification | grounding_damage | charter_breach | ...
    diagnosis: str = ""                  # the ONLY model-facing field (problems, not numbers)
    weight: float = 0.0                  # signed, trusted-only: < 0 repels (hurt before)
    count: int = 1                       # times this scar recurred (merge-and-strengthen)
    origin: str = ""                     # origin_decision_id, or synthetic "plan:<module>"
    last_cycle: int = 0
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)


class MarkerStore:
    """VectorStore-backed marker index. Text indexed = the signature (recall key);
    weight/diagnosis/etc live in the row meta."""

    def __init__(self, cfg):
        self.cfg = cfg
        path = Path(cfg.marker_store_path) if cfg.marker_store_path \
            else cfg.memory_dir / "markers_index.json"
        self.index = VectorStore(path, dims=cfg.vector_dims)

    def record(self, marker: Marker) -> Marker:
        """Insert a new scar, or MERGE-and-strengthen an existing one for the same
        signature (cosine >= cfg.marker_merge_sim). Trusted-only; never a model call."""
        hits = self.index.search(marker.signature, k=1,
                                 min_score=self.cfg.marker_merge_sim)
        if hits:
            ex = hits[0]
            meta = dict(ex["meta"])
            meta["weight"] = max(self.cfg.marker_repel_floor,
                                 float(meta.get("weight", 0.0))
                                 - self.cfg.marker_repel_step)
            meta["count"] = int(meta.get("count", 1)) + 1
            meta["diagnosis"] = marker.diagnosis or meta.get("diagnosis", "")
            meta["cause"] = marker.cause
            meta["last_cycle"] = marker.last_cycle
            self.index.add(ex["id"], marker.signature, meta)   # re-add under same id
            return self._to_marker(ex["id"], marker.signature, meta)
        marker.weight = -self.cfg.marker_repel_step
        meta = {"weight": marker.weight, "count": 1, "diagnosis": marker.diagnosis,
                "cause": marker.cause, "origin": marker.origin,
                "last_cycle": marker.last_cycle}
        self.index.add(marker.id, marker.signature, meta)
        return marker

    def recall(self, signature: str, *, k: int | None = None,
               min_sim: float | None = None) -> list[Marker]:
        """Markers whose signature is cosine >= cfg.marker_recall_sim of ``signature``."""
        hits = self.index.search(
            signature, k=k or self.cfg.marker_digest_max,
            min_score=self.cfg.marker_recall_sim if min_sim is None else min_sim)
        return [self._to_marker(h["id"], h["text"], h["meta"]) for h in hits]

    @staticmethod
    def _to_marker(id_: str, signature: str, meta: dict) -> Marker:
        return Marker(signature=signature, cause=meta.get("cause", ""),
                      diagnosis=meta.get("diagnosis", ""),
                      weight=float(meta.get("weight", 0.0)),
                      count=int(meta.get("count", 1)),
                      origin=meta.get("origin", ""),
                      last_cycle=int(meta.get("last_cycle", 0)), id=id_)
```

- [ ] **Step 4: Run it; expect PASS** (6 tests).

```
python -m pytest tests/test_markers.py -q
```

- [ ] **Step 5: Commit.**

```
git -C E:/director2 add director/memory/markers.py tests/test_markers.py
git -C E:/director2 commit -m "feat(v2): Marker + MarkerStore (VectorStore-backed, merge-and-strengthen)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.2: `marker_*` config keys + `Project.marker_deferrals`

**Files:**
- Modify: `E:/director2/director/config.py` (after the `bench` field, before `# --- sandbox / grounding ---`)
- Modify: `E:/director2/director/core/types.py` (`Project`, after `coherence_blocks`)
- Test: `E:/director2/tests/test_markers.py` (append)

- [ ] **Step 1: Append the failing test** to `tests/test_markers.py`:

```python
def test_marker_config_defaults():
    c = Config()
    assert c.marker_recall_sim == 0.6
    assert c.marker_merge_sim == 0.9
    assert c.marker_repel_step == 0.5
    assert c.marker_repel_floor == -3.0
    assert c.marker_defer_escalate_cycles == 3
    assert c.marker_digest_max == 3
    assert c.marker_store_path == ""


def test_project_marker_deferrals_default_empty():
    from director.core.types import Project, decode, encode
    p = Project(name="p")
    assert p.marker_deferrals == {}
    p.marker_deferrals = {"t1": 2}
    assert decode(Project, encode(p)).marker_deferrals == {"t1": 2}
```

- [ ] **Step 2: Run; expect FAIL** (`AttributeError: 'Config' object has no attribute 'marker_recall_sim'`).

```
python -m pytest tests/test_markers.py -k "marker_config or marker_deferrals" -q
```

- [ ] **Step 3a: Add the config block.** In `director/config.py`, after the `bench` field (the `bench: dict = field(...)` block) and before `# --- sandbox / grounding ---`, insert:

```python
    # --- gut markers (v2) -------------------------------------------------------
    # Active only when nervous_enabled. Diagnoses-only: the model never sees a
    # weight; trusted code computes every scar. First-guess constants, tuned via
    # the bench (the same discipline that recalibrated the uncertainty axis).
    marker_recall_sim: float = 0.6     # cosine to recall a scar for a task signature
    marker_merge_sim: float = 0.9      # cosine to merge-and-strengthen vs insert
    marker_repel_step: float = 0.5     # weight made more-repellent per recurrence
    marker_repel_floor: float = -3.0   # clamp so one signature can't dominate
    marker_defer_escalate_cycles: int = 3  # advisory deferrals before a packet
    marker_digest_max: int = 3         # max markers recalled/injected per task
    marker_store_path: str = ""        # "" -> cfg.memory_dir / "markers_index.json"
```

- [ ] **Step 3b: Add the Project field.** In `director/core/types.py`, in the `Project` dataclass, after `coherence_blocks: int = 0` and before `created_at`, insert:

```python
    # --- gut markers (v2) ---------------------------------------------------
    marker_deferrals: dict = field(default_factory=dict)   # {task_id: deferral_count}
```

- [ ] **Step 4: Run; expect PASS.**

```
python -m pytest tests/test_markers.py -q
```

- [ ] **Step 5: Run the full suite** (additive, OFF-inert) — expect green.

```
python -m pytest -q
```

- [ ] **Step 6: Commit.**

```
git -C E:/director2 add director/config.py director/core/types.py tests/test_markers.py
git -C E:/director2 commit -m "feat(v2): marker_* config constants + Project.marker_deferrals

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2: Credit Knife — write scars from resolved outcomes

### Task 2.1: `self.markers` wiring + FAILED-ingest scar hook

**Files:**
- Modify: `E:/director2/director/core/director.py` (`__init__`, the FAILED-ingest site ~line 819-827, + two helpers)
- Modify: `E:/director2/director/cli.py` (construct `MarkerStore` when `nervous_enabled`)
- Test: `E:/director2/tests/test_credit_knife.py` (Create)

- [ ] **Step 1: Write the failing test.** Create `E:/director2/tests/test_credit_knife.py`:

```python
"""Credit Knife: a RESOLVED failure (terminal FAILED) writes a problems-not-rubrics
scar; an in-flight retry writes nothing. Trusted-only, behind nervous_enabled."""

import pytest

import director.core.director as dmod
from director.agents.base import AgentResult, AgentSpec
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.memory.markers import MarkerStore, task_signature
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


class _FailRunner:
    """Every dispatched spec fails with a content error (non-transient)."""
    def run_parallel(self, specs):
        return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role,
                            ok=False, error="add() returned a-b not a+b")
                for s in specs]


def _boss(cfg, runner):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return Director(cfg, store, router, registry, runner,
                    markers=MarkerStore(cfg))


def test_terminal_failure_writes_a_scar(cfg):
    boss = _boss(cfg, _FailRunner())
    p = Project(name="ck")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY,
             max_attempts=1)            # fails terminally on the first attempt
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    scars = boss.markers.recall(task_signature(t))
    assert len(scars) == 1
    sc = scars[0]
    assert sc.cause == "failed_verification"
    assert "add()" in sc.diagnosis            # carries the failing case
    # problems-not-rubrics: no numeric valence/threshold/weight leaked into the text
    for forbidden in ("-0.", "valence", "threshold", "weight"):
        assert forbidden not in sc.diagnosis.lower()
    assert sc.origin                          # non-empty (synthetic origin for a plan task)


def test_transient_retry_writes_no_scar(cfg):
    class _TransientRunner:
        def run_parallel(self, specs):
            return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role,
                                ok=False, error="rate limit exceeded (429)")
                    for s in specs]
    boss = _boss(cfg, _TransientRunner())
    p = Project(name="ck2")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY, max_attempts=2)
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)      # transient -> READY retry, NOT terminal
    assert boss.markers.recall(task_signature(t)) == []


def test_off_path_writes_no_scar(cfg):
    cfg.nervous_enabled = False
    boss = _boss(cfg, _FailRunner())
    p = Project(name="ck3")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.READY, max_attempts=1)
    p.tasks = {t.id: t}
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    assert boss.markers.recall(task_signature(t)) == []   # markers untouched OFF
```

- [ ] **Step 2: Run; expect FAIL** — `Director.__init__() got an unexpected keyword argument 'markers'`.

```
python -m pytest tests/test_credit_knife.py -q
```

- [ ] **Step 3a: Add `markers` to `Director.__init__`.** Change the signature/body:

```python
    def __init__(self, cfg: Config, store: ProjectStore, router: LLMRouter,
                 registry: VerifierRegistry, runner: SubAgentRunner,
                 *, lessons=None, perf=None, markers=None):
        self.cfg = cfg
        self.store = store
        self.router = router
        self.registry = registry
        self.runner = runner
        self.lessons = lessons
        self.perf = perf
        self.markers = markers                 # MarkerStore | None (gut markers v2)
        self._run_since = None
```

- [ ] **Step 3b: Add the import + two helpers** near the other Director methods (e.g. just before `_nervous_pass`):

```python
    # ----------------------------------------------------------- credit knife
    def _record_scar(self, project: Project, task: Task, *, cause: str) -> None:
        """Write a trusted scar for a RESOLVED failure (diagnoses-only). No model
        call. Guarded by the caller behind cfg.nervous_enabled + self.markers."""
        from ..memory.markers import Marker, task_signature
        origin = task.origin_decision_id or f"plan:{task.module_id or 'root'}"
        diagnosis = (f"Task '{task.title}' (role {task.role}) failed verification "
                     f"after {task.attempts} attempt(s): "
                     f"{(task.error or 'no detail')[:300]}")
        self.markers.record(Marker(
            signature=task_signature(task), cause=cause, diagnosis=diagnosis,
            origin=origin, last_cycle=project.cycle_seq))
        self._audit(project, "scar.recorded",
                    f"scar on {task_signature(task)} ({cause})",
                    {"task_id": task.id, "cause": cause})
```

(`Marker`/`task_signature` are imported lazily inside the method to avoid an import cycle, mirroring the integrity/coherence lazy imports already in this file.)

**Origin attribution (spec §5.3, with an intentional simplification).** The spec proposes a synthetic origin of `f"hook:{task.role}"` for hook tasks and `"plan"` otherwise. The current `Task` dataclass carries **no** hook-provenance flag, so that hook-vs-plan distinction isn't derivable at this site. `_record_scar` therefore gives every non-decision task the synthetic origin `f"plan:{task.module_id or 'root'}"`, which still satisfies §5.3's actual intent — a **non-empty, recorded** attribution for the dominant (plan/hook) failure source so the Credit Knife isn't limited to decision-spawned work. The test only asserts the origin is non-empty.

- [ ] **Step 3c: Hook the FAILED-ingest site.** In `advance()`'s result-ingest loop there is an `if/elif/else` chain: the terminal-failure branch is `elif task.attempts >= task.max_attempts:` (it sets `task.status = TaskStatus.FAILED` and calls `self._audit(project, "task.failed", ...)`); the trailing `else:` re-queues a non-terminal retry as `TaskStatus.READY`; and `task.updated_at = utcnow()` runs *after* the whole chain. Add the scar hook as the **last statement inside that `elif` branch only** — immediately after the `self._audit(project, "task.failed", ...)` call, at the same indentation as that `self._audit` (20 spaces):

```python
                    if self.cfg.nervous_enabled and self.markers is not None:
                        self._record_scar(project, task,
                                          cause="failed_verification")
```

Do NOT place it after the chain (e.g. next to `task.updated_at`) or inside the `else:` — that would scar transient/early-retry READY tasks, violating resolve-before-scarring (spec §3b).

- [ ] **Step 4: Run; expect PASS** (3 tests).

```
python -m pytest tests/test_credit_knife.py -q
```

- [ ] **Step 5: Wire CLI construction.** In `director/cli.py`, where the `Director(...)` is constructed inside the services/factory (the same place `lessons`/`perf` are passed — find it by searching for `Director(`), add a markers argument:

```python
        from .memory.markers import MarkerStore
        markers = MarkerStore(cfg) if cfg.nervous_enabled else None
```
and pass `markers=markers` to the `Director(...)` call. (Read the real construction site; mirror how `lessons=`/`perf=` are passed. If the CLI does not currently pass `lessons`/`perf`, add `markers=markers` as the only new kwarg.) Then run the CLI suite:

```
python -m pytest tests/test_cli.py -q
```

- [ ] **Step 6: Commit.**

```
git -C E:/director2 add director/core/director.py director/cli.py tests/test_credit_knife.py
git -C E:/director2 commit -m "feat(v2): Credit Knife — scar on terminal FAILED (resolved-only, diagnoses)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.2: siren scar hook (strengthen the offending signatures)

**Files:**
- Modify: `E:/director2/director/core/director.py` (`_handle_siren`, after `_make_packet`, before `project.scream_open = ...`)
- Test: `E:/director2/tests/test_credit_knife.py` (append)

- [ ] **Step 1: Append the failing test:**

```python
def test_siren_strengthens_scars_for_failed_signatures(cfg):
    import director.core.director as dmod
    from director.core.types import BodyState
    boss = _boss(cfg, _FailRunner())
    p = Project(name="ck4")
    t = Task(title="Implement add", role="code", module_id="m1",
             objective="implement add(a,b)", status=TaskStatus.FAILED, max_attempts=1)
    t.error = "add() returned a-b not a+b"
    p.tasks = {t.id: t}
    p.body = BodyState(accumulated_damage=1.0, valence=-0.44,
                       provenance={"risk_ids": []})
    scream = {"level": "siren", "cause": "grounding_damage",
              "axis": "accumulated_damage", "clear_rule": "x",
              "report": "trusted damage report"}
    boss._handle_siren(p, scream, autonomous=True)
    scars = boss.markers.recall(task_signature(t))
    assert scars and scars[0].cause == "grounding_damage"   # tagged with the siren cause
    assert scars[0].count >= 1
```

- [ ] **Step 2: Run; expect FAIL** (`assert [] and ...` — no scar from the siren yet).

```
python -m pytest tests/test_credit_knife.py -k siren_strengthens -q
```

- [ ] **Step 3: Hook `_handle_siren`.** After `self._make_packet(project, trigger="scream:" + cause, hint=report, context_override=report)` and the `failed_ids = [...]` line is built, and BEFORE `project.scream_open = {...}`, add:

```python
        if self.cfg.nervous_enabled and self.markers is not None:
            for tid in failed_ids:
                ft = project.tasks.get(tid)
                if ft is not None:
                    self._record_scar(project, ft, cause=cause)
```

(`failed_ids` already exists in `_handle_siren`; `cause = scream["cause"]` is already in scope. This strengthens the scar of each failed task that drove the siren — a failure that ALSO triggered a siren is worse, so its marker deepens via merge-and-strengthen.)

- [ ] **Step 4: Run; expect PASS.** Then the credit-knife + latch suites.

```
python -m pytest tests/test_credit_knife.py tests/test_latch_state_machine.py -q
```

- [ ] **Step 5: Commit.**

```
git -C E:/director2 add director/core/director.py tests/test_credit_knife.py
git -C E:/director2 commit -m "feat(v2): Credit Knife — siren strengthens the offending-signature scars

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3: Gut Markers — recall, advisory re-rank, diagnosis injection

### Task 3.1: advisory re-rank of the full ready frontier

**Files:**
- Modify: `E:/director2/director/core/director.py` (`advance()` batch selection ~line 763-764, + `_advisory_batch` helper)
- Test: `E:/director2/tests/test_gut_markers.py` (Create)

- [ ] **Step 1: Write the failing test.** Create `E:/director2/tests/test_gut_markers.py`:

```python
"""Gut Markers bias: a scarred signature is DEFERRED behind unscarred ready work,
without mutating the canonical deterministic frontier; OFF-path is byte-identical."""

import pytest

from director.agents.base import AgentResult, AgentSpec
from director.config import Config
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.taskgraph import ready_tasks
from director.core.types import Project, Task, TaskStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.memory.markers import Marker, MarkerStore, task_signature
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.max_tasks_per_advance = 1          # only ONE dispatch per cycle -> repel must choose
    return c


class _OkRunner:
    def run_parallel(self, specs):
        return [AgentResult(spec_id=s.id, task_id=s.task_id, role=s.role, ok=True,
                            output={"summary": "ok"}) for s in specs]


def _boss(cfg, markers):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    return Director(cfg, store, router, registry, _OkRunner(), markers=markers)


def _two_ready(cfg):
    p = Project(name="gm")
    scarred = Task(title="Scarred", role="code", module_id="m1",
                   objective="the painful one", status=TaskStatus.READY)
    clean = Task(title="Clean", role="code", module_id="m1",
                 objective="the fresh one", status=TaskStatus.READY)
    p.tasks = {scarred.id: scarred, clean.id: clean}
    return p, scarred, clean


def test_scarred_signature_is_deferred_behind_clean_work(cfg):
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    # the scarred task's signature carries prior pain
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="hurt before",
                          last_cycle=0))
    boss = _boss(cfg, markers)
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)      # dispatches ONE; repel should pick CLEAN
    p2 = boss.store.load(p.id)
    assert p2.tasks[clean.id].status is TaskStatus.DONE       # clean ran first
    assert p2.tasks[scarred.id].status is TaskStatus.READY    # scarred deferred
    assert p2.marker_deferrals.get(scarred.id, 0) == 1


def test_canonical_ready_tasks_order_is_unchanged(cfg):
    # the bias is advisory; the canonical deterministic sort is NOT mutated.
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="d", last_cycle=0))
    before = [t.id for t in ready_tasks(p)]
    _boss(cfg, markers)        # constructing the director must not reorder the frontier
    after = [t.id for t in ready_tasks(p)]
    assert before == after


def test_off_path_no_repel(cfg):
    cfg.nervous_enabled = False
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="d", last_cycle=0))
    boss = _boss(cfg, markers)
    boss.store.save(p)
    boss.advance(p.id, autonomous=False)
    # OFF: canonical order dispatches; no deferral tracking
    assert boss.store.load(p.id).marker_deferrals == {}
```

- [ ] **Step 2: Run; expect FAIL** (the scarred task is not deferred — no advisory layer yet).

```
python -m pytest tests/test_gut_markers.py -k "deferred or canonical or off_path" -q
```

- [ ] **Step 3a: Add the `_advisory_batch` helper** to `director.py`:

```python
    # ------------------------------------------------------------- gut markers
    def _advisory_batch(self, project: Project, limit: int) -> list[Task]:
        """Advisory re-rank of the FULL ready frontier by prior-pain repel, WITHOUT
        mutating the canonical (created_at, id) sort. Least-repelled first; the
        front `limit` dispatch, the rest defer (and may escalate). Diagnoses drive
        the model; the weight stays trusted-only."""
        from ..memory.markers import task_signature
        frontier = ready_tasks(project)        # all READY, canonical order
        scored = []
        for i, t in enumerate(frontier):
            repel = sum(m.weight for m in self.markers.recall(task_signature(t)))
            scored.append((repel, i, t))        # repel <= 0; i = canonical tiebreak
        scored.sort(key=lambda x: (-x[0], x[1]))   # least-repelled (repel desc) first
        batch = [t for _, _, t in scored[:limit]]
        deferred = [t for _, _, t in scored[limit:]]
        self._note_deferrals(project, batch, deferred)
        return batch

    def _note_deferrals(self, project: Project, batch, deferred) -> None:
        for t in batch:                          # dispatched -> reset its counter
            project.marker_deferrals.pop(t.id, None)
        for t in deferred:
            n = project.marker_deferrals.get(t.id, 0) + 1
            project.marker_deferrals[t.id] = n
            if (n > self.cfg.marker_defer_escalate_cycles
                    and not self._open_packets(project)):
                self._make_packet(
                    project, trigger="markers:deferred:" + t.id,
                    hint=(f"Task '{t.title}' (role {t.role}) has been deferred "
                          f"{n} cycles by prior-pain markers. Commander decision: "
                          f"persevere, drop, or re-scope."))
                project.marker_deferrals[t.id] = 0      # reset after escalating
```

- [ ] **Step 3b: Use it in `advance()`.** Replace the batch-selection line:

```python
        limit = max_tasks or self.cfg.max_tasks_per_advance
        batch = ready_tasks(project, limit=limit)
```
with:
```python
        limit = max_tasks or self.cfg.max_tasks_per_advance
        if self.cfg.nervous_enabled and self.markers is not None:
            batch = self._advisory_batch(project, limit)
        else:
            batch = ready_tasks(project, limit=limit)
```

- [ ] **Step 4: Run; expect PASS** (3 tests).

```
python -m pytest tests/test_gut_markers.py -k "deferred or canonical or off_path" -q
```

- [ ] **Step 5: Commit.**

```
git -C E:/director2 add director/core/director.py tests/test_gut_markers.py
git -C E:/director2 commit -m "feat(v2): Gut Markers — advisory repel re-rank of the ready frontier + deferral escalation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.2: deferral → packet escalation (no silent starvation)

**Files:**
- Test: `E:/director2/tests/test_gut_markers.py` (append) — the escalation logic ships in Task 3.1's `_note_deferrals`; this task pins it.

- [ ] **Step 1: Append the failing test:**

```python
def test_repeated_deferral_escalates_to_packet(cfg):
    from director.core.types import PacketStatus
    cfg.marker_defer_escalate_cycles = 2
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification", diagnosis="d", last_cycle=0))
    boss = _boss(cfg, markers)
    boss.store.save(p)
    # keep a fresh clean task ready each cycle so the scarred one stays deferred
    for c in range(4):
        pr = boss.store.load(p.id)
        if not [pk for pk in pr.packets.values()
                if pk.status is PacketStatus.PRESENTED]:
            extra = Task(title=f"Clean{c}", role="code", module_id="m1",
                         objective=f"fresh {c}", status=TaskStatus.READY)
            pr.tasks[extra.id] = extra
            boss.store.save(pr)
        boss.advance(p.id, autonomous=False, force=True)
    pr = boss.store.load(p.id)
    assert any(pk.trigger.startswith("markers:deferred:")
               for pk in pr.packets.values())
```

- [ ] **Step 2: Run; expect PASS** (the escalation already exists from Task 3.1 — this is the guard-rail test). If it FAILS, the deferral counter or the `> cfg.marker_defer_escalate_cycles` comparison is off; fix `_note_deferrals` per Task 3.1.

```
python -m pytest tests/test_gut_markers.py -k repeated_deferral -q
```

- [ ] **Step 3: Commit.**

```
git -C E:/director2 add tests/test_gut_markers.py
git -C E:/director2 commit -m "test(v2): repeated marker deferral escalates to a command packet (no silent starvation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: diagnosis injection into the subagent spec

**Files:**
- Modify: `E:/director2/director/core/director.py` (`_spec_for`, append to `parts` before `return AgentSpec(...)`)
- Test: `E:/director2/tests/test_gut_markers.py` (append)

- [ ] **Step 1: Append the failing test:**

```python
def test_spec_injects_prior_pain_diagnosis_not_weight(cfg):
    markers = MarkerStore(cfg)
    p, scarred, clean = _two_ready(cfg)
    markers.record(Marker(signature=task_signature(scarred),
                          cause="failed_verification",
                          diagnosis="add() returned a-b not a+b", last_cycle=0))
    boss = _boss(cfg, markers)
    spec = boss._spec_for(p, scarred)
    assert "add() returned a-b not a+b" in spec.context     # the diagnosis reaches the model
    assert "PRIOR PAIN" in spec.context
    # un-gameable: the numeric weight NEVER reaches the generator
    assert "-0.5" not in spec.context and "weight" not in spec.context.lower()
    # a clean task gets no prior-pain block
    assert "PRIOR PAIN" not in boss._spec_for(p, clean).context
```

- [ ] **Step 2: Run; expect FAIL** (no PRIOR PAIN block yet).

```
python -m pytest tests/test_gut_markers.py -k spec_injects -q
```

- [ ] **Step 3: Inject in `_spec_for`.** In `director.py`'s `_spec_for`, AFTER the artifact/`if omitted:` block and immediately BEFORE `return AgentSpec(`, add:

```python
        if self.cfg.nervous_enabled and self.markers is not None:
            from ..memory.markers import task_signature
            diags = [m.diagnosis for m in self.markers.recall(task_signature(task))
                     if m.diagnosis]
            if diags:
                parts.append("PRIOR PAIN (trusted memory of past failures at this "
                             "kind of task — avoid repeating these): "
                             + "; ".join(diags))
```

(The diagnosis is text only — never the weight/valence. This is the pain-avoidance drive: the model reroutes because it reads a *problem*.)

- [ ] **Step 4: Run; expect PASS.** Then the full suite (OFF-inert).

```
python -m pytest tests/test_gut_markers.py -q
python -m pytest -q
```

- [ ] **Step 5: Commit.**

```
git -C E:/director2 add director/core/director.py tests/test_gut_markers.py
git -C E:/director2 commit -m "feat(v2): Gut Markers — inject prior-pain DIAGNOSES into the subagent spec (un-gameable)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4: Experiment + re-bench + gate

### Task 4.1: bench markers wiring + repeated-failure scenario + scars/recall metrics

**Honest scope (spec §7.2 vs what a deterministic bench can prove).** §7.2 lists three headline metrics: `scars_written`, `markers_recalled`, `reroutes`. The first two are **un-fakeable deterministically** — they measure that the ON arm *writes* a scar and can *recall* it, while the OFF arm has no memory layer at all. The third, `reroutes` ("did avoiding the scarred path save cycles"), is inherently a **reasoning** question: the bench's `ScriptedFaultRunner`/`MockBackend` does not reason, so a deterministic "reroute" count would be theatre. The reroute *mechanism* (a scarred signature deferred behind clean work; the diagnosis injected into the spec) is already pinned deterministically by the unit tests in Tasks 3.1 and 3.3; whether it produces emergent *behavioral* avoidance is owned by the live harness (Task 4.2), exactly where spec §7.1/§10 place it (exploratory, not asserted). So this task implements `scars_written` + `markers_recalled` only — and says so.

**Files:**
- Modify: `E:/director2/director/bench/driver.py` (`_build_director` injects markers in the ON arm; `_run_once` logs `scars_written`/`markers_recalled`; `run_arm`/`compare` carry them)
- Modify: `E:/director2/director/bench/scenarios.py` (a `repeat_fault` scenario)
- Test: `E:/director2/tests/test_bench.py` (append)

- [ ] **Step 1: Append the failing test** to `tests/test_bench.py`:

```python
def test_bench_on_arm_remembers_failures(tmp_path):
    from director.bench.driver import run_arm
    from director.bench.scenarios import get_scenario
    scenario = get_scenario("repeat_fault")
    on = run_arm(scenario, nervous=True, reps=2, home=tmp_path / "on")
    off = run_arm(scenario, nervous=False, reps=2, home=tmp_path / "off")
    # ON writes a scar and can recall it; OFF has no memory layer at all.
    assert on["totals"]["scars_written"] >= 1
    assert on["totals"]["markers_recalled"] >= 1
    assert off["totals"]["scars_written"] == 0
    assert off["totals"]["markers_recalled"] == 0
```

- [ ] **Step 2: Run; expect FAIL** (`KeyError: 'repeat_fault'`, or `KeyError: 'scars_written'` in totals).

```
python -m pytest tests/test_bench.py -k on_arm_remembers -q
```

- [ ] **Step 3a: Inject markers in `_build_director`.** In `director/bench/driver.py`, in `_build_director` (where the `Director(cfg, store, router, registry, runner)` is built), construct and pass a `MarkerStore` when `cfg.nervous_enabled`:

```python
    from ..memory.markers import MarkerStore
    markers = MarkerStore(cfg) if cfg.nervous_enabled else None
    director = Director(cfg, store, router, registry, runner, markers=markers)
```
(read the real `_build_director` and add only the `markers=` kwarg + its construction).

- [ ] **Step 3b: Log the new metrics in `_run_once`.** After the per-cycle loop and the `screams = [...]` line, just BEFORE the `return {` dict, compute both metrics from the final `director`/`project` already in scope:

```python
    markers = getattr(director, "markers", None)
    scars_written = len(markers.index) if markers is not None else 0
    if markers is not None:
        from ..memory.markers import task_signature
        markers_recalled = sum(len(markers.recall(task_signature(t)))
                               for t in project.tasks.values())
    else:
        markers_recalled = 0
```
Then add these two keys to the `_run_once` return dict (alongside `"cycles_run"`, `"outcome"`, etc.):

```python
        "scars_written": scars_written,
        "markers_recalled": markers_recalled,
```
(`VectorStore` supports `len()` — it is used by `LessonLedger`. The OFF arm builds `markers=None` in Step 3a, so both metrics are 0 there with no store ever touched — byte-identical OFF.)

- [ ] **Step 3b-ii: Sum them into `run_arm` totals and surface them in `compare`.** In `run_arm`, add to the `totals = {...}` dict:

```python
        "scars_written": sum(r["scars_written"] for r in runs),
        "markers_recalled": sum(r["markers_recalled"] for r in runs),
```
and in `compare`, extend the `metrics` tuple so the ON-vs-OFF report (the §7.2 re-bench deliverable) shows them:

```python
    metrics = ("screams_fired", "diagnostic_tasks", "cycles_run",
               "final_damage", "scars_written", "markers_recalled")
```
(`compare` reads `totals[m]` and per-run `r[m]`; both arms now carry both keys, so this is safe.)

- [ ] **Step 3c: Add the scenario.** `scenarios.py` already imports `Project`, `Task`, `TaskStatus` (from `..core.types`), `FaultScenario` (from `.faults`), and defines `_SIREN_OVERRIDES` + the `_SCENARIOS` dict — so no new imports are needed. Mirror the existing `_default_seed`/`default` pattern: ONE bad `code` task at `max_attempts=1` so a single scheduled cycle-1 fault fails it **terminally** (→ a `failed_verification` scar at FAILED-ingest), and `_SIREN_OVERRIDES` so the saturated `accumulated_damage` also fires a siren that **strengthens** that same signature's scar (Task 2.2). Add `_repeat_seed` just after `_default_seed`, and register the scenario by assigning into the `_SCENARIOS` dict right after its literal:

```python
def _repeat_seed() -> Project:
    p = Project(name="repeat-fault")
    t = Task(title="flaky-build", role="code", status=TaskStatus.READY,
             max_attempts=1, objective="build the flaky component")
    p.tasks = {t.id: t}
    return p


# ONE signature, scarred at FAILED-ingest then strengthened by the siren. A
# max_attempts=1 task is terminal after cycle 1, so cycles 2-3 are belt-and-
# suspenders (same convention as `default`). True multi-cycle accumulation under
# a HELD latch needs a reasoning model and is the live harness's job (Task 4.2).
_SCENARIOS["repeat_fault"] = lambda: FaultScenario(
    name="repeat_fault", seed_factory=_repeat_seed,
    schedule={("flaky-build", c): f"scripted fault: flaky-build failed at cycle {c}"
              for c in range(1, 4)},
    config_overrides=_SIREN_OVERRIDES)
```

- [ ] **Step 4: Run; expect PASS.** Then the bench suite.

```
python -m pytest tests/test_bench.py -k "on_arm_remembers" -q
python -m pytest tests/test_bench.py -q
```

- [ ] **Step 5: Commit.**

```
git -C E:/director2 add director/bench/driver.py director/bench/scenarios.py tests/test_bench.py
git -C E:/director2 commit -m "feat(v2): bench wires markers in the ON arm + repeat_fault scenario + scars metric

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.2: the escalate-pain live harness (exploratory, manual)

**Files:**
- Create: `E:/director2/director/bench/live_escalate.py` (a documented manual harness, NOT a pytest test)

- [ ] **Step 1:** Create `E:/director2/director/bench/live_escalate.py` — a runnable script that (a) builds a live `claude_cli` Director with `nervous_enabled=True` + a `MarkerStore`, (b) drives a multi-cycle scenario where the same signature fails repeatedly under a held latch, (c) prints, per cycle: scars written, marker weights/counts, the advisory order, and the live model's generation, and (d) records whether the model declines the scarred approach **unbidden**. This is exploratory observation, not an assertion — it mirrors the v1 live harnesses (`d2_live*.py`). Include a module docstring stating it is manual (run with `python -m director.bench.live_escalate`), uses the Max-sub `claude_cli` backend, and that a continued *null* (no unbidden avoidance) is a legitimate, reportable result.

- [ ] **Step 2: Smoke-import it** (do not run the live calls in CI):

```
python -c "import director.bench.live_escalate"
```
Expected: imports clean (no syntax/wiring errors).

- [ ] **Step 3: Commit.**

```
git -C E:/director2 add director/bench/live_escalate.py
git -C E:/director2 commit -m "feat(v2): live escalate-pain harness (manual, claude_cli) — observe unbidden avoidance

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4.3: Phase gate — full suite green + OFF byte-identical

**Files:** none (verification + checkpoint).

- [ ] **Step 1: Run the entire suite.** With `nervous_enabled=False` default, all v1 + v2 tests pass and the pre-existing suite is byte-identical (markers are never constructed/read/written OFF).

```
python -m pytest -q
```

- [ ] **Step 2:** If any pre-existing test changed, a v2 hook leaked past the `nervous_enabled`/`self.markers is not None` guard — fix the guard, do NOT change the test. Re-run.

- [ ] **Step 3: Commit the checkpoint.**

```
git -C E:/director2 commit --allow-empty -m "chore(v2): learning organs complete — Credit Knife + Gut Markers green, OFF byte-identical

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## v2 exit criteria
`director/memory/markers.py` exists with `Marker` + `MarkerStore` (record/recall/merge-and-strengthen, VectorStore-backed); the Credit Knife writes a diagnosis-only scar on terminal FAILED and strengthens it on a siren, with a synthetic recorded origin for plan tasks; the Gut Markers recall by signature, defer scarred work via an advisory re-rank that never mutates the canonical sort (escalating to a packet past N deferrals), and inject the diagnosis (never the weight) into the subagent spec; the bench ON arm writes and recalls scars (OFF has neither) and the live harness exists for the unbidden-avoidance probe; and with `nervous_enabled=False` the entire pre-existing suite is byte-identical. Un-gameability invariant holds throughout: trusted code computes every weight; only diagnoses reach the model.
