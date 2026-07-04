"""Robustness logic for the GrokChannel harness (mocked transport — no live calls)."""
from __future__ import annotations

import pytest

from director.llm.grok_channel import GrokChannel, GrokError, Turn


def _chan(tmp_path, **kw):
    return GrokChannel("t", root=tmp_path, system="SYS", **kw)


def test_send_records_both_turns_and_captures_session(tmp_path):
    c = _chan(tmp_path)
    c._invoke = lambda prompt, **k: {"text": "hi back", "sessionId": "S1",
                                     "requestId": "R1", "stopReason": "EndTurn",
                                     "thought": "thinking"}
    turn = c.send("hello")
    assert turn.ok and turn.content == "hi back" and turn.session_id == "S1"
    hist = c.history()
    assert [t.role for t in hist] == ["claude", "grok"]
    assert hist[0].content == "hello"
    assert c.state.session_id == "S1" and c.state.turns == 1


def test_second_send_uses_resume_not_system(tmp_path):
    c = _chan(tmp_path)
    seen = []

    def fake(prompt, *, resume_id, set_system, timeout):
        seen.append((resume_id, set_system))
        return {"text": "ok", "sessionId": "S1", "requestId": "", "stopReason": "",
                "thought": ""}
    c._invoke = fake
    c.send("first")          # establishes session: resume_id "", set_system True
    c.send("second")         # resumes: resume_id "S1", set_system False
    assert seen[0] == ("", True)
    assert seen[1] == ("S1", False)


def test_retry_on_transient_then_success(tmp_path):
    c = _chan(tmp_path)
    calls = {"n": 0}

    def flaky(prompt, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GrokError("blip", transient=True)
        return {"text": "recovered", "sessionId": "S", "requestId": "",
                "stopReason": "", "thought": ""}
    c._invoke = flaky
    import director.llm.grok_channel as mod
    mod.time.sleep = lambda *_: None        # no real backoff in tests
    turn = c.send("hi", retries=2)
    assert turn.ok and turn.content == "recovered" and calls["n"] == 2


def test_fidelity_records_failure_never_fabricates(tmp_path):
    c = _chan(tmp_path)
    c._invoke = lambda prompt, **k: (_ for _ in ()).throw(
        GrokError("down", transient=True))
    import director.llm.grok_channel as mod
    mod.time.sleep = lambda *_: None
    turn = c.send("hi", retries=1)
    assert turn.ok is False and turn.content == "" and "down" in turn.error
    # the JSONL holds the outgoing msg + a FAILED grok turn, but NO fake reply
    hist = c.history()
    assert hist[-1].role == "grok" and hist[-1].ok is False


def test_native_resume_failure_falls_back_to_rethread(tmp_path):
    c = _chan(tmp_path)
    c.state.session_id = "STALE"            # pretend we had a session
    attempts = []

    def fake(prompt, *, resume_id, set_system, timeout):
        attempts.append(resume_id)
        if resume_id == "STALE":
            raise GrokError("session gone", transient=False)
        return {"text": "fresh", "sessionId": "S2", "requestId": "",
                "stopReason": "", "thought": ""}
    c._invoke = fake
    turn = c.send("continue please")
    # first tried STALE resume, then fell back to a fresh session ("")
    assert attempts == ["STALE", ""]
    assert turn.ok and turn.content == "fresh" and c.state.session_id == "S2"


def test_render_and_history_roundtrip(tmp_path):
    c = _chan(tmp_path)
    c._invoke = lambda prompt, **k: {"text": "reply-X", "sessionId": "S",
                                     "requestId": "", "stopReason": "", "thought": ""}
    c.send("ask-Y")
    md = c.render()
    assert "## Claude\nask-Y" in md and "reply-X" in md
    assert len(c.history()) == 2
