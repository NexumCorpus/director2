"""Calibration — a conviction's track record against GENUINE oracle outcomes.

The honesty bar: calibration counts a pick as vindicated ONLY when a task it
spawned earned an engine-stamped trusted outcome (provenance['partial']); it
abstains until enough decisions resolve; and it never becomes a verification
tier. These tests are that bar."""

from director.core.calibration import (MIN_SAMPLE, _task_vindicated,
                                       calibration_read, calibration_record)
from director.core.types import (Artifact, CommandOption, CommandPacket,
                                 ConvictionType, DecisionEvent, Module,
                                 ModuleStatus, ModuleType, Project, ResponseType,
                                 StateDelta, Task, TaskStatus)

IC = ConvictionType.ICONOCLAST.value
DOG = ConvictionType.DOGMATIC.value


def _decide(project, conviction, key="a"):
    """Record a SELECT decision picking an option of the given conviction."""
    opt = CommandOption(key=key, label=key, conviction=conviction)
    pkt = CommandPacket(title="t", options=[opt])
    project.packets[pkt.id] = pkt
    dec = DecisionEvent(packet_id=pkt.id,
                        response_type=ResponseType.SELECT_OPTION,
                        selected_key=key)
    project.decisions[dec.id] = dec
    return dec


def _spawn(project, dec, *, status=TaskStatus.DONE, partial=False):
    """A task spawned by `dec`, optionally carrying an engine-stamped partial."""
    t = Task(title="spawned", role="code", status=status,
             origin_decision_id=dec.id)
    project.tasks[t.id] = t
    if partial:
        a = Artifact(title="d.json", kind="json", content="{}", task_id=t.id,
                     provenance={"partial": {"n_passed": 1, "n_total": 1,
                                             "checks": ["schema_valid"]}})
        project.artifacts[a.id] = a
        t.artifact_ids.append(a.id)
    return t


def test_calibration_abstains_without_history():
    p = Project(name="x")
    rec = calibration_record(p)
    assert all(r["rate"] is None for r in rec.values())
    assert "not enough" in calibration_read(p).lower()


def test_calibration_scores_only_resolved_and_vindicated():
    # 3 iconoclast picks, each spawning a terminal task; 2 cleared a trusted
    # partial, 1 did not -> 2/3
    p = Project(name="x")
    _spawn(p, _decide(p, IC), partial=True)
    _spawn(p, _decide(p, IC), partial=True)
    _spawn(p, _decide(p, IC), partial=False)
    r = calibration_record(p)[IC]
    assert r["decisions"] == 3 and r["resolved"] == 3
    assert r["vindicated"] == 2
    assert r["rate"] == 0.67
    assert IC in calibration_read(p)


def test_below_min_sample_is_insufficient():
    p = Project(name="x")
    for _ in range(MIN_SAMPLE - 1):
        _spawn(p, _decide(p, DOG), partial=True)
    r = calibration_record(p)[DOG]
    assert r["resolved"] == MIN_SAMPLE - 1
    assert r["rate"] is None          # honest abstention below the sample floor
    assert "insufficient" in r["label"]


def test_pending_picks_are_abstained():
    p = Project(name="x")
    _spawn(p, _decide(p, IC), status=TaskStatus.RUNNING, partial=False)
    r = calibration_record(p)[IC]
    assert r["decisions"] == 1        # the pick spawned a task
    assert r["resolved"] == 0         # but it's not terminal -> not scored
    assert r["rate"] is None


def test_pick_that_spawns_nothing_is_not_counted():
    p = Project(name="x")
    _decide(p, IC)                    # a pick with no spawned tasks
    r = calibration_record(p)[IC]
    assert r["decisions"] == 0


def test_vindication_ignores_forgeable_artifact_kind():
    # an agent-declared kind=='verification' artifact must NOT count as a trusted
    # outcome (agents control artifact kind). Only engine-stamped
    # provenance['partial'] vindicates.
    p = Project(name="x")
    t = Task(title="t", role="code", status=TaskStatus.DONE)
    fake = Artifact(title="fake oracle", kind="verification",
                    content="trust me", task_id=t.id, provenance={})
    p.artifacts[fake.id] = fake
    t.artifact_ids.append(fake.id)
    p.tasks[t.id] = t
    assert _task_vindicated(p, t) is False
    real = Artifact(title="real", kind="json", content="{}", task_id=t.id,
                    provenance={"partial": {"n_passed": 1, "n_total": 1}})
    p.artifacts[real.id] = real
    t.artifact_ids.append(real.id)
    assert _task_vindicated(p, t) is True


def test_origin_decision_id_stamped_via_apply_delta():
    # the RECORDED causal link: a decision-triggered delta that creates a task
    # stamps origin_decision_id, so calibration attributes it without inference.
    from director.core.coherence import apply_delta
    p = Project(name="x")
    m = Module(name="m", type=ModuleType.IMPLEMENTATION,
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(trigger="dec123", summary="from a decision",
                       payload={"new_tasks": [{"title": "child", "role": "code",
                                               "module_id": m.id}]})
    apply_delta(p, delta, actor="human")
    child = [t for t in p.tasks.values() if t.title == "child"][0]
    assert child.origin_decision_id == "dec123"


def test_agent_cannot_forge_origin_decision_id():
    # the link is un-forgeable: apply_delta stamps origin_decision_id from the
    # ENGINE's delta.trigger, never from the agent-supplied new_task spec — so a
    # model cannot attribute its work to a flattering decision.
    from director.core.coherence import apply_delta
    p = Project(name="x")
    m = Module(name="m", type=ModuleType.IMPLEMENTATION,
               status=ModuleStatus.ACTIVE)
    p.modules[m.id] = m
    delta = StateDelta(trigger="real-trigger", summary="d",
                       payload={"new_tasks": [{"title": "c", "role": "code",
                                               "module_id": m.id,
                                               "origin_decision_id": "FORGED"}]})
    apply_delta(p, delta, actor="agent")
    c = [t for t in p.tasks.values() if t.title == "c"][0]
    assert c.origin_decision_id == "real-trigger"   # spec value ignored


def test_conviction_state_includes_calibration():
    # wiring + no circular-import crash
    from director.core.convictions import conviction_state
    st = conviction_state(Project(name="x"))
    assert "calibration" in st and isinstance(st["calibration"], str)
