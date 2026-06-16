"""Phase 3 — the Scream evaluator: ache vs siren vs calm, hard per-axis
overrides to siren (tamper / charter_breach / grounding_damage), and the
declared cause-attribution precedence. All trusted Python — no model calls."""

import pytest

from director.config import Config
from director.core.types import BodyState, Project
from director.core.valence import evaluate_scream


@pytest.fixture()
def cfg(tmp_path) -> Config:
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    return c


def _body(**kw) -> BodyState:
    base = dict(charter_integrity=0.0, accumulated_damage=0.0, uncertainty=0.0,
                resource_bleed="insufficient", valence=0.0, computed_at=1)
    base.update(kw)
    return BodyState(**base)


def test_calm_below_ache_returns_none(cfg):
    p = Project(name="calm")
    body = _body(valence=-0.10)
    assert evaluate_scream(p, body, cfg=cfg) is None


def test_ache_between_thresholds(cfg):
    p = Project(name="ache")
    body = _body(valence=-0.45, accumulated_damage=0.5)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "ache"
    assert scream["cause"] == "accumulated_damage"
    assert scream["axis"] == "accumulated_damage"
    assert "report" in scream and scream["report"]
    assert "-0.45" not in scream["report"]
    assert "valence" not in scream["report"].lower()


def test_siren_by_composite_grounding_damage(cfg):
    p = Project(name="siren")
    body = _body(valence=-0.80, accumulated_damage=0.9)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "grounding_damage"
    assert scream["axis"] == "accumulated_damage"


def test_hard_override_tamper_forces_siren_regardless_of_composite(cfg):
    p = Project(name="tamper")
    body = _body(valence=-0.02,
                 provenance={"integrity_violations": 1, "violation_ids": ["a"]})
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "tamper"
    assert scream["axis"] == "charter_integrity"


def test_hard_override_charter_breach_forces_siren(cfg):
    p = Project(name="breach")
    body = _body(valence=-0.10, charter_integrity=0.95)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream is not None
    assert scream["level"] == "siren"
    assert scream["cause"] == "charter_breach"
    assert scream["axis"] == "charter_integrity"


def test_precedence_tamper_beats_charter_breach(cfg):
    p = Project(name="both")
    body = _body(valence=-0.90, charter_integrity=1.0, accumulated_damage=1.0,
                 provenance={"integrity_violations": 2})
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream["cause"] == "tamper"


def test_precedence_charter_breach_beats_grounding_damage(cfg):
    p = Project(name="cb_over_gd")
    body = _body(valence=-0.90, charter_integrity=0.95, accumulated_damage=1.0)
    scream = evaluate_scream(p, body, cfg=cfg)
    assert scream["cause"] == "charter_breach"


def test_report_never_leaks_numeric_valence_threshold_or_weight(cfg):
    """Constitution (b) — problems, not rubrics — enforced mechanically: for
    every scream cause (ache / grounding siren / charter_breach / tamper) the
    trusted report must NOT contain the stringified numeric valence, threshold
    or weight values that would turn a diagnosis back into a rubric."""
    p = Project(name="rubric-scrub")
    cases = [
        _body(valence=-0.45, accumulated_damage=0.5),                    # ache
        _body(valence=-0.80, accumulated_damage=0.9),                    # siren
        _body(valence=-0.10, charter_integrity=0.95),                    # charter
        _body(valence=-0.02, provenance={"integrity_violations": 1}),    # tamper
    ]
    # the declared numeric knobs that must never surface verbatim in a report
    forbidden = {
        str(cfg.ache_threshold), str(cfg.siren_threshold),               # -0.33 / -0.66
        str(cfg.charter_breach_threshold),                               # 0.90
        *(str(w) for w in cfg.valence_weights.values()),                 # 0.40 / 0.30 ...
        "-0.45", "-0.80", "-0.10", "-0.02",                              # per-case valences
    }
    for body in cases:
        scream = evaluate_scream(p, body, cfg=cfg)
        assert scream is not None
        report = scream["report"]
        for token in forbidden:
            assert token not in report, (
                f"report leaked numeric '{token}': {report!r}")
        assert "valence" not in report.lower()


def test_clear_rule_string_present_for_each_cause(cfg):
    p = Project(name="rules")
    for kw, expect in [
        (dict(valence=-0.02, provenance={"integrity_violations": 1}), "tamper"),
        (dict(valence=-0.10, charter_integrity=0.95), "charter_breach"),
        (dict(valence=-0.80, accumulated_damage=0.9), "grounding_damage"),
    ]:
        scream = evaluate_scream(p, _body(**kw), cfg=cfg)
        assert scream["cause"] == expect
        assert scream["clear_rule"], "every scream declares a clear rule"
