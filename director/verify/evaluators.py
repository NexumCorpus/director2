"""Deterministic quality evaluators — ported from Director 1.0 and adapted.

These grade *structure and discipline*, not truth: does a CommandPacket present
a real decision? Does an agent output carry artifacts, claims, and evidence in
the required shape? They are intentionally heuristic and cheap; the sandbox
and domain verifiers carry the hard correctness load.

Scores are 1–5 per criterion, averaged, then mapped through the declared
``score_to_verdict`` rule. Scores within ±0.15 of an action boundary are
labeled ``fragile`` (RDE v11: knife-edge verdicts are declared, not rounded).
"""

from __future__ import annotations

from ..core.types import CommandPacket, VerificationReport
from .base import score_to_verdict

_BOUNDARIES = (2.5, 3.5, 4.5)
_FRAGILE_EPS = 0.15

_FORBIDDEN_OUTPUT_KEYS = {"state_mutation", "authoritative_state",
                          "direct_db_write", "apply_immediately"}


def _fragile(score: float) -> bool:
    return any(abs(score - b) < _FRAGILE_EPS for b in _BOUNDARIES)


def _word_count(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


class CommandPacketEvaluator:
    name = "command_packet"

    def verify(self, target: CommandPacket, context: dict | None = None
               ) -> VerificationReport:
        context = context or {}
        criteria: dict[str, float] = {}
        issues: list[str] = []
        suggestions: list[str] = []
        opts = target.options

        # 1. consequential options — materially different choices
        if len(opts) < 2:
            criteria["consequential_options"] = 1.0
            issues.append("fewer than 2 options - not a decision")
        else:
            profiles = {(o.risk_impact, o.reversibility,
                         str(sorted(o.state_delta.items()))) for o in opts}
            distinct = len(profiles) > 1
            with_consequences = sum(1 for o in opts if o.consequences)
            score = 2.0 + (1.5 if distinct else 0.0) + \
                1.5 * (with_consequences / len(opts))
            criteria["consequential_options"] = min(5.0, score)
            if not distinct:
                issues.append("options have identical impact profiles")

        # 2. tradeoff specificity
        if opts:
            per = []
            for o in opts:
                txt = " ".join(o.tradeoffs + o.consequences) + " " + o.description
                s = 1.0
                s += 1.5 if o.tradeoffs else 0.0
                s += 1.0 if o.consequences else 0.0
                s += 1.5 if _word_count(txt) >= 12 else 0.5
                per.append(min(5.0, s))
            criteria["tradeoff_specificity"] = sum(per) / len(per)
            if criteria["tradeoff_specificity"] < 3.0:
                suggestions.append("add explicit tradeoffs and downstream "
                                   "consequences per option")
        else:
            criteria["tradeoff_specificity"] = 1.0

        # 3. decision salience
        s = 1.0
        s += 2.0 if _word_count(target.title) >= 3 else 0.5
        s += 2.0 if target.context.strip() else 0.0
        criteria["decision_salience"] = min(5.0, s)
        if not target.context.strip():
            issues.append("packet has no decision context")

        # 4. decision safety — recommendation + risks + irreversibility flagged
        s = 1.0
        keys = {o.key for o in opts}
        if target.recommendation_key and target.recommendation_key in keys:
            s += 1.5
        else:
            issues.append("missing or dangling recommendation_key")
        s += 1.0 if target.rationale.strip() else 0.0
        s += 1.0 if target.risks else 0.0
        irreversible_unflagged = [
            o.key for o in opts
            if o.reversibility == "irreversible" and not (o.tradeoffs or o.consequences)]
        if irreversible_unflagged:
            issues.append(f"irreversible options without stated consequences: "
                          f"{irreversible_unflagged}")
        else:
            s += 0.5
        criteria["decision_safety"] = min(5.0, s)

        # 5. impact coherence — unique keys, populated impact fields
        if opts:
            unique = len(keys) == len(opts)
            populated = all(o.key and o.label and o.risk_impact for o in opts)
            criteria["impact_coherence"] = 1.0 + (2.0 if unique else 0.0) + \
                (2.0 if populated else 0.0)
            if not unique:
                issues.append("duplicate option keys")
        else:
            criteria["impact_coherence"] = 1.0

        # 6. steering power — at least one option changes state
        any_delta = any(o.state_delta for o in opts)
        criteria["steering_power"] = 4.5 if any_delta else 2.0
        if not any_delta:
            suggestions.append("no option carries a state_delta; selecting "
                               "an option will not steer the project")

        score = sum(criteria.values()) / max(1, len(criteria))
        blocking = len(opts) < 2
        severity, action = score_to_verdict(score, blocking=blocking)
        return VerificationReport(
            verifier=self.name, target=target.id, passed=score >= 2.5 and not blocking,
            score=round(score, 2), severity=severity, action=action,
            issues=issues, suggestions=suggestions,
            details={"criteria": {k: round(v, 2) for k, v in criteria.items()}},
            fragile=_fragile(score))


class AgentOutputEvaluator:
    """Grades the dict an agent returned. Context: {"objective", "role"}."""
    name = "agent_output"

    def verify(self, target: dict, context: dict | None = None
               ) -> VerificationReport:
        context = context or {}
        objective = str(context.get("objective", ""))
        role = str(context.get("role", ""))
        criteria: dict[str, float] = {}
        issues: list[str] = []
        suggestions: list[str] = []

        summary = str(target.get("summary", ""))
        artifacts = target.get("artifacts") or []

        # 1. objective fit — keyword overlap
        if objective:
            obj_terms = {w.lower().strip(".,:;") for w in objective.split()
                         if len(w) > 3}
            out_text = (summary + " " + " ".join(
                str(a.get("title", "")) + " " + str(a.get("content", ""))[:500]
                for a in artifacts if isinstance(a, dict))).lower()
            hit = sum(1 for t in obj_terms if t in out_text)
            ratio = hit / max(1, len(obj_terms))
            criteria["objective_fit"] = 1.0 + 4.0 * min(1.0, ratio * 2.0)
            if ratio < 0.2:
                issues.append("output barely references the task objective")
        # 2. clarity and structure
        s = 1.0
        s += 2.0 if len(summary) >= 40 else 0.5
        if artifacts:
            well_formed = all(isinstance(a, dict) and
                              len(str(a.get("title", ""))) >= 3 and
                              len(str(a.get("content", ""))) >= 20
                              for a in artifacts)
            s += 2.0 if well_formed else 0.5
            if not well_formed:
                issues.append("artifacts missing titles or substantive content")
        criteria["clarity_structure"] = min(5.0, s)

        # 3. downstream actionability
        recommends_packet = bool(target.get("command_packet_recommended"))
        has_reason = bool(str(target.get("command_packet_reason", "")).strip())
        actionable = bool(artifacts) or bool(target.get("recommended_updates")) \
            or (recommends_packet and has_reason)
        criteria["actionability"] = 4.5 if actionable else 2.0
        if recommends_packet and not has_reason:
            issues.append("recommends a command packet without a reason")
            criteria["actionability"] = 2.0

        # 4. claim discipline — research/analysis only
        if role in ("research", "analysis"):
            claims = target.get("claims") or []
            ok_claims = [c for c in claims if isinstance(c, dict)
                         and c.get("text") and c.get("confidence")]
            if ok_claims:
                criteria["claim_discipline"] = 4.5
            elif claims:
                criteria["claim_discipline"] = 3.0
                suggestions.append("claims need text + confidence fields")
            else:
                criteria["claim_discipline"] = 2.0
                suggestions.append("research output should carry a claim ledger")

        # 5. boundary control — agents recommend, they never mutate
        forbidden = _FORBIDDEN_OUTPUT_KEYS & set(target.keys())
        ru = target.get("recommended_updates")
        boundary_ok = not forbidden and (ru is None or isinstance(ru, dict))
        criteria["boundary_control"] = 5.0 if boundary_ok else 1.0
        if forbidden:
            issues.append(f"output attempts direct state mutation: {sorted(forbidden)}")

        # 6. artifact grounding — deliverable-producing roles must emit
        # artifacts. Live findings: a simulation agent reported coverage only
        # in prose (2026-06-12, ungroundable); a SYNTHESIS agent claimed an
        # example/checklist in prose but emitted nothing, passing as "done"
        # with a hollow result (2026-06-13). The finalize CALL is exempt — it
        # legitimately emits a summary and bundles source artifacts itself.
        spec = context.get("spec")
        is_finalize = getattr(spec, "task_id", "") == "finalize"
        artifact_required = role in ("code", "simulation", "synthesis") \
            and not is_finalize
        grounded = bool(artifacts) or not artifact_required
        if artifact_required:
            criteria["artifact_grounding"] = 4.5 if artifacts else 1.0
            if not artifacts:
                issues.append(
                    f"{role} output carries no artifacts - a deliverable "
                    f"claimed in prose but not emitted is ungroundable; emit "
                    f"it as an artifact")

        score = sum(criteria.values()) / max(1, len(criteria))
        blocking = not boundary_ok or not grounded
        severity, action = score_to_verdict(score, blocking=blocking)
        return VerificationReport(
            verifier=self.name, target=str(target.get("task_id", "")),
            passed=score >= 2.5 and not blocking,
            score=round(score, 2), severity=severity, action=action,
            issues=issues, suggestions=suggestions,
            details={"criteria": {k: round(v, 2) for k, v in criteria.items()},
                     "role": role},
            fragile=_fragile(score))
