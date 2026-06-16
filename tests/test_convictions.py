"""Steering layer: conviction typing, verifier honesty (the load-bearing
invariant), and conviction drift. All offline."""

import pytest

from director.core.convictions import (conviction_rank, conviction_read,
                                       conviction_state, conviction_tally,
                                       conviction_violations,
                                       evaluate_packet_coherence,
                                       honest_check, verifier_favored_key,
                                       verifier_honesty_violations)
from director.core.types import (Artifact, CheckKind, CommandOption,
                                 CommandPacket, ConvictionType, DecisionEvent,
                                 PacketStatus, Project, ResponseType)
from director.dashboard.demo import build_demo_project


def _opt(key, conviction, check=CheckKind.NONE, art="", score=None):
    return CommandOption(key=key, label=key.title(), conviction=conviction,
                         check=check, verification_artifact_id=art,
                         check_score=score)


# ---------------------------------------------------- verifier honesty (core)
def test_verified_without_artifact_fails_the_build():
    """THE invariant: a Verified tag with no backing artifact is a violation
    — a green check over nothing is the blind-trust failure this kills."""
    pkt = CommandPacket(title="t", options=[
        _opt("a", "iconoclast", check=CheckKind.VERIFIED)])  # no artifact!
    problems = verifier_honesty_violations(pkt)
    assert problems and "no verification_artifact_id" in problems[0]


def test_verified_with_dangling_artifact_fails():
    proj = Project(name="p")  # empty artifacts
    pkt = CommandPacket(title="t", options=[
        _opt("a", "dogmatic", check=CheckKind.VERIFIED, art="ghost123")])
    assert verifier_honesty_violations(pkt, proj)


def test_verified_with_real_artifact_is_honest():
    proj = Project(name="p")
    a = Artifact(title="oracle run", kind="verification", content="measured")
    proj.artifacts[a.id] = a
    pkt = CommandPacket(title="t", options=[
        _opt("a", "iconoclast", check=CheckKind.VERIFIED, art=a.id,
             score=74.5)])
    assert verifier_honesty_violations(pkt, proj) == []


def test_honest_check_downgrades_unbacked_verified():
    # display boundary: unbacked verified must render as judged
    kind, score = honest_check(_opt("a", "dogmatic",
                                    check=CheckKind.VERIFIED, score=9))
    assert kind == CheckKind.JUDGED and score == 9
    # backed verified survives when the artifact resolves
    arts = {"art1": object()}
    kind2, _ = honest_check(_opt("b", "iconoclast", check=CheckKind.VERIFIED,
                                 art="art1"), arts)
    assert kind2 == CheckKind.VERIFIED
    # judged / none pass through untouched
    assert honest_check(_opt("c", "heretic", check=CheckKind.JUDGED))[0] \
        == CheckKind.JUDGED


# ---------------------------------------------------------- conviction typing
def test_conviction_completeness():
    good = CommandPacket(title="t", options=[
        _opt("a", "dogmatic"), _opt("b", "iconoclast"), _opt("c", "heretic")])
    assert conviction_violations(good) == []
    bad = CommandPacket(title="t", options=[_opt("a", "vibes")])
    assert conviction_violations(bad)


# ----------------------------------------------------------- conviction drift
def _decided_project(convictions):
    """A project whose decision history chose options of the given convictions
    (one packet+decision per entry)."""
    p = Project(name="drift")
    for i, conv in enumerate(convictions):
        pkt = CommandPacket(title=f"q{i}", status=PacketStatus.ANSWERED,
                            options=[_opt("x", conv), _opt("y", "dogmatic")])
        p.packets[pkt.id] = pkt
        dec = DecisionEvent(packet_id=pkt.id,
                            response_type=ResponseType.SELECT_OPTION,
                            selected_key="x")
        p.decisions[dec.id] = dec
    return p


def test_tally_accumulates_across_decisions():
    p = _decided_project(["heretic", "heretic", "iconoclast"])
    t = conviction_tally(p)
    assert t == {"dogmatic": 0, "iconoclast": 1, "heretic": 2}


def test_read_shifts_with_disposition():
    assert "unformed" in conviction_read(Project(name="x")).lower()
    heretic = conviction_read(_decided_project(["heretic", "heretic",
                                                "heretic"]))
    assert "heretic" in heretic.lower()
    dogmatic = conviction_read(_decided_project(["dogmatic", "dogmatic"]))
    assert "dogmatic" in dogmatic.lower()
    even = conviction_read(_decided_project(["dogmatic", "iconoclast",
                                             "heretic"]))
    assert "even-handed" in even.lower()
    # non-pick responses (defer/reject) don't count toward disposition
    p = Project(name="d")
    pkt = CommandPacket(title="q", options=[_opt("x", "heretic")])
    p.packets[pkt.id] = pkt
    p.decisions["d1"] = DecisionEvent(packet_id=pkt.id,
                                      response_type=ResponseType.DEFER,
                                      selected_key="x")
    assert conviction_state(p)["decisions_typed"] == 0


