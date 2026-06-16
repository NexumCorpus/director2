"""Phase 2 — fragile-axis labeling: knife-edge composites/axes are LABELED, never
silently rounded up into a halt (RDE v11 lesson). Trusted, model-free."""

from director.config import Config
from director.core.types import Risk, RiskLevel, Task, TaskStatus, Project
from director.core.valence import _fragile_axes, compute_body


def _proj():
    return Project(name="p")


def test_no_fragile_axes_when_composite_far_from_thresholds():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(), perf=None,
                        since=None, cfg=cfg)
    assert body.fragile_axes == []


def test_composite_within_eps_of_ache_is_fragile():
    cfg = Config()
    sev = {"accumulated_damage": 0.30}
    fragile = _fragile_axes(valence=-0.30, severities=sev, cfg=cfg)
    assert "composite" in fragile


def test_axis_at_saturation_edge_is_fragile():
    cfg = Config()
    sev = {"accumulated_damage": 0.97, "uncertainty": 0.0}
    fragile = _fragile_axes(valence=-0.50, severities=sev, cfg=cfg)
    assert "accumulated_damage" in fragile


def test_fragile_axes_populated_in_compute_body_and_provenance():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="t", status=TaskStatus.FAILED) for _ in range(5)]}
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert "accumulated_damage" in body.fragile_axes
    assert "risk_ids" in body.provenance
    assert "run_ids" in body.provenance
    assert body.provenance["integrity_violations"] == 0
    assert body.provenance["violation_ids"] == []
