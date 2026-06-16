"""Command Bridge tests: the read model, the single-op write gate, the decide
path, and HTTP routing — all on the mock backend, no real network beyond a
loopback server bound to an ephemeral port."""

import json
import threading
import time
import urllib.request

import pytest

from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import PacketStatus
from director.dashboard.server import BridgeHub, make_server
from director.dashboard.ui import INDEX_HTML
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def hub(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    director = Director(cfg, store, router, registry, runner)
    return BridgeHub(cfg, director=director, store=store)


@pytest.fixture()
def live(hub):
    """Hub behind a real loopback HTTP server on an ephemeral port."""
    srv = make_server(hub, port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield hub, base
    srv.shutdown()


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(base, path, body):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# --------------------------------------------------------------- read model
def test_overview_and_digest(hub):
    project, _ = hub.director.new_project(
        "bridge demo", "build a verified toy library")
    ov = hub.overview()
    assert ov["backend"] == "mock"
    assert any(p["id"] == project.id for p in ov["projects"])
    d = hub.digest(project.id)
    assert d["name"] == "bridge demo"
    assert d["tasks"] and "summary" in d
    # an initial command packet is present and surfaced first
    presented = [p for p in d["packets"] if p["status"] == "presented"]
    assert presented and d["packets"][0]["status"] == "presented"


def test_auto_advance_is_disabled_for_bridge(hub):
    # decide must not drag a multi-minute advance behind it
    assert hub.cfg.auto_advance_after_decision is False


def test_digest_milestone_blockers_surfaced(hub):
    project, _ = hub.director.new_project("d", "ship a thing")
    d = hub.digest(project.id)
    assert all("blockers" in m for m in d["milestones"])


# ------------------------------------------------------------- decide path
def test_decide_through_hub(hub):
    project, packet = hub.director.new_project("d", "ship a verified thing")
    key = packet.recommendation_key or packet.options[0].key
    out = hub.decide(project.id, {"packet_id": packet.id, "option_key": key,
                                  "rationale": "via bridge"})
    assert "decision_id" in out
    reloaded = hub.store.load(project.id)
    assert reloaded.packets[packet.id].status is not PacketStatus.PRESENTED


def test_decide_blocked_while_op_running(hub):
    project, packet = hub.director.new_project("d", "x")
    hub._begin("advance", project.id)            # simulate an in-flight op
    out = hub.decide(project.id, {"packet_id": packet.id,
                                  "option_key": packet.options[0].key})
    assert out.get("status") == 409
    hub._finish()
    # once clear, decide works again
    out2 = hub.decide(project.id, {"packet_id": packet.id,
                                   "option_key": packet.options[0].key})
    assert "decision_id" in out2


# ----------------------------------------------------------- op write gate
def test_single_op_gate_serializes(hub):
    project, _ = hub.director.new_project("d", "x")
    gate = threading.Event()

    def slow():
        gate.wait(2)
        return {"ok": True}

    first = hub.start_background("advance", project.id, slow)
    assert first["status"] == "started"
    second = hub.start_background("advance", project.id, lambda: {})
    assert second["status"] == 409            # rejected, not raced
    assert hub.op_state()["running"] is True
    gate.set()
    for _ in range(40):
        if not hub.op_state()["running"]:
            break
        time.sleep(0.05)
    st = hub.op_state()
    assert st["running"] is False and st["result"] == {"ok": True}


def test_background_op_captures_error(hub):
    project, _ = hub.director.new_project("d", "x")

    def boom():
        raise RuntimeError("kaboom")

    hub.start_background("finalize", project.id, boom)
    for _ in range(40):
        if not hub.op_state()["running"]:
            break
        time.sleep(0.05)
    st = hub.op_state()
    assert st["running"] is False and "kaboom" in st["error"]


# -------------------------------------------------------------- HTTP layer
def test_http_routes(live):
    hub, base = live
    project, _ = hub.director.new_project("http demo", "ship verified code")
    code, html = (lambda: (urllib.request.urlopen(base + "/").status,
                           urllib.request.urlopen(base + "/").read()))()
    assert code == 200 and b"Director" in html
    s, idx = _get(base, "/api")
    assert s == 200 and any("/api/overview" in r for r in idx["routes"])
    s, ov = _get(base, "/api/overview")
    assert s == 200 and ov["projects"]
    s, dg = _get(base, "/api/project/" + project.id)
    assert s == 200 and dg["id"] == project.id
    s, op = _get(base, "/api/op")
    assert s == 200 and op["running"] is False
    s, err = _get(base, "/api/project/" + project.id + "/artifact/nope")
    assert s == 404


def test_http_decide_roundtrip(live):
    hub, base = live
    project, packet = hub.director.new_project("d", "ship verified code")
    s, out = _post(base, "/api/project/" + project.id + "/decide",
                   {"packet_id": packet.id,
                    "option_key": packet.recommendation_key
                    or packet.options[0].key, "rationale": "http"})
    assert s == 200 and "decision_id" in out


def test_index_html_self_contained():
    # offline guarantee: no external script/style/font references (inline
    # SVG sigils carry no xmlns on purpose, so even w3.org never appears)
    low = INDEX_HTML.lower()
    assert "<script" in low and "fetch(" in low
    for bad in ("http://", "https://", "cdn.", "googleapis"):
        assert bad not in low, f"UI references external resource: {bad}"


def test_ui_synthesis_structure():
    # the synthesis: calm shell + companion avatars + rich numeric dialogue
    low = INDEX_HTML.lower()
    for token in ("projlist", "openproject", "decisioncard", "renderthread",
                  "composer", "conviction", "drawer",
                  "sigil(", "outcomecell", "spine", "_fnv"):
        assert token in low, f"UI missing {token}"
    # the command-center chrome stays gone
    for gone in ("roster", "character sheet", "command bridge",
                 "the director's roster"):
        assert gone not in low, f"UI still carries maximalist '{gone}'"
    # the avatar SVG must stay offline-safe: no xmlns/http on the inline svg
    assert "xmlns" not in low


def test_create_project_via_http(live):
    hub, base = live
    s, out = _post(base, "/api/new",
                   {"name": "fresh campaign", "objective": "ship verified x"})
    assert s in (200, 202) and out.get("status") == "started"
    # the background op completes and yields the new project id
    for _ in range(60):
        st = hub.op_state()
        if not st["running"]:
            break
        time.sleep(0.05)
    st = hub.op_state()
    assert not st["running"] and st["result"] and st["result"]["project"]
    pid = st["result"]["project"]
    assert any(p["id"] == pid for p in hub.store.list_projects())


def test_create_project_requires_fields(live):
    hub, base = live
    s, out = _post(base, "/api/new", {"name": "no objective"})
    assert s == 400 and "required" in out["error"]


def test_digest_downgrades_unbacked_verified(hub):
    # an unbacked VERIFIED option must serve as 'judged' — the UI can never
    # paint a green check over nothing, even if bad data reaches the store
    from director.core.types import (CheckKind, CommandOption, CommandPacket,
                                     PacketStatus, Project)
    p = Project(name="dishonest")
    pkt = CommandPacket(title="t", status=PacketStatus.PRESENTED, options=[
        CommandOption(key="a", label="A", conviction="iconoclast",
                      check=CheckKind.VERIFIED)])   # no artifact
    p.packets[pkt.id] = pkt
    hub.store.save(p)
    d = hub.digest(p.id)
    served = d["packets"][0]["options"][0]
    assert served["check"] == "judged"     # downgraded at the boundary
    assert "conviction_read" in d


def test_digest_serves_conviction_and_checks_for_demo(hub):
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    d = hub.digest(pid)
    pkt = [p for p in d["packets"] if p["status"] == "presented"][0]
    convs = {o["conviction"] for o in pkt["options"]}
    assert convs == {"dogmatic", "iconoclast", "heretic"}
    checks = {o["check"] for o in pkt["options"]}
    assert "verified" in checks and "judged" in checks   # both states honest
    assert "Coverage Doctrine" in d["name"]


def test_digest_and_route_surface_integrity(hub):
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    d = hub.digest(pid)
    assert "integrity" in d
    assert d["integrity"]["violations"] == 0
    assert d["integrity"]["reports"]["ok"] >= 1     # demo's bound report verifies
    full = hub.integrity(pid)
    assert any(r["status"] == "ok" for r in full["rows"])
    assert full["summary"]["violations"] == 0


def test_digest_integrity_flags_tampered_report(hub):
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    p = hub.store.load(pid)
    rep_art = [a for a in p.artifacts.values()
               if a.kind == "property_report"][0]
    rep_art.provenance["report"]["n_passed"] = 99    # breaks the bound sig
    hub.store.save(p)
    d = hub.digest(pid)
    assert d["integrity"]["violations"] >= 1
    served = [o for pk in d["packets"] for o in pk["options"]
              if o.get("verification_artifact_id") == rep_art.id]
    assert served and all(o["check"] == "judged" for o in served)


def test_all_surfaces_honest_under_tamper(hub):
    # one tamper must degrade EVERY read surface in lockstep — they all reuse the
    # secret-enforced binding gate, so none can show a badge the others reject.
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    before = hub.digest(pid)
    p = hub.store.load(pid)
    rep = [a for a in p.artifacts.values() if a.kind == "property_report"][0]
    rep.provenance["report"]["n_passed"] = 99
    hub.store.save(p)
    after = hub.digest(pid)
    opt = [o for pk in after["packets"] for o in pk["options"]
           if o.get("verification_artifact_id") == rep.id][0]
    assert opt["check"] == "judged"                              # option
    assert (after["ladder"]["verified_partial"]
            < before["ladder"]["verified_partial"])             # ladder
    assert after["integrity"]["violations"] >= 1                 # health
    assert [a for a in after["artifacts"]
            if a["id"] == rep.id][0]["report_status"] == "INVALID"  # per-report


def test_http_integrity_route(live):
    hub, base = live
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    st, body = _get(base, f"/api/project/{pid}/integrity")
    assert st == 200 and "summary" in body and "rows" in body


def test_digest_serves_verification_ladder(hub):
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    d = hub.digest(pid)
    assert "ladder" in d
    L = d["ladder"]
    assert L["verified"] >= 1 and L["judged"] >= 1   # demo has both live tiers
    assert sum(L.values()) >= 2


def test_digest_flags_per_report_integrity(hub):
    from director.dashboard.demo import seed_demo
    pid = seed_demo(hub.store)
    d = hub.digest(pid)
    reports = [a for a in d["artifacts"] if a["kind"] == "property_report"]
    assert reports and all(a["report_status"] == "ok" for a in reports)
    p = hub.store.load(pid)
    rep = [a for a in p.artifacts.values() if a.kind == "property_report"][0]
    rep.provenance["report"]["n_passed"] = 99
    hub.store.save(p)
    bad = [a for a in hub.digest(pid)["artifacts"] if a["id"] == rep.id][0]
    assert bad["report_status"] == "INVALID"
