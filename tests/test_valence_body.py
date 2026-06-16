"""Phase 2 — the Body (trusted valence pass): BodyState type, Project carrier
fields, and the pure compute_body reducer. All offline; no model is ever called."""

import dataclasses

from director.core.types import (Artifact, BodyState, Project, Risk, RiskLevel,
                                 RiskStatus, Task, TaskStatus, decode, encode)


def test_bodystate_all_fields_defaulted():
    bs = BodyState()
    assert bs.charter_integrity == "insufficient"
    assert bs.accumulated_damage == 0.0
    assert bs.uncertainty == 0.0
    assert bs.resource_bleed == "insufficient"
    assert bs.valence == 0.0
    assert bs.fragile_axes == []
    assert bs.computed_at == 0
    assert bs.provenance == {}
    assert all(f.default is not dataclasses.MISSING
               or f.default_factory is not dataclasses.MISSING
               for f in dataclasses.fields(bs))


def test_project_carries_new_nervous_fields_with_defaults():
    p = Project(name="p")
    assert p.body is None
    assert p.scream_open is None
    assert p.cycle_seq == 0
    assert p.milestone_reverts == 0
    assert p.coherence_blocks == 0


def test_bodystate_roundtrip_float_arm():
    bs = BodyState(charter_integrity=0.4, accumulated_damage=0.7,
                   uncertainty=0.2, resource_bleed=0.1, valence=-0.55,
                   fragile_axes=["uncertainty"], computed_at=3,
                   provenance={"risk_ids": ["r1"], "run_ids": ["x9"]})
    back = decode(BodyState, encode(bs))
    assert back == bs
    assert isinstance(back.charter_integrity, float)
    assert back.valence == -0.55


def test_bodystate_roundtrip_insufficient_str_arm():
    bs = BodyState(charter_integrity="insufficient", resource_bleed="insufficient")
    back = decode(BodyState, encode(bs))
    assert back.charter_integrity == "insufficient"
    assert back.resource_bleed == "insufficient"


def test_project_with_body_and_scream_open_roundtrips():
    p = Project(name="p")
    p.body = BodyState(accumulated_damage=0.5, valence=-0.3, computed_at=2)
    p.scream_open = {"cause": "grounding_damage", "axis": "accumulated_damage",
                     "opened_at": 2, "held_cycles": 1,
                     "clear_rule": "risk closes and run_properties re-passes",
                     "origin_refs": ["r7"]}
    p.cycle_seq = 2
    p.milestone_reverts = 1
    p.coherence_blocks = 0
    back = decode(Project, encode(p))
    assert back.body == p.body
    assert back.scream_open == p.scream_open
    assert back.cycle_seq == 2
    assert back.milestone_reverts == 1


def test_old_snapshot_without_body_decodes_to_defaults():
    p = Project(name="p")
    raw = encode(p)
    for k in ("body", "scream_open", "cycle_seq", "milestone_reverts",
              "coherence_blocks"):
        raw.pop(k, None)
    back = decode(Project, raw)
    assert back.body is None
    assert back.scream_open is None
    assert back.cycle_seq == 0
    assert back.milestone_reverts == 0
    assert back.coherence_blocks == 0
