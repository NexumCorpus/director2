"""Async LLM transport: acomplete/astructured/agather mirror the sync path
(failover, one-feedback-retry, recording) and agather bounds concurrency."""

import asyncio
import threading
import time

from pydantic import BaseModel

from director.errors import ModelError
from director.llm.base import LLMBackend, LLMResponse
from director.llm.router import LLMRouter


class X(BaseModel):
    x: int


class _Echo(LLMBackend):
    default_model = "echo"
    cheap_model = "echo"

    def __init__(self, text='{"x": 1}', *, fail=False, delay=0.0, nm="echo"):
        self.text, self.fail, self.delay, self.name, self.calls = \
            text, fail, delay, nm, 0

    def complete(self, system, user, *, model, temperature, max_tokens,
                 timeout_s, kind=""):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise ModelError("boom from " + self.name)
        return LLMResponse(text=self.text, model=model or self.name,
                           backend=self.name)


def test_acomplete_parity(cfg):
    r = LLMRouter(cfg, backends={"echo": _Echo(text="hello")})
    resp = asyncio.run(r.acomplete("s", "u", kind="k"))
    assert resp.text == "hello" and resp.backend == "echo"


def test_astructured_coerces(cfg):
    r = LLMRouter(cfg, backends={"echo": _Echo(text='{"x": 7}')})
    obj = asyncio.run(r.astructured("s", "u", X, kind="k"))
    assert isinstance(obj, X) and obj.x == 7


def test_agather_returns_in_order_and_is_robust(cfg):
    r = LLMRouter(cfg, backends={"echo": _Echo(text='{"x": 1}')})

    async def boom():
        raise RuntimeError("x")

    async def main():
        thunks = [lambda i=i: r.acomplete("s", f"u{i}", kind="k")
                  for i in range(5)]
        thunks.append(boom)             # one failure must not cancel the batch
        return await r.agather(thunks)
    res = asyncio.run(main())
    assert len(res) == 6
    assert sum(isinstance(x, LLMResponse) for x in res) == 5
    assert any(isinstance(x, Exception) for x in res)


def test_agather_bounded_by_limit(cfg):
    peak = {"n": 0, "cur": 0}
    lock = threading.Lock()

    class _Track(LLMBackend):
        default_model = "t"
        cheap_model = "t"
        name = "t"

        def complete(self, system, user, *, model, temperature, max_tokens,
                     timeout_s, kind=""):
            with lock:
                peak["cur"] += 1
                peak["n"] = max(peak["n"], peak["cur"])
            time.sleep(0.05)
            with lock:
                peak["cur"] -= 1
            return LLMResponse(text="{}", backend="t")

    r = LLMRouter(cfg, backends={"t": _Track()})

    async def main():
        thunks = [lambda i=i: r.acomplete("s", f"u{i}", kind="k")
                  for i in range(8)]
        return await r.agather(thunks, limit=2)
    asyncio.run(main())
    assert peak["n"] <= 2          # the semaphore truly bounds in-flight calls


def test_async_failover(cfg):
    bad = _Echo(fail=True, nm="bad")
    good = _Echo(text='{"x": 1}', nm="good")
    r = LLMRouter(cfg, backends={"bad": bad, "good": good})   # primary=bad
    resp = asyncio.run(r.acomplete("s", "u", kind="k"))
    assert resp.backend == "good"
    assert bad.calls == 1 and good.calls == 1


def test_wide_builder_fanout_is_concurrent(cfg):
    # the real async consumer: builder_fanout>1 generates N proposals per round
    # CONCURRENTLY via router.agather; fanout=1 preserves single-proposal behavior
    from types import SimpleNamespace

    from director.evolve.loop import ImprovementLoop
    proposal = ('{"rationale":"r","algo_class":"greedy",'
                '"code":"def f(x):\\n    return x"}')
    r = LLMRouter(cfg, backends={"echo": _Echo(text=proposal)})
    dom = SimpleNamespace(name="stub", describe=lambda: "stub problem")
    loop = ImprovementLoop(cfg, r, dom)
    spec = SimpleNamespace(func_name="f")
    cfg.builder_fanout = 3
    cands = loop._propose_round(1, spec, [], [], "CONTINUE")
    assert len(cands) == 3 and all(c.code for c in cands)
    cfg.builder_fanout = 1
    assert len(loop._propose_round(1, spec, [], [], "CONTINUE")) == 1
