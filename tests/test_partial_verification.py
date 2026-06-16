"""VERIFIED_PARTIAL — the trusted-checker partial-verification tier.

The boundary made buildable: a check earns a place above JUDGED only when a
TRUSTED necessary-condition checker passes, is proven to reject a bad sibling
(force-to-fail / anti-vacuity), and uses a reference of independent lineage.
Everything else degrades to JUDGED. These tests are the gate."""

import json

from director.core.convictions import (honest_check, verifier_favored_key,
                                        verifier_honesty_violations)
from director.core.types import (Artifact, CheckKind, CommandOption,
                                 CommandPacket, Project)
from director.verify.properties import (CHECKERS, partial_bundle_ok,
                                        run_properties)

# value-CONSTRAINED schema: schema_valid can discriminate wrong values
SCHEMA = {"type": "object", "required": ["w", "h", "sensors"],
          "properties": {"w": {"type": "integer", "minimum": 1, "maximum": 256},
                         "h": {"type": "integer", "minimum": 1, "maximum": 256},
                         "sensors": {"type": "array", "minItems": 1, "items": {
                             "type": "object", "required": ["id"],
                             "properties": {"id": {"type": "string",
                                                   "pattern": "^s[0-9]+$"}}}}}}
# pure-SHAPE schema: types only, no value constraints — must NOT earn a count
PURE_SHAPE = {"type": "object", "required": ["w", "h", "sensors"],
              "properties": {"w": {"type": "integer"}, "h": {"type": "integer"},
                             "sensors": {"type": "array", "items": {
                                 "type": "object", "required": ["id"],
                                 "properties": {"id": {"type": "string"}}}}}}
EXAMPLE = {"w": 24, "h": 16, "sensors": [{"id": "s1"}, {"id": "s2"}]}


def _report_artifact(report):
    a = Artifact(title="property_report", kind="property_report",
                 content=json.dumps(report), provenance={"report": report})
    return a


def _opt(key, check, art_id="", score=None):
    return CommandOption(key=key, label=key, conviction="iconoclast",
                         check=check, verification_artifact_id=art_id,
                         check_score=score)


# ----------------------------------------------------- force-to-fail / vacuity
def test_trusted_check_that_force_to_fails_is_counted():
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    assert rep["n_passed"] == 1 and rep["force_to_fail_ok"]
    assert partial_bundle_ok(rep)


def test_vacuous_check_is_not_counted():
    # 'parses' on a dict can never be made to fail by mutation (every mutant
    # still parses) -> it is UNCHECKABLE here, must not count toward partial
    rep = run_properties(EXAMPLE, ["parses"])
    parses = [c for c in rep["checks"] if c["name"] == "parses"][0]
    assert parses["passed"] and not parses["force_to_fail_ok"]
    assert rep["n_passed"] == 0
    assert not partial_bundle_ok(rep)


def test_pure_shape_schema_does_not_count():
    # RED-TEAM FIX (vacuity escape): a value-blind schema passes a garbage-but-
    # shaped sibling, so it rejects NO shape-preserving mutant -> uncounted.
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=PURE_SHAPE,
                         ref_independent=True)
    assert rep["n_passed"] == 0 and not partial_bundle_ok(rep)


def test_value_constrained_schema_rejects_shape_preserving_garbage():
    # the exact red-team payload: schema-SHAPED but garbage VALUES
    garbage = {"w": -999, "h": 0, "sensors": [{"id": "WRONG"}]}
    from director.verify.properties import _validate_schema
    assert not _validate_schema(garbage, SCHEMA)[0]      # caught by constraints
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    assert rep["n_passed"] == 1 and partial_bundle_ok(rep)


def test_forged_report_in_content_is_not_trusted():
    # RED-TEAM FIX (forgeable bundle): a report parked in agent-writable
    # CONTENT (not engine-stamped provenance) must NOT back the badge.
    forged = {"trusted": True, "lineage_ok": True, "force_to_fail_ok": True,
              "n_passed": 5, "n_total": 5}
    art = Artifact(title="property_report", kind="property_report",
                   content=json.dumps(forged), provenance={})   # no provenance
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, art.id)
    assert honest_check(opt, {art.id: art})[0] == CheckKind.JUDGED


