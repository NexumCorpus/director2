"""Zero-quota DEMO campaign — a hand-built project with a live command packet
that exercises all three convictions and BOTH check states honestly.

Built with no model call, so the Command Bridge's steering layer can be driven
without spending backend quota. The two VERIFIED options carry real backing
artifacts (standing in for a trusted ISR-simulator oracle run); the HERETIC
option that reframes the domain has no oracle yet, so it is honestly JUDGED.
:func:`build_demo_project` is pure (returns a Project) so a test can assert
the packet is conviction-complete and verifier-honest.
"""

from __future__ import annotations

from ..core.types import (Artifact, ArtifactStatus, Charter, CheckKind,
                          CommandOption, CommandPacket, ConvictionType,
                          DecisionEvent, Milestone, Module, ModuleStatus,
                          ModuleType, PacketStatus, Project, ResponseType,
                          Risk, RiskLevel, Task, TaskStatus)

DEMO_NAME = "DEMO · Coverage Doctrine"


def build_demo_project() -> Project:
    p = Project(name=DEMO_NAME)
    p.charter = Charter(
        objective="Hit ≥70% ISR coverage over the ridge-valley grid, and "
                  "decide which placement doctrine gets us there honestly.")
    mod = Module(name="Doctrine", type=ModuleType.STRATEGY,
                 purpose="Choose the placement doctrine",
                 status=ModuleStatus.ACTIVE)
    p.modules[mod.id] = mod
    t1 = Task(title="Survey placement doctrines", role="research",
              module_id=mod.id, status=TaskStatus.DONE,
              result_summary="Baseline greedy, an evolved placement, and a "
                             "reframed continuous-siting approach all surfaced.")
    t2 = Task(title="Build the chosen mesh", role="code", module_id=mod.id,
              depends_on=[t1.id], status=TaskStatus.PENDING,
              objective="Author scenarios per the chosen doctrine.")
    p.tasks[t1.id] = t1
    p.tasks[t2.id] = t2
    ms = Milestone(name="Doctrine ratified", task_ids=[t1.id])
    p.milestones[ms.id] = ms
    r = Risk(title="Terrain occlusion overestimates coverage",
             level=RiskLevel.HIGH)
    p.risks[r.id] = r

    # backing artifacts — these stand for trusted-oracle (ISR simulator) runs
    base_art = Artifact(
        title="oracle: greedy baseline coverage", kind="verification",
        status=ArtifactStatus.CURRENT,
        content="trusted isr_coverage simulator, ridge-valley 24x16, "
                "greedy placement: measured coverage 68.5% (terrain-aware "
                "Bresenham LOS).")
    evolved_art = Artifact(
        title="oracle: evolved isr_multi coverage", kind="verification",
        status=ArtifactStatus.CURRENT,
        content="trusted isr_coverage simulator, same grid, evolved "
                "isr_multi placement: measured coverage 74.5% — beats greedy "
                "baseline (RDE verdict: beats, quality 1.21).")
    for a in (base_art, evolved_art):
        p.artifacts[a.id] = a

    # a touch of prior history so the disposition is already formed on open
    # (proves drift accumulates across nodes, not just within one pick)
    prior = CommandPacket(
        title="Should we trust the simulator's coverage number as-is?",
        trigger="seed:history", status=PacketStatus.ANSWERED,
        options=[
            CommandOption(key="trust", label="Trust it; it's the oracle",
                          conviction=ConvictionType.DOGMATIC,
                          check=CheckKind.VERIFIED, check_score=1.0,
                          verification_artifact_id=base_art.id),
            CommandOption(key="cross", label="Add an independent cross-check",
                          conviction=ConvictionType.ICONOCLAST,
                          check=CheckKind.JUDGED, check_score=3.0)])
    p.packets[prior.id] = prior
    prior_dec = DecisionEvent(packet_id=prior.id,
                              response_type=ResponseType.SELECT_OPTION,
                              selected_key="cross",
                              rationale="one oracle isn't enough to bet on")
    p.decisions[prior_dec.id] = prior_dec

    pkt = CommandPacket(
        title="Which placement doctrine do we commit to?",
        context="Three doctrines are on the table. Two have actually been run "
                "through the trusted coverage simulator; the third reframes "
                "the problem and has no oracle yet. Your pick steers what the "
                "build agent does next.",
        trigger="milestone:doctrine",
        recommendation_key="evolved",
        rationale="the evolved placement is the only option MEASURED to clear "
                  "70%, and the simulator — not my judgement — says so",
        affected_modules=[mod.id],
        status=PacketStatus.PRESENTED,
        options=[
            CommandOption(
                key="greedy", label="Conform to the greedy baseline",
                description="Use the established greedy max-coverage "
                            "placement — the proven pattern.",
                conviction=ConvictionType.DOGMATIC,
                check=CheckKind.VERIFIED, check_score=68.5,
                verification_artifact_id=base_art.id,
                tradeoffs=["proven, well-understood",
                           "measured below the 70% target"],
                consequences=["target missed by ~1.5 points"],
                risk_impact="unchanged", reversibility="reversible",
                state_delta={"notes": ["doctrine: greedy baseline"]}),
            CommandOption(
                key="evolved",
                label="Adopt the evolved isr_multi placement",
                description="Use the discovered placement that beat greedy in "
                            "the discovery loop — reform the primitive.",
                conviction=ConvictionType.ICONOCLAST,
                check=CheckKind.VERIFIED, check_score=74.5,
                verification_artifact_id=evolved_art.id,
                tradeoffs=["measured above target",
                           "newer, less battle-tested in the field"],
                consequences=["clears 70% with margin",
                              "build proceeds on the evolved layout"],
                risk_impact="lowered", reversibility="reversible",
                state_delta={"notes": ["doctrine: evolved isr_multi"],
                             "task_updates": [{"task_id": t2.id,
                                               "status": "ready"}]}),
            CommandOption(
                key="continuous",
                label="Reject the fixed-grid framing entirely",
                description="Stop placing on a discrete grid; model "
                            "continuous siting with a mixed sensor inventory. "
                            "The problem as posed may be the wrong problem.",
                conviction=ConvictionType.HERETIC,
                check=CheckKind.JUDGED, check_score=3.5,
                tradeoffs=["could dominate both grid options",
                           "no oracle exists for this domain yet"],
                consequences=["needs a new verifier before any claim is real",
                              "pivots the whole modeling approach"],
                risk_impact="raised", reversibility="costly",
                state_delta={"notes": ["doctrine: continuous siting (pivot)"]}),
        ])
    p.packets[pkt.id] = pkt

    pkt2 = CommandPacket(
        title="What bar must the final deliverable clear?",
        context="Once the mesh is built, how high do we set the deliverable "
                "bar? Only one of these has a measured precedent.",
        trigger="milestone:doctrine", recommendation_key="pareto",
        rationale="the Pareto trade space already beat the single-point bar "
                  "in the discovery loop — measured, not asserted",
        affected_modules=[mod.id], status=PacketStatus.PRESENTED,
        options=[
            CommandOption(
                key="standard", label="Match the standard ISR report",
                description="Produce the conventional single-scenario "
                            "coverage report — the established deliverable.",
                conviction=ConvictionType.DOGMATIC, check=CheckKind.JUDGED,
                check_score=3.0,
                tradeoffs=["familiar to reviewers", "no trade-space insight"],
                consequences=["fast sign-off, thin analysis"],
                risk_impact="unchanged", reversibility="reversible",
                state_delta={"notes": ["bar: standard report"]}),
            CommandOption(
                key="pareto",
                label="Exceed it with a measured Pareto trade space",
                description="Ship a coverage/redundancy/cost frontier — the "
                            "isr_multi approach that beat the baseline.",
                conviction=ConvictionType.ICONOCLAST,
                check=CheckKind.VERIFIED, check_score=1.21,
                verification_artifact_id=evolved_art.id,
                tradeoffs=["decision-grade trade space",
                           "more synthesis work"],
                consequences=["commander sees the whole frontier"],
                risk_impact="lowered", reversibility="reversible",
                state_delta={"notes": ["bar: Pareto trade space"]}),
            CommandOption(
                key="live",
                label="Reject a static report — ship a live model",
                description="No document at all; hand over the runnable "
                            "simulator so any placement can be checked live.",
                conviction=ConvictionType.HERETIC, check=CheckKind.JUDGED,
                check_score=2.5,
                tradeoffs=["maximal flexibility",
                           "no precedent; unclear acceptance"],
                consequences=["reframes the deliverable entirely"],
                risk_impact="raised", reversibility="costly",
                state_delta={"notes": ["bar: live model (pivot)"]}),
        ])
    p.packets[pkt2.id] = pkt2

    # third packet showcases the VERIFIED_PARTIAL tier with a REAL property
    # run: the example validates against the (independently-authored) schema —
    # a trusted necessary-condition check, force-to-fail proven. Not green;
    # amber "1/1 trusted", because validity is not truth.
    import json
    from ..verify.properties import run_properties
    # value-CONSTRAINED schema (minimum/minItems/pattern) so schema_valid
    # discriminates wrong VALUES, not just shape — a garbage-but-shaped sibling
    # (w:-999) violates minimum and is rejected, earning an HONEST partial.
    schema = {"type": "object", "required": ["w", "h", "sensors"],
              "properties": {"w": {"type": "integer", "minimum": 1,
                                   "maximum": 256},
                             "h": {"type": "integer", "minimum": 1,
                                   "maximum": 256},
                             "sensors": {"type": "array", "minItems": 1,
                                         "items": {
                                 "type": "object", "required": ["id"],
                                 "properties": {"id": {
                                     "type": "string", "minLength": 1,
                                     "pattern": "^s[0-9]+$"}}}}}}
    example = {"w": 24, "h": 16, "sensors": [{"id": "s1"}, {"id": "s2"}]}
    report = run_properties(example, ["schema_valid"], ref=schema,
                            ref_independent=True)   # schema is upstream-authored
    # the graded deliverable as its own artifact, so the report can be SIGNED
    # bound to it (id + content) — matching the live path's binding
    example_art = Artifact(title="scenario example (graded)", kind="json",
                           status=ArtifactStatus.CURRENT,
                           content=json.dumps(example))
    p.artifacts[example_art.id] = example_art
    prop_art = Artifact(title="property_report: example ⊨ schema",
                        kind="property_report", status=ArtifactStatus.CURRENT,
                        content=json.dumps(report),
                        provenance={"report": report,
                                    "deliverable": example_art.id,
                                    "checker": "schema_valid (trusted)"})
    p.artifacts[prop_art.id] = prop_art
    pkt3 = CommandPacket(
        title="How firm is the schema deliverable?",
        context="One option is partially VERIFIED by a trusted checker — the "
                "example provably validates against the schema — but validity "
                "is not truth, so it is amber, not green.",
        trigger="milestone:doctrine", recommendation_key="accept",
        affected_modules=[mod.id], status=PacketStatus.PRESENTED,
        options=[
            CommandOption(
                key="accept", label="Accept it — example validates the schema",
                description="A trusted necessary-condition checker ran: the "
                            "example conforms to the independently-authored "
                            "schema. Necessary, not sufficient.",
                conviction=ConvictionType.DOGMATIC,
                check=CheckKind.VERIFIED_PARTIAL,
                verification_artifact_id=prop_art.id,
                sub_claims_verified=report["n_passed"],
                sub_claims_total=report["n_total"],
                tradeoffs=["structurally sound", "validity is not truth"],
                consequences=["ship the structurally-checked schema"],
                risk_impact="lowered", reversibility="reversible",
                state_delta={"notes": ["schema: accepted (partial-verified)"]}),
            CommandOption(
                key="harden", label="Add coverage-invariant property tests",
                description="Write more trusted checkers before accepting.",
                conviction=ConvictionType.ICONOCLAST, check=CheckKind.JUDGED,
                check_score=3.0,
                tradeoffs=["stronger partial verification", "more work"],
                consequences=["raises the trusted-check count"],
                risk_impact="lowered", reversibility="reversible",
                state_delta={"notes": ["schema: harden checks"]}),
            CommandOption(
                key="truth", label="Reject validity — only field truth counts",
                description="A schema-valid scenario can be operationally "
                            "worthless; demand operational ground truth.",
                conviction=ConvictionType.HERETIC, check=CheckKind.JUDGED,
                check_score=2.0,
                tradeoffs=["honest about validity≠truth",
                           "no oracle for operational truth yet"],
                consequences=["reframes the acceptance bar"],
                risk_impact="raised", reversibility="costly",
                state_delta={"notes": ["schema: demand operational truth"]}),
        ])
    p.packets[pkt3.id] = pkt3
    return p


