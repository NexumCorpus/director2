"""Robust JSON extraction from LLM replies (ported from RDE, battle-tested
v1→v11). Models are chronically chatty; downstream code must never parse prose.
"""

from __future__ import annotations

import json


def extract_json(text: str):
    """Best-effort: pull the first well-formed JSON object/array from a reply.

    Strategy: straight parse; then fenced ```json blocks; then the earliest
    balanced {...} / [...] span (string-literal aware). Raises ValueError if
    nothing parses.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        for chunk in text.split("```"):
            c = chunk.strip()
            if c.startswith("json"):
                c = c[4:].strip()
            if c[:1] in "{[":
                try:
                    return json.loads(c)
                except json.JSONDecodeError:
                    continue

    candidates = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start != -1:
            candidates.append((start, opener, closer))
    for _, opener, closer in sorted(candidates):
        span = _balanced_span(text, opener, closer)
        if span is not None:
            try:
                return json.loads(span)
            except json.JSONDecodeError:
                continue
    raise ValueError("no parseable JSON found in model reply")


def _balanced_span(text: str, opener: str, closer: str) -> str | None:
    start = text.find(opener)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch == '"':
                in_str = True
                quote = ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None
