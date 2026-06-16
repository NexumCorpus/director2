"""Phase 2 — declared nervous-system config constants. These are recorded
first-guesses (tuned later via the bench), never hardcoded in valence.py."""

from director.config import Config


def test_nervous_disabled_by_default():
    assert Config().nervous_enabled is False


def test_valence_weights_declared_and_sum_to_one():
    w = Config().valence_weights
    assert set(w) == {"charter_integrity", "accumulated_damage",
                      "uncertainty", "resource_bleed"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_thresholds_in_range_and_ordered():
    c = Config()
    assert -1.0 <= c.siren_threshold < c.ache_threshold <= 0.0
    assert c.valence_eps > 0.0
    assert c.hysteresis_margin > 0.0
    assert 0.0 < c.charter_breach_threshold <= 1.0


def test_axis_saturation_declared():
    sat = Config().axis_saturation
    assert sat["accumulated_damage"] == 5.0
    assert sat["charter_integrity"] == 3.0
    assert sat["uncertainty"] == 4.0


def test_budget_absent_by_default():
    assert Config().budget is None


def test_weights_are_per_instance_not_shared():
    a, b = Config(), Config()
    a.valence_weights["uncertainty"] = 0.99
    assert b.valence_weights["uncertainty"] == 0.20
