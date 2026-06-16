"""HMAC signing for engine-stamped trusted reports — cross-process tamper-
evidence.

In-process, an agent already cannot write an artifact's provenance, so a
``property_report`` parked in provenance is un-forgeable while the Director runs.
This module defends the *persisted* state: a hand-edited snapshot could inject a
fake report into provenance. Signing the report with a per-workspace secret kept
OUTSIDE the snapshot means a tampered or fabricated report won't carry a valid
signature, so the display-boundary bundle gate can reject it.

The signature is stored ALONGSIDE the report (provenance['report_sig']), computed
over the clean report dict, so the report itself is unchanged.
"""

from __future__ import annotations

import hashlib
import hmac
import json


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign(payload: dict, secret: bytes) -> str:
    """HMAC-SHA256 hex digest of the canonical JSON of ``payload``."""
    if not secret:
        return ""
    return hmac.new(secret, _canonical(payload), hashlib.sha256).hexdigest()


def verify(payload: dict, sig: str, secret: bytes) -> bool:
    """True iff ``sig`` is a valid signature of ``payload`` under ``secret``.
    Constant-time compare. A missing sig or secret is INVALID (fail-closed)."""
    if not sig or not secret or not isinstance(payload, dict):
        return False
    return hmac.compare_digest(sign(payload, secret), str(sig))


def content_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def bound_payload(report: dict, *, report_id: str, deliverable_id: str,
                  deliverable_sha: str) -> dict:
    """The payload that is actually signed: the report BOUND to the artifact that
    carries it and the deliverable (by id + content hash) it graded.

    Without this binding a signed report is a BEARER TOKEN (red-team finding):
    an editor with no secret could replay a legitimately-signed passing report
    onto a garbage deliverable, or swap the graded content while keeping the
    valid signature. Binding makes a signature meaningful only for the exact
    (report-artifact, deliverable, deliverable-bytes) it was minted for."""
    return {"r": report, "rid": report_id or "", "did": deliverable_id or "",
            "dsha": deliverable_sha or ""}


def report_binding_ok(*, report, sig, report_id: str, deliverable_id: str,
                      deliverable_content: str, secret: bytes) -> bool:
    """Verify a report's signature is valid AND bound to this exact carrying
    artifact and deliverable content. Fail-closed."""
    if not isinstance(report, dict):
        return False
    payload = bound_payload(report, report_id=report_id,
                            deliverable_id=deliverable_id,
                            deliverable_sha=content_sha(deliverable_content))
    return verify(payload, sig or "", secret)
