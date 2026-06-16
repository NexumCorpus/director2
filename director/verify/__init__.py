"""Verification layer — trusted code that grades generated work.

``make_default_registry()`` wires the built-in verifiers under stable names so
tasks can reference them as plain strings in persisted state. Domain hooks
register additional verifiers on top.
"""

from .base import (VerifierRegistry, chain_needs_human, chain_passed,
                   run_chain, score_to_verdict)
from .evaluators import AgentOutputEvaluator, CommandPacketEvaluator


def make_default_registry() -> VerifierRegistry:
    reg = VerifierRegistry()
    reg.register("agent_output", AgentOutputEvaluator)
    reg.register("command_packet", CommandPacketEvaluator)
    return reg


__all__ = [
    "VerifierRegistry", "make_default_registry", "run_chain", "chain_passed",
    "chain_needs_human", "score_to_verdict", "AgentOutputEvaluator",
    "CommandPacketEvaluator",
]
