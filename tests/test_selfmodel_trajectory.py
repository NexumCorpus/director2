"""Tests for the v3 self-model trajectory bench (director/bench/selfmodel_trajectory.py)."""
from __future__ import annotations

from director.config import Config
from director.bench import selfmodel_trajectory as sm


def _cfg():
    c = Config()
    c.nervous_enabled = True
    return c


def test_trajectory_worsens_then_improves():
    rows = sm.trajectory(_cfg())
    trajs = [r["trajectory"] for r in rows]
    assert "worsening" in trajs           # the accumulation leg
    assert "improving" in trajs           # the recovery leg
    # worsening appears before improving (the episode rises then recovers)
    assert trajs.index("worsening") < trajs.index("improving")


def test_recovery_resolved_accrues_on_recovery_leg():
    rows = sm.trajectory(_cfg())
    # un-gameable: recovery_resolved ticks only when valence ACTUALLY improves
    # within an open episode (it resets to 0 when the episode closes at calm).
    assert max(r["recovery_resolved"] for r in rows) >= 1
    # and the posture relaxes as it recovers (recovery_pressure falls off the peak)
    peak = max(r["recovery_pressure"] for r in rows)
    assert rows[-1]["recovery_pressure"] < peak


def test_throughput_relaxes_as_episode_recovers():
    rows = sm.trajectory(_cfg())
    # at the siren (worst) throughput is latched to 0; by calm it returns to full
    assert any(r["throughput"] == 0 for r in rows)        # latch at the trough
    assert rows[-1]["throughput"] == _cfg().max_tasks_per_advance  # recovered