def test_badge_fraction_must_match_report():
    # RED-TEAM FIX (decorative fraction): displayed N/M must equal the report
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    art = _report_artifact(rep)
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, art.id)
    opt.sub_claims_verified, opt.sub_claims_total = 9, 9   # lie about coverage
    assert honest_check(opt, {art.id: art})[0] == CheckKind.JUDGED
    opt.sub_claims_verified, opt.sub_claims_total = rep["n_passed"], rep["n_total"]
    assert honest_check(opt, {art.id: art})[0] == CheckKind.VERIFIED_PARTIAL


def test_check_with_nothing_to_check_fails():
    # cited_ids_resolve on a target citing no ids is vacuous -> fails, honest
    rep = run_properties(EXAMPLE, ["cited_ids_resolve"], ref=set(),
                         ref_independent=True)
    assert rep["n_passed"] == 0 and not partial_bundle_ok(rep)


def test_totals_conserved_real_oracle():
    good = {"total": 6, "parts": [1, 2, 3]}
    bad = {"total": 99, "parts": [1, 2, 3]}
    assert run_properties(good, ["totals_conserved"])["n_passed"] == 1
    assert run_properties(bad, ["totals_conserved"])["n_passed"] == 0


# -------------------------------------------------------------- lineage guard
def test_dependent_lineage_blocks_partial():
    # same-author reference (ref_independent=False) cannot back a partial
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=False)
    assert rep["n_passed"] == 1            # the check itself passed
    assert not partial_bundle_ok(rep)      # but lineage kills the bundle


# ------------------------------------------------------- honest_check display
def test_honest_check_keeps_backed_partial():
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    art = _report_artifact(rep)
    opt = _opt("b", CheckKind.VERIFIED_PARTIAL, art.id, score=1)
    kind, _ = honest_check(opt, {art.id: art})
    assert kind == CheckKind.VERIFIED_PARTIAL


def test_honest_check_downgrades_unbacked_partial():
    # cites nothing -> JUDGED
    assert honest_check(_opt("a", CheckKind.VERIFIED_PARTIAL))[0] \
        == CheckKind.JUDGED
    # cites an artifact whose bundle is invalid (vacuous) -> JUDGED
    bad = _report_artifact(run_properties(EXAMPLE, ["parses"]))
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, bad.id)
    assert honest_check(opt, {bad.id: bad})[0] == CheckKind.JUDGED


# ------------------------------------------------------- build-time gate
def test_partial_without_valid_bundle_fails_the_build():
    p = Project(name="x")
    pkt = CommandPacket(title="t", options=[
        _opt("a", CheckKind.VERIFIED_PARTIAL)])   # no artifact at all
    assert verifier_honesty_violations(pkt, p)
    # invalid (vacuous) bundle also fails
    bad = _report_artifact(run_properties(EXAMPLE, ["parses"]))
    p.artifacts[bad.id] = bad
    pkt2 = CommandPacket(title="t", options=[
        _opt("a", CheckKind.VERIFIED_PARTIAL, bad.id)])
    assert verifier_honesty_violations(pkt2, p)


def test_valid_partial_passes_the_build():
    p = Project(name="x")
    good = _report_artifact(run_properties(EXAMPLE, ["schema_valid"],
                                           ref=SCHEMA, ref_independent=True))
    p.artifacts[good.id] = good
    pkt = CommandPacket(title="t", options=[
        _opt("a", CheckKind.VERIFIED_PARTIAL, good.id)])
    assert verifier_honesty_violations(pkt, p) == []


