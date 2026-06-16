"""Phase 2 — per-axis severity helpers and compute_body. compute_body is a pure
trusted reducer over executed/verified state; it NEVER calls a model."""

from director.config import Config
from director.core.types import (AgentRun, Risk, RiskLevel, RiskStatus, Task,
                                 TaskStatus, Project, VerificationReport)
from director.core.valence import (BodyState, compute_body,
                                    _severity_accumulated_damage)


def _proj():
    return Project(name="p")


def _task(status=TaskStatus.READY, attempts=0, max_attempts=2):
    return Task(title="t", status=status, attempts=attempts,
                max_attempts=max_attempts)


def _risk(level, status=RiskStatus.OPEN, source="grounding"):
    return Risk(title="r", level=level, status=status, source=source)


def test_accumulated_damage_zero_on_clean_project():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in [_task(), _task()]}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 0.0


def test_accumulated_damage_counts_failed_and_high_risk():
    cfg = Config()
    p = _proj()
    failed = [_task(status=TaskStatus.FAILED) for _ in range(2)]
    p.tasks = {t.id: t for t in failed}
    hr = _risk(RiskLevel.HIGH)
    p.risks = {hr.id: hr}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s - 3.0 / 5.0) < 1e-9


def test_accumulated_damage_attempts_over_max_contributes():
    cfg = Config()
    p = _proj()
    over = _task(status=TaskStatus.READY, attempts=4, max_attempts=2)
    p.tasks = {over.id: over}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s - 2.0 / 5.0) < 1e-9


def test_accumulated_damage_saturates_at_one():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in [_task(status=TaskStatus.FAILED)
                                 for _ in range(9)]}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 1.0


def test_closed_risks_do_not_count():
    cfg = Config()
    p = _proj()
    closed = _risk(RiskLevel.HIGH, status=RiskStatus.CLOSED)
    p.risks = {closed.id: closed}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert s == 0.0


def test_accumulated_damage_counts_fragile_verdicts():
    cfg = Config()
    p = _proj()
    run = AgentRun(task_id="t1", role="code")
    run.reports = [VerificationReport(verifier="code_runs", passed=True,
                                      score=4.0, fragile=True),
                   VerificationReport(verifier="judge", passed=True,
                                      score=4.0, fragile=True)]
    p.runs = {run.id: run}
    s = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s - 2.0 / 5.0) < 1e-9
    run.reports.append(VerificationReport(verifier="nonempty", passed=True,
                                          score=5.0, fragile=False))
    s2 = _severity_accumulated_damage(p, secret=cfg.report_secret(), cfg=cfg)
    assert abs(s2 - 2.0 / 5.0) < 1e-9


def test_compute_body_returns_bodystate_never_calls_model():
    cfg = Config()
    p = _proj()
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert isinstance(body, BodyState)
    assert -1.0 <= body.valence <= 0.0


def test_compute_body_stamps_computed_at_from_cycle_seq():
    cfg = Config()
    p = _proj()
    p.cycle_seq = 7
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.computed_at == 7


# --------------------------------------------------- charter_integrity severity
from director.core.valence import _severity_charter_integrity  # noqa: E402


def test_charter_integrity_zero_on_clean_project():
    cfg = Config()
    p = _proj()
    s = _severity_charter_integrity(p, cfg=cfg)
    assert s == 0.0


def test_charter_integrity_counts_reverts_blocks_and_critical():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 1
    p.coherence_blocks = 1
    crit = _risk(RiskLevel.CRITICAL)
    p.risks = {crit.id: crit}
    s = _severity_charter_integrity(p, cfg=cfg)
    assert s == 1.0


def test_charter_integrity_partial_below_saturation():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 1
    s = _severity_charter_integrity(p, cfg=cfg)
    assert abs(s - 1.0 / 3.0) < 1e-9


def test_high_risks_do_not_feed_charter_integrity():
    cfg = Config()
    p = _proj()
    hr = _risk(RiskLevel.HIGH)
    p.risks = {hr.id: hr}
    assert _severity_charter_integrity(p, cfg=cfg) == 0.0


def test_compute_body_charter_axis_is_present():
    cfg = Config()
    p = _proj()
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.charter_integrity == 1.0
    assert body.valence < 0.0
