"""Fast-lane model routing: low-stakes kinds (command_packet, …) take a faster
model when configured, while deliverables + verification keep the primary model.
A rejected fast model degrades gracefully to the default (never breaks a run).
Profiling a live arc showed command_packet was ~26% of wall-clock."""

from director.config import FAST_KINDS, Config
from director.llm.base import LLMResponse
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter


def test_fast_kinds_set():
    assert "command_packet" in FAST_KINDS
    # deliverable/verification kinds must NEVER be downgraded — nor the kinds
    # that must be CLEVER (the adversary) to do their job
    for k in ("agent_code", "agent_test", "agent_synthesis", "initial_plan",
              "agent_research", "agent_review", "adversary_attack",
              "synthesizer_decide"):
        assert k not in FAST_KINDS


def test_router_routes_fast_kinds_to_fast_model(cfg):
    seen = {}

    class Spy(MockBackend):
        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            seen[kind] = model
            return LLMResponse(text="{}", model=model, backend="mock")

    cfg.fast_model = "fast-haiku"
    r = LLMRouter(cfg, backends={"mock": Spy()})
    r.complete("s", "u", role="director", kind="command_packet")
    r.complete("s", "u", role="builder", kind="agent_code")
    assert seen["command_packet"] == "fast-haiku"      # low-stakes -> fast lane
    assert seen["agent_code"] != "fast-haiku"          # deliverable -> primary


def test_no_fast_model_means_no_routing(cfg):
    seen = {}

    class Spy(MockBackend):
        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            seen[kind] = model
            return LLMResponse(text="{}", model=model, backend="mock")

    cfg.fast_model = ""        # no fast lane configured
    r = LLMRouter(cfg, backends={"mock": Spy()})
    r.complete("s", "u", role="director", kind="command_packet")
    assert seen["command_packet"] != "fast-haiku"      # unchanged default behavior


def test_claude_cli_model_rejection_detector():
    from director.llm.claude_cli import ClaudeCliBackend
    f = ClaudeCliBackend._is_model_rejection
    assert f("API Error: 400 model not found")
    assert f("invalid model: haiku")
    assert not f("401 Invalid authentication credentials")   # auth, not model
    assert not f("claude CLI timed out after 360s")          # transient


def test_claude_cli_falls_back_on_rejected_model(monkeypatch):
    from director.llm import claude_cli as cc

    class FakeProc:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        model = argv[argv.index("--model") + 1] if "--model" in argv else ""
        if model and model != "sonnet":          # the fast model is rejected
            return FakeProc(1, '{"is_error":true,"result":'
                               '"API Error 400 model not found"}')
        return FakeProc(0, '{"result":"OK","usage":{"output_tokens":1}}')

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    b = cc.ClaudeCliBackend()
    resp = b.complete("sys", "user", model="fast-x", temperature=0.0,
                      max_tokens=2000, timeout_s=45)
    assert resp.text == "OK"                      # degraded to default, succeeded
    assert "fast-x" in b._rejected_models         # cached the rejection
    assert len(calls) == 2                        # tried fast, then default
    # a second call with the same rejected model skips straight to default
    calls.clear()
    b.complete("sys", "user", model="fast-x", temperature=0.0,
               max_tokens=2000, timeout_s=45)
    assert len(calls) == 1                         # no wasted probe second time
