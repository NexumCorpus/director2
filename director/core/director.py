"""The Director — strategic orchestrator that owns coherence.

Lifecycle it drives (the command loop):

    new_project(objective)
        └─ LLM plan → Charter + Modules + Task graph + Milestones + Risks
        └─ first Command Packet (posture decision) PRESENTED
    decide(packet, option)
        └─ DecisionEvent → StateDelta → coherence pass → applied
        └─ bounded auto-advance (policy-gated)
    advance()
        └─ ready tasks → parallel verified subagents → ingest artifacts/
           risks/lessons → milestones refresh → packets on forks
    finalize()
        └─ synthesis agent over accepted artifacts → final report

Philosophy guardrails (from the Director 1.0 doctrine): consequential choices
surface as Command Packets; auto-advance is bounded and stops whenever a
packet is open; verification failures route to human judgment, never silently
through.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator, model_validator

from ..agents.base import AgentSpec
from ..agents.runner import SubAgentRunner
from ..agents.roles import role_names
from ..config import Config
from ..errors import (CoherenceBlockedError, ModelError, ModelValidationError,
                      NotFoundError)
from ..llm.router import LLMRouter
from ..logging_setup import get_logger
from ..verify import VerifierRegistry
from .coherence import apply_delta, coherence_pass
from .integrity import integrity_violations, report_integrity
from .convictions import (conviction_rank, conviction_read,
                          evaluate_packet_coherence, honest_check,
                          verifier_favored_key)
from .state import ProjectStore
from .taskgraph import (detect_cycles, graph_summary, ready_tasks,
                        refresh_milestones, refresh_statuses)
from .types import (AgentRun, Artifact, AuditEvent, Charter, CommandOption,
                    CommandPacket, DecisionEvent, Milestone, Module,
                    ModuleStatus, ModuleType, PacketStatus, Project,
                    ResponseType, Risk, RiskLevel, StateDelta, Task,
                    TaskStatus, utcnow)
from .valence import check_clear_rule, compute_body, evaluate_scream

log = get_logger("director")


# --------------------------------------------------------------------------- #
# LLM plan schemas
# --------------------------------------------------------------------------- #

class CharterOut(BaseModel):
    objective: str
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    risk_posture: str = "medium"

    _listify = field_validator(
        "scope_in", "scope_out", "success_criteria", "constraints",
        "deliverables", mode="before")(lambda v: [v] if isinstance(v, str) else v)


#: keyword → role inference. The planner often lazily labels everything
#: "research"; when it does, recover the right specialist from the task wording
#: (live finding: every task came back role=research, so code/test never ran).
_ROLE_RULES = [
    # simulation BEFORE test: "execute/run" is a run task even if it says "tests"
    # (the test role WRITES tests; executing them is simulation)
    ("simulation", ("simulate", "simulation", "benchmark", "execute the",
                    "execute tests", "run the test", "run the sim")),
    ("test", ("test suite", "pytest", "unit test", "adversarial test",
              " tests ", "test cases")),
    ("review", ("review", "audit", "integration report", "evaluate the",
                "assess the")),
    ("synthesis", ("synthesize", "integrate the", "merge the",
                   "final report", "consolidate")),
    ("code", ("implement", "reference implementation", "write the code",
              "json schema", "build the", "define the schema", "script",
              " function", " class ", "module that")),
]


_TRANSIENT_MARKERS = ("timed out", "timeout", "modeltransienterror",
                      "rate limit", "ratelimit", "429", "temporarily")


def _is_transient_failure(err: str) -> bool:
    """True for infra failures (timeout/rate-limit) that are worth retrying —
    NOT content/validation failures, which should cap at max_attempts."""
    s = (err or "").lower()
    return any(m in s for m in _TRANSIENT_MARKERS)


def _ensure_recommendation(packet) -> None:
    """A packet must always carry a valid recommendation_key so the commander
    has a default ★; fall back to the first option if the model omitted one."""
    keys = {o.key for o in packet.options}
    if packet.recommendation_key not in keys and packet.options:
        packet.recommendation_key = packet.options[0].key


#: execution grounding auto-declared per role — a code task should at minimum
#: parse and run; a test task should actually pass against its upstream code.
_DEFAULT_PROPS = {
    "code": ("python_parses", "code_runs"),
    "test": ("tests_pass",),
}


def _infer_role(title: str, objective: str, declared: str,
                known: set) -> str:
    """Trust an explicit non-generic role; otherwise infer the specialist from
    the wording. Keeps an explicit 'code'/'test'/etc., upgrades a generic
    'research' (or unknown) when the task clearly calls for a specialist."""
    if declared in known and declared != "research":
        return declared
    text = (str(title) + " " + str(objective)).lower()
    for role, kws in _ROLE_RULES:
        if role in known and any(k in text for k in kws):
            return role
    return declared if declared in known else "research"


def _title_to_name(v):
    # live finding: the planner model says 'title' where the schema says
    # 'name' — same synonym drift as the subagent contract
    if isinstance(v, dict) and "name" not in v and isinstance(
            v.get("title"), str):
        v = dict(v)
        v["name"] = v["title"]
    return v


class ModuleOut(BaseModel):
    name: str
    type: str = "implementation"
    purpose: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)

    _alias = model_validator(mode="before")(_title_to_name)
    _listify = field_validator(
        "acceptance_criteria",
        mode="before")(lambda v: [v] if isinstance(v, str) else v)


class TaskOut(BaseModel):
    title: str
    role: str = "research"
    module: str = ""                       # module NAME (mapped to id at ingest)
    objective: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)   # task TITLES
    # trusted partial-verification checks to run over this task's deliverable
    # (verify/properties.py names). Unknown names are dropped at validation: the
    # planner can only SELECT from the reviewed checker library, never invent a
    # checker — and a check that can't resolve its reference simply earns
    # nothing (the force-to-fail + lineage gates make over-declaration a no-op).
    properties: list[str] = Field(default_factory=list)

    _listify = field_validator(
        "acceptance_criteria", "depends_on",
        mode="before")(lambda v: [v] if isinstance(v, str) else v)

    @field_validator("properties", mode="before")
    @classmethod
    def _known_checkers_only(cls, v):
        from ..verify.properties import CHECKERS
        items = [v] if isinstance(v, str) else list(v or [])
        return [s for s in items if isinstance(s, str) and s in CHECKERS]


class MilestoneOut(BaseModel):
    name: str
    tasks: list[str] = Field(default_factory=list)        # task TITLES

    _alias = model_validator(mode="before")(_title_to_name)
    _listify = field_validator(
        "tasks", mode="before")(lambda v: [v] if isinstance(v, str) else v)


class RiskOutPlan(BaseModel):
    title: str
    level: str = "medium"
    description: str = ""
    mitigation: str = ""


class PlanOut(BaseModel):
    charter: CharterOut
    modules: list[ModuleOut]
    tasks: list[TaskOut]
    milestones: list[MilestoneOut] = Field(default_factory=list)
    risks: list[RiskOutPlan] = Field(default_factory=list)


class OptionOut(BaseModel):
    key: str
    label: str
    description: str = ""
    tradeoffs: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    risk_impact: str = "neutral"
    reversibility: str = "reversible"
    state_delta: dict = Field(default_factory=dict)
    # steering: dogmatic (conform to baseline) | iconoclast (exceed it) |
    # heretic (reject the framing, pivot). The model proposes; the Commander
    # steers by picking. Default dogmatic = the safe "conform" reading.
    conviction: str = "dogmatic"

    # live finding: real models emit these as a single string every time
    _listify = field_validator(
        "tradeoffs", "consequences",
        mode="before")(lambda v: [v] if isinstance(v, str) else v)

    @field_validator("conviction", mode="before")
    @classmethod
    def _norm_conviction(cls, v):
        s = str(v or "").strip().lower()
        return s if s in ("dogmatic", "iconoclast", "heretic") else "dogmatic"


class PacketOut(BaseModel):
    title: str
    context: str = ""
    options: list[OptionOut]
    recommendation_key: str = ""
    rationale: str = ""
    risks: list[str] = Field(default_factory=list)
    default_if_deferred: str = ""

    _listify = field_validator(
        "risks", mode="before")(lambda v: [v] if isinstance(v, str) else v)


PLAN_SYSTEM = (
    "You are the Director: a strategic orchestrator planning a long-horizon "
    "project to be executed by specialized subagents (roles: {roles}). "
    "Produce a charter (objective, explicit scope_in/scope_out, measurable "
    "success criteria), 2-5 modules (bounded workstreams), 3-10 tasks across "
    "those modules with realistic dependencies (reference other tasks by "
    "exact title), 1-3 milestones grouping tasks, and the top risks. Tasks "
    "must be bounded (one agent, one sitting) and objective-complete: a "
    "stateless agent must be able to execute from the task objective alone. "
    "A task MAY declare `properties`: names of TRUSTED automatic checks run "
    "over its deliverable to earn partial verification (choose ONLY from: "
    "parses, nonempty, schema_valid, cited_ids_resolve, totals_conserved). "
    "Declare schema_valid only on a task whose deliverable is JSON data to be "
    "validated against a JSON Schema produced by a DIFFERENT task it "
    "depends_on — so pair a 'define the JSON schema' task before any task that "
    "emits structured data you want checked. Declaring a check that cannot "
    "resolve its reference simply earns nothing (no harm), so declare it only "
    "where a trusted check genuinely applies."
)

PACKET_SYSTEM = (
    "You are the Director presenting a consequential decision to the human "
    "commander. This is not an approval form: present 2-4 materially "
    "different options (CRPG-style), each with honest tradeoffs, downstream "
    "consequences, risk impact, and reversibility. Recommend one and say "
    "why. Options may carry a state_delta object using these keys: "
    "module_updates [{{module_id, status?, note?}}], task_updates "
    "[{{task_id, status?, note?}}], new_tasks [{{title, role, module_id, "
    "objective, depends_on}}], risk_updates [{{risk_id?|title, level?, "
    "status?, mitigation?}}], notes [str]. Only reference ids that appear in "
    "the project state given to you. VALID ENUM VALUES (anything else is "
    "rejected): task status: pending|ready|running|needs_verify|done|failed|"
    "cancelled|blocked; module status: proposed|active|in_command|frozen|"
    "blocked|completed|deprecated; risk level: low|medium|high|critical; "
    "risk status: open|mitigating|accepted|closed|realized. tradeoffs and "
    "consequences are LISTS of strings. LEGAL task transitions for deltas: "
    "pending->ready|blocked|cancelled; ready->pending|blocked|cancelled; "
    "needs_verify->done|failed|ready|blocked; failed->ready|cancelled; "
    "blocked->ready|pending|cancelled; done->ready|needs_verify (human "
    "reopen). NEVER set status 'running' in a delta - only the runner sets "
    "running when it actually dispatches an agent. "
    "CONVICTION: give every option a 'conviction' describing its relationship "
    "to the proven baseline - 'dogmatic' (conform to the established "
    "pattern/baseline), 'iconoclast' (exceed it; reform the approach), or "
    "'heretic' (reject the framing itself; the problem is mis-posed, pivot). "
    "Span the convictions across your options where the situation allows, and "
    "recommend the one you'd actually back. NEVER claim an option is verified "
    "or proven - you have not run an external test. State confidence only as "
    "judgement in the description; trusted code attaches verification."
)


class Director:
    def __init__(self, cfg: Config, store: ProjectStore, router: LLMRouter,
                 registry: VerifierRegistry, runner: SubAgentRunner,
                 *, lessons=None, perf=None, markers=None):
        self.cfg = cfg
        self.store = store
        self.router = router
        self.registry = registry
        self.runner = runner
        self.lessons = lessons                 # LessonLedger | None (memory pkg)
        self.perf = perf                       # PerfLedger | None (run-scoped token burn)
        self.markers = markers                 # MarkerStore | None (gut markers v2)
        self._run_since = None                 # perf.stats(since=...) anchor for this run

    # ------------------------------------------------------------------ audit
    def _audit(self, project: Project, type_: str, summary: str,
               payload: dict | None = None, actor: str = "director") -> None:
        self.store.append_event(project.id, AuditEvent(
            type=type_, summary=summary, actor=actor, payload=payload or {}))

    # ------------------------------------------------------------ new project
    def new_project(self, name: str, objective: str) -> tuple[Project, CommandPacket]:
        prev_current = self.store.get_current()
        project = self.store.create(name)
        try:
            plan = self._plan(objective)
            self._ingest_plan(project, objective, plan)
        except Exception:
            # Don't leave an empty orphan project as the current selection —
            # and restore the pointer create() moved, or every subsequent
            # command dies on a dangling current id (live finding).
            import shutil
            shutil.rmtree(self.store.project_dir(project.id),
                          ignore_errors=True)
            self.store.set_current(prev_current or "")
            raise
        self._audit(project, "plan.created",
                    f"Plan: {len(project.modules)} modules, "
                    f"{len(project.tasks)} tasks, "
                    f"{len(project.milestones)} milestones")
        packet = self._make_packet(
            project, trigger="initial_plan",
            hint="The initial plan was just created. Surface the most "
                 "consequential posture/approach decision for this project.")
        refresh_statuses(project)
        self.store.save(project)
        return project, packet

    def _plan(self, objective: str) -> PlanOut:
        user = (f"objective: {objective}\n\n"
                f"Available agent roles: {', '.join(role_names())}")
        plan: PlanOut = self.router.structured(
            PLAN_SYSTEM.format(roles=", ".join(role_names())), user,
            PlanOut, role="director", kind="initial_plan")
        # semantic validation beyond schema
        problems = []
        if not plan.modules:
            problems.append("plan has no modules")
        if not plan.tasks:
            problems.append("plan has no tasks")
        titles = [t.title for t in plan.tasks]
        if len(titles) != len(set(titles)):
            problems.append("duplicate task titles")
        if problems:
            raise ModelValidationError("plan rejected: " + "; ".join(problems))
        return plan

    def _ingest_plan(self, project: Project, objective: str, plan: PlanOut) -> None:
        c = plan.charter
        project.charter = Charter(
            objective=c.objective or objective, scope_in=c.scope_in,
            scope_out=c.scope_out, success_criteria=c.success_criteria,
            constraints=c.constraints, deliverables=c.deliverables,
            risk_posture=c.risk_posture)

        modules_by_name: dict[str, Module] = {}
        for m in plan.modules:
            try:
                mtype = ModuleType(m.type)
            except ValueError:
                mtype = ModuleType.IMPLEMENTATION
            module = Module(name=m.name, type=mtype, purpose=m.purpose,
                            status=ModuleStatus.ACTIVE,
                            acceptance_criteria=m.acceptance_criteria)
            project.modules[module.id] = module
            modules_by_name[m.name] = module

        known_roles = set(role_names())
        tasks_by_title: dict[str, Task] = {}
        for t in plan.tasks:
            module = modules_by_name.get(t.module)
            role = _infer_role(t.title, t.objective, t.role, known_roles)
            # auto-declare EXECUTION grounding for code/test tasks so they're run
            # for real (parses/runs/tests_pass) even when the planner didn't ask —
            # but NOT for tasks that declare DATA checks (schema_valid /
            # cited_ids_resolve), which signal JSON/data output, not runnable code.
            props = list(t.properties)
            is_data_task = bool({"schema_valid", "cited_ids_resolve"} & set(props))
            if not is_data_task:
                for p in _DEFAULT_PROPS.get(role, ()):
                    if p not in props:
                        props.append(p)
            task = Task(
                title=t.title, role=role,
                objective=t.objective or t.title,
                module_id=module.id if module else "",
                acceptance_criteria=t.acceptance_criteria,
                properties=props,
                verifiers=["agent_output"])
            project.tasks[task.id] = task
            tasks_by_title[t.title] = task
        # map title-deps to ids (unknown titles dropped with a warning)
        for t in plan.tasks:
            task = tasks_by_title[t.title]
            for dep_title in t.depends_on:
                dep = tasks_by_title.get(dep_title)
                if dep and dep.id != task.id:
                    task.depends_on.append(dep.id)
                elif not dep:
                    log.warning("plan: task '%s' depends on unknown '%s'",
                                t.title, dep_title)
        cycles = detect_cycles(project.tasks)
        if cycles:
            # break cycles deterministically rather than failing the project
            for cycle in cycles:
                victim = project.tasks[cycle[0]]
                victim.depends_on = []
                log.warning("plan: broke dependency cycle at '%s'", victim.title)

        # backfill charter deliverables from the planned work products if the
        # planner left them empty (live finding: charter.deliverables came back
        # [] even though the objective named four) — a project should always
        # declare what it will produce.
        if not project.charter.deliverables:
            project.charter.deliverables = [t.title
                                            for t in tasks_by_title.values()][:8]

        for ms in plan.milestones:
            milestone = Milestone(name=ms.name, task_ids=[
                tasks_by_title[t].id for t in ms.tasks if t in tasks_by_title])
            project.milestones[milestone.id] = milestone
            for tid in milestone.task_ids:
                project.tasks[tid].milestone_id = milestone.id

        for r in plan.risks:
            try:
                level = RiskLevel(r.level)
            except ValueError:
                level = RiskLevel.MEDIUM
            risk = Risk(title=r.title, description=r.description, level=level,
                        mitigation=r.mitigation, source="plan")
            project.risks[risk.id] = risk

    # ------------------------------------------------------------- packets
    def _project_digest(self, project: Project, *, max_chars: int = 3500) -> str:
        lines = [f"PROJECT: {project.name} [{project.id}]",
                 f"OBJECTIVE: {project.charter.objective}",
                 f"SCOPE IN: {'; '.join(project.charter.scope_in)}",
                 f"SCOPE OUT: {'; '.join(project.charter.scope_out)}",
                 "MODULES:"]
        for m in project.modules.values():
            lines.append(f"  - {m.id} '{m.name}' [{m.type.value}] "
                         f"status={m.status.value} :: {m.purpose}")
        lines.append("TASKS:")
        for t in project.tasks.values():
            dep = f" deps={t.depends_on}" if t.depends_on else ""
            lines.append(f"  - {t.id} '{t.title}' role={t.role} "
                         f"status={t.status.value}{dep}")
        if project.risks:
            lines.append("OPEN RISKS:")
            for r in project.risks.values():
                lines.append(f"  - {r.id} [{r.level.value}] {r.title}")
        if project.artifacts:
            lines.append("ARTIFACTS:")
            for a in list(project.artifacts.values())[-8:]:
                lines.append(f"  - {a.id} '{a.title}' ({a.kind}, {a.status.value})")
        text = "\n".join(lines)
        return text[:max_chars]

    def _disposition_brief(self, project: Project) -> str:
        """Inject the project's earned disposition into packet generation —
        the RT 'rank reshapes the option space' translation. A project that
        has earned a high conviction rank gets options nudged toward that
        stance, because its track record there has paid off."""
        rk = conviction_rank(project)
        if not rk["rank"]:
            return ""
        nudge = {
            "heretic": "This project has EARNED standing to question framings "
                       "(past pivots paid off) — include at least one heretic "
                       "reframe option that challenges the problem as posed.",
            "iconoclast": "This project favors reform — surface at least one "
                          "iconoclast option that exceeds the proven baseline, "
                          "and hold it to a high verification bar.",
            "dogmatic": "This project trusts proven baselines — lead with a "
                        "dogmatic conform option and propose a regression "
                        "check before any riskier move.",
        }.get(rk["conviction"], "")
        return (f"\n\nDISPOSITION: {conviction_read(project)} "
                f"({rk['conviction']} rank {rk['rank']}, {rk['rank_name']}). "
                f"{nudge}")

    def _make_packet(self, project: Project, *, trigger: str,
                     hint: str, context_override: str | None = None
                     ) -> CommandPacket:
        try:
            out: PacketOut = self.router.structured(
                PACKET_SYSTEM, self._project_digest(project) +
                self._disposition_brief(project) +
                f"\n\nDECISION NEEDED: {hint}",
                PacketOut, role="director", kind="command_packet")
            packet = CommandPacket(
                title=out.title, context=out.context, trigger=trigger,
                options=[CommandOption(
                    key=o.key, label=o.label, description=o.description,
                    tradeoffs=o.tradeoffs, consequences=o.consequences,
                    risk_impact=o.risk_impact, reversibility=o.reversibility,
                    state_delta=o.state_delta, conviction=o.conviction,
                    # the model only ever JUDGES; verification is attached by
                    # trusted code that has actually run an oracle, never here
                    check="judged") for o in out.options],
                recommendation_key=out.recommendation_key,
                rationale=out.rationale, risks=out.risks,
                default_if_deferred=out.default_if_deferred,
                affected_modules=list(project.modules))
        except ModelError as exc:
            log.warning("packet generation failed (%s); deterministic fallback", exc)
            packet = self._fallback_packet(trigger, hint, context_override)

        report = self.registry.get("command_packet").verify(packet)
        if not report.passed:
            self._audit(project, "packet.rejected",
                        f"Generated packet failed evaluation "
                        f"(score={report.score}): {report.issues}")
            packet = self._fallback_packet(trigger, hint, context_override)
            report = self.registry.get("command_packet").verify(packet)
        # verifier-honesty guard: no option may keep a VERIFIED check unless a
        # real artifact backs it — downgrade before it can ever be presented
        for o in packet.options:
            kind, _ = honest_check(o, project.artifacts)
            if kind != o.check:
                o.check = kind
                self._audit(project, "packet.verify_downgraded",
                            f"option '{o.key}': unbacked VERIFIED -> {kind}",
                            {"packet_id": packet.id})
        # honest-recommendation: when ground truth exists, the ★ must track the
        # verifier-favored option, not a judged guess over measured evidence
        favored = verifier_favored_key(packet, project)
        if favored and packet.recommendation_key != favored:
            rec = next((o for o in packet.options
                        if o.key == packet.recommendation_key), None)
            if rec is None or honest_check(rec, project.artifacts)[0] \
                    != "verified":
                self._audit(project, "packet.recommendation_realigned",
                            f"★ {packet.recommendation_key or '(none)'} -> "
                            f"{favored} (verifier-favored)",
                            {"packet_id": packet.id})
                packet.recommendation_key = favored
        # always present a recommendation (live finding: every packet came back
        # with an empty recommendation_key, leaving the commander no default)
        _ensure_recommendation(packet)
        # coherency evaluation — trusted scoring of the decision itself
        coh = evaluate_packet_coherence(packet, project)
        self._audit(project, "packet.coherence",
                    f"coherence {coh['score']} (spread={coh['spread']}"
                    f"{', issues=' + str(coh['issues']) if coh['issues'] else ''}"
                    f"{', warnings=' + str(coh['warnings']) if coh['warnings'] else ''})",
                    {"packet_id": packet.id})
        # trusted-body path (Constitution #3): when the siren supplies a
        # trusted damage report, surface it VERBATIM — the LLM may still
        # propose recovery OPTIONS, but it does not get to re-narrate the
        # measured damage. Set last so no post-processing can overwrite it.
        if context_override is not None:
            packet.context = context_override
        packet.status = PacketStatus.PRESENTED
        project.packets[packet.id] = packet
        self._audit(project, "packet.presented",
                    f"Command packet '{packet.title}' "
                    f"(eval {report.score}, fragile={report.fragile})",
                    {"packet_id": packet.id, "trigger": trigger})
        return packet

    @staticmethod
    def _fallback_packet(trigger: str, hint: str,
                         context_override: str | None = None) -> CommandPacket:
        """Deterministic, always-valid packet for offline/failed generation."""
        return CommandPacket(
            title="Choose how to proceed",
            context=(context_override if context_override is not None
                     else f"Decision point reached ({trigger}). {hint}"),
            trigger=trigger,
            options=[
                CommandOption(
                    key="A", label="Proceed as planned",
                    description="Continue executing the current task graph "
                                "without modification.",
                    tradeoffs=["fastest path", "carries current assumptions"],
                    consequences=["next ready tasks dispatch on advance"],
                    risk_impact="unchanged", reversibility="reversible",
                    conviction="dogmatic", check="judged",
                    state_delta={"notes": ["human chose: proceed"]}),
                CommandOption(
                    key="B", label="Pause and strengthen verification",
                    description="Add a review task before further building.",
                    tradeoffs=["slower", "raises confidence"],
                    consequences=["one extra review cycle"],
                    risk_impact="lowered", reversibility="reversible",
                    conviction="iconoclast", check="judged",
                    state_delta={"new_tasks": [{
                        "title": f"Extra review ({trigger})",
                        "role": "review",
                        "objective": "Review all current artifacts for gaps, "
                                     "weak assumptions, and missing evidence "
                                     "before further work proceeds."}]}),
            ],
            recommendation_key="A",
            rationale="Default posture: proceed, verification gates remain "
                      "active on every task.",
            risks=["fallback packet (LLM generation unavailable or rejected)"],
            default_if_deferred="A")

    # ------------------------------------------------------------- decisions
    def decide(self, project_ref: str, packet_id: str, *,
               response: ResponseType = ResponseType.SELECT_OPTION,
               option_key: str = "", rationale: str = "",
               modifications: str = "") -> dict:
        project = self.store.load(project_ref)
        packet = self._find_packet(project, packet_id)
        if packet.status is not PacketStatus.PRESENTED:
            raise NotFoundError(f"packet {packet.id} is {packet.status.value}, "
                                f"not open")

        decision = DecisionEvent(packet_id=packet.id, response_type=response,
                                 selected_key=option_key, rationale=rationale,
                                 modifications=modifications)
        result: dict = {"decision_id": decision.id, "applied": False,
                        "coherence": "n/a", "follow_up": "none"}

        if response in (ResponseType.SELECT_OPTION, ResponseType.SELECT_AND_MODIFY):
            option = next((o for o in packet.options if o.key == option_key), None)
            if option is None:
                raise NotFoundError(f"option '{option_key}' not in packet")
            if option.state_delta:
                delta = StateDelta(trigger=decision.id,
                                   summary=f"decision '{option.label}'",
                                   payload=dict(option.state_delta))
                if modifications:
                    delta.payload.setdefault("notes", []).append(
                        f"human modification: {modifications}")
                # Apply BEFORE marking the packet answered: if coherence blocks
                # the delta, the packet stays PRESENTED and the decision is
                # recorded as blocked rather than leaving a stuck-answered packet.
                try:
                    rep = apply_delta(project, delta, actor="human")
                except CoherenceBlockedError as exc:
                    self._audit(project, "decision.blocked",
                                f"Decision on '{packet.title}' blocked by "
                                f"coherence: {exc}", {"packet_id": packet.id},
                                actor="human")
                    self.store.save(project)
                    result["coherence"] = "blocked"
                    result["error"] = str(exc)
                    return result
                result["applied"] = True
                result["coherence"] = rep.status
                self._audit(project, "delta.applied",
                            f"Delta from decision {decision.id}: {rep.status}",
                            {"delta_id": delta.id}, actor="human")
            packet.status = PacketStatus.ANSWERED
            packet.answered_at = utcnow()
        elif response is ResponseType.DEFER:
            packet.status = PacketStatus.DEFERRED
        elif response is ResponseType.REJECT_ALL:
            packet.status = PacketStatus.CANCELLED
        elif response is ResponseType.TAKE_COMMAND:
            packet.status = PacketStatus.ANSWERED
            packet.answered_at = utcnow()
            taken = 0
            for mid in packet.affected_modules:
                module = project.modules.get(mid)
                if module and module.status is ModuleStatus.ACTIVE:
                    delta = StateDelta(trigger=decision.id,
                                       summary=f"human takes command of {module.name}",
                                       payload={"module_updates": [
                                           {"module_id": mid,
                                            "status": "in_command"}]})
                    apply_delta(project, delta, actor="human")
                    taken += 1
            result["applied"] = taken > 0
            result["modules_taken"] = taken

        project.decisions[decision.id] = decision
        self._audit(project, "decision.recorded",
                    f"{response.value} on '{packet.title}'"
                    + (f" -> {option_key}" if option_key else ""),
                    {"packet_id": packet.id}, actor="human")
        refresh_statuses(project)
        self.store.save(project)

        if (self.cfg.auto_advance_after_decision and
                response in (ResponseType.SELECT_OPTION,
                             ResponseType.SELECT_AND_MODIFY) and
                not self._open_packets(project) and
                not (self.cfg.nervous_enabled and project.scream_open)):
            adv = self.advance(project.id)
            result["follow_up"] = f"auto-advanced: {adv['summary']}"
        return result

    def _find_packet(self, project: Project, ref: str) -> CommandPacket:
        if ref in project.packets:
            return project.packets[ref]
        matches = [p for pid, p in project.packets.items() if pid.startswith(ref)]
        if len(matches) == 1:
            return matches[0]
        raise NotFoundError(f"no unique packet matching '{ref}'")

    @staticmethod
    def _open_packets(project: Project) -> list[CommandPacket]:
        return [p for p in project.packets.values()
                if p.status is PacketStatus.PRESENTED]

    # --------------------------------------------------------------- advance
    def advance(self, project_ref: str, *, max_tasks: int | None = None,
                force: bool = False, autonomous: bool = False) -> dict:
        """One bounded work cycle: dispatch ready tasks to parallel verified
        subagents and ingest the results. Stops (unless force) while a command
        packet is open — human command outranks autonomy."""
        project = self.store.load(project_ref)
        open_pkts = self._open_packets(project)
        if open_pkts and not force:
            return {"status": "awaiting_command",
                    "summary": f"{len(open_pkts)} command packet(s) open - "
                               f"decide first or use force",
                    "packets": [p.id for p in open_pkts], "ran": 0}

        # latch halt: a held scream stops AUTONOMOUS work (and the
        # decide()->advance auto-advance path); a human-commanded advance is
        # exempt and drives recovery. This gate is READ-ONLY on held_cycles: the
        # autonomous loop merely HALTS here. The held_cycles increment and the
        # deadlock escalation live in _nervous_pass's "latch still held" branch,
        # which the human/force recovery hops actually run — that is where a held
        # cycle is genuinely spent, so the deadlock guard is reachable (FIX 4).
        if (self.cfg.nervous_enabled and autonomous and project.scream_open
                and not force):
            sc = project.scream_open
            self.store.save(project)
            return {"status": "latched",
                    "summary": f"SCREAM held ({sc['cause']}); "
                               f"held_cycles={sc.get('held_cycles', 0)} - "
                               f"clear: {sc.get('clear_rule', '')}",
                    "scream": dict(sc), "ran": 0}

        # Recover tasks stranded RUNNING by a crash in a prior advance: nothing
        # promotes RUNNING automatically, so reset them for retry.
        recovered = 0
        for task in project.tasks.values():
            if task.status is TaskStatus.RUNNING:
                task.status = TaskStatus.READY
                task.updated_at = utcnow()
                recovered += 1
        if recovered:
            self._audit(project, "advance.recovered",
                        f"reset {recovered} task(s) stranded RUNNING by a "
                        f"prior crash")

        refresh_statuses(project)
        limit = max_tasks or self.cfg.max_tasks_per_advance
        if self.cfg.nervous_enabled and self.markers is not None:
            batch = self._advisory_batch(project, limit)
        else:
            batch = ready_tasks(project, limit=limit)
        if not batch:
            self.store.save(project)
            return {"status": "idle", "summary": "no ready tasks", "ran": 0}

        self._audit(project, "advance.started",
                    f"Dispatching {len(batch)} task(s): "
                    + ", ".join(t.title for t in batch))
        specs = []
        for task in batch:
            task.status = TaskStatus.RUNNING
            task.attempts += 1
            specs.append(self._spec_for(project, task))
        self.store.save(project)

        results = self.runner.run_parallel(specs)

        done, failed, needs_human = 0, 0, 0
        new_packets: list[str] = []
        for spec, res in zip(specs, results):
            task = project.tasks[spec.task_id]
            run = self._record_run(project, spec, res)
            if res.ok:
                self._ingest_output(project, task, run.id, res.output)
                task.status = TaskStatus.DONE
                task.result_summary = str(res.output.get("summary", ""))[:400]
                done += 1
                self._audit(project, "task.completed",
                            f"'{task.title}' done (score "
                            f"{res.reports[0].score if res.reports else '?'})",
                            {"task_id": task.id, "run_id": run.id})
            elif res.needs_human:
                task.status = TaskStatus.NEEDS_VERIFY
                task.error = res.error
                needs_human += 1
                self._audit(project, "task.needs_verify",
                            f"'{task.title}' requires human review: {res.error}",
                            {"task_id": task.id, "run_id": run.id})
            else:
                task.error = res.error
                # a TRANSIENT infra failure (timeout/rate/quota) is not the
                # agent's fault — keep it retryable (bounded) so a later cycle or
                # the long-timeout lane can complete it instead of terminally
                # failing and blocking dependents (live finding: a research
                # timeout cascaded into 2 stuck tasks). Content failures still
                # cap at max_attempts.
                transient = _is_transient_failure(res.error)
                if transient and task.attempts < task.max_attempts + 3:
                    task.status = TaskStatus.READY
                    self._audit(project, "task.retry_transient",
                                f"'{task.title}' transient failure "
                                f"(attempt {task.attempts}), requeued: "
                                f"{(res.error or '')[:120]}",
                                {"task_id": task.id})
                elif task.attempts >= task.max_attempts:
                    task.status = TaskStatus.FAILED
                    failed += 1
                    self._audit(project, "task.failed",
                                f"'{task.title}' failed after "
                                f"{task.attempts} attempts: {res.error}",
                                {"task_id": task.id})
                    if self.cfg.nervous_enabled and self.markers is not None:
                        self._record_scar(project, task,
                                          cause="failed_verification")
                else:
                    task.status = TaskStatus.READY     # retry next advance
            task.updated_at = utcnow()

            if res.ok and res.output.get("command_packet_recommended"):
                reason = str(res.output.get("command_packet_reason", ""))
                pkt = self._make_packet(project, trigger=f"agent:{task.id}",
                                        hint=f"Subagent '{task.role}' on task "
                                             f"'{task.title}' surfaced a fork: "
                                             f"{reason}")
                new_packets.append(pkt.id)

        refresh_statuses(project)
        reached = refresh_milestones(project)
        for ms in reached:
            self._audit(project, "milestone.reached", f"Milestone '{ms.name}'")
            if not self._open_packets(project):
                pkt = self._make_packet(
                    project, trigger=f"milestone:{ms.id}",
                    hint=f"Milestone '{ms.name}' reached. Decide the next "
                         f"emphasis before further work.")
                new_packets.append(pkt.id)

        if self.cfg.nervous_enabled:
            self._nervous_pass(project, autonomous=autonomous)

        self.store.save(project)
        summary = (f"{done} done, {failed} failed, {needs_human} need review, "
                   f"{len(new_packets)} new packet(s)")
        self._audit(project, "advance.completed", summary)
        return {"status": "ok", "summary": summary, "ran": len(batch),
                "done": done, "failed": failed, "needs_human": needs_human,
                "new_packets": new_packets,
                "milestones_reached": [m.name for m in reached]}

    # ------------------------------------------------------------------- run
    def run(self, project_ref: str, *, autonomous: bool = True,
            max_cycles: int | None = None) -> dict:
        """Bounded autonomous loop: call advance(autonomous=True) until a
        declared stop condition fires. The loop OWNS NO STATE. `since` is
        captured ONCE at entry so the budget stop and resource_bleed see
        run-scoped tokens, not the lifetime ledger."""
        import time
        from ..evolve.metrics import PerfLedger
        perf = getattr(self, "perf", None) or PerfLedger(self.cfg)
        since = utcnow().isoformat()
        started_at = time.monotonic()
        cycles = 0
        # thread `since` to the valence pass so resource_bleed/clear-rule see
        # run-scoped tokens (perf.stats(since=since)), consistent with stop()'s
        # budget_tokens. Save+restore so a nested/abnormal exit doesn't leak the
        # anchor into a later, unrelated call.
        prev_since = getattr(self, "_run_since", None)
        self._run_since = since
        try:
            while True:
                project = self.store.load(project_ref)
                reason = self.stop(project, perf=perf, since=since,
                                   cycles=cycles, started_at=started_at)
                if reason is not None:
                    return {"status": "stopped", "stop_reason": reason,
                            "cycles": cycles, "since": since}
                if max_cycles is not None and cycles >= max_cycles:
                    return {"status": "stopped", "stop_reason": "max_cycles",
                            "cycles": cycles, "since": since}
                self.advance(project_ref, autonomous=autonomous)
                cycles += 1
        finally:
            self._run_since = prev_since

    def stop(self, project: Project, *, perf, since,
             cycles: int = 0, started_at: float | None = None) -> str | None:
        """The declared stop predicate, in precedence order (spec section 6)."""
        import time
        rows = report_integrity(project, self.cfg.report_secret())
        if integrity_violations(rows):
            return "integrity_tamper"
        if self._open_packets(project):
            return "open_packet"
        if getattr(project, "scream_open", None):
            return "latch_held"
        budget = getattr(self.cfg, "budget", None)
        if budget:
            if budget.get("max_cycles") is not None \
                    and cycles >= budget["max_cycles"]:
                return "budget_cycles"
            if budget.get("max_tokens") is not None:
                st = perf.stats(since=since)
                tok = st.get("prompt_tokens", 0) + st.get("completion_tokens", 0)
                if tok >= budget["max_tokens"]:
                    return "budget_tokens"
            if budget.get("max_wall_clock") is not None \
                    and started_at is not None \
                    and (time.monotonic() - started_at) >= budget["max_wall_clock"]:
                return "budget_wall_clock"
        running = any(t.status is TaskStatus.RUNNING
                      for t in project.tasks.values())
        ready = ready_tasks(project)
        summary = graph_summary(project)
        if (summary["done"] == summary["tasks_total"]
                and summary["tasks_total"] > 0
                and not ready and not running):
            return "done"
        if not ready and not running:
            return "drained"
        return None

    # ------------------------------------------------------------- gut markers
    def _advisory_batch(self, project: Project, limit: int) -> list[Task]:
        """Advisory re-rank of the FULL ready frontier by prior-pain repel, WITHOUT
        mutating the canonical (created_at, id) sort. Least-repelled first; the
        front `limit` dispatch, the rest defer (and may escalate). Diagnoses drive
        the model; the weight stays trusted-only."""
        from ..memory.markers import task_signature
        frontier = ready_tasks(project)        # all READY, canonical order
        scored = []
        for i, t in enumerate(frontier):
            repel = sum(m.weight for m in self.markers.recall(
                task_signature(t), min_sim=self.cfg.marker_merge_sim))
            scored.append((repel, i, t))        # repel <= 0; i = canonical tiebreak
        scored.sort(key=lambda x: (-x[0], x[1]))   # least-repelled (repel desc) first
        batch = [t for _, _, t in scored[:limit]]
        deferred = [t for _, _, t in scored[limit:]]
        self._note_deferrals(project, batch, deferred)
        return batch

    def _note_deferrals(self, project: Project, batch, deferred) -> None:
        for t in batch:                          # dispatched -> reset its counter
            project.marker_deferrals.pop(t.id, None)
        for t in deferred:
            n = project.marker_deferrals.get(t.id, 0) + 1
            project.marker_deferrals[t.id] = n
            if (n > self.cfg.marker_defer_escalate_cycles
                    and not self._open_packets(project)):
                self._make_packet(
                    project, trigger="markers:deferred:" + t.id,
                    hint=(f"Task '{t.title}' (role {t.role}) has been deferred "
                          f"{n} cycles by prior-pain markers. Commander decision: "
                          f"persevere, drop, or re-scope."))
                project.marker_deferrals[t.id] = 0      # reset after escalating

    # ----------------------------------------------------------- credit knife
    def _record_scar(self, project: Project, task: Task, *, cause: str) -> None:
        """Write a trusted scar for a RESOLVED failure (diagnoses-only). No model
        call. Guarded by the caller behind cfg.nervous_enabled + self.markers."""
        from ..memory.markers import Marker, task_signature
        origin = task.origin_decision_id or f"plan:{task.module_id or 'root'}"
        diagnosis = (f"Task '{task.title}' (role {task.role}) failed verification "
                     f"after {task.attempts} attempt(s): "
                     f"{(task.error or 'no detail')[:300]}")
        self.markers.record(Marker(
            signature=task_signature(task), cause=cause, diagnosis=diagnosis,
            origin=origin, last_cycle=project.cycle_seq))
        self._audit(project, "scar.recorded",
                    f"scar on {task_signature(task)} ({cause})",
                    {"task_id": task.id, "cause": cause})

    # ---------------------------------------------------------- nervous pass
    def _nervous_pass(self, project: Project, *, autonomous: bool) -> None:
        """Trusted valence pass: bump cycle_seq, recompute the Body, re-test an
        open latch's clear rule, then evaluate the scream. Guarded entirely by
        cfg.nervous_enabled so the OFF path never reaches here."""
        project.cycle_seq += 1
        secret = self.cfg.report_secret()
        since = getattr(self, "_run_since", None)
        body = compute_body(project, secret=secret, perf=self.perf,
                            since=since, cfg=self.cfg)
        project.body = body

        if project.scream_open is not None:
            if check_clear_rule(project, project.scream_open, secret=secret,
                                perf=self.perf, since=since, cfg=self.cfg):
                cause = project.scream_open["cause"]
                self._audit(project, "scream.cleared",
                            f"latch cleared: {cause} re-verified",
                            {"cause": cause})
                project.scream_open = None
            else:
                # the latch is STILL held this cycle: count a held cycle and
                # escalate-if-needed HERE (single owner). Each advance that runs
                # _nervous_pass with the latch unresolved — the human/force
                # recovery hops — spends a held cycle and can trip the deadlock
                # guard. The autonomous halt-gate in advance() is read-only.
                self._count_held_cycle(project)
                return

        scream = evaluate_scream(project, body, cfg=self.cfg)
        if scream is None:
            return
        if scream["level"] == "ache":
            self._handle_ache(project, scream)
        else:
            self._handle_siren(project, scream, autonomous=autonomous)

    def _count_held_cycle(self, project: Project) -> None:
        """A held-latch recovery hop just ran the body and the clear rule still
        FAILED. Count the held cycle and, the first time it exceeds
        max_held_cycles, raise a one-shot deadlock packet + audit. Single owner
        of the held_cycles lifecycle (the advance() halt-gate is read-only)."""
        sc = project.scream_open
        if sc is None:
            return
        sc["held_cycles"] = int(sc.get("held_cycles", 0)) + 1
        if sc["held_cycles"] > self.cfg.max_held_cycles and not sc.get("escalated"):
            sc["escalated"] = True
            self._make_packet(
                project, trigger="scream:deadlock:" + sc["cause"],
                hint=(f"Latch on {sc['cause']} has held "
                      f"{sc['held_cycles']} cycles past the limit - "
                      f"unrecoverable; operator decision required."),
                context_override=(
                    f"DEADLOCK: the {sc['cause']} scream has not cleared "
                    f"after {sc['held_cycles']} held cycles. Trusted "
                    f"re-verification ({sc.get('clear_rule', '')}) still "
                    f"fails. Operator decision required."))
            self._audit(project, "scream.deadlock",
                        f"latch {sc['cause']} exceeded max_held_cycles "
                        f"({self.cfg.max_held_cycles})",
                        {"cause": sc["cause"],
                         "held_cycles": sc["held_cycles"]})

    def _handle_ache(self, project: Project, scream: dict) -> None:
        """An ache is a wince: record it (always) and inject AT MOST one bounded
        diagnostic review task at the frontier tail — no priority, no early
        dependency edge, no posture change (Constitution #5)."""
        self._audit(project, "scream.ache",
                    f"ache on {scream['axis']}: {scream['report'][:200]}",
                    {"axis": scream["axis"]})
        axis = scream["axis"]
        module_id = ""
        from .coherence import apply_delta
        from .types import StateDelta
        delta = StateDelta(
            trigger=f"ache:{project.cycle_seq}",
            summary=f"diagnostic for ache on {axis}",
            payload={"new_tasks": [{
                "title": f"Diagnose {axis.replace('_', ' ')} "
                         f"(cycle {project.cycle_seq})",
                "role": "review", "module_id": module_id,
                "objective": ("Diagnose this failing case and its cause, then "
                              "propose a fix: " + scream["report"])}]})
        try:
            apply_delta(project, delta, actor="director")
        except CoherenceBlockedError as exc:
            project.coherence_blocks += 1
            self._audit(project, "scream.ache_blocked",
                        f"ache diagnostic blocked by coherence: {exc}",
                        {"axis": axis})

    def _handle_siren(self, project: Project, scream: dict, *,
                      autonomous: bool) -> None:
        """A siren raises a Command Packet carrying the TRUSTED damage report
        verbatim and opens the latch. It never picks a recovery branch."""
        from .types import TaskStatus
        report = scream["report"]
        cause = scream["cause"]
        # a SCREAM is a halt-the-world interrupt: it outranks any routine
        # packet (milestone/fork) raised earlier in this same advance, so the
        # commander faces the latch alone, not a menu next to it. Supersede the
        # in-flight ones before raising the siren packet — and audit the dropped
        # ids so the lost decision points are observable, not silently swallowed.
        superseded = self._open_packets(project)
        for pk in superseded:
            pk.status = PacketStatus.SUPERSEDED
        if superseded:
            self._audit(project, "scream.superseded",
                        f"siren superseded {len(superseded)} open packet(s)",
                        {"packet_ids": [pk.id for pk in superseded]})
        self._make_packet(project, trigger="scream:" + cause, hint=report,
                          context_override=report)
        # origin_refs = the UNION of the open grounding risk ids AND the
        # currently-FAILED task ids (dedup, order-preserving). Both kinds of ref
        # are directly re-verifiable by check_clear_rule's grounding_damage
        # branch: risk ids live in project.risks, task ids in project.tasks. The
        # earlier risk-OR-failed split left a risk-driven latch with ONLY risk
        # ids, which the (old) deliverable re-pass could never resolve.
        risk_ids = list((project.body.provenance or {}).get("risk_ids", [])) \
            if project.body else []
        failed_ids = [t.id for t in project.tasks.values()
                      if t.status is TaskStatus.FAILED]
        origin_refs = list(dict.fromkeys(risk_ids + failed_ids))
        if self.cfg.nervous_enabled and self.markers is not None:
            for tid in failed_ids:
                ft = project.tasks.get(tid)
                if ft is not None:
                    self._record_scar(project, ft, cause=cause)
        opened_severity = float(getattr(project.body, "accumulated_damage", 0.0)
                                if project.body else 0.0)
        project.scream_open = {
            "cause": cause, "axis": scream["axis"],
            "opened_at": project.cycle_seq, "held_cycles": 1,
            "clear_rule": scream["clear_rule"], "origin_refs": origin_refs,
            "opened_severity": opened_severity}
        self._audit(project, "scream.siren",
                    f"SCREAM ({cause}) - latch opened, clear: "
                    f"{scream['clear_rule']}",
                    {"cause": cause, "axis": scream["axis"]})

    def _spec_for(self, project: Project, task: Task) -> AgentSpec:
        """Build the bounded work order. Live finding (2026-06-12): a blind
        tail-chop starved downstream agents of upstream artifacts — the
        budget is now explicit, artifacts are trimmed individually with
        visible markers, and anything omitted is NAMED so a stateless agent
        knows what it did not see."""
        module = project.modules.get(task.module_id)
        head = [f"Project objective: {project.charter.objective}"]
        if project.charter.scope_out:
            head.append("Out of scope: " + "; ".join(project.charter.scope_out))
        if module:
            head.append(f"Module: {module.name} - {module.purpose}")
        art_blocks: list[tuple[str, str, str]] = []   # (title, kind, content)
        for dep_id in task.depends_on:
            dep = project.tasks.get(dep_id)
            if dep and dep.result_summary:
                head.append(
                    f"Upstream '{dep.title}': {dep.result_summary[:600]}")
            for aid in (dep.artifact_ids if dep else []):
                art = project.artifacts.get(aid)
                if art:
                    art_blocks.append((art.title, art.kind, art.content or ""))

        parts = list(head)
        budget = max(2000, self.cfg.ctx_total_chars) - len("\n\n".join(head))
        if art_blocks:
            per = min(self.cfg.ctx_artifact_chars,
                      max(400, budget // len(art_blocks) - 80))
            included = 0
            omitted: list[str] = []
            for title, kind, content in art_blocks:
                block = (f"Upstream artifact '{title}' ({kind}):\n"
                         f"{content[:per]}")
                if len(content) > per:
                    block += f"\n[truncated: {len(content) - per} more chars]"
                if budget - (len(block) + 2) < 0:
                    omitted.append(title)
                    continue
                parts.append(block)
                budget -= len(block) + 2
                included += 1
            if omitted:
                parts.append(
                    "NOTE: context budget exhausted; upstream artifacts "
                    "OMITTED (request them if needed): " + "; ".join(omitted))
        return AgentSpec(
            role=task.role, objective=task.objective or task.title,
            context="\n\n".join(parts),
            inputs=task.inputs, acceptance_criteria=task.acceptance_criteria,
            constraints=project.charter.constraints,
            task_id=task.id,
            verifiers=[v for v in task.verifiers if v != "agent_output"])

    @staticmethod
    def _author(art) -> tuple:
        """An artifact's recorded author: (authoring task id, authoring run id).
        Both are engine-stamped (Artifact.task_id + provenance['run_id']) and
        not agent-writable, so they are a trustworthy lineage fingerprint."""
        prov = getattr(art, "provenance", None) or {}
        return (getattr(art, "task_id", "") or "", prov.get("run_id", "") or "")

    def _upstream_schema(self, project: Project, task: Task, deliverable=None):
        """A JSON-schema-shaped artifact of INDEPENDENT LINEAGE from
        ``deliverable`` — i.e. authored by a DIFFERENT task (and, when run ids
        are recorded, a different run). Independence is DERIVED from the schema
        artifact's recorded author vs the deliverable's, not asserted from which
        dependency we happened to read. Returns (schema_dict, independent) or
        (None, False)."""
        deliv_author = (self._author(deliverable) if deliverable is not None
                        else (task.id, ""))
        for dep_id in task.depends_on:
            dep = project.tasks.get(dep_id)
            if not dep:
                continue
            for aid in dep.artifact_ids:
                art = project.artifacts.get(aid)
                if not art:
                    continue
                try:
                    obj = json.loads(art.content or "")
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
                if isinstance(obj, dict) and obj.get("type") == "object" \
                        and "properties" in obj:
                    s_author = self._author(art)
                    indep = s_author[0] != deliv_author[0]   # different task
                    if s_author[1] and deliv_author[1]:      # both runs known
                        indep = indep and s_author[1] != deliv_author[1]
                    return obj, indep
        return None, False

    def _upstream_code(self, project: Project, task: Task, deliverable=None):
        """The implementation SOURCE from an upstream (dependency) task — of
        independent lineage from ``deliverable`` — used as the reference a
        tests_pass check runs against. Returns (code_str, independent) or
        (None, False). Picks a code-kind artifact that parses as Python."""
        import ast as _ast
        deliv_author = (self._author(deliverable) if deliverable is not None
                        else (task.id, ""))
        for dep_id in task.depends_on:
            dep = project.tasks.get(dep_id)
            if not dep:
                continue
            for aid in dep.artifact_ids:
                art = project.artifacts.get(aid)
                if not art or art.kind not in ("code", "python"):
                    continue
                try:
                    _ast.parse(art.content or "")
                except SyntaxError:
                    continue
                s_author = self._author(art)
                indep = s_author[0] != deliv_author[0]
                if s_author[1] and deliv_author[1]:
                    indep = indep and s_author[1] != deliv_author[1]
                return art.content, indep
        return None, False

    def _run_task_properties(self, project: Project, task: Task,
                             run_id: str) -> None:
        """Run the task's declared TRUSTED checkers over its deliverable and,
        if they earn it, persist a property_report + stamp VERIFIED_PARTIAL on
        the deliverable's provenance. The schema reference comes from an
        upstream task (independent lineage); known ids come from the project.
        This is how a REAL task deliverable — not the demo — earns partial
        verification."""
        if not task.properties:
            return
        own = [project.artifacts[a] for a in task.artifact_ids
               if a in project.artifacts
               and project.artifacts[a].kind != "property_report"]
        if not own:
            return
        # pick the SUBSTANTIVE deliverable to verify: a task may emit a code/json
        # output PLUS a markdown sidecar; verifying the doc instead of the real
        # output silently misses the badge (live finding: schema_valid ran on an
        # annotated markdown doc, not the valid JSON config beside it).
        _DOC = {"markdown", "report", "text", "md", "doc", "notes"}
        substantive = [a for a in own if a.kind not in _DOC]
        deliverable = (substantive or own)[-1]
        ref, independent = None, True
        if "schema_valid" in task.properties:
            ref, independent = self._upstream_schema(project, task, deliverable)
            if ref is None:
                # no independent schema to check against -> nothing to verify
                self._audit(project, "task.partial_skipped",
                            f"'{task.title}': schema_valid declared but no "
                            f"upstream schema of independent lineage",
                            {"task_id": task.id})
                names = [p for p in task.properties if p != "schema_valid"]
            else:
                names = list(task.properties)
        elif "tests_pass" in task.properties:
            ref, independent = self._upstream_code(project, task, deliverable)
            if ref is None:
                self._audit(project, "task.partial_skipped",
                            f"'{task.title}': tests_pass declared but no upstream "
                            f"implementation of independent lineage",
                            {"task_id": task.id})
                names = [p for p in task.properties if p != "tests_pass"]
            else:
                names = list(task.properties)
        else:
            names = list(task.properties)
        if "cited_ids_resolve" in names and ref is None:
            # resolve cited ids against project entities EXCLUDING the
            # deliverable's OWN task and artifacts. A self-citation (an id you
            # authored) can therefore never satisfy the check, so it cannot fish
            # a badge (red-team: self-citation escape). What remains are entities
            # authored by OTHER tasks, so a citation that resolves is a genuine
            # cross-reference of independent lineage — independent=True is honest,
            # and the check earns its keep as a structural-integrity guarantee:
            # "this deliverable's references point at real, other-authored work."
            own = {task.id} | set(task.artifact_ids)
            ref = (set(project.artifacts) | set(project.tasks)) - own
            independent = True
        # code checks only apply to a CODE deliverable — never run them over JSON
        # or prose (a JSON dict literal happens to be valid Python, which would
        # be a vacuous/misleading python_parses badge).
        if deliverable.kind not in ("code", "python"):
            names = [n for n in names
                     if n not in ("python_parses", "code_runs", "tests_pass")]
        if not names:
            return
        from ..verify.properties import partial_bundle_ok, run_properties
        from ..verify.signing import (bound_payload, content_sha,
                                      sign as _sign_report)
        report = run_properties(deliverable.content, names, ref=ref,
                                ref_independent=independent)
        prop_art = Artifact(
            title=f"property_report: {task.title[:48]}",
            kind="property_report", module_id=task.module_id, task_id=task.id,
            content=json.dumps(report),
            provenance={"run_id": run_id, "role": "trusted:properties",
                        "report": report, "deliverable": deliverable.id})
        # HMAC-sign the report BOUND to this carrying artifact + the exact
        # deliverable it graded (id + content hash), so a hand-edited snapshot
        # can neither replay it onto other content nor swap the graded bytes
        # (red-team: signed report was an unbound bearer token).
        prop_art.provenance["report_sig"] = _sign_report(
            bound_payload(report, report_id=prop_art.id,
                          deliverable_id=deliverable.id,
                          deliverable_sha=content_sha(deliverable.content)),
            self.cfg.report_secret())
        project.artifacts[prop_art.id] = prop_art
        task.artifact_ids.append(prop_art.id)
        try:
            self.store.mirror_artifact(project.id, prop_art)
        except OSError as exc:
            log.warning("property_report mirror failed: %s", exc)
        # surface GROUNDING FAILURES, not just absence of a badge: a declared
        # check that actually FAILED on the deliverable (e.g. code_runs hit a
        # SyntaxError) is a fidelity problem the operator should see — record it
        # as a risk so broken code doesn't pass silently.
        from .types import Risk, RiskLevel
        for c in report.get("checks", []):
            if not c.get("passed"):
                self._audit(project, "task.check_failed",
                            f"'{task.title}': {c['name']} FAILED — "
                            f"{c.get('detail', '')[:120]}", {"task_id": task.id})
                if c["name"] in ("code_runs", "tests_pass"):
                    rk = Risk(title=f"{task.title}: {c['name']} failed",
                              description=str(c.get("detail", ""))[:200],
                              level=RiskLevel.HIGH, source="grounding")
                    project.risks[rk.id] = rk
        if partial_bundle_ok(report):
            # self-describing badge: name the necessary conditions actually
            # verified so "N/M trusted" can never be misread as "fully checked".
            verified_names = [c["name"] for c in report["checks"]
                              if c.get("counted")]
            deliverable.provenance["partial"] = {
                "n_passed": report["n_passed"], "n_total": report["n_total"],
                "checks": verified_names, "report_id": prop_art.id}
            self._audit(project, "task.partial_verified",
                        f"'{task.title}': verified {', '.join(verified_names)} "
                        f"({report['n_passed']}/{report['n_total']} trusted)",
                        {"task_id": task.id, "report_id": prop_art.id})

    def _record_run(self, project: Project, spec: AgentSpec, res) -> AgentRun:
        run = AgentRun(task_id=spec.task_id, role=spec.role,
                       backend=res.backend, model=res.model,
                       status="succeeded" if res.ok else "failed",
                       output=res.output, reports=res.reports,
                       usage=res.usage, latency_s=res.latency_s,
                       error=res.error, completed_at=utcnow())
        project.runs[run.id] = run
        return run

    def _ingest_output(self, project: Project, task: Task, run_id: str,
                       output: dict) -> None:
        for a in output.get("artifacts", []):
            art = Artifact(title=str(a.get("title", "untitled")),
                           kind=str(a.get("kind", "markdown")),
                           content=str(a.get("content", "")),
                           module_id=task.module_id, task_id=task.id,
                           provenance={"run_id": run_id, "role": task.role,
                                       "backend": project.runs[run_id].backend,
                                       "model": project.runs[run_id].model})
            project.artifacts[art.id] = art
            task.artifact_ids.append(art.id)
            try:
                self.store.mirror_artifact(project.id, art)
            except OSError as exc:
                log.warning("artifact mirror failed: %s", exc)
        # trusted partial-verification of this task's deliverable, if declared
        self._run_task_properties(project, task, run_id)
        for r in output.get("risks", []):
            if not isinstance(r, dict) or not r.get("title"):
                continue
            try:
                level = RiskLevel(str(r.get("level", "medium")))
            except ValueError:
                level = RiskLevel.MEDIUM
            risk = Risk(title=str(r["title"]),
                        description=str(r.get("description", "")),
                        level=level, mitigation=str(r.get("mitigation", "")),
                        module_id=task.module_id, source=f"run:{run_id}")
            project.risks[risk.id] = risk
        if self.lessons is not None:
            for lesson in output.get("lessons", []):
                if isinstance(lesson, str) and lesson.strip():
                    self.lessons.add(lesson.strip(),
                                     context=f"task '{task.title}' ({task.role})",
                                     source=f"{project.id}:{run_id}",
                                     tags=[task.role])

    # ---------------------------------------------------------- human review
    def approve_task(self, project_ref: str, task_ref: str) -> dict:
        """Human command: accept a NEEDS_VERIFY task as done."""
        project = self.store.load(project_ref)
        task = self._find_task(project, task_ref)
        if task.status is not TaskStatus.NEEDS_VERIFY:
            return {"status": "noop",
                    "summary": f"task is {task.status.value}, not needs_verify"}
        task.status = TaskStatus.DONE
        task.updated_at = utcnow()
        self._audit(project, "task.approved",
                    f"Human approved '{task.title}' past verification",
                    {"task_id": task.id}, actor="human")
        refresh_statuses(project)
        refresh_milestones(project)
        self.store.save(project)
        return {"status": "ok", "summary": f"'{task.title}' approved"}

    def _find_task(self, project: Project, ref: str) -> Task:
        if ref in project.tasks:
            return project.tasks[ref]
        matches = [t for tid, t in project.tasks.items() if tid.startswith(ref)]
        if len(matches) == 1:
            return matches[0]
        raise NotFoundError(f"no unique task matching '{ref}'")

    # --------------------------------------------------------------- finalize
    def finalize(self, project_ref: str) -> dict:
        project = self.store.load(project_ref)
        arts = [a for a in project.artifacts.values()
                if a.status.value in ("current", "accepted")]
        # be honest about what DIDN'T get done — finalize must never present a
        # partial run as complete (live finding: it synthesized from 4/7 tasks
        # with no mention of the failed test suite + blocked dependents).
        incomplete = [t for t in project.tasks.values()
                      if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)]
        gaps = [f"{t.title} [{t.status.value}]"
                + (f" — {t.error[:120]}" if t.error else "")
                for t in incomplete]
        gap_note = ("\n\nINCOMPLETE/FAILED TASKS — be HONEST about these gaps in "
                    "the report; do NOT present them as delivered:\n"
                    + "\n".join("- " + g for g in gaps)) if gaps else ""
        digest = "\n\n".join(
            f"### {a.title} ({a.kind})\n{a.content[:1200]}" for a in arts[-12:])
        spec = AgentSpec(
            role="synthesis",
            objective="Synthesize all project artifacts into one final, coherent "
                      "deliverable report aligned with the charter. Explicitly "
                      "note any incomplete or failed work.",
            context=(f"Charter objective: {project.charter.objective}\n"
                     f"Success criteria: "
                     f"{'; '.join(project.charter.success_criteria)}{gap_note}"
                     f"\n\nARTIFACTS:\n{digest}")[:8000],
            task_id="finalize")
        res = self.runner.run(spec)
        if not res.ok:
            return {"status": "failed", "summary": res.error}
        run = self._record_run(project, spec, res)

        # persist any artifacts the synthesis agent emitted as REAL project
        # artifacts (e.g. a reframed example/checklist), so they aren't lost
        synth_arts: list[Artifact] = []
        for a in res.output.get("artifacts", []):
            if not isinstance(a, dict) or not str(a.get("content", "")).strip():
                continue
            art = Artifact(
                title=str(a.get("title") or "synthesis artifact"),
                kind=str(a.get("kind", "report")),
                content=str(a.get("content", "")),
                provenance={"run_id": run.id, "role": "synthesis"})
            project.artifacts[art.id] = art
            synth_arts.append(art)
            try:
                self.store.mirror_artifact(project.id, art)
            except OSError as exc:
                log.warning("synthesis artifact mirror failed: %s", exc)

        # the FINAL bundles the real accepted artifacts (the actual
        # deliverables) PLUS any new synthesis artifacts — deduped by title —
        # so a thin/empty synthesis can never produce a hollow deliverable
        seen_titles = {a.title.strip() for a in arts}
        bundle = list(arts) + [a for a in synth_arts
                               if a.title.strip() not in seen_titles]
        body = "\n\n".join(f"## {a.title} ({a.kind})\n{a.content}"
                           for a in bundle)
        summary = str(res.output.get("summary", "")).strip()
        if not bundle:
            body = "(no source artifacts were produced by this project)"
        # verification ledger: how much GROUND TRUTH backs each deliverable, so
        # the FINAL is honest about its own fidelity (TRUSTED = a trusted checker
        # ran AND force-to-fail proven; judged = model output only, no oracle).
        ledger_rows = []
        for a in bundle:
            if a.kind == "property_report":
                continue
            checks = ((a.provenance or {}).get("partial") or {}).get("checks") \
                or []
            tier = ("TRUSTED — " + ", ".join(checks) if checks
                    else "judged (no trusted check ran)")
            ledger_rows.append(f"- {a.title} ({a.kind}): {tier}")
        if ledger_rows:
            body = ("## Verification ledger — ground truth behind each "
                    "deliverable\n" + "\n".join(ledger_rows) + "\n\n" + body)
        if gaps:        # an honest ledger of what was NOT delivered, up front
            body = ("## Known gaps — incomplete or failed work\n"
                    + "\n".join("- " + g for g in gaps) + "\n\n" + body)
        final = Artifact(
            title=f"FINAL: {project.name}",
            kind="report",
            content=(summary + "\n\n---\n\n" + body) if summary else body,
            provenance={"run_id": run.id,
                        "bundled_artifacts": [a.id for a in bundle]})
        project.artifacts[final.id] = final
        path = self.store.mirror_artifact(project.id, final)
        project.status = "finalized"
        self._audit(project, "project.finalized",
                    f"Final deliverable {final.id} -> {path}")
        self.store.save(project)
        return {"status": "ok", "summary": f"final deliverable at {path}",
                "artifact_id": final.id, "path": str(path)}

    # ----------------------------------------------------------------- status
    def status(self, project_ref: str) -> dict:
        project = self.store.load(project_ref)
        refresh_statuses(project)        # ensure readiness reflects deps
        summary = graph_summary(project)
        open_pkts = self._open_packets(project)
        needs_verify = [t for t in project.tasks.values()
                        if t.status is TaskStatus.NEEDS_VERIFY]
        failed = [t for t in project.tasks.values()
                  if t.status is TaskStatus.FAILED]
        next_action = "advance"
        if open_pkts:
            pk = open_pkts[0]
            key = pk.recommendation_key or (pk.options[0].key if pk.options
                                            else "A")
            next_action = f"decide {pk.id[:8]} --select {key}"
        elif needs_verify:
            next_action = f"approve {needs_verify[0].id[:8]} (or rerun)"
        elif not ready_tasks(project) and summary["done"] == summary["tasks_total"]:
            next_action = "finalize"
        elif failed and not ready_tasks(project):
            # a failed task with no ready work = its dependents are blocked. Don't
            # silently idle (live finding: a research timeout blocked 2 tasks and
            # the arc just spun) — point the commander at retrying it.
            next_action = (f"retry {failed[0].id[:8]} "
                           f"(failed; {len(failed)} blocking dependents)")
        scream = (project.scream_open
                  if (self.cfg.nervous_enabled and project.scream_open)
                  else None)
        if scream:
            next_action = (f"SCREAM: {scream['cause']} - recover then advance "
                           f"(clear: {scream.get('clear_rule', '')})")
        health = None
        if self.cfg.nervous_enabled:
            hbody = compute_body(project, secret=self.cfg.report_secret(),
                                 perf=self.perf, since=None, cfg=self.cfg)
            health = {"valence": hbody.valence,
                      "fragile_axes": list(hbody.fragile_axes)}
        return {
            "id": project.id, "name": project.name, "status": project.status,
            "objective": project.charter.objective,
            **summary,
            "open_packet_ids": [p.id for p in open_pkts],
            "needs_verify_ids": [t.id for t in needs_verify],
            "failed_ids": [t.id for t in failed],
            "artifacts": len(project.artifacts),
            "next_action": next_action,
            # `scream` and `health` are ALWAYS present in this dict but are None
            # when nervous is OFF (a documented superset, not a feature flag).
            # A caller must NOT read their mere presence as "nervous is on" —
            # check the value (or cfg.nervous_enabled), not the key.
            "scream": scream,
            "health": health,
        }
