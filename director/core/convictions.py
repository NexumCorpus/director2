"""Conviction steering + verifier honesty + conviction drift.

Three pure concerns over command packets and project history:

1. **Conviction vocabulary** — every option relates to the proven baseline as
   one of DOGMATIC (conform), ICONOCLAST (exceed), HERETIC (reframe). The
   Commander's pick is the steering signal for the next agent move.

2. **Verifier honesty (load-bearing)** — a ``VERIFIED`` check may exist ONLY
   when an external oracle ran and left an artifact. :func:`honest_check`
   downgrades any unbacked ``VERIFIED`` to ``JUDGED`` at the display boundary,
   and :func:`verifier_honesty_violations` is the build-time guard that fails
   if such a packet is constructed. A green check firing where nothing was
   externally verified is the exact blind-trust failure this system exists to
   kill — so it is impossible to *render* and impossible to *ship*.

3. **Conviction drift** — a per-character disposition derived from the
   decision history (hidden tallies, surfaced only as a one-line read). It
   accumulates across nodes, so it is a relationship to reality rather than a
   series of independent quizzes.
"""

from __future__ import annotations

from .types import (CheckKind, CommandOption, CommandPacket, ConvictionType,
                    Project, ResponseType)

CONVICTIONS = (ConvictionType.DOGMATIC, ConvictionType.ICONOCLAST,
               ConvictionType.HERETIC)

_PICK_RESPONSES = {ResponseType.SELECT_OPTION, ResponseType.SELECT_AND_MODIFY}


# --------------------------------------------------------------------------- #
# Verifier honesty
# --------------------------------------------------------------------------- #

def _resolve_report_and_sig(opt: CommandOption,
                            artifacts: dict | None) -> tuple:
    """(report, sig) backing a VERIFIED_PARTIAL option, or (None, None). Read
    ONLY from the artifact's PROVENANCE — which is engine-stamped by trusted code
    (run_properties / _ingest), NEVER agent-writable. The artifact CONTENT is
    agent-controllable (ArtifactOut carries title/kind/content), so a
    content-parsed report would be a forgeable bundle (red-team finding) — we
    never read it. ``sig`` is the HMAC over the report for the persisted-state
    boundary."""
    if not artifacts or not opt.verification_artifact_id:
        return None, None
    art = artifacts.get(opt.verification_artifact_id)
    if art is None:
        return None, None
    prov = getattr(art, "provenance", None) or {}
    rep = prov.get("report")
    return (rep if isinstance(rep, dict) else None), prov.get("report_sig")


def _resolve_report(opt: CommandOption, artifacts: dict | None) -> dict | None:
    """The property_report backing a VERIFIED_PARTIAL option (no sig)."""
    return _resolve_report_and_sig(opt, artifacts)[0]


def _partial_binding_ok(opt: CommandOption, artifacts: dict | None,
                        secret: bytes) -> bool:
    """The report's signature is valid AND bound to its carrying artifact and the
    exact deliverable (id + content) it graded. Defeats bearer-token replay: a
    signed report cannot be transplanted onto a different deliverable, nor can
    the graded content be swapped under a still-valid signature."""
    if not artifacts or not opt.verification_artifact_id:
        return False
    rart = artifacts.get(opt.verification_artifact_id)
    if rart is None:
        return False
    prov = getattr(rart, "provenance", None) or {}
    report, sig, did = prov.get("report"), prov.get("report_sig"), \
        prov.get("deliverable")
    deliv = artifacts.get(did) if did else None
    if not isinstance(report, dict) or deliv is None:
        return False
    from ..verify.signing import report_binding_ok
    return report_binding_ok(report=report, sig=sig,
                             report_id=getattr(rart, "id", ""),
                             deliverable_id=did,
                             deliverable_content=getattr(deliv, "content", ""),
                             secret=secret)


def honest_check(opt: CommandOption,
                 artifacts: dict | None = None, *,
                 secret: bytes | None = None) -> tuple[str, float | None]:
    """The check kind safe to DISPLAY for ``opt``.

    * ``VERIFIED`` with no artifact (or an id that doesn't resolve) degrades to
      ``JUDGED`` — a green check over nothing is the blind-trust failure.
    * ``VERIFIED_PARTIAL`` whose backing property_report doesn't satisfy the
      bundle gate (trusted + lineage-independent + force-to-fail-proven + >=1
      counted check passed) degrades to ``JUDGED`` — a partial badge must be
      earned, never asserted.

    Pass ``project.artifacts`` to resolve ids; pass ``None`` to enforce only
    the weaker "must cite an id" bar (which fail-safes partials to JUDGED)."""
    kind = opt.check or CheckKind.NONE
    if kind == CheckKind.VERIFIED:
        backed = bool(opt.verification_artifact_id) and (
            artifacts is None or opt.verification_artifact_id in artifacts)
        if not backed:
            return CheckKind.JUDGED, opt.check_score
    elif kind == CheckKind.VERIFIED_PARTIAL:
        from ..verify.properties import partial_bundle_ok
        report, _sig = _resolve_report_and_sig(opt, artifacts)
        if not partial_bundle_ok(report):
            return CheckKind.JUDGED, opt.check_score
        # persisted-state boundary: the report's signature must be BOUND to its
        # carrying artifact and the exact deliverable it graded — a replayed or
        # content-swapped report has no valid binding and degrades to JUDGED.
        if secret is not None and not _partial_binding_ok(opt, artifacts,
                                                          secret):
            return CheckKind.JUDGED, opt.check_score
        # badge self-consistency: a displayed N/M may not exceed or differ from
        # what the report actually counted (no decorative fraction)
        if opt.sub_claims_total and (
                opt.sub_claims_verified != report.get("n_passed")
                or opt.sub_claims_total != report.get("n_total")):
            return CheckKind.JUDGED, opt.check_score
    return kind, opt.check_score


