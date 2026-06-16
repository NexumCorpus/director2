"""Per-kind LLM timeouts — two regimes: heavy single-shot calls get the long
budget; fail-fast base for everything else (live finding: finalize ~360s vs
~150s for parallel cycle calls)."""

from director.config import LONG_CALL_KINDS, Config
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter


def test_kind_timeout_two_regime():
    c = Config(request_timeout_s=100.0)
    assert c.kind_timeout("command_packet") == 100.0   # base
    assert c.kind_timeout("") == 100.0
    for k in LONG_CALL_KINDS:
        assert c.kind_timeout(k) == 300.0              # default 3x
    assert "agent_synthesis" in LONG_CALL_KINDS         # finalize is covered
    c2 = Config(request_timeout_s=100.0, long_timeout_s=420.0)
    assert c2.kind_timeout("initial_plan") == 420.0     # explicit override wins


def test_router_passes_per_kind_timeout(cfg):
    seen = {}

    class Spy(MockBackend):
        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            seen[kind] = timeout_s
            return super().complete(system, user, model=model,
                                    temperature=temperature,
                                    max_tokens=max_tokens, timeout_s=timeout_s,
                                    kind=kind)

    cfg.request_timeout_s = 50.0
    r = LLMRouter(cfg, backends={"mock": Spy()})
    r.complete("s", "u", role="director", kind="command_packet")
    r.complete("s", "u", role="synthesis", kind="agent_synthesis")
    assert seen["command_packet"] == 50.0     # base regime
    assert seen["agent_synthesis"] == 150.0   # long regime (3x)
