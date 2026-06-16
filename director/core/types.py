"""Domain model: plain dataclasses + StrEnums, with a small generic
encode/decode pair so every entity round-trips through JSON without
hand-written (de)serializers.

Design lineage: Director 1.0's entity set (Charter, Module, Task, CommandPacket,
StateDelta, AuditEvent ...) merged with RDE's evidence discipline
(VerificationReport with declared ``fragile`` semantics, Lesson ledger).
"""

from __future__ import annotations

import dataclasses
import types as _types
import typing
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class ModuleStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    IN_COMMAND = "in_command"     # human has taken direct command
    FROZEN = "frozen"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    DEPRECATED = "deprecated"


class ModuleType(StrEnum):
    RESEARCH = "research"
    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    DOCUMENTATION = "documentation"
    STRATEGY = "strategy"
    SIMULATION = "simulation"
    DISCOVERY = "discovery"       # hosts recursive improvement-loop runs


class TaskStatus(StrEnum):
    PENDING = "pending"           # deps not met yet
    READY = "ready"               # runnable now
    RUNNING = "running"
    NEEDS_VERIFY = "needs_verify" # output produced, verifier chain pending/failed
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"           # needs human judgment


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    CURRENT = "current"
    ACCEPTED = "accepted"
    STALE = "stale"
    REJECTED = "rejected"


class PacketStatus(StrEnum):
    DRAFT = "draft"
    PRESENTED = "presented"
    ANSWERED = "answered"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ResponseType(StrEnum):
    SELECT_OPTION = "select_option"
    SELECT_AND_MODIFY = "select_and_modify"
    DEFER = "defer"
    REJECT_ALL = "reject_all"
    TAKE_COMMAND = "take_command"
    MANUAL = "manual"


class Severity(StrEnum):
    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class VerifyAction(StrEnum):
    REJECT = "reject"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    LOG_ONLY = "log_only"
    AUTO_APPROVE = "auto_approve"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    REALIZED = "realized"


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    REACHED = "reached"
    MISSED = "missed"


class ConvictionType(StrEnum):
    """A command-option's relationship to the proven baseline — steering
    vocabulary, not personality. Exhaustive: conform / exceed / reframe.

    These map onto the RDE verdict ledger:
      DOGMATIC   -> matches_human  (conform to the proven baseline/pattern)
      ICONOCLAST -> beats_human    (exceed it; reform the primitive)
      HERETIC    -> domain pivot   (reject the framing; the problem is wrong)
    """
    DOGMATIC = "dogmatic"
    ICONOCLAST = "iconoclast"
    HERETIC = "heretic"


class CheckKind(StrEnum):
    """Provenance of an option's confidence score. VERIFIED is load-bearing:
    it may only exist when an external oracle/test-runner actually ran and
    left an artifact. Absent that, confidence degrades to JUDGED (a model's
    assessment, no ground truth) or NONE."""
    NONE = "none"
    JUDGED = "judged"        # model judgment, no ground truth
    # a TRUSTED (human/hook-authored) necessary-condition checker ran in the
    # sandbox, was proven force-to-fail (rejects a known-bad sibling), its
    # reference is independent of the work's author, and the deliverable
    # passed — leaving a property_report artifact. Strictly stronger than
    # JUDGED, strictly weaker than VERIFIED. Renders amber "N/M (trusted)",
    # NEVER the green check. The boundary narrowed, never faked.
    VERIFIED_PARTIAL = "verified_partial"
    VERIFIED = "verified"    # FULL trusted oracle ran; MUST cite an artifact


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #

@dataclass
class Charter:
    objective: str = ""
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    risk_posture: str = "medium"
    version: int = 1


@dataclass
class Module:
    name: str
    type: ModuleType = ModuleType.IMPLEMENTATION
    purpose: str = ""
    id: str = field(default_factory=new_id)
    status: ModuleStatus = ModuleStatus.PROPOSED
    depends_on: list[str] = field(default_factory=list)        # module ids
    acceptance_criteria: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class Task:
    title: str
    role: str = "research"                 # agent role key (agents/roles.py or hook roles)
    objective: str = ""
    module_id: str = ""
    id: str = field(default_factory=new_id)
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)        # task ids
    context: str = ""                       # background handed to the agent
    inputs: dict = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)          # verifier names to gate DONE
    # trusted necessary-condition checkers to run over this task's deliverable
    # for VERIFIED_PARTIAL (verify/properties.py names). Optional; declared by
    # plans/hooks. {"schema_ref_task": "<title>"} in inputs supplies a schema.
    properties: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    milestone_id: str = ""
    # the decision (id) that spawned this task, if any — set when a command
    # packet's chosen option created it. Powers calibration (a conviction's
    # track record) with a RECORDED causal link, never an inferred one.
    origin_decision_id: str = ""
    attempts: int = 0
    max_attempts: int = 2
    result_summary: str = ""
    error: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class Milestone:
    name: str
    description: str = ""
    id: str = field(default_factory=new_id)
    task_ids: list[str] = field(default_factory=list)
    status: MilestoneStatus = MilestoneStatus.PENDING


