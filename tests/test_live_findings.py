"""Regressions for the 2026-06-12 live-Opus smoke findings.

Each test reproduces a failure shape OBSERVED against the real model:
scalar-for-list packet fields, bare-list subagent roots, synonym keys,
list-shaped recommended_updates, context starvation of upstream artifacts,
prose-only quantitative results, and invisible coherence-block reasons.
"""

import pytest

from director.agents.base import ArtifactOut, SubAgentOutput
from director.agents.runner import SubAgentRunner
from director.core.director import Director, OptionOut, PacketOut
from director.core.state import ProjectStore
from director.core.types import (Artifact, CommandOption, CommandPacket,
                                 PacketStatus, Project, Task, TaskStatus)
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry
from director.verify.evaluators import AgentOutputEvaluator


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


# ------------------------------------------------------- schema shape lenience
def test_packetout_coerces_scalar_list_fields():
    # observed on EVERY live packet generation: consequences as a string
    out = PacketOut.model_validate({
        "title": "choose", "risks": "one risk",
        "options": [{"key": "a", "label": "A",
                     "tradeoffs": "fast but fragile",
                     "consequences": "the validation task runs again"}]})
    assert out.options[0].consequences == ["the validation task runs again"]
    assert out.options[0].tradeoffs == ["fast but fragile"]
    assert out.risks == ["one risk"]
    # lists still pass through untouched
    assert OptionOut.model_validate(
        {"key": "b", "label": "B", "consequences": ["x", "y"]}
    ).consequences == ["x", "y"]


def test_subagent_output_bare_list_root_becomes_artifacts():
    # observed live: research agent returned a JSON array of artifact objects
    out = SubAgentOutput.model_validate(
        [{"type": "markdown", "name": "terrain-notes",
          "content": "ridge rows at 4 and 12, elevation 10"}])
    assert "coerced" in out.summary
    assert out.artifacts[0].title == "terrain-notes"
    assert out.artifacts[0].kind == "markdown"


def test_subagent_output_synonym_keys_and_updates_list():
    # observed live: risks carried 'statement' not 'title';
    # recommended_updates came as a list of update objects
    out = SubAgentOutput.model_validate({
        "summary": "review attempted",
        "risks": [{"id": "RSK-1", "statement": "artifacts not provided",
                   "confidence": "high"}],
        "recommended_updates": [{"target": "review_status",
                                 "value": "blocked"}],
        "lessons": "single lesson as a string"})
    assert out.risks[0].title == "artifacts not provided"
    assert out.recommended_updates == {
        "items": [{"target": "review_status", "value": "blocked"}]}
    assert out.lessons == ["single lesson as a string"]


def test_artifact_out_key_aliases():
    a = ArtifactOut.model_validate(
        {"name": "compute.py", "type": "code", "text": "print(1)"})
    assert (a.title, a.kind, a.content) == ("compute.py", "code", "print(1)")


def test_artifact_out_label_alias():
    # live finding 2026-06-13: a finalize agent keyed artifacts with 'label'
    a = ArtifactOut.model_validate(
        {"label": "isr_scenario_schema.json", "kind": "code",
         "content": "{}"})
    assert a.title == "isr_scenario_schema.json"


def test_artifact_out_object_content_serialized():
    # observed live: the scenario JSON OBJECT placed directly in content
    import json as _json
    a = ArtifactOut.model_validate(
        {"title": "scenario.cheap.json", "kind": "json",
         "content": {"w": 24, "h": 16,
                     "sensors": [{"id": "s1", "x": 3, "y": 4,
                                  "range": 7, "height": 4}]}})
    parsed = _json.loads(a.content)
    assert parsed["w"] == 24 and parsed["sensors"][0]["id"] == "s1"


