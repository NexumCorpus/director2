"""Nervous-system v1 declared config constants (defaults + nervous_enabled OFF)."""

from director.config import Config


def test_nervous_enabled_defaults_false():
    # The 133-test suite must stay byte-identical until this is turned ON.
    assert Config().nervous_enabled is False


def test_valence_weights_default_sum_to_one():
    w = Config().valence_weights
    assert w == {
        "charter_integrity": 0.30,
        "accumulated_damage": 0.40,
        "uncertainty": 0.20,
        "resource_bleed": 0.10,
    }
    assert round(sum(w.values()), 6) == 1.0


def test_threshold_and_band_defaults():
    c = Config()
    assert c.ache_threshold == -0.33
    assert c.siren_threshold == -0.66
    assert c.valence_eps == 0.05
    assert c.hysteresis_margin == 0.10
    assert c.charter_breach_threshold == 0.90
    assert c.max_held_cycles == 20


def test_axis_saturation_defaults():
    assert Config().axis_saturation == {
        "accumulated_damage": 5.0,
        "charter_integrity": 3.0,
        "uncertainty": 4.0,
    }


def test_budget_and_director_temperature_default_none():
    c = Config()
    assert c.budget is None
    assert c.director_temperature is None


def test_bench_defaults():
    assert Config().bench == {
        "arms": ["on", "off"],
        "reps": 5,
        "fault_scenario": "default",
        "model_pin": "claude-sonnet-4-6",
        "temperature": 0.0,
    }


def test_nested_defaults_are_independent_instances(cfg):
    # field(default_factory=...) means two Configs must not share mutable state.
    a = Config()
    b = Config()
    a.valence_weights["charter_integrity"] = 0.99
    a.axis_saturation["accumulated_damage"] = 999.0
    a.bench["reps"] = 1
    assert b.valence_weights["charter_integrity"] == 0.30
    assert b.axis_saturation["accumulated_damage"] == 5.0
    assert b.bench["reps"] == 5
    assert cfg.nervous_enabled is False