def verifier_honesty_violations(packet: CommandPacket,
                                project: Project | None = None) -> list[str]:
    """Build-time guard. Returns reasons a packet is dishonest about
    verification (empty == honest). A VERIFIED or VERIFIED_PARTIAL option that
    isn't genuinely backed — the blind-trust rebuild — is a violation and must
    fail tests."""
    from ..verify.properties import partial_bundle_ok
    arts = project.artifacts if project is not None else None
    problems: list[str] = []
    for o in packet.options:
        kind = o.check or CheckKind.NONE
        if kind == CheckKind.VERIFIED:
            if not o.verification_artifact_id:
                problems.append(
                    f"option '{o.key}' claims VERIFIED with no "
                    f"verification_artifact_id (no external oracle backs it)")
            elif arts is not None and o.verification_artifact_id not in arts:
                problems.append(
                    f"option '{o.key}' cites verification artifact "
                    f"'{o.verification_artifact_id}' that does not exist")
        elif kind == CheckKind.VERIFIED_PARTIAL:
            if not o.verification_artifact_id:
                problems.append(
                    f"option '{o.key}' claims VERIFIED_PARTIAL with no "
                    f"property_report artifact")
            elif arts is not None:
                if o.verification_artifact_id not in arts:
                    problems.append(
                        f"option '{o.key}' cites property_report "
                        f"'{o.verification_artifact_id}' that does not exist")
                elif not partial_bundle_ok(_resolve_report(o, arts)):
                    problems.append(
                        f"option '{o.key}' VERIFIED_PARTIAL bundle is invalid "
                        f"(needs trusted + independent-lineage + force-to-fail "
                        f"+ >=1 passed) — a partial badge over nothing")
    return problems


# --------------------------------------------------------------------------- #
# Conviction coverage (for option construction / prompts)
# --------------------------------------------------------------------------- #

def conviction_violations(packet: CommandPacket) -> list[str]:
    """Every numbered response must carry exactly one valid conviction."""
    valid = {c.value for c in CONVICTIONS}
    problems = []
    for o in packet.options:
        if o.conviction not in valid:
            problems.append(
                f"option '{o.key}' has no valid conviction "
                f"(got {o.conviction!r}; need one of {sorted(valid)})")
    return problems


# --------------------------------------------------------------------------- #
# Conviction drift — hidden tally, surfaced only as a read
# --------------------------------------------------------------------------- #

def _option_by_key(packet: CommandPacket, key: str) -> CommandOption | None:
    return next((o for o in packet.options if o.key == key), None)


def conviction_tally(project: Project) -> dict[str, int]:
    """Hidden per-character tally: how many times each conviction was CHOSEN
    across the decision history. Derived from decisions (not stored) so it can
    never desync from what actually happened."""
    tally = {c.value: 0 for c in CONVICTIONS}
    for dec in project.decisions.values():
        if dec.response_type not in _PICK_RESPONSES:
            continue
        pkt = project.packets.get(dec.packet_id)
        if not pkt:
            continue
        opt = _option_by_key(pkt, dec.selected_key)
        if opt and opt.conviction in tally:
            tally[opt.conviction] += 1
    return tally


def conviction_read(project: Project) -> str:
    """One-line disposition descriptor — never the raw integers. The read is
    a relationship to reality accumulated across the whole session."""
    t = conviction_tally(project)
    total = sum(t.values())
    if total == 0:
        return "Disposition unformed — no convictions chosen yet."
    d = t[ConvictionType.DOGMATIC]
    i = t[ConvictionType.ICONOCLAST]
    h = t[ConvictionType.HERETIC]
    top = max(d, i, h)
    leaders = [k for k, v in (("d", d), ("i", i), ("h", h)) if v == top]
    # a real lean needs a sole leader holding a plurality (≥ ~45%)
    if len(leaders) > 1 or top < total * 0.45:
        return ("Even-handed — moves between conforming, reforming, and "
                "reframing as the problem demands.")
    lead = leaders[0]
    if lead == "h":
        return ("Trending Heretic — keeps rejecting the framing; this "
                "commander distrusts the problem as posed.")
    if lead == "i":
        return ("Trending Iconoclast — pushes past the proven baseline, "
                "favoring reform over conformity.")
    return ("Trending Dogmatic — converging on proven solutions; trusts the "
            "established baseline.")


