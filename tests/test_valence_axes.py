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


# --------------------------------------------------------- uncertainty severity
from director.core.types import (CheckKind, CommandOption, CommandPacket,  # noqa: E402
                                 PacketStatus)
from director.core.valence import _severity_uncertainty  # noqa: E402


def test_uncertainty_zero_on_clean_project():
    cfg = Config()
    assert _severity_uncertainty(_proj(), cfg=cfg) == 0.0


def test_uncertainty_counts_needs_verify():
    cfg = Config()
    p = _proj()
    nv = [_task(status=TaskStatus.NEEDS_VERIFY) for _ in range(2)]
    p.tasks = {t.id: t for t in nv}
    s = _severity_uncertainty(p, cfg=cfg)
    assert abs(s - 2.0 / 4.0) < 1e-9


def test_uncertainty_counts_judged_options_in_open_packets():
    cfg = Config()
    p = _proj()
    pkt = CommandPacket(title="t", status=PacketStatus.PRESENTED, options=[
        CommandOption(key="A", label="A", conviction="dogmatic",
                      check=CheckKind.JUDGED),
        CommandOption(key="B", label="B", conviction="iconoclast",
                      check=CheckKind.JUDGED)])
    p.packets = {pkt.id: pkt}
    s = _severity_uncertainty(p, cfg=cfg)
    assert abs(s - 2.0 / 4.0) < 1e-9


def test_uncertainty_ignores_answered_packets():
    cfg = Config()
    p = _proj()
    pkt = CommandPacket(title="t", status=PacketStatus.ANSWERED, options=[
        CommandOption(key="A", label="A", conviction="dogmatic",
                      check=CheckKind.JUDGED)])
    p.packets = {pkt.id: pkt}
    assert _severity_uncertainty(p, cfg=cfg) == 0.0


def test_uncertainty_saturates():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [_task(status=TaskStatus.NEEDS_VERIFY) for _ in range(9)]}
    assert _severity_uncertainty(p, cfg=cfg) == 1.0


# ----------------------------------------------- resource_bleed + abstention
from director.core.valence import _severity_resource_bleed, _composite  # noqa: E402


class _FakePerf:
    """Minimal duck-type of PerfLedger: only stats(since=...) is read."""
    def __init__(self, prompt_tokens, completion_tokens):
        self._p, self._c = prompt_tokens, completion_tokens

    def stats(self, *, since=None):
        return {"calls": 1, "prompt_tokens": self._p,
                "completion_tokens": self._c}


def test_resource_bleed_abstains_with_no_budget():
    cfg = Config()
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(10, 10), since=None,
                                 cfg=cfg)
    assert s == "insufficient"


def test_resource_bleed_severity_against_token_budget():
    cfg = Config()
    cfg.budget = {"max_tokens": 1000}
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(400, 200), since=None,
                                 cfg=cfg)
    assert abs(s - 0.6) < 1e-9


def test_resource_bleed_saturates_at_budget():
    cfg = Config()
    cfg.budget = {"max_tokens": 100}
    s = _severity_resource_bleed(_proj(), perf=_FakePerf(500, 0), since=None,
                                 cfg=cfg)
    assert s == 1.0


def test_resource_bleed_abstains_when_perf_is_none():
    cfg = Config()
    cfg.budget = {"max_tokens": 1000}
    s = _severity_resource_bleed(_proj(), perf=None, since=None, cfg=cfg)
    assert s == "insufficient"


def test_composite_renormalizes_when_one_axis_abstains():
    cfg = Config()
    sev = {"accumulated_damage": 1.0, "uncertainty": 0.0,
           "charter_integrity": 0.0}
    v = _composite(sev, cfg)
    assert abs(v - (-0.40 / 0.90)) < 1e-6


def test_composite_with_all_axes_present_uses_raw_weights():
    cfg = Config()
    sev = {"accumulated_damage": 1.0, "uncertainty": 0.0,
           "charter_integrity": 0.0, "resource_bleed": 0.0}
    v = _composite(sev, cfg)
    assert abs(v - (-0.40)) < 1e-9


def test_compute_body_reports_insufficient_bleed_by_default():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(),
                        perf=_FakePerf(50, 50), since=None, cfg=cfg)
    assert body.resource_bleed == "insufficient"
