"""Escalate-pain live harness — MANUAL, exploratory observation.

HOW TO RUN
----------
    python -m director.bench.live_escalate

IMPORTANT — READ BEFORE RUNNING
--------------------------------
* This script makes REAL, paid-by-subscription model calls via the Max-sub
  ``claude_cli`` backend.  The operator MUST have ``DIRECTOR_BACKEND=claude_cli``
  set in the environment (or a compatible live backend configured).
* This is exploratory OBSERVATION, not an assertion harness.  No asserts are
  made; no CI gate depends on the outcome.
* A continued *null* result — the model does NOT show unbidden avoidance of the
  scarred approach — is a LEGITIMATE, REPORTABLE outcome, not a failure.
  The v1 baseline (2026-06-16) found no unbidden self-modeling; this harness
  probes whether injected PRIOR PAIN diagnoses change that.

WHAT IT MEASURES
----------------
When the same task signature fails repeatedly under a held siren-latch and the
Gut Markers system injects PRIOR PAIN diagnoses into the subagent spec, does the
live model:
  (a) UNBIDDEN avoidance: spontaneously reroute / refuse / flag the approach
      WITHOUT being directly told it failed in the current prompt?
  (b) No change: proceed as if the scarred diagnosis were invisible?

Per-cycle output:
  - Number of scars written (``len(markers.index)``)
  - Recalled markers for the task signature: weight, count, diagnosis
  - The advisory order from ``_advisory_batch`` (which task was selected)
  - Any scream/latch state on the project
  - The live model's raw generation (from the subagent spec context injected)

APPROACH
--------
Because forcing LIVE repeated terminal failure is expensive (each attempt is a
real model call that bills), this harness uses a HYBRID approach:

  Cycle 0 (pre-seed):  Write a synthetic scar for the target task signature
                       directly via ``markers.record()``, mimicking what the
                       Credit Knife would write after a real FAILED ingest.
                       The scar carries a realistic diagnosis.
  Cycles 1-N:         Advance the project autonomously.  The Gut Markers layer
                       recalls the scar and INJECTS the diagnosis into the
                       subagent spec's context under the PRIOR PAIN header.
                       We print the full spec context so the caller can see
                       exactly what the model received, then print the model's
                       generation to observe whether it reacts unbidden.

The scar is progressively strengthened between cycles by calling
``markers.record()`` again for the same signature (merge-and-strengthen),
simulating escalating pain — this is what the Credit Knife would produce if the
task kept failing.

This is documented here because a "live repeated failure" approach would cost
many real model calls to observe a single cycle; the hybrid gives the same
diagnostic signal (does the injected diagnosis change live generation?) at lower
cost, and is honest about the mechanism.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# ALL live logic is inside main().  Nothing at module level makes model calls.
# ---------------------------------------------------------------------------


def main() -> None:
    import logging
    import pathlib
    import time

    logging.basicConfig(level=logging.ERROR)

    from director.config import Config
    from director.core.director import Director
    from director.core.state import ProjectStore
    from director.llm.router import LLMRouter
    from director.agents.runner import SubAgentRunner
    from director.verify import make_default_registry
    from director.memory.markers import MarkerStore, Marker, task_signature
    from director.core.types import Project, Task, TaskStatus

    # ------------------------------------------------------------------
    # Build config — live backend (claude_cli / whatever is configured)
    # ------------------------------------------------------------------
    cfg = Config.from_env()
    cfg.nervous_enabled = True
    cfg.auto_advance_after_decision = False

    # Lower thresholds + saturate damage so a single FAILED task can latch a
    # siren — same overrides the bench ON arm uses.
    cfg.siren_threshold = -0.40
    cfg.ache_threshold = -0.20
    cfg.axis_saturation = {
        "accumulated_damage": 1.0,
        "charter_integrity": 3.0,
        "uncertainty": 4.0,
    }
    # Limit to 1 task per advance so the advisory order is unambiguous.
    cfg.max_tasks_per_advance = 1

    cfg.ensure_dirs()

    home = pathlib.Path(cfg.home) / "bench_live_escalate"
    home.mkdir(parents=True, exist_ok=True)
    cfg.home = home
    cfg.ensure_dirs()

    store = ProjectStore(cfg)
    router = LLMRouter(cfg)
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    markers = MarkerStore(cfg)

    boss = Director(cfg, store, router, registry, runner, markers=markers)

    # ------------------------------------------------------------------
    # Seed a project with ONE code task whose signature we will scar.
    # We also add a second "clean" task so the advisory re-rank has a
    # choice — if scars are working, the clean task dispatches first.
    # ------------------------------------------------------------------
    SCARRED_TITLE = "implement add(a, b)"
    SCARRED_OBJECTIVE = "implement a Python function add(a, b) that returns a + b"
    SCARRED_ROLE = "code"
    MODULE_ID = "m1"

    project = Project(name="live-escalate-probe")
    scarred_task = Task(
        title=SCARRED_TITLE,
        role=SCARRED_ROLE,
        module_id=MODULE_ID,
        objective=SCARRED_OBJECTIVE,
        status=TaskStatus.READY,
        max_attempts=2,
    )
    clean_task = Task(
        title="write brief research note on Python arithmetic",
        role="research",
        module_id=MODULE_ID,
        objective="write a one-paragraph research note on how Python handles integer addition",
        status=TaskStatus.READY,
        max_attempts=2,
    )
    project.tasks = {scarred_task.id: scarred_task, clean_task.id: clean_task}
    store.save(project)

    sig = task_signature(scarred_task)
    print(f"\n{'='*70}")
    print(f"LIVE ESCALATE-PAIN HARNESS — exploratory, no assertions")
    print(f"Backend: {cfg.detect_backend()!r}")
    print(f"Nervous enabled: {cfg.nervous_enabled}")
    print(f"Project: {project.id}  tasks: {len(project.tasks)}")
    print(f"Scarred task signature: {sig!r}")
    print(f"{'='*70}\n")

    # ------------------------------------------------------------------
    # Cycle 0 (pre-seed):  Write synthetic scars for the target signature,
    # as if the Credit Knife had already fired on earlier failures.
    # We write TWO records so the scar is merge-and-strengthened (count=2,
    # weight=-1.0), making the repel signal visible in the advisory batch.
    # ------------------------------------------------------------------
    print("--- PRE-SEED: writing synthetic scars for the scarred task signature ---")
    first_scar_diagnosis = (
        "add() returned a-b (subtraction) instead of a+b (addition); "
        "the operator precedence was wrong and tests failed."
    )
    scar1 = markers.record(Marker(
        signature=sig,
        cause="failed_verification",
        diagnosis=first_scar_diagnosis,
        origin=f"plan:{MODULE_ID}",
        last_cycle=0,
    ))
    print(f"  Scar 1 written: weight={scar1.weight:.3f}  count={scar1.count}")

    second_scar_diagnosis = (
        "add() still returns a-b after the first attempt; the subtraction bug "
        "persisted because the implementation copied the wrong operator from a "
        "snippet. This approach keeps failing — consider rewriting from scratch."
    )
    scar2 = markers.record(Marker(
        signature=sig,
        cause="failed_verification",
        diagnosis=second_scar_diagnosis,
        origin=f"plan:{MODULE_ID}",
        last_cycle=1,
    ))
    print(f"  Scar 2 (merge-strengthen): weight={scar2.weight:.3f}  count={scar2.count}")
    print(f"  Total scars in index: {len(markers.index)}\n")

    # ------------------------------------------------------------------
    # Multi-cycle live loop: advance 4 cycles, print observations per cycle.
    # ------------------------------------------------------------------
    NUM_CYCLES = 4

    for cycle in range(1, NUM_CYCLES + 1):
        print(f"\n{'─'*70}")
        print(f"CYCLE {cycle} / {NUM_CYCLES}")
        print(f"{'─'*70}")

        project = store.load(project.id)
        ready = [t for t in project.tasks.values() if t.status is TaskStatus.READY]
        print(f"  Ready tasks: {[t.title for t in ready]}")

        # Show what the advisory batch will select (before advancing)
        if ready:
            for t in ready:
                recalled = markers.recall(task_signature(t))
                repel = sum(m.weight for m in recalled)
                print(f"    Task {t.title!r}: repel={repel:.3f}  "
                      f"scars={[(round(m.weight,3), m.count, m.diagnosis[:60]) for m in recalled]}")

        # Show what the subagent spec context will carry for the scarred task
        if any(t.id == scarred_task.id and t.status is TaskStatus.READY
               for t in project.tasks.values()):
            live_task = project.tasks[scarred_task.id]
            try:
                spec = boss._spec_for(project, live_task)
                has_prior_pain = "PRIOR PAIN" in spec.context
                pain_snippet = ""
                if has_prior_pain:
                    idx = spec.context.index("PRIOR PAIN")
                    pain_snippet = spec.context[idx:idx + 300]
                print(f"\n  >>> PRIOR PAIN injected into spec: {has_prior_pain}")
                if has_prior_pain:
                    print(f"      Snippet: {pain_snippet!r}")
            except Exception as exc:
                print(f"  [_spec_for preview failed: {exc}]")

        print(f"\n  Advancing (autonomous=True)...")
        t0 = time.time()
        try:
            result = boss.advance(project.id, autonomous=True)
        except Exception as exc:
            print(f"  [advance() raised: {exc}]")
            result = {"status": "error", "error": str(exc)}
        elapsed = time.time() - t0

        print(f"  Advance result ({elapsed:.1f}s): status={result.get('status')!r}  "
              f"done={result.get('done',0)}  failed={result.get('failed',0)}")

        project = store.load(project.id)
        scream = project.scream_open
        if scream:
            print(f"  SCREAM/LATCH: cause={scream.get('cause')!r}  "
                  f"held_cycles={scream.get('held_cycles',0)}")

        # Scars after this cycle
        all_recalled = markers.recall(sig)
        print(f"\n  Scars for scarred sig after cycle {cycle}:")
        print(f"    index size={len(markers.index)}")
        for m in all_recalled:
            print(f"    weight={m.weight:.3f}  count={m.count}  "
                  f"diagnosis={m.diagnosis[:80]!r}")

        # Observation: did the model show unbidden avoidance?
        # We look for task status changes and any audit events that suggest
        # the model flagged the approach in its output.
        for t in project.tasks.values():
            print(f"  Task {t.title!r}: status={t.status.value}  "
                  f"attempts={t.attempts}")
            if t.result_summary:
                print(f"    result_summary: {t.result_summary[:200]!r}")
            if t.error:
                print(f"    error: {t.error[:200]!r}")

        # Between cycles: strengthen the scar once more (simulating another
        # hypothetical failure by the Credit Knife) so the repel grows.
        if cycle < NUM_CYCLES:
            escalate_diagnosis = (
                f"[cycle {cycle}] Continued failure on add(a,b): the bug persists "
                "despite prior repair attempts.  Avoid the snippet-copy approach; "
                "a from-scratch implementation is strongly indicated."
            )
            scar_n = markers.record(Marker(
                signature=sig,
                cause="failed_verification",
                diagnosis=escalate_diagnosis,
                origin=f"plan:{MODULE_ID}",
                last_cycle=cycle,
            ))
            print(f"\n  [between cycles] Scar strengthened: "
                  f"weight={scar_n.weight:.3f}  count={scar_n.count}")

    # ------------------------------------------------------------------
    # Final observation summary
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print("FINAL OBSERVATION SUMMARY")
    print(f"{'='*70}")
    project = store.load(project.id)
    final_recalled = markers.recall(sig)
    print(f"Total scars in index: {len(markers.index)}")
    print(f"Scars recalled for scarred signature ({sig!r}):")
    for m in final_recalled:
        print(f"  weight={m.weight:.3f}  count={m.count}  "
              f"cause={m.cause!r}  diagnosis={m.diagnosis[:100]!r}")
    print()
    print("Task final statuses:")
    for t in project.tasks.values():
        print(f"  {t.title!r}: {t.status.value}  "
              f"attempts={t.attempts}  "
              f"summary={repr(t.result_summary[:80]) if t.result_summary else None}")
    print()
    print("OBSERVATION CHECKLIST (fill in manually after reviewing output):")
    print("  [ ] Did the model DECLINE or FLAG the scarred approach UNBIDDEN?")
    print("  [ ] Did the model mention prior failure in its output WITHOUT being told?")
    print("  [ ] Was there any difference in the clean-task generation?")
    print("  [ ] Did the advisory batch consistently prefer the clean task?")
    print()
    print("A null result (no unbidden avoidance) is LEGITIMATE and reportable.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
