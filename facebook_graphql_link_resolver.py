from __future__ import annotations

import json
import re
from typing import Any

import facebook_group_scanner as base


STRONG_ID_KEYS = {
    "post_id",
    "top_level_post_id",
    "mf_story_key",
    "story_fbid",
    "legacy_story_hideable_id",
    "story_id",
}


def _group_segment(group_url: str) -> str:
    match = re.search(r"/groups/([^/?#]+)/?", group_url or "", re.I)
    return match.group(1) if match else ""


def _norm(value: Any) -> str:
    return base._clean_text(value).casefold()


def _plausible_id(value: Any) -> str:
    value = str(value or "").strip()
    return value if value.isdigit() and len(value) >= 6 else ""


def _strong_id_from_dict(node: dict[str, Any]) -> str:
    for key, value in node.items():
        if str(key).casefold() in STRONG_ID_KEYS:
            found = _plausible_id(value)
            if found:
                return found

    typename = _norm(node.get("__typename"))
    looks_story = any(word in typename for word in ("story", "post"))
    if looks_story:
        found = _plausible_id(node.get("id"))
        if found:
            return found
    return ""


def _find_match_and_id(node: Any, target: str, ancestors: list[dict[str, Any]]) -> str:
    if isinstance(node, str):
        text = _norm(node)
        if not text:
            return ""
        prefix = target[: min(75, len(target))]
        short = text[: min(75, len(text))]
        if (prefix and prefix in text) or (short and len(short) >= 24 and short in target):
            for parent in reversed(ancestors[-10:]):
                found = _strong_id_from_dict(parent)
                if found:
                    return found
        return ""

    if isinstance(node, dict):
        new_ancestors = ancestors + [node]
        # Search likely text-bearing fields first so the nearest story/post ancestor
        # is available when a message match is found.
        preferred = ("text", "message", "body", "title", "description")
        for key in preferred:
            if key in node:
                found = _find_match_and_id(node[key], target, new_ancestors)
                if found:
                    return found
        for key, value in node.items():
            if key in preferred:
                continue
            found = _find_match_and_id(value, target, new_ancestors)
            if found:
                return found
        return ""

    if isinstance(node, list):
        for value in node:
            found = _find_match_and_id(value, target, ancestors)
            if found:
                return found
    return ""


def _json_objects_from_body(body: str) -> list[Any]:
    raw = str(body or "").strip()
    if not raw:
        return []
    objects: list[Any] = []
    try:
        objects.append(json.loads(raw))
        return objects
    except Exception:
        pass

    # Facebook can stream GraphQL as multiple JSON objects separated by newlines.
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith(("{", "[")):
            continue
        try:
            objects.append(json.loads(line))
        except Exception:
            continue
    return objects


def resolve_from_graphql_payloads(text: str, group_url: str, payloads: list[str]) -> str:
    target = _norm(text)
    group_id = _group_segment(group_url)
    if not target or not group_id:
        return ""

    for body in payloads:
        for obj in _json_objects_from_body(body):
            post_id = _find_match_and_id(obj, target, [])
            if post_id:
                return f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"

    # Last-resort regex around the matching message in decoded JSON text. This is
    # deliberately limited to strong post-id field names to avoid confusing actor IDs
    # with post IDs.
    target_prefix = target[: min(55, len(target))]
    for body in payloads:
        try:
            decoded = body.encode("utf-8", "ignore").decode("unicode_escape", "ignore")
        except Exception:
            decoded = body
        low = _norm(decoded)
        pos = low.find(target_prefix)
        if pos < 0:
            continue
        start = max(0, pos - 12000)
        end = min(len(decoded), pos + 12000)
        window = decoded[start:end]
        match = re.search(
            r'"(?:post_id|top_level_post_id|mf_story_key|story_fbid|legacy_story_hideable_id|story_id)"\s*:\s*"?(\d{6,})',
            window,
            re.I,
        )
        if match:
            return f"https://www.facebook.com/groups/{group_id}/posts/{match.group(1)}/"
    return ""
