"""SubAgentRunner — parallel, verified subagent execution.

Every spec runs as: role prompt → router (structured SubAgentOutput) →
verifier chain (trusted code) → AgentResult. Failures are isolated per agent;
a crashed agent returns ok=False, it never sinks the batch. Verification
happens HERE, before the Director ever ingests an output — generators don't
grade themselves and unverified work doesn't enter state.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import Config
from ..errors import DirectorError, ModelError
from ..llm.router import LLMRouter
from ..logging_setup import get_logger
from ..verify import VerifierRegistry, chain_needs_human, chain_passed, run_chain
from .base import AgentResult, AgentSpec, SubAgentOutput
from .roles import get_role, render_user_prompt

log = get_logger("agents.runner")


class SubAgentRunner:
    def __init__(self, cfg: Config, router: LLMRouter,
                 registry: VerifierRegistry, *, lessons_digest: str = "",
                 prompts=None):
        self.cfg = cfg
        self.router = router
        self.registry = registry
        self.lessons_digest = lessons_digest
        self.prompts = prompts            # PromptRegistry | None — evolved
        #                                   role prompts override the defaults

    # ----------------------------------------------------------------- single
    def run(self, spec: AgentSpec) -> AgentResult:
        result = AgentResult(spec_id=spec.id, task_id=spec.task_id, role=spec.role)
        try:
            role = get_role(spec.role)
            user = render_user_prompt(
                spec.objective, spec.context, spec.inputs,
                spec.acceptance_criteria, spec.constraints,
                lessons_digest=self.lessons_digest)
            system = role.system
            if self.prompts is not None:
                system = self.prompts.override(f"role_{spec.role}", role.system)
            out = self.router.structured(
                system, user, SubAgentOutput,
                role=spec.profile_role or role.profile_role,
                kind=role.routing_kind)
            resp = getattr(out, "_llm_response", None)
            output = out.model_dump()
            output["task_id"] = spec.task_id
            result.output = output
            if resp is not None:
                result.backend = resp.backend
                result.model = resp.model
                result.latency_s = resp.latency_s
                result.usage = {"prompt_tokens": resp.prompt_tokens,
                                "completion_tokens": resp.completion_tokens}
                # capture the raw generation (was discarded): post-hoc replay +
                # the live-stream's persisted record of what the model wrote
                result.raw_generation = resp.text

            verifiers = [self.registry.get("agent_output")]
            for name in spec.verifiers:
                if name == "agent_output":
                    continue
                verifiers.append(self.registry.get(name))
            reports = run_chain(verifiers, output,
                                context={"objective": spec.objective,
                                         "role": spec.role,
                                         "spec": spec})
            result.reports = reports
            result.needs_human = chain_needs_human(reports)
            result.ok = chain_passed(reports)
            if not result.ok:
                issues = [i for r in reports for i in r.issues]
                result.error = "verification failed: " + "; ".join(issues[:5])
        except (ModelError, DirectorError, KeyError) as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            log.warning("agent %s (%s) failed: %s", spec.id, spec.role, exc)
        except Exception as exc:                              # noqa: BLE001
            result.ok = False
            result.error = f"unexpected: {type(exc).__name__}: {exc}"
            log.exception("agent %s (%s) crashed", spec.id, spec.role)
        return result

    # --------------------------------------------------------------- parallel
    def run_parallel(self, specs: list[AgentSpec]) -> list[AgentResult]:
        """Run specs concurrently (bounded by cfg.max_parallel_agents).
        Results return in the order of ``specs``."""
        if not specs:
            return []
        if len(specs) == 1:
            return [self.run(specs[0])]
        results: dict[str, AgentResult] = {}
        workers = max(1, min(self.cfg.max_parallel_agents, len(specs)))
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="subagent") as pool:
            futures = {pool.submit(self.run, spec): spec for spec in specs}
            for fut in as_completed(futures):
                spec = futures[fut]
                try:
                    results[spec.id] = fut.result()
                except Exception as exc:                      # noqa: BLE001
                    log.exception("executor failure for agent %s", spec.id)
                    results[spec.id] = AgentResult(
                        spec_id=spec.id, task_id=spec.task_id, role=spec.role,
                        ok=False, error=f"executor: {exc}")
        return [results[s.id] for s in specs]
