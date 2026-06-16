"""Claude Code CLI backend: argv/env contract, JSON parsing, failure modes.
All subprocess calls are mocked — the suite never spawns a real CLI."""

import json
import subprocess

import pytest

from director.config import Config
from director.errors import ModelProviderError, ModelTransientError
from director.llm import claude_cli
from director.llm.claude_cli import ClaudeCliBackend


def _ok_payload(result="hello", in_toks=10, out_toks=5):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": result, "session_id": "s1", "total_cost_usd": 0,
        "num_turns": 1,
        "usage": {"input_tokens": in_toks, "output_tokens": out_toks,
                  "cache_read_input_tokens": 2,
                  "cache_creation_input_tokens": 1}})


@pytest.fixture()
def capture(monkeypatch):
    """Mock subprocess.run, capturing argv/env/input."""
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env")
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(
            argv, seen.get("rc", 0),
            stdout=seen.get("stdout", _ok_payload()), stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    return seen


def test_complete_contract(capture, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-passes-through")
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    resp = b.complete("SYSTEM", "USER PROMPT", model="", temperature=0.3,
                      max_tokens=4096, timeout_s=120)
    assert resp.text == "hello" and resp.backend == "claude_cli"
    assert resp.prompt_tokens == 13 and resp.completion_tokens == 5
    assert resp.meta["total_cost_usd"] == 0
    # prompt over stdin, system over flag, single turn, no --model when ""
    assert capture["input"] == "USER PROMPT"
    argv = capture["argv"]
    assert "--system-prompt" in argv
    assert argv[argv.index("--system-prompt") + 1] == "SYSTEM"
    # all built-in tools disabled -> pure text oracle, single turn
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--max-turns") + 1] == "1"
    # factory defaults: no user/project settings (live finding: the child
    # inherited the user's output style and wrote docs instead of JSON)
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--no-session-persistence" in argv
    assert "--model" not in argv
    # the key and harness markers can never leak into the child ->
    # subscription auth like a fresh terminal, never the parent session
    assert "ANTHROPIC_API_KEY" not in capture["env"]
    assert "CLAUDECODE" not in capture["env"]
    assert "CLAUDE_CODE_ENTRYPOINT" not in capture["env"]
    # output cap floored at 32k: the CLI hard-fails calls exceeding it
    assert capture["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "32000"
    # the one deliberate exception: setup-token subscription credential
    assert capture["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "oat-passes-through"


def test_model_flag_and_cmd_shim(capture):
    b = ClaudeCliBackend(exe=r"C:\fake\claude.cmd")
    b.complete("s", "u", model="haiku", temperature=0, max_tokens=1024,
               timeout_s=60)
    argv = capture["argv"]
    assert argv[:2] == ["cmd", "/c"]          # .cmd needs the shell shim
    assert argv[argv.index("--model") + 1] == "haiku"


def test_failure_modes(capture):
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    capture["rc"] = 1
    capture["stdout"] = "boom"
    with pytest.raises(ModelProviderError, match="exit 1"):
        b.complete("s", "u", model="", temperature=0, max_tokens=64,
                   timeout_s=60)
    capture["rc"] = 0
    capture["stdout"] = json.dumps({"is_error": True, "result": "nope"})
    with pytest.raises(ModelProviderError, match="error result"):
        b.complete("s", "u", model="", temperature=0, max_tokens=64,
                   timeout_s=60)
    capture["stdout"] = json.dumps({"subtype": "error_max_turns",
                                    "result": ""})
    with pytest.raises(ModelTransientError, match="empty result"):
        b.complete("s", "u", model="", temperature=0, max_tokens=64,
                   timeout_s=60)


def test_plain_text_fallback(capture):
    capture["stdout"] = "not json at all"
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    resp = b.complete("s", "u", model="", temperature=0, max_tokens=64,
                      timeout_s=60)
    assert resp.text == "not json at all"


def _auth_401_payload():
    # shape the real CLI emits on a subscription auth failure (rc!=0, JSON on
    # stdout carrying api_error_status 401)
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": True,
        "api_error_status": 401,
        "result": "Failed to authenticate. API Error: 401 Invalid "
                  "authentication credentials", "session_id": "s401"})


def test_auth_blip_retries_then_recovers(monkeypatch):
    """A transient 401 is retried in-process and recovers — the call SUCCEEDS
    instead of failing. This is what should have happened during the live arc."""
    calls = {"n": 0}

    def fake_run(argv, **kw):
        calls["n"] += 1
        # 401 on the first attempt, real reply on the retry
        out = _auth_401_payload() if calls["n"] == 1 else _ok_payload("RECOVERED")
        return subprocess.CompletedProcess(
            argv, 1 if calls["n"] == 1 else 0, stdout=out, stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_cli.time, "sleep", lambda *_: None)   # no real wait
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    resp = b.complete("s", "u", model="", temperature=0, max_tokens=64,
                      timeout_s=60)
    assert resp.text == "RECOVERED"
    assert calls["n"] == 2                       # blip on #1, success on retry #2


def test_persistent_auth_is_transient_not_dead(monkeypatch):
    """A 401 that never clears raises ModelTransientError (which the router
    RECORDS but never quarantines), NOT ModelProviderError (a 'dead backend').
    A single auth hiccup must not be able to kill the only backend for a run."""
    calls = {"n": 0}

    def fake_run(argv, **kw):
        calls["n"] += 1
        return subprocess.CompletedProcess(argv, 1, stdout=_auth_401_payload(),
                                           stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_cli.time, "sleep", lambda *_: None)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    with pytest.raises(ModelTransientError, match="transient 401"):
        b.complete("s", "u", model="", temperature=0, max_tokens=64,
                   timeout_s=60)
    assert calls["n"] == claude_cli._AUTH_RETRIES + 1   # tried, then gave up


def test_auth_error_detector():
    f = ClaudeCliBackend._is_auth_error
    assert f("API Error: 401 Invalid authentication credentials")
    assert f("401 Unauthorized")
    assert f("Failed to authenticate")
    assert not f("400 model not found")          # model rejection, not auth
    assert not f("claude CLI timed out after 360s")


def test_explicit_only_selection(monkeypatch):
    # never autodetected: keyless config still resolves to mock
    assert Config(backend="").detect_backend() == "mock"
    # explicit selection wins
    assert Config(backend="claude_cli").detect_backend() == "claude_cli"
    # missing binary is a loud config-time error, not a silent fallback
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: None)
    with pytest.raises(ModelProviderError, match="not found"):
        ClaudeCliBackend()
