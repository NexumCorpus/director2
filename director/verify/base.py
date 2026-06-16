"""Verifier contract + chain.

A Verifier inspects a target (agent output dict, CommandPacket, code string...)
and returns a :class:`~director.core.types.VerificationReport` with declared
severity→action semantics. Chains run several verifiers and reduce to a single
gate decision. Verifiers are TRUSTED CODE — the constitution's "correctness
decoupling": generators never grade themselves.
"""

from __future__ import annotations

from typing import Callable, Protocol

from ..core.types import Severity, VerificationReport, VerifyAction
from ..logging_setup import get_logger

log = get_logger("verify")


class Verifier(Protocol):
    name: str

    def verify(self, target, context: dict | None = None) -> VerificationReport: ...


def score_to_verdict(score: float, *, blocking: bool = False,
                     major: bool = False) -> tuple[Severity, VerifyAction]:
    """Director 1.0's declared mapping from a 1–5 score to severity/action."""
    if blocking or score < 2.5:
        return Severity.BLOCKING, VerifyAction.REJECT
    if major or score < 3.5:
        return Severity.MAJOR, VerifyAction.REQUIRE_HUMAN_REVIEW
    if score < 4.5:
        return Severity.MINOR, VerifyAction.LOG_ONLY
    return Severity.INFO, VerifyAction.AUTO_APPROVE


class VerifierRegistry:
    """Name → verifier factory, so Tasks can carry verifier names as plain
    strings in persisted state."""

    def __init__(self):
        self._factories: dict[str, Callable[[], Verifier]] = {}

    def register(self, name: str, factory: Callable[[], Verifier]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> Verifier:
        if name not in self._factories:
            raise KeyError(f"unknown verifier '{name}' "
                           f"(known: {sorted(self._factories)})")
        return self._factories[name]()

    def names(self) -> list[str]:
        return sorted(self._factories)


def run_chain(verifiers: list[Verifier], target, *,
              context: dict | None = None) -> list[VerificationReport]:
    """Run every verifier (no short-circuit — full evidence beats fast exit)."""
    reports = []
    for v in verifiers:
        try:
            reports.append(v.verify(target, context or {}))
        except Exception as exc:                              # noqa: BLE001
            log.exception("verifier %s crashed", getattr(v, "name", v))
            reports.append(VerificationReport(
                verifier=getattr(v, "name", str(v)), passed=False, score=1.0,
                severity=Severity.BLOCKING, action=VerifyAction.REQUIRE_HUMAN_REVIEW,
                issues=[f"verifier crashed: {exc}"]))
    return reports


def chain_passed(reports: list[VerificationReport]) -> bool:
    """The gate: no REJECT and no blocking severity."""
    return all(r.action is not VerifyAction.REJECT and
               r.severity is not Severity.BLOCKING for r in reports)


def chain_needs_human(reports: list[VerificationReport]) -> bool:
    return any(r.action is VerifyAction.REQUIRE_HUMAN_REVIEW for r in reports)