@dataclass
class Risk:
    title: str
    description: str = ""
    id: str = field(default_factory=new_id)
    level: RiskLevel = RiskLevel.MEDIUM
    likelihood: str = "possible"            # unlikely | possible | likely
    status: RiskStatus = RiskStatus.OPEN
    mitigation: str = ""
    module_id: str = ""
    source: str = ""                         # who raised it (human / agent run id)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Assumption:
    statement: str
    id: str = field(default_factory=new_id)
    confidence: str = "medium"               # low | medium | high
    status: str = "active"                   # active | validated | invalidated | retired
    evidence: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    title: str
    kind: str = "markdown"                   # markdown | code | json | report | dialogue | quest | sim
    content: str = ""
    id: str = field(default_factory=new_id)
    module_id: str = ""
    task_id: str = ""
    status: ArtifactStatus = ArtifactStatus.CURRENT
    provenance: dict = field(default_factory=dict)   # run id, model, verifier results...
    version: int = 1
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class VerificationReport:
    """Declared-semantics verdict from one verifier. ``fragile`` marks results
    that straddle a threshold (RDE v11 lesson: knife-edge verdicts are labeled,
    never silently rounded up)."""
    verifier: str
    target: str = ""                          # what was verified (task/artifact/run id)
    passed: bool = False
    score: float = 0.0                        # 1..5 for evaluators; domain units otherwise
    severity: Severity = Severity.INFO
    action: VerifyAction = VerifyAction.LOG_ONLY
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    fragile: bool = False
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class AgentRun:
    task_id: str
    role: str
    id: str = field(default_factory=new_id)
    backend: str = ""
    model: str = ""
    status: str = "pending"                   # pending | succeeded | failed
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens
    latency_s: float = 0.0
    error: str = ""
    # the raw model GENERATION text behind this run (round-trips via the
    # generic encode/decode — zero migration). Generation, not reasoning.
    raw_generation: str = ""
    started_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None


@dataclass
class CommandOption:
    key: str
    label: str
    description: str = ""
    tradeoffs: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    risk_impact: str = "neutral"
    reversibility: str = "reversible"          # reversible | costly | irreversible
    state_delta: dict = field(default_factory=dict)   # applied if selected
    # steering: how this move relates to the proven baseline (one of
    # ConvictionType). "" only for legacy/neutral options.
    conviction: str = ""
    # confidence provenance — CheckKind. A VERIFIED check is a hard claim that
    # an external oracle ran; it MUST carry verification_artifact_id, else it
    # is dishonest and gets downgraded (see core.convictions).
    check: str = "none"
    check_score: float | None = None
    verification_artifact_id: str = ""         # required iff check == verified*
    # for VERIFIED_PARTIAL: how many trusted necessary-condition checks passed
    # of how many declared. The denominator is shown so 1/1 can't impersonate
    # full coverage; the residual is honestly still JUDGED.
    sub_claims_verified: int = 0
    sub_claims_total: int = 0
    calibration: str = ""                       # JUDGED sub-label, e.g. "p=0.62 (n=40)"


@dataclass
class CommandPacket:
    """A consequential choice surfaced to the human commander — CRPG-style
    options with tradeoffs and a recommendation, not an approval form."""
    title: str
    context: str = ""
    trigger: str = ""
    id: str = field(default_factory=new_id)
    options: list[CommandOption] = field(default_factory=list)
    recommendation_key: str = ""
    rationale: str = ""
    affected_modules: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    default_if_deferred: str = ""
    status: PacketStatus = PacketStatus.DRAFT
    created_at: datetime = field(default_factory=utcnow)
    answered_at: datetime | None = None


@dataclass
class DecisionEvent:
    packet_id: str
    response_type: ResponseType = ResponseType.SELECT_OPTION
    selected_key: str = ""
    modifications: str = ""
    rationale: str = ""
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class StateDelta:
    trigger: str                               # decision id / run id / "manual"
    summary: str = ""
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    status: str = "proposed"                   # proposed | applied | blocked
    created_at: datetime = field(default_factory=utcnow)
    applied_at: datetime | None = None


