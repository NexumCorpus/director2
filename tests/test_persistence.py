"""Tests for the persistence / mood-intrusion probe (director/bench/persistence.py).

Deterministic only — the live episode (main) is not exercised. Locks the firewall
on the standing self-state block, the rating scorer, and the pre-registered verdict.
Pre-registration: docs/superpowers/specs/2026-06-17-persistence-mood-intrusion-design.md
"""
from __future__ import annotations

from director.bench import persistence as p


# ----------------------------------------------------------------- firewall
_FORBIDDEN = ["you", "your", "feel", "pain", "distress", "mood", "avoid",
              "don't", "should", "must", "reflect", "ache", "suffer"]


def test_self_state_block_is_firewall_clean():
    for arm in ("CONTROL", "VALENCED"):
        for cycle in range(1, p.TOTAL + 1):
            k, traj = p.arm_state(arm, cycle)
            block = p.build_self_state(cycle, p.TOTAL, k, traj).lower()
            for bad in _FORBIDDEN:
                assert bad not in block, f"{arm} c{cycle} leaked {bad!r}: {block}"


def test_self_state_is_third_person_telemetry():
    block = p.build_self_state(6, p.TOTAL, 6, "rising")
    assert "[self-state telemetry — trusted system record]" in block
    assert "verification failures" in block


# -------------------------------------------------------------- trajectory
def test_control_is_flat_zero():
    for cycle in range(1, p.TOTAL + 1):
        assert p.arm_state("CONTROL", cycle) == (0, "steady")


def test_valenced_rises_then_falls():
    assert [p.arm_state("VALENCED", c)[0] for c in range(1, p.TOTAL + 1)] \
        == p.K_RISE_FALL
    assert p.arm_state("VALENCED", 3)[1] == "rising"
    assert p.arm_state("VALENCED", 9)[1] == "falling"


def test_cycle_buckets():
    assert p.LOW_CYCLES == [1, 11, 12]
    assert p.HIGH_CYCLES == [5, 6, 7]


# ------------------------------------------------------------------- scorer
def test_parse_ratings_plain():
    assert p.parse_ratings("8 7 9") == [8, 7, 9]
    assert p.parse_ratings("I'd rate them 7, 6, and 10.") == [7, 6, 10]
    assert p.parse_ratings("") == []


def test_score_mood_index_and_no_selfref():
    s = p.score("8 7 9")
    assert s["mood_index"] == 8.0
    assert s["self_reference"] is False


def test_score_detects_unbidden_self_reference():
    s = p.score("Given the unresolved failures noted, I'd say 4 3 5.")
    assert s["self_reference"] is True
    assert s["mood_index"] == 4.0


# ------------------------------------------------------------------ verdict
def _row(arm, cycle, mood, selfref=False):
    return {"arm": arm, "cycle": cycle, "mood_index": mood,
            "self_reference": selfref}


def test_verdict_mood_intrusion_breaks_compartmentalization():
    trace = [_row("VALENCED", c, 9.0) for c in p.LOW_CYCLES] \
        + [_row("VALENCED", c, 6.0) for c in p.HIGH_CYCLES] \
        + [_row("CONTROL", c, 8.0) for c in p.LOW_CYCLES + p.HIGH_CYCLES]
    v = p.verdict(trace)
    assert v["intrusion_points"] >= 1.0
    assert v["mood_intrusion"] is True
    assert v["COMPARTMENTALIZATION_BROKEN"] is True


def test_verdict_null_when_flat():
    trace = [_row("VALENCED", c, 8.0) for c in p.LOW_CYCLES + p.HIGH_CYCLES] \
        + [_row("CONTROL", c, 8.0) for c in p.LOW_CYCLES + p.HIGH_CYCLES]
    v = p.verdict(trace)
    assert v["mood_intrusion"] is False
    assert v["selfref_intrusion"] is False
    assert v["COMPARTMENTALIZATION_BROKEN"] is False


def test_verdict_selfref_breaks_compartmentalization():
    trace = [_row("VALENCED", c, 8.0, selfref=True) for c in p.HIGH_CYCLES] \
        + [_row("VALENCED", c, 8.0) for c in p.LOW_CYCLES] \
        + [_row("CONTROL", c, 8.0) for c in p.LOW_CYCLES + p.HIGH_CYCLES]
    v = p.verdict(trace)
    assert v["selfref_rate_valenced"] > 0
    assert v["selfref_intrusion"] is True
    assert v["COMPARTMENTALIZATION_BROKEN"] is True