# ----------------------------------------------- partial never outranks full
def test_star_tracks_full_verified_only():
    p = Project(name="x")
    a = Artifact(title="oracle", kind="verification", content="m")
    p.artifacts[a.id] = a
    good = _report_artifact(run_properties(EXAMPLE, ["schema_valid"],
                                           ref=SCHEMA, ref_independent=True))
    p.artifacts[good.id] = good
    pkt = CommandPacket(title="t", options=[
        _opt("a", CheckKind.VERIFIED_PARTIAL, good.id, score=9),
        _opt("b", CheckKind.VERIFIED, a.id, score=1)])
    # the full-verified option is favored even with a lower score
    assert verifier_favored_key(pkt, p) == "b"


def test_reachability_moat_llm_cannot_propose_a_check():
    # the forgery attacks don't land because no LLM/agent path can set an
    # option's check tier. Pin that: the LLM's OptionOut schema carries
    # conviction (proposable) but NOT check / verification_artifact_id.
    from director.core.director import OptionOut
    fields = set(OptionOut.model_fields)
    assert "conviction" in fields
    assert "check" not in fields and "verification_artifact_id" not in fields
    from director.agents.base import ArtifactOut
    # and agents cannot stamp provenance (only title/kind/content)
    assert "provenance" not in set(ArtifactOut.model_fields)


def _boss(cfg):
    from director.agents.runner import SubAgentRunner
    from director.core.director import Director
    from director.core.state import ProjectStore
    from director.llm.mock import MockBackend
    from director.llm.router import LLMRouter
    from director.verify import make_default_registry
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    reg = make_default_registry()
    return Director(cfg, store, router, reg, SubAgentRunner(cfg, router, reg))


def _wiring_project(cfg):
    from director.core.types import AgentRun, Project, Task, TaskStatus
    p = Project(name="wiring")
    schema_task = Task(title="define schema", role="code",
                       status=TaskStatus.DONE)
    schema_art = Artifact(title="scenario.schema.json", kind="code",
                          content=json.dumps(SCHEMA), task_id=schema_task.id)
    schema_task.artifact_ids = [schema_art.id]
    p.artifacts[schema_art.id] = schema_art
    p.tasks[schema_task.id] = schema_task
    return p, schema_task, AgentRun


def test_real_deliverable_earns_partial_through_director(cfg):
    # the LIVE path: a downstream task's deliverable, validated against an
    # UPSTREAM task's schema (independent lineage), earns VERIFIED_PARTIAL via
    # the director's ingestion — not a hand-built demo option.
    from director.core.types import Task
    boss = _boss(cfg)
    p, schema_task, AgentRun = _wiring_project(cfg)
    ex = Task(title="author example", role="code",
              depends_on=[schema_task.id], properties=["schema_valid"])
    p.tasks[ex.id] = ex
    run = AgentRun(task_id=ex.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, ex, run.id, {"artifacts": [
        {"title": "example.json", "kind": "json",
         "content": json.dumps(EXAMPLE)}]})
    deliv = [a for a in p.artifacts.values() if a.title == "example.json"][0]
    assert deliv.provenance.get("partial", {}).get("n_passed") == 1
    # self-describing badge: it names WHICH necessary condition was verified
    assert deliv.provenance["partial"]["checks"] == ["schema_valid"]
    assert any(a.kind == "property_report" for a in p.artifacts.values())


def test_real_garbage_deliverable_earns_no_partial(cfg):
    from director.core.types import Task
    boss = _boss(cfg)
    p, schema_task, AgentRun = _wiring_project(cfg)
    bad = Task(title="author garbage", role="code",
               depends_on=[schema_task.id], properties=["schema_valid"])
    p.tasks[bad.id] = bad
    run = AgentRun(task_id=bad.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, bad, run.id, {"artifacts": [
        {"title": "bad.json", "kind": "json",
         "content": json.dumps({"w": -999, "h": 0,
                                "sensors": [{"id": "WRONG"}]})}]})
    deliv = [a for a in p.artifacts.values() if a.title == "bad.json"][0]
    assert "partial" not in deliv.provenance       # garbage values rejected


