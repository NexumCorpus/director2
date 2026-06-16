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


# ------------------------------------------------------- --backend selection
def test_config_backend_makes_detect_return_it():
    # the robust live-selection path: a config-level backend wins, even with a
    # blanked env (claude_cli stays explicit-only; never autodetected)
    assert Config(backend="claude_cli").detect_backend() == "claude_cli"
    assert Config(backend="").detect_backend() == "mock"


def test_cli_new_accepts_backend_flag():
    # the `new` command exposes --backend so a live run is selectable directly
    from click.testing import CliRunner

    from director.cli import main
    res = CliRunner().invoke(main, ["new", "--help"])
    assert res.exit_code == 0
    assert "--backend" in res.output


def test_cli_dashboard_accepts_backend_flag():
    from click.testing import CliRunner

    from director.cli import main
    res = CliRunner().invoke(main, ["dashboard", "--help"])
    assert res.exit_code == 0
    assert "--backend" in res.output
