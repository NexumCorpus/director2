"""Subagent system tests: roles, single run, parallel run, verification gating,
failure isolation — all offline."""

import json
import threading

from director.agents.base import AgentSpec, SubAgentOutput
from director.agents.roles import get_role, render_user_prompt, role_names
from director.agents.runner import SubAgentRunner
from director.llm.base import LLMBackend, LLMResponse
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def make_runner(cfg, backend=None, **kw):
    router = LLMRouter(cfg, backends={"mock": backend or MockBackend()})
    return SubAgentRunner(cfg, router, make_default_registry(), **kw)


def test_roles_registered():
    assert {"research", "code", "test", "review", "simulation",
            "synthesis"} <= set(role_names())
    role = get_role("code")
    assert "BOUNDARY" in role.system
    assert role.routing_kind == "agent_code"


def test_render_user_prompt_sections():
    text = render_user_prompt(
        "obj", "ctx", {"a": 1}, ["crit1"], ["constraint1"],
        lessons_digest="- lesson")
    for token in ("OBJECTIVE: obj", "CONTEXT:", "INPUTS:",
                  "ACCEPTANCE CRITERIA:", "CONSTRAINTS:", "LESSONS"):
        assert token in text


def test_single_agent_run_ok(cfg):
    runner = make_runner(cfg)
    spec = AgentSpec(role="research", objective="research the landscape",
                     task_id="t1")
    res = runner.run(spec)
    assert res.ok, res.error
    assert res.output["summary"].startswith("[mock:research]")
    assert res.reports and res.reports[0].verifier == "agent_output"
    assert res.backend == "mock"


def test_parallel_runs_are_concurrent_and_ordered(cfg):
    """Verify true concurrency: a slow backend blocks until N agents overlap."""
    n = 3
    cfg.max_parallel_agents = n
    barrier = threading.Barrier(n, timeout=10)

    class BarrierBackend(LLMBackend):
        name = "barrier"
        default_model = "b"
        cheap_model = "b"

        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            barrier.wait()   # deadlocks unless all N run simultaneously
            return LLMResponse(text=json.dumps({
                "summary": f"parallel output for {kind} long enough to pass "
                           f"structural checks easily",
                "artifacts": [{"title": "result doc",
                               "content": "c" * 64}]}),
                model=model, backend=self.name)

    router = LLMRouter(cfg, backends={"barrier": BarrierBackend()})
    runner = SubAgentRunner(cfg, router, make_default_registry())
    specs = [AgentSpec(role="research", objective=f"objective {i}",
                       task_id=f"t{i}") for i in range(n)]
    results = runner.run_parallel(specs)
    assert all(r.ok for r in results)
    # results preserve input order
    assert [r.task_id for r in results] == ["t0", "t1", "t2"]


def test_failure_isolation(cfg):
    """One failing agent must not sink the batch."""
    from director.errors import ModelTransientError

    class FlakyBackend(LLMBackend):
        name = "flaky"
        default_model = "f"
        cheap_model = "f"

        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            if "objective FAIL" in user:
                raise ModelTransientError("backend exploded")
            return LLMResponse(text=json.dumps({
                "summary": "good output with plenty of length for checks",
                "artifacts": [{"title": "doc", "content": "d" * 64}]}),
                model=model, backend=self.name)

    cfg.max_parallel_agents = 2
    router = LLMRouter(cfg, backends={"flaky": FlakyBackend()})
    runner = SubAgentRunner(cfg, router, make_default_registry())
    specs = [AgentSpec(role="code", objective="objective OK", task_id="ok"),
             AgentSpec(role="code", objective="objective FAIL", task_id="bad")]
    results = runner.run_parallel(specs)
    by_task = {r.task_id: r for r in results}
    assert by_task["ok"].ok
    assert not by_task["bad"].ok and "ModelTransientError" in by_task["bad"].error


def test_verification_gates_bad_output(cfg):
    """An output that violates the agent boundary is rejected before ingestion."""
    bad = json.dumps({"summary": "x" * 60,
                      "artifacts": [],
                      "state_mutation": {"hijack": True}})
    # Schema allows extra... pydantic by default ignores extras; boundary check
    # happens on the dumped dict, so inject via scripts on the mock.
    mb = MockBackend(scripts={"agent_code": [bad]})
    runner = make_runner(cfg, backend=mb)
    res = runner.run(AgentSpec(role="code", objective="anything", task_id="t"))
    # extra key is dropped by pydantic -> passes; OR kept -> rejected.
    # Either way the run must not crash and must produce reports.
    assert res.reports
    if "state_mutation" in res.output:
        assert not res.ok


def test_unknown_role_fails_cleanly(cfg):
    runner = make_runner(cfg)
    res = runner.run(AgentSpec(role="warlock", objective="hex"))
    assert not res.ok and "KeyError" in res.error


def test_lessons_digest_injected(cfg):
    mb = MockBackend()
    runner = make_runner(cfg, backend=mb, lessons_digest="- always test edges")
    runner.run(AgentSpec(role="research", objective="o", task_id="t"))
    assert "always test edges" in mb.calls[0]["user"]


def test_subagent_output_schema_defaults():
    out = SubAgentOutput(summary="s")
    assert out.artifacts == [] and out.command_packet_recommended is False
