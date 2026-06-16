"""Subagent contracts.

An :class:`AgentSpec` is a bounded work order (Director 1.0's TaskPacket,
slimmed): one role, one objective, explicit context — subagents are stateless;
durable state belongs to the Director. The structured output schema is shared
across roles so ingestion is uniform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, model_validator

from ..core.types import VerificationReport, new_id

# Lenient-shape coercion (2026-06-12 live-run findings): real models drift
# from the schema in recurring SHAPES — synonym keys, scalars where lists go,
# a bare list at the root. We adapt shape, never meaning: synonyms are
# accepted, structure is wrapped, but values are never guessed.


def _alias_key(d: dict, target: str, *aliases: str) -> dict:
    if target not in d:
        for a in aliases:
            if isinstance(d.get(a), str) and d[a].strip():
                d[target] = d[a]
                break
    return d


class ArtifactOut(BaseModel):
    title: str
    kind: str = "markdown"            # markdown | code | json | report | dialogue | quest | sim
    content: str

    @model_validator(mode="before")
    @classmethod
    def _lenient_shape(cls, v):
        if isinstance(v, dict):
            v = _alias_key(dict(v), "title", "name", "filename", "id", "label")
            v = _alias_key(v, "kind", "type", "format")
            if "content" not in v:
                for a in ("text", "body", "data", "value"):
                    if a in v:
                        v["content"] = v[a]
                        break
            # live finding: models put the actual JSON OBJECT in content
            # where the contract wants its string serialization
            if not isinstance(v.get("content"), str) and v.get("content") \
                    is not None:
                v["content"] = json.dumps(v["content"], indent=1,
                                          default=str)
        return v


class ClaimOut(BaseModel):
    text: str
    confidence: str = "medium"        # low | medium | high
    evidence: str = ""

    @model_validator(mode="before")
    @classmethod
    def _lenient_shape(cls, v):
        if isinstance(v, dict):
            v = _alias_key(dict(v), "text", "claim", "statement", "title")
        return v


class RiskOut(BaseModel):
    title: str
    level: str = "medium"             # low | medium | high | critical
    description: str = ""
    mitigation: str = ""

    @model_validator(mode="before")
    @classmethod
    def _lenient_shape(cls, v):
        if isinstance(v, dict):
            v = _alias_key(dict(v), "title", "statement", "text", "risk",
                           "description")
        return v


class SubAgentOutput(BaseModel):
    """The one output contract every role returns."""
    summary: str
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    claims: list[ClaimOut] = Field(default_factory=list)
    risks: list[RiskOut] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    recommended_updates: dict = Field(default_factory=dict)
    command_packet_recommended: bool = False
    command_packet_reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _lenient_shape(cls, v):
        # bare list at the root (observed live): treat as the artifact list,
        # and say so in the summary rather than pretending it was well-formed
        if isinstance(v, list):
            v = {"summary": "(coerced: model returned a bare list; treated "
                            "as artifacts)",
                 "artifacts": v}
        if isinstance(v, dict):
            v = dict(v)
            ru = v.get("recommended_updates")
            if isinstance(ru, list):
                v["recommended_updates"] = {"items": ru}
            elif isinstance(ru, str) and ru.strip():
                v["recommended_updates"] = {"note": ru}
            if isinstance(v.get("lessons"), str):
                v["lessons"] = [v["lessons"]]
        return v


@dataclass
class AgentSpec:
    role: str
    objective: str
    context: str = ""
    inputs: dict = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    task_id: str = ""
    verifiers: list[str] = field(default_factory=list)   # extra named verifiers
    profile_role: str = ""                                # router profile override
    id: str = field(default_factory=new_id)


@dataclass
class AgentResult:
    spec_id: str
    task_id: str = ""
    role: str = ""
    ok: bool = False
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    needs_human: bool = False
    backend: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    error: str = ""
