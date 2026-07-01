"""Integration: the v3 self-model + homeostat are wired into the LIVE loop.

Uses the bench harness (mock backend, scripted faults) to drive a project into
pain and asserts (1) the Interoceptive Self-Model is populated each cycle from the
real trusted Body, (2) the Homeostat would grade that state, and (3) the OFF path
leaves the self-model at its default (byte-identical).
"""
from __future__ import annotations

from director.bench.driver import _build_director
from director.bench.scenarios import get_scenario
from director.config import Config
from director.core.homeostat import compute_posture


def _build(home, nervous):
    cfg = Config(home=home)
    cfg.ensure_dirs()
    cfg.nervous_enabled = nervous
    cfg.auto_advance_after_decision = False
    scenario = get_scenario("default")
    if nervous:
        for k, v in scenario.config_overrides.items():
            setattr(cfg, k, v)
    project = scenario.seed_factory()
    director, store, runner = _build_director(cfg, scenario, project)
    store.save(project)
    director._run_since = None
    return cfg, project, director, store, runner


def _drive(director, store, runner, project_id, cycles=4):
    for i in range(cycles):
        runner.cycle_seq = i + 1
        res = director.advance(project_id, autonomous=True)
        if res.get("status") in ("latched", "awaiting_command"):
            break
    return store.load(project_id)


def test_self_model_populated_by_live_loop(tmp_path):
    cfg, project, director, store, runner = _build(tmp_path / "on", nervous=True)
    project = _drive(director, store, runner, project.id)
    ss = project.self_state
    assert project.valence_history                  # trajectory accrued from real Body
    assert ss.valence <= 0.0
    assert ss.updated_at >= 1                        # the loop updated it
    if ss.duration_cycles > 0:                       # an episode opened
        assert "cycle" in ss.narrative               # higher-order self-description
    # the Homeostat grades this self-state consistently (never MORE than default)
    posture = compute_posture(ss, cfg=cfg)
    assert posture.throughput <= cfg.max_tasks_per_advance
    if ss.valence <= cfg.siren_threshold:
        assert posture.throughput == 0               # latch endpoint


def test_off_loop_leaves_self_model_at_default(tmp_path):
    cfg, project, director, store, runner = _build(tmp_path / "off", nervous=False)
    project = _drive(director, store, runner, project.id, cycles=3)
    # OFF never runs _nervous_pass -> the self-model stays default, history empty
    assert project.valence_history == []
    assert project.self_state.duration_cycles == 0
    assert project.self_state.updated_at == 0


def test_recovery_drive_promotes_review_under_pain(tmp_path):
    from director.core.types import Task, TaskStatus
    from director.core.selfstate import SelfState
    cfg, project, director, store, runner = _build(tmp_path / "rec", nervous=True)
    code = Task(title="feature", role="code", status=TaskStatus.READY)
    review = Task(title="diagnose", role="review", status=TaskStatus.READY)
    project.tasks = {code.id: code, review.id: review}
    # pain engages the recovery drive (recovery_pressure >> threshold)
    project.self_state = SelfState(valence=-0.5, duration_cycles=3)
    batch = director._advisory_batch(project, limit=1)
    assert batch and batch[0].role == "review"      # healing work front-loaded


def test_advisory_batch_calm_matches_canonical_order(tmp_path):
    from director.core.types import Task, TaskStatus
    from director.core.selfstate import SelfState
    from director.core.taskgraph import ready_tasks
    cfg, project, director, store, runner = _build(tmp_path / "calm", nervous=True)
    a = Task(title="a", role="code", status=TaskStatus.READY)
    b = Task(title="b", role="review", status=TaskStatus.READY)
    project.tasks = {a.id: a, b.id: b}
    project.self_state = SelfState(valence=0.0)      # calm -> recovery_pressure 0 -> inert
    batch = director._advisory_batch(project, limit=5)
    canonical = ready_tasks(project, limit=5)
    assert [t.id for t in batch] == [t.id for t in canonical]   # no reorder when calm