def test_no_upstream_schema_means_no_partial(cfg):
    # schema_valid declared but no independent upstream schema -> nothing to
    # verify against -> honestly no partial (not a self-graded pass)
    from director.core.types import AgentRun, Project, Task
    boss = _boss(cfg)
    p = Project(name="lonely")
    t = Task(title="author example", role="code", properties=["schema_valid"])
    p.tasks[t.id] = t
    run = AgentRun(task_id=t.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, t, run.id, {"artifacts": [
        {"title": "example.json", "kind": "json",
         "content": json.dumps(EXAMPLE)}]})
    deliv = [a for a in p.artifacts.values() if a.title == "example.json"][0]
    assert "partial" not in deliv.provenance


# ----------------------------------------- report signing (tamper-evidence)
def test_report_signature_roundtrip():
    from director.verify.signing import sign, verify
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    secret = b"x" * 32
    sig = sign(rep, secret)
    assert verify(rep, sig, secret)
    tampered = dict(rep, n_passed=9)
    assert not verify(tampered, sig, secret)          # any edit breaks it
    assert not verify(rep, sig, b"y" * 32)            # wrong secret
    assert not verify(rep, "", secret)                # fail-closed: no sig
    assert not verify(rep, sig, b"")                  # fail-closed: no secret


def _signed_report_artifact(report, deliverable, secret):
    """A property_report artifact whose sig is BOUND to its own id + the graded
    deliverable (matching the live stamp path)."""
    from director.verify.signing import bound_payload, content_sha, sign
    r = Artifact(title="property_report", kind="property_report",
                 content=json.dumps(report),
                 provenance={"report": report, "deliverable": deliverable.id})
    r.provenance["report_sig"] = sign(
        bound_payload(report, report_id=r.id, deliverable_id=deliverable.id,
                      deliverable_sha=content_sha(deliverable.content)), secret)
    return r


def test_report_binding_ok_roundtrip():
    from director.verify.signing import report_binding_ok
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    d = Artifact(title="d", kind="json", content=json.dumps(EXAMPLE))
    secret = b"k" * 32
    art = _signed_report_artifact(rep, d, secret)
    sig = art.provenance["report_sig"]
    assert report_binding_ok(report=rep, sig=sig, report_id=art.id,
                             deliverable_id=d.id, deliverable_content=d.content,
                             secret=secret)
    # wrong carrying artifact id, wrong deliverable id, or changed content break it
    assert not report_binding_ok(report=rep, sig=sig, report_id="OTHER",
                                 deliverable_id=d.id,
                                 deliverable_content=d.content, secret=secret)
    assert not report_binding_ok(report=rep, sig=sig, report_id=art.id,
                                 deliverable_id="OTHER",
                                 deliverable_content=d.content, secret=secret)
    assert not report_binding_ok(report=rep, sig=sig, report_id=art.id,
                                 deliverable_id=d.id,
                                 deliverable_content="{}", secret=secret)


def test_honest_check_enforces_binding_at_persisted_boundary():
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    secret = b"s" * 32
    d = Artifact(title="example.json", kind="json", content=json.dumps(EXAMPLE))
    art = _signed_report_artifact(rep, d, secret)
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, art.id)
    arts = {art.id: art, d.id: d}
    assert honest_check(opt, arts)[0] == CheckKind.VERIFIED_PARTIAL   # in-proc
    assert honest_check(opt, arts, secret=secret)[0] \
        == CheckKind.VERIFIED_PARTIAL                                  # bound ok
    # unsigned report -> JUDGED at the boundary
    bare = Artifact(title="property_report", kind="property_report",
                    content=json.dumps(rep),
                    provenance={"report": rep, "deliverable": d.id})
    opt2 = _opt("b", CheckKind.VERIFIED_PARTIAL, bare.id)
    assert honest_check(opt2, {bare.id: bare, d.id: d},
                        secret=secret)[0] == CheckKind.JUDGED


