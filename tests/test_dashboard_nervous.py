"""Dashboard v2-capability: nervous_enabled is env-readable (DIRECTOR_NERVOUS_ENABLED),
and BridgeHub wires the MarkerStore when nervous is on so the Credit Knife / Gut
Markers hooks actually fire (they are guarded by self.markers is not None). With
nervous off, markers is None -> OFF byte-identical, no store ever constructed."""

from director.config import Config
from director.dashboard.server import BridgeHub


def test_nervous_enabled_env_truthy(monkeypatch):
    monkeypatch.setenv("DIRECTOR_NERVOUS_ENABLED", "1")
    assert Config.from_env().nervous_enabled is True


def test_nervous_enabled_default_false(monkeypatch):
    monkeypatch.delenv("DIRECTOR_NERVOUS_ENABLED", raising=False)
    assert Config.from_env().nervous_enabled is False


def test_bridgehub_wires_markers_when_nervous(cfg):
    cfg.nervous_enabled = True
    hub = BridgeHub(cfg)
    assert hub.director.markers is not None          # v2 organs can fire


def test_bridgehub_no_markers_when_off(cfg):
    cfg.nervous_enabled = False
    hub = BridgeHub(cfg)
    assert hub.director.markers is None               # OFF byte-identical