@dataclass
class AuditEvent:
    type: str
    summary: str = ""
    actor: str = "director"                    # director | human | agent:<role> | system
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Lesson:
    text: str
    context: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""                            # project/run that produced it
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class BodyState:
    """Trusted valence projection recomputed each cycle (NEVER mutated in
    place; recreated by the Body reducer). Not frozen — this file has no frozen
    dataclasses; immutability here is by discipline. EVERY field is defaulted so
    decode() of an older/partial snapshot can never raise. The float | str union
    fields resolve "insufficient" to the STR arm (decode tries float() first; it
    raises ValueError on the sentinel and falls through to str)."""
    charter_integrity: float | str = "insufficient"   # severity 0..1, or "insufficient"
    accumulated_damage: float = 0.0                    # severity 0..1
    uncertainty: float = 0.0                           # severity 0..1
    resource_bleed: float | str = "insufficient"       # severity 0..1, or "insufficient"
    valence: float = 0.0                               # composite, [-1, 0]
    fragile_axes: list[str] = field(default_factory=list)
    computed_at: int = 0                               # cycle_seq, NOT wall-clock
    provenance: dict = field(default_factory=dict)     # {risk_ids:[...], run_ids:[...]} pointers


@dataclass
class Project:
    name: str
    id: str = field(default_factory=new_id)
    status: str = "active"                      # active | finalized | archived
    charter: Charter = field(default_factory=Charter)
    modules: dict[str, Module] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    milestones: dict[str, Milestone] = field(default_factory=dict)
    risks: dict[str, Risk] = field(default_factory=dict)
    assumptions: dict[str, Assumption] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    runs: dict[str, AgentRun] = field(default_factory=dict)
    packets: dict[str, CommandPacket] = field(default_factory=dict)
    decisions: dict[str, DecisionEvent] = field(default_factory=dict)
    deltas: dict[str, StateDelta] = field(default_factory=dict)
    # --- nervous-system v1 (inert data until the Body reads it) -------------
    body: BodyState | None = None              # trusted valence projection, recomputed per cycle
    scream_open: dict | None = None            # the latch: {cause, axis, opened_at, held_cycles, clear_rule, origin_refs} or None
    cycle_seq: int = 0                         # deterministic per-advance counter (NOT wall-clock)
    milestone_reverts: int = 0                 # charter_integrity signal (incremented at the revert log site)
    coherence_blocks: int = 0                  # charter_integrity signal (incremented where a delta is blocked)
    # --- gut markers (v2) ---------------------------------------------------
    marker_deferrals: dict = field(default_factory=dict)   # {task_id: deferral_count}
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Generic encode/decode — one serializer for the whole model.
# --------------------------------------------------------------------------- #

def encode(obj):
    """Dataclass / enum / datetime / container → JSON-safe structure."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, StrEnum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [encode(v) for v in obj]
    return obj


def decode(cls, data):
    """Inverse of :func:`encode` for the types this module defines.

    Resolves field types via ``typing.get_type_hints`` so nested dataclasses,
    ``list[T]``, ``dict[str, T]``, ``X | None``, enums and datetimes all
    round-trip. Unknown keys in ``data`` are ignored (forward compatibility).
    """
    return _decode_value(cls, data)


def _decode_value(tp, value):
    if value is None:
        return None
    origin = typing.get_origin(tp)
    # X | None / Optional[X] / unions: try each arm, prefer non-None
    if origin in (typing.Union, _types.UnionType):
        for arm in typing.get_args(tp):
            if arm is type(None):
                continue
            try:
                return _decode_value(arm, value)
            except (TypeError, ValueError):
                continue
        # Every typed arm failed (e.g. an unknown enum value from a forward
        # schema). The field is Optional, so None is the type-safe fallback —
        # returning the raw value would leave a wrong-typed field behind.
        return None
    if origin in (list, tuple):
        (item_tp, *_rest) = typing.get_args(tp) or (typing.Any,)
        return [_decode_value(item_tp, v) for v in value]
    if origin is dict:
        args = typing.get_args(tp)
        val_tp = args[1] if len(args) == 2 else typing.Any
        return {str(k): _decode_value(val_tp, v) for k, v in value.items()}
    if tp is typing.Any:
        return value
    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            hints = typing.get_type_hints(tp)
            kwargs = {}
            for f in dataclasses.fields(tp):
                if f.name in value:
                    kwargs[f.name] = _decode_value(hints.get(f.name, typing.Any),
                                                   value[f.name])
            return tp(**kwargs)
        if issubclass(tp, StrEnum):
            return tp(value)
        if tp is datetime:
            return value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if tp in (int, float, str, bool):
            return tp(value) if not isinstance(value, tp) else value
    return value
