"""Tests for the v3 Homeostat (director/core/homeostat.py).

compute_posture: OFF/calm = unmodulated defaults; monotonic in valence; the latch
(throughput 0 at <= siren) is the continuum endpoint; floors respected.
"""
from __future__ import annotations

from types import SimpleNamespace

from director.config import Config
from director.core.selfstate import SelfState
from director.core.homeostat import compute_posture, recovery_score


def _cfg(on=True):
    c = Config()
    c.nervous_enabled = on
    return c


def test_off_returns_unmodulated_defaults():
    c = _cfg(on=False)
    p = compute_posture(SelfState(valence=-0.9), cfg=c)   # deep pain, but OFF
    assert p.throughput == c.max_tasks_per_advance
    assert p.persistence == c.default_max_attempts
    assert p.recovery_pressure == 0.0
    assert p.caution == 1.0


def test_calm_on_equals_defaults():
    c = _cfg()
    p = compute_posture(SelfState(valence=0.0), cfg=c)
    assert p.throughput == c.max_tasks_per_advance
    assert p.persistence == c.default_max_attempts
    assert p.recovery_pressure == 0.0


def test_latch_endpoint_throughput_zero():
    c = _cfg()
    p = compute_posture(SelfState(valence=-0.7), cfg=c)   # below siren -0.66
    assert p.throughput == 0
    assert p.recovery_pressure == 1.0


def test_monotonic_in_valence():
    c = _cfg()
    ps = [compute_posture(SelfState(valence=v), cfg=c)
          for v in (0.0, -0.1, -0.2, -0.33, -0.5, -0.66, -0.8)]
    for a, b in zip(ps, ps[1:]):
        assert b.throughput <= a.throughput
        assert b.persistence <= a.persistence
        assert b.recovery_pressure >= a.recovery_pressure
        assert b.caution >= a.caution


def test_floors_respected_just_above_latch():
    c = _cfg()
    p = compute_posture(SelfState(valence=-0.65), cfg=c)   # heavy pain, not latched
    assert p.throughput >= c.posture_throughput_floor
    assert p.persistence >= c.posture_persistence_floor


def test_recovery_pressure_ramps_zero_to_one():
    c = _cfg()
    assert compute_posture(SelfState(valence=0.0), cfg=c).recovery_pressure == 0.0
    assert compute_posture(SelfState(valence=-0.66), cfg=c).recovery_pressure == 1.0


def test_recovery_score_promotes_review_role_only():
    assert recovery_score(SimpleNamespace(role="review")) == 1.0
    assert recovery_score(SimpleNamespace(role="code")) == 0.0
    assert recovery_score(SimpleNamespace(role="")) == 0.0