# --------------------------------------------------- context budget / handoff
def _project_with_dep_artifacts(n_arts: int, art_len: int):
    p = Project(name="ctx")
    t1 = Task(title="upstream", status=TaskStatus.DONE,
              result_summary="produced the inputs")
    arts = []
    for i in range(n_arts):
        a = Artifact(title=f"big{i}", kind="code", content="x" * art_len)
        p.artifacts[a.id] = a
        arts.append(a.id)
    t1.artifact_ids = arts
    t2 = Task(title="downstream", role="test", depends_on=[t1.id])
    p.tasks = {t1.id: t1, t2.id: t2}
    return p, t2


def test_spec_for_includes_artifacts_with_visible_truncation(boss):
    p, t2 = _project_with_dep_artifacts(n_arts=2, art_len=10_000)
    spec = boss._spec_for(p, t2)
    # both artifacts present, each individually trimmed with a marker —
    # the old tail-chop silently deleted them entirely
    assert "Upstream artifact 'big0'" in spec.context
    assert "Upstream artifact 'big1'" in spec.context
    assert "[truncated:" in spec.context
    assert len(spec.context) <= boss.cfg.ctx_total_chars + 1000


def test_spec_for_names_omitted_artifacts_when_budget_exhausted(boss):
    boss.cfg.ctx_total_chars = 3000
    p, t2 = _project_with_dep_artifacts(n_arts=8, art_len=5_000)
    spec = boss._spec_for(p, t2)
    assert "OMITTED" in spec.context          # omission is named, not silent
    assert len(spec.context) <= 3000 + 1500


# ------------------------------------------------------ artifact grounding gate
def test_simulation_output_without_artifacts_is_blocked():
    rep = AgentOutputEvaluator().verify(
        {"summary": "Modeled coverage and achieved an estimated 73.4 percent "
                    "over 384 cells using assumed terrain semantics."},
        context={"role": "simulation", "objective": "measure coverage"})
    assert not rep.passed
    assert any("ungroundable" in i for i in rep.issues)


def test_synthesis_task_without_artifacts_is_blocked():
    # 2026-06-13 finding: a synthesis agent claimed a deliverable in prose but
    # emitted no artifact, passing as "done" with a hollow result.
    rep = AgentOutputEvaluator().verify(
        {"summary": "Synthesized the example and checklist into a package."},
        context={"role": "synthesis", "objective": "produce the package"})
    assert not rep.passed
    assert any("ungroundable" in i for i in rep.issues)


def test_finalize_call_is_exempt_from_synthesis_gate():
    # the finalize CALL legitimately emits a summary and bundles artifacts
    # itself — it must NOT be blocked for emitting no artifacts of its own
    spec = type("S", (), {"task_id": "finalize"})()
    rep = AgentOutputEvaluator().verify(
        {"summary": "Final synthesis report over the bundled artifacts."},
        context={"role": "synthesis", "objective": "finalize", "spec": spec})
    assert rep.passed


def test_synthesis_task_with_artifacts_passes():
    rep = AgentOutputEvaluator().verify(
        {"summary": "Produced the example instance.",
         "artifacts": [{"title": "example.json", "kind": "json",
                        "content": "{\"w\": 24}"}]},
        context={"role": "synthesis", "objective": "produce example"})
    assert "artifact_grounding" in rep.details["criteria"]
    assert rep.details["criteria"]["artifact_grounding"] >= 4.0


def test_research_output_without_artifacts_is_not_gated():
    rep = AgentOutputEvaluator().verify(
        {"summary": "Surveyed the terrain abstraction options and recorded "
                    "claims with confidence levels for the decision.",
         "claims": [{"text": "LOS occlusion matters here",
                     "confidence": "high"}],
         "recommended_updates": {"note": "proceed"}},
        context={"role": "research", "objective": "survey terrain options"})
    assert "artifact_grounding" not in rep.details["criteria"]


