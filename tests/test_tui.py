"""Terminal dashboard: pure ANSI renderers (dict -> str) + the `director tui` CLI.
The honesty tiers from the web UI must carry over (VERIFIED vs TRUSTED vs judged),
and tampered reports must shout."""

from director.dashboard.tui import render_overview, render_project


def _digest():
    return {
        "name": "Proj", "status": "active",
        "conviction_read": "Trending Iconoclast",
        "conviction_rank": {"rank": 1, "conviction": "iconoclast",
                            "rank_name": "Follower"},
        "conviction_calibration": "Calibration — iconoclast 50% (1/2)",
        "integrity": {"reports": {"ok": 2}, "violations": 0,
                      "partial_deliverables": 1},
        "summary": {"done": 1, "tasks_total": 3,
                    "tasks_by_status": {"running": 1}, "blocked": 0},
        "ladder": {"verified": 1, "verified_partial": 1, "judged": 1,
                   "none": 0},
        "packets": [{"status": "presented", "title": "Pick a path",
                     "recommendation_key": "a", "options": [
                         {"key": "a", "label": "Conform",
                          "conviction": "dogmatic", "check": "verified",
                          "check_score": 2},
                         {"key": "b", "label": "Exceed",
                          "conviction": "iconoclast", "check": "verified_partial",
                          "sub_claims_verified": 1, "sub_claims_total": 1},
                         {"key": "c", "label": "Reframe",
                          "conviction": "heretic", "check": "judged",
                          "check_score": 1}]}]}


def test_render_project_shows_tiers_and_health():
    out = render_project(_digest(), color=False)
    assert "Proj" in out and "Pick a path" in out
    assert "VERIFIED 2" in out and "TRUSTED 1/1" in out and "judged" in out
    assert "1 trusted deliverable" in out
    assert "evidence:" in out and "1 verified" in out   # ladder readout
    assert "★" in out                       # recommendation marked
    assert "\x1b[" not in out               # no_color is truly plain
    assert "\x1b[" in render_project(_digest(), color=True)


def test_render_project_flags_tamper():
    d = {"name": "P", "status": "active", "summary": {},
         "integrity": {"violations": 2, "reports": {}, "partial_deliverables": 0},
         "packets": []}
    out = render_project(d, color=False)
    assert "TAMPERED" in out and "2" in out


def test_render_overview_lists_projects():
    ov = {"backend": "mock", "current": "abc123",
          "projects": [{"id": "abc123", "status": "active", "name": "Alpha",
                        "open_packets": 2}]}
    out = render_overview(ov, color=False)
    assert "Alpha" in out and "awaits" in out and "▶" in out


def test_tui_cli_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRECTOR_HOME", str(tmp_path / "ws"))
    from click.testing import CliRunner

    from director.cli import main
    from director.config import Config
    from director.core.state import ProjectStore
    from director.dashboard.demo import seed_demo
    cfg = Config.from_env()
    cfg.ensure_dirs()
    pid = seed_demo(ProjectStore(cfg))
    r = CliRunner().invoke(main, ["tui", pid, "--no-color"])
    assert r.exit_code == 0, r.output
    assert "DIRECTOR" in r.output and "Doctrine" in r.output
