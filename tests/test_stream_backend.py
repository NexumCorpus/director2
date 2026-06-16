"""Live-generation-streaming backend + router (Phase 2). All offline:
mock backend + a canned stream-json fixture; no real CLI is ever spawned."""

import json
import subprocess

import pytest

from director.config import Config
from director.llm import claude_cli
from director.llm.base import LLMResponse
from director.llm.claude_cli import ClaudeCliBackend
from director.llm.mock import MockBackend


# ------------------------------------------------ base default stream()
def test_base_stream_default_emits_one_delta_and_returns_response():
    b = MockBackend()
    events = []
    resp = b.stream("SYS", "USER", on_event=events.append, model="",
                    temperature=0.3, max_tokens=64, timeout_s=30, kind="")
    assert isinstance(resp, LLMResponse)
    # exactly one text_delta carrying the whole completion text
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"] == resp.text
    # the non-streaming backend NEVER emits thinking_delta
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_base_stream_returns_identical_text_to_complete():
    b = MockBackend()
    kw = dict(model="", temperature=0.3, max_tokens=64, timeout_s=30,
              kind="initial_plan")
    r_complete = b.complete("SYS", "objective: x", **kw)
    r_stream = b.stream("SYS", "objective: x", on_event=lambda e: None, **kw)
    assert r_stream.text == r_complete.text
    assert r_stream.backend == r_complete.backend == "mock"


# ----------------------------------------- claude_cli stream-json line reader
class _FakeStdout:
    """A line-iterable stdout that also supports read()."""
    def __init__(self, lines):
        self._lines = list(lines)

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return "".join(self._lines)


class _FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        pass


class _FakeStdin:
    def write(self, data):
        pass

    def close(self):
        pass


def _stream_lines(chunks, full=None, in_toks=10, out_toks=5):
    full = full if full is not None else "".join(chunks)
    lines = [json.dumps({"type": "system", "subtype": "init",
                         "session_id": "s1"}) + "\n"]
    for ch in chunks:
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": ch}]}}) + "\n")
    lines.append(json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": full, "session_id": "s1", "total_cost_usd": 0, "num_turns": 1,
        "usage": {"input_tokens": in_toks, "output_tokens": out_toks,
                  "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}}) + "\n")
    return lines


def test_claude_stream_emits_delta_per_chunk_and_concats(monkeypatch):
    chunks = ['{"charter":', ' {"objective":', ' "x"}}']
    proc = _FakeProc(_stream_lines(chunks))
    monkeypatch.setattr(claude_cli.subprocess, "Popen", lambda *a, **k: proc)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("SYS", "USER", on_event=events.append, model="",
                    temperature=0.3, max_tokens=64, timeout_s=60, kind="")
    deltas = [e["text"] for e in events if e.get("type") == "text_delta"]
    assert deltas == chunks                     # one text_delta per assistant chunk
    assert resp.text == "".join(chunks)         # final == concatenation
    assert resp.backend == "claude_cli"
    assert resp.prompt_tokens == 10 and resp.completion_tokens == 5
    # NEVER reasoning on the subscription CLI
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_claude_stream_uses_stream_json_argv(monkeypatch):
    seen = {}

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        return _FakeProc(_stream_lines(["ok"]))

    monkeypatch.setattr(claude_cli.subprocess, "Popen", fake_popen)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    b.stream("S", "U", on_event=lambda e: None, model="", temperature=0,
             max_tokens=64, timeout_s=60, kind="")
    argv = seen["argv"]
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert argv[argv.index("--max-turns") + 1] == "1"
    assert argv[argv.index("--tools") + 1] == ""


def test_claude_stream_tolerates_garbage_lines(monkeypatch):
    lines = ["not json\n"] + _stream_lines(["A", "B"])
    monkeypatch.setattr(claude_cli.subprocess, "Popen",
                        lambda *a, **k: _FakeProc(lines))
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("S", "U", on_event=events.append, model="", temperature=0,
                    max_tokens=64, timeout_s=60, kind="")
    assert resp.text == "AB"
    assert [e["text"] for e in events if e.get("type") == "text_delta"] == ["A", "B"]


def test_claude_stream_falls_back_to_complete_on_launch_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(claude_cli.subprocess, "Popen", boom)
    # complete() path is exercised via subprocess.run -> mock it to a real reply
    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(
            argv, 0,
            stdout=json.dumps({"type": "result", "subtype": "success",
                               "is_error": False, "result": "FALLBACK",
                               "usage": {"input_tokens": 1, "output_tokens": 1}}),
            stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("S", "U", on_event=events.append, model="", temperature=0,
                    max_tokens=64, timeout_s=60, kind="")
    # the verified result is authoritative even when the stream can't be established
    assert resp.text == "FALLBACK"
    # the base-default-style single delta is emitted from the fallback text
    assert [e["text"] for e in events if e.get("type") == "text_delta"] == ["FALLBACK"]


# ---------------------------------------------------- router stream_structured
from director.core.director import PlanOut  # noqa: E402
from director.llm.router import LLMRouter  # noqa: E402


def _router_mock():
    return LLMRouter(Config(), backends={"mock": MockBackend()})


def test_stream_structured_mock_emits_one_delta_and_matches_structured():
    r = _router_mock()
    events = []
    a = r.stream_structured("SYS", "objective: build x", PlanOut,
                            on_event=events.append, role="director",
                            kind="initial_plan")
    b = r.structured("SYS", "objective: build x", PlanOut, role="director",
                     kind="initial_plan")
    # identical validated schema (same fixture) — only the side-channel differs
    assert a.model_dump() == b.model_dump()
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert len(deltas) == 1 and deltas[0]["text"]   # mock -> one whole-result delta
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_stream_structured_none_sink_routes_to_structured():
    r = _router_mock()
    out = r.stream_structured("SYS", "objective: y", PlanOut, on_event=None,
                              role="director", kind="initial_plan")
    ref = r.structured("SYS", "objective: y", PlanOut, role="director",
                       kind="initial_plan")
    assert out.model_dump() == ref.model_dump()


def test_stream_structured_returns_validated_schema_type():
    r = _router_mock()
    out = r.stream_structured("SYS", "objective: z", PlanOut,
                              on_event=lambda e: None, role="director",
                              kind="initial_plan")
    assert isinstance(out, PlanOut) and out.tasks