def test_code_output_with_artifacts_passes_gate():
    rep = AgentOutputEvaluator().verify(
        {"summary": "Implemented the coverage function with bresenham line "
                    "of sight and returned it as a code artifact.",
         "artifacts": [{"title": "compute_coverage.py", "kind": "code",
                        "content": "def compute_coverage(t, s):\n    ..."}]},
        context={"role": "code", "objective": "implement coverage function"})
    assert "artifact_grounding" in rep.details["criteria"]
    assert rep.details["criteria"]["artifact_grounding"] >= 4.0


# ------------------------------------------------- blocked decisions are loud
def test_decide_blocked_surfaces_reason_and_keeps_packet_open(boss):
    p = Project(name="t")
    t1 = Task(title="work")
    p.tasks[t1.id] = t1
    pkt = CommandPacket(title="choose", options=[CommandOption(
        key="bad", label="Bad enum delta",
        state_delta={"task_updates": [
            {"task_id": t1.id, "status": "active"}]})])   # observed live
    pkt.status = PacketStatus.PRESENTED
    p.packets[pkt.id] = pkt
    boss.store.save(p)
    out = boss.decide(p.id, pkt.id, option_key="bad")
    assert out["applied"] is False
    assert out["coherence"] == "blocked"
    assert out.get("error")                   # reason travels to the CLI now
    p2 = boss.store.load(p.id)
    assert p2.packets[pkt.id].status is PacketStatus.PRESENTED


# ------------------------------------------------- planner synonym keys
def test_planout_accepts_title_for_name():
    from director.core.director import PlanOut
    plan = PlanOut.model_validate({
        "charter": {"objective": "study the mesh trade space"},
        "modules": [{"title": "Scenario Definition", "purpose": "p"}],
        "tasks": [{"title": "define scenarios", "role": "research"}],
        "milestones": [{"title": "Scenarios defined",
                        "tasks": ["define scenarios"]}]})
    assert plan.modules[0].name == "Scenario Definition"
    assert plan.milestones[0].name == "Scenarios defined"


def test_failed_planning_restores_current_pointer(boss):
    from director.errors import ModelValidationError
    ok_project, _ = boss.new_project("first", "a real project")
    assert boss.store.get_current() == ok_project.id

    def boom(objective):
        raise ModelValidationError("plan rejected: synthetic failure")
    boss._plan = boom
    with pytest.raises(ModelValidationError):
        boss.new_project("doomed", "this will fail")
    # pointer restored to the surviving project, no dangling orphan id
    assert boss.store.get_current() == ok_project.id
    boss.store.load(boss.store.get_current())   # resolves cleanly


# ------------------------------------------------------- human hold (freeze)
def test_human_can_block_ready_task_and_it_stays_parked():
    from director.core.coherence import apply_delta
    from director.core.taskgraph import ready_tasks, refresh_statuses
    from director.core.types import StateDelta
    p = Project(name="hold")
    t = Task(title="author scenario", status=TaskStatus.READY)
    p.tasks[t.id] = t
    rep = apply_delta(p, StateDelta(trigger="x", payload={
        "task_updates": [{"task_id": t.id, "status": "blocked"}]}),
        actor="human")
    assert rep.status != "blocked"            # the DELTA applied fine
    assert t.status is TaskStatus.BLOCKED
    refresh_statuses(p)                       # nothing auto-resumes a hold
    assert t.status is TaskStatus.BLOCKED
    assert t.id not in [x.id for x in ready_tasks(p)]
    # release is an explicit second delta — straight to ready, or back into
    # the dependency pool (pending) for refresh_statuses to promote
    apply_delta(p, StateDelta(trigger="y", payload={
        "task_updates": [{"task_id": t.id, "status": "pending"}]}),
        actor="human")
    assert t.status is TaskStatus.PENDING
    refresh_statuses(p)                       # no deps -> promoted
    assert t.status is TaskStatus.READY


