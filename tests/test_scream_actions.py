"""Phase 3 — scream actions: ache injects ONE tail diagnostic review task with
no ordering bump; siren raises a packet whose context is the trusted report and
opens the latch; the deadlock guard escalates past max_held_cycles."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.taskgraph import ready_tasks
from director.core.types import BodyState, PacketStatus, TaskStatus
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


def test_ache_injects_one_tail_review_task(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.45,
                                                       accumulated_damage=0.5,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "ache", "cause": "accumulated_damage",
                            "axis": "accumulated_damage", "clear_rule": "",
                            "report": "failing case: code_runs failed on X"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: True)
    project, packet = boss.new_project("ache", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    before = len(boss.store.load(project.id).tasks)
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    injected = [t for t in p.tasks.values()
                if t.role == "review" and "diagnos" in t.objective.lower()]
    assert len(injected) == 1
    t = injected[0]
    assert t.depends_on == []
    assert t.status in (TaskStatus.PENDING, TaskStatus.READY)
    assert p.scream_open is None
    assert any(e.type == "scream.ache" for e in boss.store.journal(p.id))


def test_ache_injects_at_frontier_tail_not_ahead(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.45,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "ache", "cause": "uncertainty",
                            "axis": "uncertainty", "clear_rule": "",
                            "report": "diagnostic needed"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: True)
    project, packet = boss.new_project("tail", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    order = ready_tasks(p)
    injected = next(t for t in p.tasks.values()
                    if t.role == "review" and "diagnos" in t.objective.lower())
    if injected in order:
        assert order[-1].id == injected.id


def test_siren_packet_context_is_trusted_report_and_opens_latch(boss, monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       accumulated_damage=0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "risk closed and re-pass",
                            "report": "TRUSTED DAMAGE REPORT - code_runs failed"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)
    project, packet = boss.new_project("siren", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    p = boss.store.load(project.id)
    assert p.scream_open is not None
    open_pkts = [pk for pk in p.packets.values()
                 if pk.status is PacketStatus.PRESENTED]
    siren_pkts = [pk for pk in open_pkts
                  if pk.trigger == "scream:grounding_damage"]
    assert siren_pkts and "TRUSTED DAMAGE REPORT" in siren_pkts[0].context


def test_deadlock_escalation_past_max_held_cycles(boss, monkeypatch):
    boss.cfg.max_held_cycles = 2
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "x", "report": "report"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)
    project, packet = boss.new_project("dead", "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)        # open latch (held_cycles=1)
    assert boss.store.load(project.id).scream_open is not None

    def _ready_a_task():
        # ensure each recovery hop dispatches a batch (else advance() returns
        # "idle" BEFORE _nervous_pass and no held cycle is counted).
        p = boss.store.load(project.id)
        next(iter(p.tasks.values())).status = TaskStatus.READY
        boss.store.save(p)

    # climb held_cycles via human RECOVERY hops: force bypasses the open-packet
    # and latch gates and runs _nervous_pass, which now owns the held_cycles
    # increment + deadlock escalation (FIX 4). The fault is STILL present
    # (check_clear_rule monkeypatched to False), so the latch never clears.
    for _ in range(5):
        p = boss.store.load(project.id)
        if int(p.scream_open["held_cycles"]) > boss.cfg.max_held_cycles:
            break
        _ready_a_task()
        boss.advance(project.id, autonomous=False, force=True)

    p = boss.store.load(project.id)
    assert int(p.scream_open["held_cycles"]) > boss.cfg.max_held_cycles
    assert any(e.type == "scream.deadlock" for e in boss.store.journal(p.id))
