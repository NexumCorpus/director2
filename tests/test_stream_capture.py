"""raw_generation capture + persistence + round-trip (Phase 2). Offline mock."""

from director.agents.base import AgentResult
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import AgentRun, decode, encode
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def test_agentresult_has_raw_generation_field():
    r = AgentResult(spec_id="s")
    assert r.raw_generation == ""


def test_agentrun_raw_generation_round_trips():
    run = AgentRun(task_id="t", role="code", raw_generation='{"summary":"hi"}')
    back = decode(AgentRun, encode(run))
    assert back.raw_generation == '{"summary":"hi"}'


def test_runner_captures_raw_generation(cfg):
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    from director.agents.base import AgentSpec
    res = runner.run(AgentSpec(role="research", objective="survey x",
                               task_id="t1"))
    assert res.ok
    # the raw model text is captured, not discarded — and it's the actual reply
    assert res.raw_generation
    assert "summary" in res.raw_generation


def test_record_run_persists_raw_generation(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    director = Director(cfg, store, router, registry, runner)
    project, _ = director.new_project("cap", "ship a verified toy")
    director.advance(project.id, force=True)
    reloaded = store.load(project.id)
    runs = list(reloaded.runs.values())
    assert runs and any(r.raw_generation for r in runs)
