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
