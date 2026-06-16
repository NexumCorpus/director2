"""Phase 3 — decide() must not auto-advance while a latch is held; a packet
answer never clears the latch; status() surfaces the SCREAM line."""

import pytest

import director.core.director as dmod
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import BodyState, PacketStatus
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    c.nervous_enabled = True
    c.auto_advance_after_decision = True
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


def _arm_siren(monkeypatch):
    monkeypatch.setattr(dmod, "compute_body",
                        lambda project, **k: BodyState(valence=-0.9,
                                                       accumulated_damage=0.9,
                                                       computed_at=1))
    monkeypatch.setattr(dmod, "evaluate_scream",
                        lambda project, body, *, cfg: {
                            "level": "siren", "cause": "grounding_damage",
                            "axis": "accumulated_damage",
                            "clear_rule": "risk closed and re-pass",
                            "report": "trusted damage report"})
    monkeypatch.setattr(dmod, "check_clear_rule", lambda *a, **k: False)


def _open_latch(boss, monkeypatch, name):
    _arm_siren(monkeypatch)
    project, packet = boss.new_project(name, "objective")
    boss.decide(project.id, packet.id, option_key="A")
    boss.advance(project.id, autonomous=True)
    return project


def test_decide_does_not_auto_advance_while_latched(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "noadv")
    p = boss.store.load(project.id)
    siren_pkt = next(pk for pk in p.packets.values()
                     if pk.trigger == "scream:grounding_damage"
                     and pk.status is PacketStatus.PRESENTED)
    result = boss.decide(project.id, siren_pkt.id, option_key="A")
    assert result["follow_up"] == "none"


def test_answering_siren_packet_does_not_clear_latch(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "noclear")
    p = boss.store.load(project.id)
    siren_pkt = next(pk for pk in p.packets.values()
                     if pk.trigger == "scream:grounding_damage"
                     and pk.status is PacketStatus.PRESENTED)
    boss.decide(project.id, siren_pkt.id, option_key="A")
    assert boss.store.load(project.id).scream_open is not None


def test_status_shows_scream_line(boss, monkeypatch):
    project = _open_latch(boss, monkeypatch, "statusline")
    st = boss.status(project.id)
    assert st.get("scream") is not None
    assert st["scream"]["cause"] == "grounding_damage"
    assert "scream:grounding_damage" in st["next_action"] or \
        st["scream"]["clear_rule"]
    assert st["health"] is not None
    assert "valence" in st["health"] and "fragile_axes" in st["health"]


def test_status_no_scream_when_calm(boss):
    project, packet = boss.new_project("calm", "objective")
    st = boss.status(project.id)
    assert st.get("scream") is None
