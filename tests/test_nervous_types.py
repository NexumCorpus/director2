"""Nervous-system v1 data model: BodyState + new Project fields round-trip."""

from director.core.types import (
    BodyState, Project, decode, encode,
)


def test_bodystate_defaults_resolve_insufficient_str_arm():
    # The float|str union fields default to the "insufficient" STR arm, not None.
    b = BodyState()
    assert b.charter_integrity == "insufficient"
    assert b.resource_bleed == "insufficient"
    assert b.valence == 0.0
    assert b.accumulated_damage == 0.0
    assert b.uncertainty == 0.0
    assert b.fragile_axes == []
    assert b.computed_at == 0
    assert b.provenance == {}


def test_project_new_fields_default_inert():
    p = Project(name="alpha")
    assert p.body is None
    assert p.scream_open is None
    assert p.cycle_seq == 0
    assert p.milestone_reverts == 0
    assert p.coherence_blocks == 0


def test_bodystate_roundtrip_with_insufficient_str_arm():
    p = Project(name="alpha")
    p.body = BodyState(
        charter_integrity="insufficient",
        accumulated_damage=0.4,
        uncertainty=0.2,
        resource_bleed="insufficient",
        valence=-0.37,
        fragile_axes=["uncertainty"],
        computed_at=3,
        provenance={"risk_ids": ["r1"], "run_ids": ["x9"]},
    )
    p.scream_open = {
        "cause": "charter_breach",
        "axis": "charter_integrity",
        "opened_at": 3,
        "held_cycles": 1,
        "clear_rule": "charter_integrity recovers below threshold",
        "origin_refs": ["r1"],
    }
    p.cycle_seq = 3
    p.milestone_reverts = 2
    p.coherence_blocks = 1

    data = encode(p)
    p2 = decode(Project, data)

    assert isinstance(p2.body, BodyState)
    assert p2.body.charter_integrity == "insufficient"
    assert p2.body.resource_bleed == "insufficient"
    assert p2.body.charter_integrity is not None
    assert p2.body.resource_bleed is not None
    assert p2.body.accumulated_damage == 0.4
    assert p2.body.uncertainty == 0.2
    assert p2.body.valence == -0.37
    assert p2.body.fragile_axes == ["uncertainty"]
    assert p2.body.computed_at == 3
    assert p2.body.provenance == {"risk_ids": ["r1"], "run_ids": ["x9"]}
    assert p2.scream_open == p.scream_open
    assert p2.cycle_seq == 3
    assert p2.milestone_reverts == 2
    assert p2.coherence_blocks == 1
    assert encode(p2) == data


def test_bodystate_numeric_severity_arm_roundtrip():
    p = Project(name="beta")
    p.body = BodyState(charter_integrity=1.0, resource_bleed=0.5, valence=-0.66)
    data = encode(p)
    p2 = decode(Project, data)
    assert p2.body.charter_integrity == 1.0
    assert p2.body.resource_bleed == 0.5
    assert p2.body.valence == -0.66


def test_partial_old_snapshot_decodes_without_body_or_scream():
    p = Project(name="legacy")
    data = encode(p)
    for k in ("body", "scream_open", "cycle_seq",
              "milestone_reverts", "coherence_blocks"):
        data.pop(k, None)
    p2 = decode(Project, data)
    assert p2.body is None
    assert p2.scream_open is None
    assert p2.cycle_seq == 0
    assert p2.milestone_reverts == 0
    assert p2.coherence_blocks == 0
