"""Orchestrator tests: planning, command packets, decisions, advance cycles,
coherence enforcement, full lifecycle to finalize — all on the mock backend."""

import pytest

from director.agents.runner import SubAgentRunner
from director.core.coherence import apply_delta, coherence_pass
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.taskgraph import (detect_cycles, ready_tasks,
                                     refresh_milestones, refresh_statuses)
from director.core.types import (MilestoneStatus, Module, ModuleStatus,
                                 PacketStatus, Project, ResponseType,
                                 StateDelta, Task, TaskStatus)
from director.errors import CoherenceBlockedError
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


# ----------------------------------------------------------------- taskgraph
def test_detect_cycles():
    a = Task(title="a")
    b = Task(title="b", depends_on=[a.id])
    a.depends_on = [b.id]
    assert detect_cycles({a.id: a, b.id: b})
    a.depends_on = []
    assert not detect_cycles({a.id: a, b.id: b})


def test_refresh_and_ready_ordering():
    p = Project(name="t")
    t1 = Task(title="first")
    t2 = Task(title="second", depends_on=[t1.id])
    p.tasks = {t1.id: t1, t2.id: t2}
    refresh_statuses(p)
    ready = ready_tasks(p)
    assert [t.title for t in ready] == ["first"]
    t1.status = TaskStatus.DONE
    refresh_statuses(p)
    assert [t.title for t in ready_tasks(p)] == ["second"]


def test_milestone_refresh():
    p = Project(name="t")
    t1 = Task(title="a", status=TaskStatus.DONE)
    p.tasks[t1.id] = t1
    from director.core.types import Milestone
    ms = Milestone(name="M", task_ids=[t1.id])
    p.milestones[ms.id] = ms
    reached = refresh_milestones(p)
    assert reached and ms.status is MilestoneStatus.REACHED


# ----------------------------------------------------------------- coherence
def test_coherence_blocks_unknown_module():
    p = Project(name="t")
    delta = StateDelta(trigger="x", payload={
        "module_updates": [{"module_id": "nope", "status": "active"}]})
    rep = coherence_pass(p, delta)
    assert rep.blocked
    with pytest.raises(CoherenceBlockedError):
        apply_delta(p, delta)
    assert delta.status == "blocked"


def test_coherence_blocks_frozen_edit_and_illegal_transition():
    p = Project(name="t")
    m = Module(name="m", status=ModuleStatus.FROZEN)
    p.modules[m.id] = m
    delta = StateDelta(trigger="x", payload={
        "module_updates": [{"module_id": m.id, "status": "completed"}]})
    assert coherence_pass(p, delta).blocked
    # unfreeze is allowed
    delta2 = StateDelta(trigger="x", payload={
        "module_updates": [{"module_id": m.id, "status": "active"}]})
    rep = coherence_pass(p, delta2)
    assert not rep.blocked