def seed_demo(store) -> str:
    """Replace any existing DEMO project with a fresh one. Returns its id."""
    for row in store.list_projects():
        if row.get("name") == DEMO_NAME:
            import shutil
            shutil.rmtree(store.project_dir(row["id"]), ignore_errors=True)
    project = build_demo_project()
    # sign the demo's property_report BOUND to its carrying artifact + graded
    # deliverable (matching the live path) so its partial badge survives the
    # display boundary's binding check (else honestly downgraded to JUDGED)
    from ..verify.signing import bound_payload, content_sha
    from ..verify.signing import sign as _sign_report
    secret = store.cfg.report_secret()
    for art in project.artifacts.values():
        if art.kind != "property_report":
            continue
        prov = art.provenance or {}
        rep, did = prov.get("report"), prov.get("deliverable")
        deliv = project.artifacts.get(did) if did else None
        if isinstance(rep, dict) and deliv is not None:
            art.provenance["report_sig"] = _sign_report(
                bound_payload(rep, report_id=art.id, deliverable_id=did,
                              deliverable_sha=content_sha(deliv.content or "")),
                secret)
    # create() makes a fresh id+dir and sets current; keep our built id/state
    # by saving directly instead
    (store.project_dir(project.id) / "artifacts").mkdir(
        parents=True, exist_ok=True)
    store.save(project)
    return project.id
