"""Tests for the v3 Interoceptive Self-Model (director/core/selfstate.py).

Pure reducer; un-gameable. Locks episode lifecycle, trajectory, the measured
(not claimed) recovery tally, and the no-raw-valence narrative.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from director.config import Config
from director.core.selfstate import SelfState, update_self_state


def _cfg():
    c = Config()
    c.nervous_enabled = True
    return c


def _body(v):
    return SimpleNamespace(valence=v)


def test_calm_closes_episode_and_resets():
    prior = SelfState(valence=-0.5, duration_cycles=5, peak_valence=-0.6,
                      recovery_attempts=3, recovery_resolved=1)
    s = update_self_state(prior, _body(0.0), cfg=_cfg(), cycle_seq=10)
    assert s.duration_cycles == 0
    assert s.peak_valence == 0.0
    assert s.recovery_attempts == 0
    assert s.recovery_resolved == 0
    assert "Calm" in s.narrative


def test_episode_opens_on_pain():
    s = update_self_state(SelfState(valence=0.0, duration_cycles=0),
                          _body(-0.4), cfg=_cfg(), axis="accumulated_damage")
    assert s.duration_cycles == 1
    assert s.trajectory == "worsening"
    assert s.peak_valence == -0.4


def test_episode_accumulates_and_tracks_peak():
    prior = SelfState(valence=-0.4, duration_cycles=3, peak_valence=-0.4)
    s = update_self_state(prior, _body(-0.55), cfg=_cfg())
    assert s.duration_cycles == 4
    assert s.peak_valence == -0.55
    assert s.trajectory == "worsening"


def test_trajectory_improving_within_pain_band():
    prior = SelfState(valence=-0.6, duration_cycles=3, peak_valence=-0.6)
    s = update_self_state(prior, _body(-0.45), cfg=_cfg())
    assert s.trajectory == "improving"
    assert s.peak_valence == -0.6   # peak holds the worst, even as it improves


def test_recovery_resolved_counts_only_real_improvement():
    prior = SelfState(valence=-0.6, duration_cycles=3, recovery_resolved=0)
    improved = update_self_state(prior, _body(-0.45), cfg=_cfg(),
                                 recovery_attempts_delta=1)
    assert improved.recovery_attempts == 1
    assert improved.recovery_resolved == 1
    worse = update_self_state(prior, _body(-0.66), cfg=_cfg(),
                              recovery_attempts_delta=1)
    assert worse.recovery_attempts == 1
    assert worse.recovery_resolved == 0   # no real improvement => not counted


def test_narrative_is_qualitative_no_raw_valence():
    s = update_self_state(
        SelfState(valence=-0.5, duration_cycles=2, peak_valence=-0.5),
        _body(-0.6), cfg=_cfg(), axis="accumulated_damage")
    assert "cycle" in s.narrative
    assert re.search(r"-?\d+\.\d+", s.narrative) is None   # no raw valence floats
