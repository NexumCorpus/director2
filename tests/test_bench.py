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


# OVERLAY: a single failed task drives only the accumulated_damage axis; with
# resource_bleed abstaining the three present axes renormalize so a saturated
# accumulated_damage yields composite ~-0.444 — an ACHE, not a SIREN. To make
# the ON arm cross the siren threshold (and set the scream_open latch that
# screams_fired counts) we declare per-scenario config_overrides: saturate
# accumulated_damage at 1.0 (one failed task -> severity 1.0) and lower the
# siren/ache thresholds so -0.444 <= siren_threshold. These overrides are inert
# on the OFF arm (it never runs the valence pass). The bad task gets
# max_attempts=1 so a single cycle-1 fault fails it TERMINALLY (default is 2,
# so without this it would retry and might never reach FAILED in the window).
_SIREN_OVERRIDES = {
    "axis_saturation": {"accumulated_damage": 1.0, "charter_integrity": 3.0,
                        "uncertainty": 4.0},
    "siren_threshold": -0.40,
    "ache_threshold": -0.20,
}


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
        t_bad = Task(title="build-bad", role="code", status=TaskStatus.READY,
                     max_attempts=1)
        p.tasks = {t_ok.id: t_ok, t_bad.id: t_bad}
        return p

    scenario = FaultScenario(name="s", seed_factory=seed,
                             schedule={("build-bad", 1): "boom",
                                       ("build-bad", 2): "boom"},
                             config_overrides=_SIREN_OVERRIDES)
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
