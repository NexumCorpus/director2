"""Round-trip + persistence tests for the domain model and ProjectStore."""

from datetime import datetime

from director.core.state import ProjectStore
from director.core.types import (
    AgentRun, Artifact, AuditEvent, Charter, CommandOption, CommandPacket,
    DecisionEvent, Milestone, Module, ModuleStatus, ModuleType, PacketStatus,
    Project, ResponseType, Risk, RiskLevel, Severity, StateDelta, Task,
    TaskStatus, VerificationReport, VerifyAction, decode, encode,
)


def make_rich_project() -> Project:
    p = Project(name="alpha")
    p.charter = Charter(objective="Build X", scope_in=["a"], success_criteria=["works"])
    m = Module(name="core", type=ModuleType.IMPLEMENTATION, purpose="build core",
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    t = Task(title="write code", role="code", module_id=m.id,
             status=TaskStatus.READY, verifiers=["agent_output"],
             acceptance_criteria=["compiles"])
    p.tasks[t.id] = t
    t2 = Task(title="test code", role="test", module_id=m.id, depends_on=[t.id])
    p.tasks[t2.id] = t2
    ms = Milestone(name="M0", task_ids=[t.id, t2.id])
    p.milestones[ms.id] = ms
    r = Risk(title="scope creep", level=RiskLevel.HIGH)
    p.risks[r.id] = r
    a = Artifact(title="main.py", kind="code", content="print('hi')",
                 module_id=m.id, task_id=t.id)
    p.artifacts[a.id] = a
    run = AgentRun(task_id=t.id, role="code", status="succeeded",
                   output={"summary": "did it"},
                   reports=[VerificationReport(verifier="agent_output", passed=True,
                                               score=4.2, severity=Severity.INFO,
                                               action=VerifyAction.AUTO_APPROVE)])
    p.runs[run.id] = run
    pkt = CommandPacket(
        title="Choose approach", trigger="planning",
        options=[CommandOption(key="A", label="Fast", state_delta={"x": 1}),
                 CommandOption(key="B", label="Safe")],
        recommendation_key="A", status=PacketStatus.PRESENTED)
    p.packets[pkt.id] = pkt
    d = DecisionEvent(packet_id=pkt.id, response_type=ResponseType.SELECT_OPTION,
                      selected_key="A")
    p.decisions[d.id] = d
    sd = StateDelta(trigger=d.id, summary="apply A", payload={"module_updates": []})
    p.deltas[sd.id] = sd
    return p


def test_encode_decode_roundtrip():
    p = make_rich_project()
    data = encode(p)
    p2 = decode(Project, data)
    assert p2.name == "alpha"
    assert p2.charter.objective == "Build X"
    # enums survive
    m2 = list(p2.modules.values())[0]
    assert m2.status is ModuleStatus.ACTIVE
    assert m2.type is ModuleType.IMPLEMENTATION
    # nested dataclasses survive
    run2 = list(p2.runs.values())[0]
    assert run2.reports[0].passed is True
    assert run2.reports[0].action is VerifyAction.AUTO_APPROVE
    # datetimes survive
    assert isinstance(p2.created_at, datetime)
    # optional None survives
    pkt2 = list(p2.packets.values())[0]
    assert pkt2.answered_at is None
    assert pkt2.options[0].state_delta == {"x": 1}
    # full fidelity: re-encoding gives identical structure
    assert encode(p2) == data


def test_decode_ignores_unknown_keys():
    data = encode(Task(title="t"))
    data["totally_new_field"] = 123
    t = decode(Task, data)
    assert t.title == "t"


def test_store_create_save_load(cfg):
    store = ProjectStore(cfg)
    p = store.create("proj-one")
    p2 = store.load(p.id)
    assert p2.name == "proj-one"
    # prefix resolution
    p3 = store.load(p.id[:6])
    assert p3.id == p.id
    # current pointer set on create
    assert store.get_current() == p.id


def test_store_mutate_and_reload(cfg):
    store = ProjectStore(cfg)
    p = store.create("proj-two")
    t = Task(title="do thing", role="research")
    p.tasks[t.id] = t
    store.save(p)
    p2 = store.load(p.id)
    assert p2.tasks[t.id].title == "do thing"
    assert p2.tasks[t.id].status is TaskStatus.PENDING


def test_journal_append_and_read(cfg):
    store = ProjectStore(cfg)
    p = store.create("proj-three")
    for i in range(5):
        store.append_event(p.id, AuditEvent(type="tick", summary=f"event {i}"))
    events = list(store.journal(p.id))
    # +1 for project.created
    assert len(events) == 6
    assert events[-1].summary == "event 4"
    limited = list(store.journal(p.id, limit=2))
    assert len(limited) == 2


def test_artifact_mirror(cfg):
    store = ProjectStore(cfg)
    p = store.create("proj-four")
    a = Artifact(title="Design Notes: v1", kind="markdown", content="# hi")
    path = store.mirror_artifact(p.id, a)
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "# hi"
    assert path.suffix == ".md"


def test_list_projects(cfg):
    store = ProjectStore(cfg)
    store.create("one")
    store.create("two")
    listing = store.list_projects()
    assert {row["name"] for row in listing} == {"one", "two"}