def verifier_favored_key(packet: CommandPacket,
                         project: Project | None = None) -> str | None:
    """The option the VERIFIER currently favors: the highest-scoring option
    whose check is honestly VERIFIED. None if no option is verified. This is
    what the ★ recommendation should track when ground truth exists."""
    arts = project.artifacts if project is not None else None
    best_key, best_score = None, float("-inf")
    for o in packet.options:
        kind, score = honest_check(o, arts)
        if kind == CheckKind.VERIFIED and (score if score is not None
                                           else 0) > best_score:
            best_key, best_score = o.key, (score if score is not None else 0)
    return best_key


# --------------------------------------------------------------------------- #
# Packet coherence — a trusted evaluation of the decision itself
# --------------------------------------------------------------------------- #

def evaluate_packet_coherence(packet: CommandPacket,
                              project: Project | None = None) -> dict:
    """Trusted coherence evaluation of a command packet. Scores whether the
    decision is well-formed as a *choice of stance backed by honest evidence*:

      * conviction-complete — every option carries a valid conviction
      * spread — options offer ≥2 distinct convictions (a real stance choice,
        not three flavors of the same move)
      * verifier-honest — no option claims VERIFIED without a backing artifact
      * recommendation valid — the ★ points at a real option
      * recommendation honest — when ground truth exists, the ★ tracks the
        verifier-favored option (not a judged guess over measured evidence)
      * distinct outcomes — options don't collapse to the same state change

    Returns {score 0..1, ok, issues[], warnings[], spread, favored_key}.
    Hard issues (not ok): incomplete convictions, dishonest verification,
    dangling recommendation. The rest are warnings.
    """
    issues: list[str] = []
    warnings: list[str] = []
    opts = packet.options

    issues.extend(conviction_violations(packet))
    issues.extend(verifier_honesty_violations(packet, project))

    keys = {o.key for o in opts}
    if packet.recommendation_key and packet.recommendation_key not in keys:
        issues.append(f"recommendation '{packet.recommendation_key}' is not "
                      f"an option")

    spread = len({o.conviction for o in opts if o.conviction})
    if len(opts) >= 2 and spread < 2:
        warnings.append("all options share one conviction — not a real "
                        "choice of stance")

    favored = verifier_favored_key(packet, project)
    if favored and packet.recommendation_key:
        rec = next((o for o in opts if o.key == packet.recommendation_key),
                   None)
        rec_kind = honest_check(rec, project.artifacts if project else None
                                )[0] if rec else CheckKind.NONE
        if packet.recommendation_key != favored \
                and rec_kind != CheckKind.VERIFIED:
            warnings.append(
                f"recommendation '{packet.recommendation_key}' is not the "
                f"verifier-favored option '{favored}' (measured evidence "
                f"points elsewhere)")

    deltas = [str(sorted((o.state_delta or {}).items())) for o in opts]
    if len(opts) >= 2 and len(set(deltas)) < len(deltas):
        warnings.append("two or more options carry identical state changes")

    # score: start full, dock for issues (hard) and warnings (soft)
    score = 1.0 - 0.34 * len(issues) - 0.12 * len(warnings)
    score = max(0.0, min(1.0, score))
    return {"score": round(score, 2), "ok": not issues,
            "issues": issues, "warnings": warnings,
            "spread": spread, "favored_key": favored}


# RT-shaped rank ladder (Rogue Trader: Follower→Zealot at escalating gates),
# scaled to decision counts rather than 15/75/150/300/600 conviction points.
_RANK_LADDER = [(1, "Follower"), (3, "Adherent"), (6, "Votary"),
                (10, "Fanatic"), (15, "Zealot")]


def conviction_rank(project: Project) -> dict:
    """The dominant conviction's earned RANK (RT translation): rank is a
    legible, earned standing — not a buff. ``rank`` 0 = unaligned. The rank a
    project holds in its dominant conviction is what later reshapes the option
    space the Director surfaces (see _make_packet)."""
    t = conviction_tally(project)
    total = sum(t.values())
    if total == 0:
        return {"conviction": None, "points": 0, "rank": 0,
                "rank_name": "Unaligned"}
    dom = max(CONVICTIONS, key=lambda c: t[c])   # ties -> ladder order
    pts = t[dom]
    rank, name = 0, "Initiate"
    for i, (thr, nm) in enumerate(_RANK_LADDER, start=1):
        if pts >= thr:
            rank, name = i, nm
    return {"conviction": dom.value, "points": pts, "rank": rank,
            "rank_name": name}


def conviction_state(project: Project) -> dict:
    """Bundle for the API: the hidden tallies stay server-side context; the
    UI is handed the read, the earned rank, the calibration track-record line,
    and the typed-decision count — never the raw per-type integers as a surfaced
    score. Calibration is imported lazily (it imports back from this module)."""
    from .calibration import calibration_read
    t = conviction_tally(project)
    return {"read": conviction_read(project),
            "rank": conviction_rank(project),
            "calibration": calibration_read(project),
            "decisions_typed": sum(t.values())}
