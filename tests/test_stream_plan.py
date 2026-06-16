"""Plan-surface streaming (Phase 3). Offline mock; gate-on vs gate-off."""

from director.agents.runner import SubAgentRunner
from director.core.director import Director, PlanOut
from director.core.state import ProjectStore
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def _director(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner), store


def test_plan_streams_when_gated_on_with_sink(cfg):
    cfg.stream_generation = True
    director, _ = _director(cfg)
    events = []
    plan = director._plan("build a verified toy", on_event=events.append)
    assert isinstance(plan, PlanOut) and plan.tasks
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert deltas and deltas[0]["text"]            # generation streamed
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_plan_does_not_stream_when_gate_off(cfg):
    cfg.stream_generation = False                  # default
    director, _ = _director(cfg)
    events = []
    plan = director._plan("build a verified toy", on_event=events.append)
    assert isinstance(plan, PlanOut) and plan.tasks
    assert events == []                            # OFF byte-identical: no deltas


def test_plan_no_sink_is_unchanged(cfg):
    cfg.stream_generation = True
    director, _ = _director(cfg)
    plan = director._plan("build a verified toy")  # no on_event
    assert isinstance(plan, PlanOut) and plan.tasks


def test_new_project_threads_sink_when_gated(cfg):
    cfg.stream_generation = True
    director, store = _director(cfg)
    events = []
    project, packet = director.new_project("streamed", "ship verified x",
                                           on_event=events.append)
    assert project.tasks and packet
    assert any(e.get("type") == "text_delta" for e in events)


def test_new_project_no_sink_default_call_still_works(cfg):
    director, store = _director(cfg)
    project, packet = director.new_project("plain", "ship verified x")
    assert project.tasks and packet


def test_off_path_uses_structured_not_stream(cfg, monkeypatch):
    # OFF byte-identical, proven by interception: with the gate off, _plan must
    # call router.structured and must NOT call router.stream_structured
    cfg.stream_generation = False
    director, _ = _director(cfg)
    calls = {"structured": 0, "stream": 0}
    real_structured = director.router.structured

    def spy_structured(*a, **k):
        calls["structured"] += 1
        return real_structured(*a, **k)

    def spy_stream(*a, **k):
        calls["stream"] += 1
        raise AssertionError("stream_structured must not run when gate is OFF")

    monkeypatch.setattr(director.router, "structured", spy_structured)
    monkeypatch.setattr(director.router, "stream_structured", spy_stream)
    plan = director._plan("ship x", on_event=lambda e: None)
    assert plan.tasks
    assert calls["structured"] == 1 and calls["stream"] == 0
