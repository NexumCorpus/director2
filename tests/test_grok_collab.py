"""Collaboration primitives (mocked transports — no live model calls)."""
from __future__ import annotations

import director.llm.grok_collab as gc
from director.llm.grok_channel import Turn


class _FakeGrok:
    """Stand-in GrokChannel: records sends, returns scripted Turns."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def send(self, msg, *, timeout=300.0):
        self.sent.append(msg)
        return self.replies.pop(0)


class _FakeBackend:
    def __init__(self, texts):
        self.texts = list(texts)
        self.prompts = []

    def complete(self, system, user, *, model, temperature, max_tokens,
                 timeout_s, kind=""):
        self.prompts.append(user)
        class _R:
            text = self.texts.pop(0)
        return _R()


def test_adversarial_check_frames_a_refutation(monkeypatch):
    captured = {}

    class _Chan:
        def __init__(self, name, system=""):
            captured["system"] = system
        def send(self, prompt, *, timeout=300.0):
            captured["prompt"] = prompt
            return Turn(role="grok", content="objection: X", ts=0.0, ok=True)
    monkeypatch.setattr(gc, "GrokChannel", _Chan)
    out = gc.adversarial_check("My design is sound", context="ctx")
    assert out.content == "objection: X"
    assert "REFUTE" in captured["prompt"]
    assert "My design is sound" in captured["prompt"] and "ctx" in captured["prompt"]
    assert "Grok" in captured["system"]              # peer persona applied


def test_cross_lab_debate_runs_n_rounds_in_order():
    backend = _FakeBackend(["claude-1", "claude-2"])
    grok = _FakeGrok([Turn("grok", "grok-1", 0.0, ok=True),
                      Turn("grok", "grok-2", 0.0, ok=True)])
    tr = gc.cross_lab_debate("the topic", rounds=2, backend=backend, grok=grok)
    assert [t.speaker for t in tr] == ["Claude", "Grok", "Claude", "Grok"]
    assert [t.text for t in tr] == ["claude-1", "grok-1", "claude-2", "grok-2"]
    # round 2's claude prompt must thread round 1 (full history to the stateless side)
    assert "claude-1" in backend.prompts[1] and "grok-1" in backend.prompts[1]
    # grok only receives Claude's latest turn (native session holds the rest)
    assert grok.sent == ["claude-1", "claude-2"]


def test_debate_stops_on_grok_error():
    backend = _FakeBackend(["claude-1", "claude-2"])
    grok = _FakeGrok([Turn("grok", "", 0.0, ok=False, error="down")])
    tr = gc.cross_lab_debate("t", rounds=3, backend=backend, grok=grok)
    assert [t.speaker for t in tr] == ["Claude", "Grok"]
    assert tr[-1].ok is False and "down" in tr[-1].text


def test_debate_stops_on_claude_error():
    class _Boom(_FakeBackend):
        def complete(self, *a, **k):
            raise RuntimeError("claude down")
    grok = _FakeGrok([Turn("grok", "g", 0.0, ok=True)])
    tr = gc.cross_lab_debate("t", rounds=2, backend=_Boom([]), grok=grok)
    assert len(tr) == 1 and tr[0].speaker == "Claude" and tr[0].ok is False
