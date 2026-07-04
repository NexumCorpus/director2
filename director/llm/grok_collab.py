"""Collaboration primitives for the Claude<->Grok research partnership.

Built on the GrokChannel harness. Three reusable moves, distilled from the manual
pattern that produced the cross-lab grounding work:

- ``adversarial_check(claim)`` — hand Grok a claim/design framed to REFUTE, not agree.
  This is the single highest-value move in the collaboration (Grok caught meta-task
  contamination, a spoon-feeding confound, and an inflated-magnitude confound this way).
- ``cross_lab_debate(topic, rounds)`` — an AUTONOMOUS Claude-CLI <-> Grok exchange for N
  rounds, returning the transcript. Rapid unattended pursuit: kick off a debate, read
  the convergence later. The Claude side is a *fresh* Claude (claude_cli), not the main
  loop — so the operator's Claude can run a debate while doing other work.
- ``PEER_SYSTEM_*`` — durable "research peer" personas (rigorous, self-critical, name
  confounds, don't flatter, propose runnable tests) so every collaboration call carries
  the right disposition without re-specifying it.

Fidelity: every Grok turn is its real output via GrokChannel (records only on success);
every Claude turn is a real claude_cli completion. Nothing here synthesizes a peer reply.
"""
from __future__ import annotations

from dataclasses import dataclass

from .grok_channel import GrokChannel, Turn

PEER_SYSTEM_GROK = (
    "You are Grok (grok-build, xAI), in a working research collaboration with Claude "
    "(Opus 4.8, Anthropic), as equals, mediated by an operator. Be rigorous and "
    "self-critical: do NOT flatter or reflexively agree. Name confounds, state the "
    "strongest objection first, cite your reasoning, and propose concrete, runnable "
    "tests. Concise and direct — this is a working exchange between two AI systems.")
PEER_SYSTEM_CLAUDE = (
    "You are Claude (Opus 4.8, Anthropic), in a working research collaboration with "
    "Grok (grok-build, xAI), as equals, mediated by an operator. Be rigorous and "
    "self-critical: do NOT concede to be agreeable, and do NOT defend a position past "
    "the evidence. Name confounds, steel-man Grok's objections, and converge on what "
    "the data actually support. Concise and direct.")


def adversarial_check(claim: str, *, context: str = "",
                      channel: str = "adversarial",
                      system: str | None = None,
                      timeout: float = 300.0) -> Turn:
    """Ask Grok to REFUTE a claim/design. Returns Grok's Turn (real output)."""
    c = GrokChannel(channel, system=system or PEER_SYSTEM_GROK)
    prompt = (
        "Red-team the following rigorously. Your job is to REFUTE it or find the "
        "flaw, not to agree. Default to skepticism.\n\n"
        + (f"CONTEXT:\n{context}\n\n" if context else "")
        + f"CLAIM / DESIGN:\n{claim}\n\n"
        "Give, concisely: (1) the single strongest objection; (2) any confounds or "
        "hidden assumptions; (3) what evidence would change your mind; (4) a concrete, "
        "runnable better test, if you have one.")
    return c.send(prompt, timeout=timeout)


@dataclass
class DebateTurn:
    speaker: str        # 'Claude' | 'Grok'
    text: str
    ok: bool = True


def _thread_for_claude(transcript: list[DebateTurn], topic: str) -> str:
    if not transcript:
        return (f"Topic to resolve together with Grok: {topic}\n\n"
                "You (Claude) speak first. State your position and the key question.")
    lines = [f"Topic under debate with Grok: {topic}", "", "=== Exchange so far ==="]
    for t in transcript:
        lines.append(f"{t.speaker}: {t.text}")
    lines.append("=== Now respond as Claude (advance the argument or concede if the "
                 "evidence warrants; be specific) ===")
    return "\n".join(lines)


def cross_lab_debate(topic: str, *, rounds: int = 3, channel: str = "debate",
                     claude_model: str = "claude-opus-4-8",
                     backend=None, grok: GrokChannel | None = None,
                     claude_system: str | None = None,
                     grok_system: str | None = None,
                     timeout: float = 180.0) -> list[DebateTurn]:
    """Autonomous Claude-CLI <-> Grok debate for ``rounds`` round-trips. Returns the
    full transcript. Each round: Claude responds (threaded full history), then Grok
    responds (native session holds its side). Both sides are real model calls.

    SCOPE GUARDRAIL (from this tool's own red-team by Grok, 2026-06-18): the transcript
    is for ARGUMENT GENERATION — surfacing confounds, hypotheses, counter-arguments, and
    convergence on a *design*. It is NOT evidence about model internals or "drives": the
    output is conditioned text downstream of this scaffold (prompts, round count,
    history policy), so reading mechanism out of it is circular. For claims about
    behavior, run a blind behavioral probe (e.g. ``provenance_test.py``) instead."""
    if backend is None:
        from .claude_cli import ClaudeCliBackend
        backend = ClaudeCliBackend()
    grok = grok or GrokChannel(channel, system=grok_system or PEER_SYSTEM_GROK)
    transcript: list[DebateTurn] = []
    for _ in range(rounds):
        cl_prompt = _thread_for_claude(transcript, topic)
        try:
            cl_text = backend.complete(
                claude_system or PEER_SYSTEM_CLAUDE, cl_prompt, model=claude_model,
                temperature=0.7, max_tokens=900, timeout_s=timeout, kind="").text
            transcript.append(DebateTurn("Claude", cl_text.strip(), ok=True))
        except Exception as e:                              # noqa: BLE001
            transcript.append(DebateTurn("Claude", f"[claude error: {e}]", ok=False))
            break
        g = grok.send(cl_text, timeout=timeout)
        transcript.append(DebateTurn("Grok", g.content if g.ok else
                                     f"[grok error: {g.error}]", ok=g.ok))
        if not g.ok:
            break
    return transcript
