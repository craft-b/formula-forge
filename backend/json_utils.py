"""Shared JSON extraction for LLM output.

Single source of truth for pulling a JSON object out of a model response,
replacing the two divergent fence-stripping copies that previously lived in
main.py and graph.py (audit finding F13).
"""
from __future__ import annotations


def extract_json_block(text: str) -> str:
    """Return the first JSON object in `text`, tolerating ``` code fences.

    If no fenced block starting with `{` is found, the stripped input is
    returned unchanged (it may already be bare JSON).
    """
    raw = text.strip()
    if "```" in raw:
        for block in raw.split("```"):
            cleaned = block.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                return cleaned
    return raw
