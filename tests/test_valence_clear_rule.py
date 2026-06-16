"""Phase 3 — per-cause clear-rule re-verification. The latch clears ONLY when
trusted Python re-verifies the declared per-cause condition, never on packet
answer/defer and never on an LLM assertion."""

import pytest

from director.config import Config
from director.core.types import (Project, Risk, RiskLevel, RiskStatus, Task,
                                  TaskStatus)
from director.core.valence import check_clear_rule
from director.evolve.metrics import PerfLedger


@pytest.fixture()
def cfg(tmp_path) -> Config:
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


@pytest.fixture()
def perf(cfg) -> PerfLedger:
    return PerfLedger(cfg)


def _latch(cause, axis="charter_integrity", refs=None):
    return {"cause": cause, "axis": axis, "opened_at": 1, "held_cycles": 1,
            "clear_rule": "x", "origin_refs": refs or []}


def test_tamper_clears_when_no_violations(cfg, perf):
    p = Project(name="t")
    secret = cfg.report_secret()
    latch = _latch("tamper")
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True


def test_tamper_stays_held_while_violation_present(cfg, perf, monkeypatch):
    p = Project(name="t")
    secret = cfg.report_secret()
    import director.core.valence as val
    monkeypatch.setattr(val, "_integrity_violation_count",
                        lambda project, secret: 1)
    assert check_clear_rule(p, _latch("tamper"), secret=secret, perf=perf,
                            since=None, cfg=cfg) is False


def test_charter_breach_clears_only_below_hysteresis_band(cfg, perf, monkeypatch):
    p = Project(name="cb")
    secret = cfg.report_secret()
    import director.core.valence as val
    monkeypatch.setattr(val, "_charter_integrity_severity",
                        lambda project, secret, perf, since, cfg: 0.85)
    assert check_clear_rule(p, _latch("charter_breach"), secret=secret,
                            perf=perf, since=None, cfg=cfg) is False
    monkeypatch.setattr(val, "_charter_integrity_severity",
                        lambda project, secret, perf, since, cfg: 0.70)
    assert check_clear_rule(p, _latch("charter_breach"), secret=secret,
                            perf=perf, since=None, cfg=cfg) is True


def test_grounding_damage_needs_risk_closed(cfg, perf):
    """A real grounding risk in origin_refs: the latch is HELD while the risk is
    OPEN and clears (no monkeypatch) once it is CLOSED. Directly re-verified
    against project.risks — the un-clearable deliverable re-pass is gone."""
    p = Project(name="gd")
    secret = cfg.report_secret()
    rk = Risk(title="code_runs failed", level=RiskLevel.HIGH,
              status=RiskStatus.OPEN, source="grounding")
    p.risks[rk.id] = rk
    latch = _latch("grounding_damage", axis="accumulated_damage",
                   refs=[rk.id])

    # held while the risk is OPEN
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
    # clears once the risk is CLOSED
    rk.status = RiskStatus.CLOSED
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True
    # ACCEPTED also counts as resolved
    rk.status = RiskStatus.ACCEPTED
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True
    # re-opening re-holds the latch
    rk.status = RiskStatus.OPEN
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False


def test_grounding_damage_failed_task_refs_clear_when_recovered(cfg, perf):
    p = Project(name="gd-failed")
    secret = cfg.report_secret()
    failed = [Task(title=f"t{i}", status=TaskStatus.FAILED) for i in range(5)]
    for t in failed:
        p.tasks[t.id] = t
    latch = {"cause": "grounding_damage", "axis": "accumulated_damage",
             "opened_at": 1, "held_cycles": 1, "clear_rule": "x",
             "origin_refs": [t.id for t in failed],
             "opened_severity": 1.0}
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
    for t in failed:
        t.status = TaskStatus.DONE
    assert check_clear_rule(p, latch, secret=secret, perf=perf,
                            since=None, cfg=cfg) is True


def test_unknown_cause_does_not_clear(cfg, perf):
    p = Project(name="u")
    secret = cfg.report_secret()
    assert check_clear_rule(p, _latch("mystery"), secret=secret, perf=perf,
                            since=None, cfg=cfg) is False
