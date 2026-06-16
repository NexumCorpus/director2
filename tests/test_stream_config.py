"""Live-generation-streaming: config gate + workflow patch (Phase 1).
All offline; no backend is ever reached."""

import os

from director.config import Config


# ---------------------------------------------------------------- the gate
def test_stream_generation_defaults_false():
    # OFF byte-identical: the gate must default False so no streaming code runs
    assert Config().stream_generation is False


def test_stream_generation_env_truthy(monkeypatch):
    monkeypatch.setenv("DIRECTOR_STREAM_GENERATION", "1")
    assert Config.from_env().stream_generation is True


def test_stream_generation_env_falsey(monkeypatch):
    monkeypatch.setenv("DIRECTOR_STREAM_GENERATION", "0")
    assert Config.from_env().stream_generation is False


def test_stream_generation_env_absent_is_false(monkeypatch):
    monkeypatch.delenv("DIRECTOR_STREAM_GENERATION", raising=False)
    assert Config.from_env().stream_generation is False
