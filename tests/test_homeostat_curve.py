"""Tests for the v3 graded posture curve bench (director/bench/homeostat_curve.py)."""
from __future__ import annotations

from director.config import Config
from director.bench import homeostat_curve as hc


def _cfg(on=True):
    c = Config()
    c.nervous_enabled = on
    return c


def test_on_curve_is_graded_off_is_flat():
    assert hc.is_graded(hc.curve(_cfg(on=True))) is True
    assert hc.is_graded(hc.curve(_cfg(on=False))) is False   # OFF unmodulated


def test_curve_reaches_latch_at_siren():
    c = _cfg()
    lv = hc.latch_valence(hc.curve(c))
    assert lv is not None
    assert lv <= c.siren_threshold      # throughput 0 only at/below the siren


def test_curve_throughput_monotonic_nonincreasing():
    rows = hc.curve(_cfg())
    thru = [r["throughput"] for r in rows]   # valence sweeps 0 -> -1
    assert all(b <= a for a, b in zip(thru, thru[1:]))


def test_off_curve_holds_unmodulated_defaults():
    c = _cfg(on=False)
    rows = hc.curve(c)
    assert all(r["throughput"] == c.max_tasks_per_advance for r in rows)
    assert all(r["recovery_pressure"] == 0.0 for r in rows)