# --------------------------------------------------- commander reopen orders
def test_human_can_reopen_done_task_but_not_to_running():
    from director.core.coherence import coherence_pass
    from director.core.types import StateDelta
    p = Project(name="reopen")
    t = Task(title="conventions", status=TaskStatus.DONE)
    p.tasks[t.id] = t

    def delta(status):
        return StateDelta(trigger="x", payload={
            "task_updates": [{"task_id": t.id, "status": status}]})

    rep = coherence_pass(p, delta("ready"), actor="human")
    assert not rep.blocked and any("reopened" in w for w in rep.warnings)
    # RUNNING asserts an agent is on it — reopen cannot make that true
    assert coherence_pass(p, delta("running"), actor="human").blocked
    # the Director cannot reopen its own finished work
    assert coherence_pass(p, delta("ready"), actor="director").blocked


def test_milestone_reverts_when_member_reopened():
    from director.core.taskgraph import refresh_milestones
    from director.core.types import Milestone, MilestoneStatus
    p = Project(name="revert")
    t = Task(title="a", role="research", status=TaskStatus.DONE)
    p.tasks[t.id] = t
    ms = Milestone(name="M", task_ids=[t.id])
    p.milestones[ms.id] = ms
    refresh_milestones(p)
    assert ms.status is MilestoneStatus.REACHED
    t.status = TaskStatus.READY                  # commander reopened it
    refresh_milestones(p)
    assert ms.status is MilestoneStatus.PENDING  # no false 'delivered' claim


# -------------------------------------------------- milestone integrity gate
def test_milestone_held_back_without_artifacts():
    from director.core.taskgraph import milestone_blockers, refresh_milestones
    from director.core.types import Milestone, MilestoneStatus
    p = Project(name="ms")
    sim = Task(title="measure coverage", role="simulation",
               status=TaskStatus.DONE)          # done, but no artifact_ids
    doc = Task(title="write notes", role="research", status=TaskStatus.DONE)
    p.tasks = {sim.id: sim, doc.id: doc}
    ms = Milestone(name="Delivered", task_ids=[sim.id, doc.id])
    p.milestones[ms.id] = ms
    assert refresh_milestones(p) == []          # held back, not reached
    assert ms.status is MilestoneStatus.PENDING
    assert any("ungrounded" in b for b in milestone_blockers(p, ms))
    # the moment the artifact exists, the milestone clears
    a = Artifact(title="scenario.json", kind="sim", content="{}")
    p.artifacts[a.id] = a
    sim.artifact_ids = [a.id]
    assert refresh_milestones(p) == [ms]
    assert ms.status is MilestoneStatus.REACHED


def test_milestone_non_artifact_roles_unaffected():
    from director.core.taskgraph import refresh_milestones
    from director.core.types import Milestone, MilestoneStatus
    p = Project(name="ms2")
    t = Task(title="survey", role="research", status=TaskStatus.DONE)
    p.tasks[t.id] = t
    ms = Milestone(name="Foundations", task_ids=[t.id])
    p.milestones[ms.id] = ms
    assert refresh_milestones(p) == [ms]
    assert ms.status is MilestoneStatus.REACHED


# ------------------------------------------------ finalize bundles deliverables
def test_finalize_bundles_real_source_artifacts(boss):
    from director.core.types import Artifact, ArtifactStatus
    project, _ = boss.new_project("d", "ship a verified schema")
    a = Artifact(title="the_schema.json", kind="code",
                 content="SCHEMA_MARKER_42 {real content}",
                 status=ArtifactStatus.CURRENT)
    project.artifacts[a.id] = a
    boss.store.save(project)
    out = boss.finalize(project.id)
    assert out["status"] == "ok"
    final = boss.store.load(project.id).artifacts[out["artifact_id"]]
    # the FINAL bundles the real artifact content, not just a synthesis summary
    assert "SCHEMA_MARKER_42" in final.content
    assert "the_schema.json" in final.content


# ----------------------------------------------------------- token headroom
def test_token_profiles_raised(cfg):
    assert cfg.max_output_tokens >= 8192
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    assert router.profile_for("judge").max_tokens >= 4096
    assert router.profile_for("adversary").max_tokens >= 4096
