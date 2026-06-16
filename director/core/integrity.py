"""Integrity self-check — re-validate every engine-stamped trusted report's HMAC
signature against the workspace secret.

This is the operator-facing companion to report signing: an ``INVALID`` row means
a persisted ``property_report`` was tampered with (or signed under a different
secret) — its partial badge would already be honestly downgraded at the display
boundary, and here it is surfaced explicitly rather than silently trusted.
``unsigned`` rows are legacy reports stamped before signing existed (a warning,
not a forgery).
"""

from __future__ import annotations

from ..verify.signing import report_binding_ok
from .types import Project


def report_integrity(project: Project, secret: bytes) -> list[dict]:
    """One row per property_report: status in {ok, unsigned, INVALID, no_report}.
    ``ok`` requires a signature BOUND to the carrying artifact and the exact
    deliverable it graded — a replayed or content-swapped report reads INVALID."""
    rows: list[dict] = []
    for art in project.artifacts.values():
        if getattr(art, "kind", "") != "property_report":
            continue
        prov = getattr(art, "provenance", None) or {}
        rep, sig, did = prov.get("report"), prov.get("report_sig"), \
            prov.get("deliverable")
        deliv = project.artifacts.get(did) if did else None
        if not isinstance(rep, dict):
            status = "no_report"
        elif not sig:
            status = "unsigned"
        elif deliv is not None and report_binding_ok(
                report=rep, sig=sig, report_id=art.id, deliverable_id=did,
                deliverable_content=getattr(deliv, "content", ""),
                secret=secret):
            status = "ok"
        else:
            status = "INVALID"   # bad binding, or graded deliverable missing
        rows.append({"artifact_id": art.id,
                     "task_id": getattr(art, "task_id", ""),
                     "title": art.title, "status": status})
    return rows


def integrity_violations(rows: list[dict]) -> list[dict]:
    """The hard failures: reports present but with a BROKEN signature (tamper
    evidence). Unsigned/no_report are not counted here (warnings)."""
    return [r for r in rows if r["status"] == "INVALID"]


def deliverable_partial_ok(project: Project, deliverable, secret: bytes) -> bool:
    """True iff ``deliverable``'s VERIFIED_PARTIAL badge is genuine: its backing
    report's signature is BOUND to this deliverable (id + current content). The
    single source of truth for "should this partial badge be shown/trusted",
    shared by the dashboard digest and the integrity summary."""
    part = (getattr(deliverable, "provenance", None) or {}).get("partial")
    if not part:
        return False
    rart = project.artifacts.get(part.get("report_id"))
    rprov = (getattr(rart, "provenance", None) or {}) if rart else {}
    return bool(rart and report_binding_ok(
        report=rprov.get("report"), sig=rprov.get("report_sig"),
        report_id=rart.id, deliverable_id=getattr(deliverable, "id", ""),
        deliverable_content=getattr(deliverable, "content", "") or "",
        secret=secret))


def integrity_summary(project: Project, secret: bytes,
                      rows: list[dict] | None = None) -> dict:
    """Project-level verification health for the dashboard: report-signature
    tallies + how many deliverables carry a genuine partial badge. Pass
    precomputed ``rows`` to avoid re-verifying signatures twice in one digest."""
    if rows is None:
        rows = report_integrity(project, secret)
    status = {"ok": 0, "unsigned": 0, "INVALID": 0, "no_report": 0}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    partial = sum(1 for a in project.artifacts.values()
                  if deliverable_partial_ok(project, a, secret))
    return {"reports": status, "violations": status.get("INVALID", 0),
            "partial_deliverables": partial}
