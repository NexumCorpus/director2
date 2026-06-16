"""Phase 3 — _make_packet trusted-body path: when context_override is set, the
presented packet's .context is the trusted damage report VERBATIM (Constitution
#3: the trusted report is not re-narrated by the generator)."""

import pytest

from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.errors import ModelError
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def cfg(tmp_path):
    from director.config import Config
    c = Config(home=tmp_path / "ws")
    c.ensure_dirs()
    return c


@pytest.fixture()
def boss(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner)


TRUSTED = ("Damage on accumulated damage: trusted state shows accumulated "
           "failures on this axis from executed/verified work.")


def test_generated_packet_context_is_overridden(boss):
    project, _ = boss.new_project("ov", "objective")
    pkt = boss._make_packet(project, trigger="scream:grounding_damage",
                            hint=TRUSTED, context_override=TRUSTED)
    assert pkt.context == TRUSTED


def test_fallback_packet_carries_override_context(boss, monkeypatch):
    project, _ = boss.new_project("ov2", "objective")

    def boom(*a, **k):
        raise ModelError("forced fallback")

    monkeypatch.setattr(boss.router, "structured", boom)
    pkt = boss._make_packet(project, trigger="scream:tamper",
                            hint=TRUSTED, context_override=TRUSTED)
    assert pkt.context == TRUSTED


def test_fallback_packet_default_context_unchanged_without_override(boss):
    pkt = Director._fallback_packet("milestone:x", "some hint")
    assert pkt.context == "Decision point reached (milestone:x). some hint"


def test_no_override_leaves_generated_context_intact(boss):
    project, _ = boss.new_project("ov3", "objective")
    pkt = boss._make_packet(project, trigger="agent:x", hint="a fork")
    assert isinstance(pkt.context, str) and pkt.context