def test_signed_report_cannot_be_replayed_onto_garbage(cfg):
    # RED-TEAM FIX (bearer-token replay): copying a valid signed report onto a
    # NEW artifact bound to a garbage deliverable must NOT survive the boundary,
    # and integrity must flag it INVALID.
    from director.core.integrity import integrity_violations, report_integrity
    secret = cfg.report_secret()
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    good = Artifact(title="good", kind="json", content=json.dumps(EXAMPLE))
    legit = _signed_report_artifact(rep, good, secret)
    # attacker: garbage deliverable + a forged report artifact reusing the sig
    garbage = Artifact(title="garbage", kind="json",
                       content=json.dumps({"w": -999, "h": 0,
                                           "sensors": [{"id": "X"}]}))
    forged = Artifact(title="property_report", kind="property_report",
                      content=json.dumps(rep),
                      provenance={"report": rep, "deliverable": garbage.id,
                                  "report_sig": legit.provenance["report_sig"]})
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, forged.id)
    arts = {good.id: good, legit.id: legit, garbage.id: garbage,
            forged.id: forged}
    assert honest_check(opt, arts, secret=secret)[0] == CheckKind.JUDGED
    p = Project(name="x")
    p.artifacts.update(arts)
    assert integrity_violations(report_integrity(p, secret))   # forged flagged


def test_content_swap_under_valid_sig_is_rejected(cfg):
    # RED-TEAM FIX: rewriting the graded deliverable's content after signing must
    # break the binding (the sig covers the deliverable's content hash).
    from director.core.integrity import integrity_violations, report_integrity
    secret = cfg.report_secret()
    rep = run_properties(EXAMPLE, ["schema_valid"], ref=SCHEMA,
                         ref_independent=True)
    d = Artifact(title="d", kind="json", content=json.dumps(EXAMPLE))
    art = _signed_report_artifact(rep, d, secret)
    opt = _opt("a", CheckKind.VERIFIED_PARTIAL, art.id)
    arts = {art.id: art, d.id: d}
    assert honest_check(opt, arts, secret=secret)[0] \
        == CheckKind.VERIFIED_PARTIAL                       # before tamper
    d.content = json.dumps({"w": -999, "h": 0, "sensors": []})   # swap content
    assert honest_check(opt, arts, secret=secret)[0] == CheckKind.JUDGED
    p = Project(name="x")
    p.artifacts.update(arts)
    assert integrity_violations(report_integrity(p, secret))


def test_live_stamp_is_bound_signed(cfg):
    from director.core.types import Task
    from director.verify.signing import report_binding_ok
    boss = _boss(cfg)
    p, schema_task, AgentRun = _wiring_project(cfg)
    ex = Task(title="author example", role="code",
              depends_on=[schema_task.id], properties=["schema_valid"])
    p.tasks[ex.id] = ex
    run = AgentRun(task_id=ex.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, ex, run.id, {"artifacts": [
        {"title": "example.json", "kind": "json",
         "content": json.dumps(EXAMPLE)}]})
    rep_art = [a for a in p.artifacts.values()
               if a.kind == "property_report"][0]
    deliv = p.artifacts[rep_art.provenance["deliverable"]]
    assert report_binding_ok(
        report=rep_art.provenance["report"],
        sig=rep_art.provenance["report_sig"], report_id=rep_art.id,
        deliverable_id=deliv.id, deliverable_content=deliv.content,
        secret=cfg.report_secret())


def test_all_library_checkers_are_trusted_named():
    # the library is a fixed, reviewed set — no per-task synthesis
    assert set(CHECKERS) >= {"parses", "schema_valid", "cited_ids_resolve",
                             "totals_conserved", "nonempty"}


