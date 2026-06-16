"""Phase 3 — latch state machine driven through the real advance(): a siren
opens the latch, autonomous advance halts while held, held_cycles increments,
a human (force) advance proceeds and (when the clear rule re-verifies) clears the
latch, and nervous_enabled=False leaves advance() byte-identical."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import (BodyState, PacketStatus, ResponseType, Risk,
                                  RiskLevel, RiskStatus, Task, TaskStatus)
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.auto_advance_after_decision = False
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


def _calm_body():
    return BodyState(valence=0.0, computed_at=0)


def _arm_siren(monkeypatch):
    """Make the valence pass fire a grounding_damage siren while NOT cleared, and
    go calm once cleared — so a cleared latch does not immediately re-fire. The
    three valence functions are monkeypatched at module scope (director imports
    them as module globals), so this exercises the WIRING, not the math."""
    state = {"clear": False}

    def fake_compute(project, *, secret, perf, since, cfg):
        if state["clear"]:
            return BodyState(valence=0.0, computed_at=1)
        return BodyState(valence=-0.9, accumulated_damage=0.9, computed_at=1)

    def fake_eval(project, body, *, cfg):
        if float(getattr(body, "valence", 0.0)) <= -0.66:
            return {"level": "siren", "cause": "grounding_damage",
                    "axis": "accumulated_damage",
                    "clear_rule": "risk closed and re-pass",
                    "report": "trusted damage report"}
        return None

    def fake_clear(project, scream_open, *, secret, perf, since, cfg):
        return state["clear"]

    monkeypatch.setattr(dmod, "compute_body", fake_compute)
    monkeypatch.setattr(dmod, "evaluate_scream", fake_eval)
    monkeypatch.setattr(dmod, "check_clear_rule", fake_clear)
    return state


def _open_presented(boss, project_id):
    p = boss.store.load(project_id)
    return next(pk for pk in p.packets.values()
               if pk.status is PacketStatus.PRESENTED)


def test_siren_opens_latch_and_autonomous_advance_halts(boss, monkeypatch):
    _arm_siren(monkeypatch)
    project, packet = boss.new_project("latch", "objective")
    boss.decide(project.id, packet.id, option_key="A")  # clear the plan packet
    boss.advance(project.id, autonomous=True)  # trips siren -> latch + siren packet
    p = boss.store.load(project.id)
    assert p.scream_open is not None
    assert p.scream_open["cause"] == "grounding_damage"
    assert p.scream_open["held_cycles"] >= 1
    opened = p.scream_open["opened_at"]
    # the siren packet (PRESENTED) would trip the open-packet gate first; defer it
    siren_pkt = _open_presented(boss, project.id)
    boss.decide(project.id, siren_pkt.id, response=ResponseType.DEFER)
    # now the held latch halts the autonomous advance with "latched". The
    # autonomous halt-gate is READ-ONLY on held_cycles (FIX 4): it no longer
    # increments, so held_cycles stays at its opened value (>= 1). The increment
    # now happens only on recovery hops that run _nervous_pass.
    out = boss.advance(project.id, autonomous=True)
    assert out["status"] == "latched"
    p2 = boss.store.load(project.id)
    assert p2.scream_open["held_cycles"] >= 1
    assert p2.scream_open["opened_at"] == opened


def test_human_advance_proceeds_through_held_latch_and_clears(boss, monkeypatch):
    state = _arm_siren(monkeypatch)
    project, packet = boss.new_project("human", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)  # open latch (+ siren packet)
    assert boss.store.load(project.id).scream_open is not None
    # human recovery: force bypasses the open siren packet; autonomous=False
    # exempts the latch halt; clear rule now re-verifies -> latch clears.
    state["clear"] = True
    out = boss.advance(project.id, autonomous=False, force=True)
    assert out["status"] != "latched"
    assert boss.store.load(project.id).scream_open is None


def test_latch_does_not_clear_until_reverified(boss, monkeypatch):
    state = _arm_siren(monkeypatch)
    project, packet = boss.new_project("hold", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)  # open latch
    # human recovery advance while the clear rule still fails -> latch stays open
    state["clear"] = False
    boss.advance(project.id, autonomous=False, force=True)
    assert boss.store.load(project.id).scream_open is not None


def test_cycle_seq_increments_each_advance(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: _calm_body())
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: None)
    monkeypatch.setattr(dmod, "check_clear_rule",
                        lambda *a, **k: True)
    project, packet = boss.new_project("seq", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    seq0 = boss.store.load(project.id).cycle_seq
    boss.advance(project.id, autonomous=True)
    seq1 = boss.store.load(project.id).cycle_seq
    assert seq1 == seq0 + 1


def test_real_risk_driven_grounding_latch_clears_when_risk_closes(boss):
    """End-to-end with the REAL valence functions (NO monkeypatch): a
    grounding_damage latch whose origin_refs hold a real OPEN HIGH grounding
    risk stays HELD across a human-recovery advance, and clears once the risk is
    CLOSED — proving FIX 1's risk-driven clearability is not structurally
    un-clearable. Regression guard for the blocker."""
    project = boss.store.create("real-grounding")
    risk = Risk(title="grounding failure", level=RiskLevel.HIGH,
                status=RiskStatus.OPEN, source="grounding")
    project.risks[risk.id] = risk
    # a trivial ready task so each advance reaches _nervous_pass (an empty batch
    # returns "idle" BEFORE the valence pass runs). It is re-readied below so the
    # second advance also dispatches a batch.
    task = Task(title="noop", role="code", status=TaskStatus.READY)
    project.tasks[task.id] = task
    # open a real grounding_damage latch pointing at the real risk id
    project.scream_open = {
        "cause": "grounding_damage", "axis": "accumulated_damage",
        "opened_at": 0, "held_cycles": 1,
        "clear_rule": "every offending grounding risk closes",
        "origin_refs": [risk.id], "opened_severity": 1.0}
    boss.store.save(project)

    # human-recovery advance while the risk is still OPEN -> latch HELD (the real
    # check_clear_rule re-verifies against project.risks and returns False)
    boss.advance(project.id, autonomous=False, force=True)
    assert boss.store.load(project.id).scream_open is not None

    # operator closes the risk and re-readies a task so the next human-recovery
    # advance dispatches a batch and runs the valence pass, which clears the latch
    p = boss.store.load(project.id)
    p.risks[risk.id].status = RiskStatus.CLOSED
    next(iter(p.tasks.values())).status = TaskStatus.READY
    boss.store.save(p)
    boss.advance(project.id, autonomous=False, force=True)
    p2 = boss.store.load(project.id)
    assert p2.scream_open is None, "closing the offending risk must clear the latch"
    assert any(e.type == "scream.cleared" for e in boss.store.journal(p2.id))


def test_nervous_disabled_no_latch_no_cycle_seq(cfg, monkeypatch):
    cfg.nervous_enabled = False
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    boss = Director(cfg, store, router, registry, runner)
    _arm_siren(monkeypatch)
    project, packet = boss.new_project("off", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    assert p.scream_open is None
    assert p.cycle_seq == 0
