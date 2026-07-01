"""Phase 2 — full-composite integration over compute_body: all axes at once,
renormalization on abstain (thresholds NOT rescaled), and the OFF-path guarantee
that the reducer is pure and unwired (Phase 3 does the wiring)."""

import inspect

from director.config import Config
from director.core import director as director_mod
from director.core.types import (Risk, RiskLevel, RiskStatus, Task, TaskStatus,
                                 Project)
from director.core.valence import BodyState, compute_body


def _proj():
    return Project(name="p")


def test_clean_project_has_zero_valence():
    cfg = Config()
    body = compute_body(_proj(), secret=cfg.report_secret(), perf=None,
                        since=None, cfg=cfg)
    assert body.valence == 0.0
    assert body.fragile_axes == []


def test_full_composite_with_abstaining_bleed():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(5)]}
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert body.accumulated_damage == 1.0
    assert body.charter_integrity == 1.0
    assert body.resource_bleed == "insufficient"
    expected = -((0.40 * 1.0 + 0.30 * 1.0 + 0.20 * 0.0) / 0.90)
    assert abs(body.valence - expected) < 1e-6


def test_thresholds_not_rescaled_on_abstain():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(5)]}
    p.milestone_reverts = 3
    body = compute_body(p, secret=cfg.report_secret(), perf=None, since=None,
                        cfg=cfg)
    assert -1.0 <= body.valence <= 0.0
    assert body.valence < cfg.siren_threshold


def test_valence_floor_is_minus_one_when_all_present_axes_saturated():
    cfg = Config()
    cfg.budget = {"max_tokens": 1}

    class _Perf:
        def stats(self, *, since=None):
            return {"prompt_tokens": 9999, "completion_tokens": 0}

    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(9)]}
    p.milestone_reverts = 9
    nv = [Task(title="u", status=TaskStatus.NEEDS_VERIFY) for _ in range(9)]
    for t in nv:
        p.tasks[t.id] = t
    body = compute_body(p, secret=cfg.report_secret(), perf=_Perf(), since=None,
                        cfg=cfg)
    assert abs(body.valence - (-1.0)) < 1e-6


def test_advance_consults_posture_but_never_recomputes_the_body():
    # v1 invariant that SURVIVES v3: advance() never recomputes the trusted Body
    # itself — compute_body lives only in _nervous_pass (separation of concerns).
    # v3 reality: advance MAY read the persisted Homeostat posture to grade its
    # throughput, but every such consultation is gated behind nervous_enabled.
    src = inspect.getsource(director_mod.Director.advance)
    assert "compute_body" not in src           # never recomputes the Body
    assert "nervous_enabled" in src            # any valence consultation is gated


def test_compute_body_is_pure_no_mutation_of_project():
    cfg = Config()
    p = _proj()
    p.tasks = {t.id: t for t in
               [Task(title="d", status=TaskStatus.FAILED) for _ in range(2)]}
    before = {"tasks": dict(p.tasks), "body": p.body,
              "scream_open": p.scream_open, "cycle_seq": p.cycle_seq}
    compute_body(p, secret=cfg.report_secret(), perf=None, since=None, cfg=cfg)
    assert p.body is before["body"]
    assert p.scream_open is before["scream_open"]
    assert p.cycle_seq == before["cycle_seq"]
    assert p.tasks == before["tasks"]