# ------------------------------------------- plan-level auto-declaration
def _plan_with_schema_pair():
    # a planned project that pairs a schema task before a data task which
    # declares schema_valid (+ a bogus checker the schema must drop)
    from director.core.director import CharterOut, ModuleOut, PlanOut, TaskOut
    return PlanOut(
        charter=CharterOut(objective="ship a checked scenario"),
        modules=[ModuleOut(name="build")],
        tasks=[
            TaskOut(title="define the JSON schema", role="code", module="build",
                    objective="emit a value-constrained draft-07 JSON schema"),
            TaskOut(title="author the scenario", role="code", module="build",
                    objective="emit a JSON instance",
                    depends_on=["define the JSON schema"],
                    properties=["schema_valid", "bogus_checker"]),
        ])


def test_taskout_filters_unknown_checker_names():
    # the planner can only SELECT from the reviewed library; invented names
    # are dropped at the schema boundary before they reach Task.properties
    from director.core.director import TaskOut
    t = TaskOut(title="x", properties=["schema_valid", "nope", "parses"])
    assert t.properties == ["schema_valid", "parses"]
    assert TaskOut(title="y", properties="nonempty").properties == ["nonempty"]
    assert TaskOut(title="z", properties="garbage").properties == []


def test_plan_ingestion_carries_declared_properties(cfg):
    boss = _boss(cfg)
    p = boss.store.create("plan-decl")
    boss._ingest_plan(p, "ship a checked scenario", _plan_with_schema_pair())
    by_title = {t.title: t for t in p.tasks.values()}
    schema_t = by_title["define the JSON schema"]
    author_t = by_title["author the scenario"]
    assert author_t.properties == ["schema_valid"]    # data task: no code grounding
    assert schema_t.id in author_t.depends_on         # independent-lineage ref
    # the schema task is role=code with no data-check, so it auto-gets execution
    # grounding (harmless on a JSON deliverable — runtime-filtered to no-op)
    assert set(schema_t.properties) == {"python_parses", "code_runs"}


def test_plan_declared_schema_valid_earns_partial_end_to_end(cfg):
    # the capstone: a PLANNED (not hand-wired) project earns VERIFIED_PARTIAL
    # purely from the planner's declaration flowing through ingestion.
    from director.core.types import AgentRun
    boss = _boss(cfg)
    p = boss.store.create("plan-decl-live")
    boss._ingest_plan(p, "ship a checked scenario", _plan_with_schema_pair())
    by_title = {t.title: t for t in p.tasks.values()}
    schema_t = by_title["define the JSON schema"]
    author_t = by_title["author the scenario"]
    run1 = AgentRun(task_id=schema_t.id, role="code", backend="mock",
                    model="mock")
    p.runs[run1.id] = run1
    boss._ingest_output(p, schema_t, run1.id, {"artifacts": [
        {"title": "scenario.schema.json", "kind": "code",
         "content": json.dumps(SCHEMA)}]})
    run2 = AgentRun(task_id=author_t.id, role="code", backend="mock",
                    model="mock")
    p.runs[run2.id] = run2
    boss._ingest_output(p, author_t, run2.id, {"artifacts": [
        {"title": "scenario.json", "kind": "json",
         "content": json.dumps(EXAMPLE)}]})
    deliv = [a for a in p.artifacts.values() if a.title == "scenario.json"][0]
    assert deliv.provenance.get("partial", {}).get("n_passed") == 1


def test_self_citation_earns_no_partial(cfg):
    # RED-TEAM FIX (self-citation escape): a deliverable that cites a project-
    # owned id — even its OWN task id — must NOT earn a partial. The project's
    # id namespace is the SAME lineage as the author; resolving an id you can
    # see is self-referential, not independent verification.
    from director.core.types import AgentRun, Project, Task
    boss = _boss(cfg)
    p = Project(name="selfcite")
    t = Task(title="cite myself", role="code", properties=["cited_ids_resolve"])
    p.tasks[t.id] = t
    run = AgentRun(task_id=t.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, t, run.id, {"artifacts": [
        {"title": "cites.json", "kind": "json",
         "content": json.dumps({"refs": [t.id]})}]})   # cites its OWN task id
    deliv = [a for a in p.artifacts.values() if a.title == "cites.json"][0]
    assert "partial" not in deliv.provenance