# ---------------------------------------------------------- rank (RT ladder)
def test_rank_ladder_and_naming():
    assert conviction_rank(Project(name="x"))["rank"] == 0
    r1 = conviction_rank(_decided_project(["iconoclast"]))
    assert r1["rank"] == 1 and r1["rank_name"] == "Follower"
    assert r1["conviction"] == "iconoclast"
    r3 = conviction_rank(_decided_project(["heretic"] * 6))
    assert r3["rank"] == 3 and r3["rank_name"] == "Votary"
    r5 = conviction_rank(_decided_project(["dogmatic"] * 15))
    assert r5["rank"] == 5 and r5["rank_name"] == "Zealot"
    assert conviction_state(_decided_project(["heretic"]))["rank"]["rank"] == 1


# ----------------------------------------------------- packet coherence eval
def test_coherence_rewards_well_formed_packet():
    proj = Project(name="p")
    a = Artifact(title="oracle", kind="verification", content="m")
    proj.artifacts[a.id] = a
    good = CommandPacket(title="t", recommendation_key="b", options=[
        _opt("a", "dogmatic", check=CheckKind.JUDGED, score=3),
        _opt("b", "iconoclast", check=CheckKind.VERIFIED, art=a.id, score=9),
        _opt("c", "heretic", check=CheckKind.JUDGED, score=2)])
    # distinguish state deltas so distinctness doesn't warn
    good.options[0].state_delta = {"notes": ["x"]}
    good.options[1].state_delta = {"notes": ["y"]}
    good.options[2].state_delta = {"notes": ["z"]}
    coh = evaluate_packet_coherence(good, proj)
    assert coh["ok"] and coh["spread"] == 3 and coh["score"] >= 0.9


def test_coherence_flags_single_conviction_and_dishonesty():
    proj = Project(name="p")
    bad = CommandPacket(title="t", recommendation_key="a", options=[
        _opt("a", "dogmatic"), _opt("b", "dogmatic")])  # no spread
    coh = evaluate_packet_coherence(bad, proj)
    assert any("one conviction" in w for w in coh["warnings"])
    dishonest = CommandPacket(title="t", options=[
        _opt("a", "iconoclast", check=CheckKind.VERIFIED)])  # unbacked
    assert not evaluate_packet_coherence(dishonest, proj)["ok"]


def test_recommendation_should_track_verifier_favored():
    proj = Project(name="p")
    a = Artifact(title="oracle", kind="verification", content="m")
    proj.artifacts[a.id] = a
    # ★ points at a judged option while a verified one scores higher
    pkt = CommandPacket(title="t", recommendation_key="a", options=[
        _opt("a", "heretic", check=CheckKind.JUDGED, score=5),
        _opt("b", "iconoclast", check=CheckKind.VERIFIED, art=a.id, score=9)])
    assert verifier_favored_key(pkt, proj) == "b"
    coh = evaluate_packet_coherence(pkt, proj)
    assert any("verifier-favored" in w for w in coh["warnings"])


# --------------------------------------------------------------- demo sandbox
def test_demo_exercises_all_convictions_and_both_checks():
    p = build_demo_project()
    presented = [pk for pk in p.packets.values()
                 if pk.status == PacketStatus.PRESENTED]
    assert presented, "demo must have live packets to steer"
    # at least one presented packet spans all three convictions
    full = [pk for pk in presented
            if {o.conviction for o in pk.options} ==
            {ConvictionType.DOGMATIC, ConvictionType.ICONOCLAST,
             ConvictionType.HERETIC}]
    assert full, "a demo packet must offer all three convictions"
    pkt = full[0]
    checks = {honest_check(o, p.artifacts)[0] for o in pkt.options}
    assert CheckKind.VERIFIED in checks and CheckKind.JUDGED in checks
    # every Verified option across the WHOLE demo is artifact-backed
    for pk in p.packets.values():
        assert verifier_honesty_violations(pk, p) == []
    # the recommended option is the verifier-favored (measured) one
    rec = next(o for o in pkt.options if o.key == pkt.recommendation_key)
    assert honest_check(rec, p.artifacts)[0] == CheckKind.VERIFIED
    # the seeded prior history means the disposition is already formed
    assert "unformed" not in conviction_read(p).lower()