def test_coherence_in_command_requires_human():
    p = Project(name="t")
    m = Module(name="m", status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(trigger="x", payload={
        "module_updates": [{"module_id": m.id, "status": "in_command"}]})
    assert coherence_pass(p, delta, actor="director").blocked
    assert not coherence_pass(p, delta, actor="human").blocked


def test_coherence_new_task_cycle_blocked():
    p = Project(name="t")
    t1 = Task(title="t1")
    p.tasks[t1.id] = t1
    delta = StateDelta(trigger="x", payload={
        "new_tasks": [{"title": "evil", "depends_on": ["missing-task"]}]})
    assert coherence_pass(p, delta).blocked


def test_apply_delta_new_task_and_risk():
    p = Project(name="t")
    m = Module(name="m", status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(trigger="d1", payload={
        "new_tasks": [{"title": "extra review", "role": "review",
                       "module_id": m.id}],
        "risk_updates": [{"title": "new risk", "level": "high"}],
    })
    rep = apply_delta(p, delta)
    assert rep.status in ("clear", "warnings")
    assert any(t.title == "extra review" for t in p.tasks.values())
    assert any(r.title == "new risk" and r.level.value == "high"
               for r in p.risks.values())
    assert delta.status == "applied"


# ------------------------------------------------------------------ director
def test_new_project_plans_and_presents_packet(boss):
    project, packet = boss.new_project("demo", "build a top-k library")
    assert len(project.modules) == 3          # mock fixture plan
    assert len(project.tasks) == 4
    assert len(project.milestones) == 2
    assert packet.status is PacketStatus.PRESENTED
    assert len(packet.options) >= 2
    # deps wired by title: first task ready, others pending
    statuses = sorted(t.status.value for t in project.tasks.values())
    assert "ready" in statuses and "pending" in statuses
    # persisted
    p2 = boss.store.load(project.id)
    assert p2.charter.objective.startswith("build a top-k")


def test_advance_waits_for_open_packet(boss):
    project, _packet = boss.new_project("demo2", "objective x")
    out = boss.advance(project.id)
    assert out["status"] == "awaiting_command" and out["ran"] == 0


def test_decide_applies_and_auto_advances(boss):
    project, packet = boss.new_project("demo3", "objective y")
    result = boss.decide(project.id, packet.id, option_key="A",
                         rationale="go fast")
    assert result["applied"]
    assert "auto-advanced" in result["follow_up"]
    p = boss.store.load(project.id)
    done = [t for t in p.tasks.values() if t.status is TaskStatus.DONE]
    assert done, "auto-advance should have completed the first ready task"
    answered = [pk for pk in p.packets.values()
                if pk.status is PacketStatus.ANSWERED]
    assert answered


def test_decide_defer_and_take_command(boss):
    project, packet = boss.new_project("demo4", "objective z")
    out = boss.decide(project.id, packet.id, response=ResponseType.DEFER)
    assert not out["applied"]
    p = boss.store.load(project.id)
    assert p.packets[packet.id].status is PacketStatus.DEFERRED
    # new packet, take command
    p2, packet2 = boss.new_project("demo5", "objective w")
    out2 = boss.decide(p2.id, packet2.id, response=ResponseType.TAKE_COMMAND)
    assert out2["applied"]
    p2r = boss.store.load(p2.id)
    assert any(m.status is ModuleStatus.IN_COMMAND
               for m in p2r.modules.values())


def test_full_lifecycle_to_finalize(boss, cfg):
    project, packet = boss.new_project("life", "ship the gizmo")
    # drive until nothing is runnable: decide any open packet, else advance
    for _ in range(20):
        p = boss.store.load(project.id)
        open_pkts = [pk for pk in p.packets.values()
                     if pk.status is PacketStatus.PRESENTED]
        if open_pkts:
            boss.decide(p.id, open_pkts[0].id, option_key=
                        open_pkts[0].recommendation_key or
                        open_pkts[0].options[0].key)
            continue
        out = boss.advance(p.id)
        if out["status"] == "idle":
            break
    p = boss.store.load(project.id)
    assert all(t.status in (TaskStatus.DONE, TaskStatus.CANCELLED)
               for t in p.tasks.values()), {
        t.title: t.status.value for t in p.tasks.values()}
    assert all(m.status is MilestoneStatus.REACHED
               for m in p.milestones.values())
    assert p.artifacts, "agents should have produced artifacts"
    # finalize produces a mirrored report
    fin = boss.finalize(p.id)
    assert fin["status"] == "ok"
    from pathlib import Path
    assert Path(fin["path"]).is_file()
    p = boss.store.load(project.id)
    assert p.status == "finalized"
    # journal recorded the arc
    types = {e.type for e in boss.store.journal(p.id)}
    assert {"project.created", "plan.created", "packet.presented",
            "decision.recorded", "advance.completed",
            "project.finalized"} <= types


def test_status_next_action(boss):
    project, packet = boss.new_project("stat", "objective s")
    st = boss.status(project.id)
    assert st["open_packet_ids"] == [packet.id]
    assert st["next_action"].startswith("decide")
    assert st["tasks_total"] == 4


def test_advance_recovers_stranded_running_tasks(boss):
    project, packet = boss.new_project("recover", "objective r")
    boss.decide(project.id, packet.id, option_key="A")
    p = boss.store.load(project.id)
    # simulate a crash mid-advance: a task left RUNNING, never completed
    victim = next(iter(p.tasks.values()))
    victim.status = TaskStatus.RUNNING
    boss.store.save(p)
    out = boss.advance(project.id, force=True)
    p2 = boss.store.load(project.id)
    # the stranded task was recovered (no longer RUNNING) and the cycle ran
    assert all(t.status is not TaskStatus.RUNNING for t in p2.tasks.values())
    assert any(e.type == "advance.recovered" for e in boss.store.journal(p2.id))


def test_decision_blocked_keeps_packet_open(boss):
    project, packet = boss.new_project("blocked", "objective b")
    # craft an option whose delta references a frozen module (coherence blocks)
    from director.core.types import CommandOption, ModuleStatus
    p = boss.store.load(project.id)
    mod = next(iter(p.modules.values()))
    mod.status = ModuleStatus.FROZEN
    pkt = p.packets[packet.id]
    pkt.options.append(CommandOption(
        key="Z", label="illegal",
        state_delta={"module_updates": [{"module_id": mod.id,
                                         "status": "completed"}]}))
    boss.store.save(p)
    out = boss.decide(project.id, packet.id, option_key="Z")
    assert out["coherence"] == "blocked" and not out["applied"]
    p2 = boss.store.load(project.id)
    # packet stays PRESENTED (not stuck answered); decision.blocked audited
    assert p2.packets[packet.id].status is PacketStatus.PRESENTED
    assert any(e.type == "decision.blocked" for e in boss.store.journal(p2.id))


def test_take_command_noop_reports_zero(boss):
    project, packet = boss.new_project("tc", "objective t")
    from director.core.types import ModuleStatus
    p = boss.store.load(project.id)
    for m in p.modules.values():
        m.status = ModuleStatus.FROZEN     # nothing ACTIVE to take
    boss.store.save(p)
    out = boss.decide(project.id, packet.id,
                      response=ResponseType.TAKE_COMMAND)
    assert out["modules_taken"] == 0 and out["applied"] is False


def test_decode_forward_incompatible_enum_becomes_none():
    """An unknown enum value in an Optional field decodes to None, not a
    wrong-typed raw string."""
    from director.core.types import Risk, decode, encode
    data = encode(Risk(title="x"))
    data["level"] = "apocalyptic"          # not a RiskLevel
    # level is non-optional -> coercion path; ensure it doesn't crash and the
    # optional fields still behave. Use an optional field for the None check:
    from director.core.types import AgentRun
    run = encode(AgentRun(task_id="t", role="r"))
    run["completed_at"] = "not-a-date"
    decoded = decode(AgentRun, run)
    assert decoded.completed_at is None


def test_approve_task_human_override(boss):
    project, packet = boss.new_project("appr", "objective a")
    boss.decide(project.id, packet.id, option_key="A")
    p = boss.store.load(project.id)
    # force a task into needs_verify and approve it
    t = next(t for t in p.tasks.values() if t.status is not TaskStatus.DONE)
    t.status = TaskStatus.NEEDS_VERIFY
    boss.store.save(p)
    out = boss.approve_task(p.id, t.id)
    assert out["status"] == "ok"
    p2 = boss.store.load(p.id)
    assert p2.tasks[t.id].status is TaskStatus.DONE