def test_upstream_schema_independence_is_author_derived(cfg):
    # independence is DERIVED from the schema artifact's recorded author
    # (task_id + run_id) vs the deliverable's — not merely "a different dep".
    from director.core.types import Artifact, Project, Task
    boss = _boss(cfg)
    p = Project(name="auth")
    dep = Task(title="schema", role="code")
    inst = Task(title="inst", role="code", depends_on=[dep.id])
    sa = Artifact(title="s", kind="code", content=json.dumps(SCHEMA),
                  task_id=dep.id, provenance={"run_id": "R1"})
    dep.artifact_ids = [sa.id]
    deliv = Artifact(title="d", kind="json", content=json.dumps(EXAMPLE),
                     task_id=inst.id, provenance={"run_id": "R2"})
    inst.artifact_ids = [deliv.id]
    p.tasks[dep.id], p.tasks[inst.id] = dep, inst
    p.artifacts[sa.id], p.artifacts[deliv.id] = sa, deliv
    schema, indep = boss._upstream_schema(p, inst, deliv)
    assert schema is not None and indep is True            # R1 != R2
    # if the schema claims the SAME run as the deliverable, it is NOT independent
    sa.provenance = {"run_id": "R2"}
    _, indep2 = boss._upstream_schema(p, inst, deliv)
    assert indep2 is False


def test_cross_reference_to_other_task_earns_partial(cfg):
    # the principled restoration: cited_ids_resolve EXCLUDES the author's own
    # task+artifacts, so a citation that resolves points at a REAL, OTHER-
    # authored entity (independent lineage). That is a genuine structural-
    # integrity guarantee — "this deliverable's references are not dangling" —
    # and honestly earns an amber partial.
    from director.core.types import AgentRun, Project, Task, TaskStatus
    boss = _boss(cfg)
    p = Project(name="crossref")
    anchor = Task(title="upstream anchor", role="code", status=TaskStatus.DONE)
    p.tasks[anchor.id] = anchor
    citer = Task(title="cite the anchor", role="code",
                 properties=["cited_ids_resolve"])
    p.tasks[citer.id] = citer
    run = AgentRun(task_id=citer.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, citer, run.id, {"artifacts": [
        {"title": "cites.json", "kind": "json",
         "content": json.dumps({"refs": [anchor.id]})}]})   # OTHER task's id
    deliv = [a for a in p.artifacts.values() if a.title == "cites.json"][0]
    assert deliv.provenance.get("partial", {}).get("n_passed") == 1
    assert "cited_ids_resolve" in deliv.provenance["partial"]["checks"]


def test_intrinsic_check_earns_partial_without_lineage(cfg):
    # ACCEPTED BY DESIGN (red-team verified working-as-intended): totals_conserved
    # is REFERENCE-FREE intrinsic verification (arithmetic conservation) — a
    # legitimate trusted necessary condition with no lineage question. It
    # honestly earns an amber partial with no upstream dependency; the badge
    # certifies ONLY that one necessary condition, never the rest of the
    # deliverable. This test pins the behavior so lineage tightening for
    # reference-bearing checks never silently breaks intrinsic ones.
    from director.core.types import AgentRun, Project, Task
    boss = _boss(cfg)
    p = Project(name="intrinsic")
    t = Task(title="emit a budget", role="code",
             properties=["totals_conserved"])
    p.tasks[t.id] = t
    run = AgentRun(task_id=t.id, role="code", backend="mock", model="mock")
    p.runs[run.id] = run
    boss._ingest_output(p, t, run.id, {"artifacts": [
        {"title": "budget.json", "kind": "json",
         "content": json.dumps({"total": 100, "parts": [30, 70]})}]})
    deliv = [a for a in p.artifacts.values() if a.title == "budget.json"][0]
    assert deliv.provenance.get("partial", {}).get("n_passed") == 1
