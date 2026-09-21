from __future__ import annotations

import json
import os

import requests

import facebook_demand_search as demand
from facebook_graphql_link_resolver import resolve_from_graphql_payloads
from facebook_live_post_capture import resolve_live_post_link
from facebook_post_link_resolver import canonical_direct, resolve_latest_leads
from facebook_post_menu_resolver import _is_actionable_facebook_link, resolve_unresolved_with_copy_menu


_ORIGINAL_RESOLVE_POST_PERMALINK = demand._resolve_post_permalink
_ORIGINAL_SCAN_SEARCH = demand._scan_search


def _resolve_post_permalink_live(page, post, group):
    """Prefer normal DOM permalink extraction, then capture Copy link immediately."""
    direct = _ORIGINAL_RESOLVE_POST_PERMALINK(page, post, group)
    if direct:
        return direct

    captured = resolve_live_post_link(page, post, group)
    if captured:
        print("    live post link: CAPTURED")
        return captured
    return ""


def _scan_search_with_graphql(page, group, query, max_posts=15):
    """Capture Facebook GraphQL responses while the group search is loading.

    The search-result UI can omit the real permalink entirely. The underlying GraphQL
    payload still has the result text and post/story id, so correlate each extracted
    post with those payloads after the normal scan finishes.
    """
    payloads: list[str] = []
    captured_bytes = 0
    max_payloads = 50
    max_total_bytes = 16 * 1024 * 1024

    def on_response(response):
        nonlocal captured_bytes
        try:
            url = str(response.url or "").casefold()
            if "facebook.com" not in url or "graphql" not in url:
                return
            if len(payloads) >= max_payloads or captured_bytes >= max_total_bytes:
                return
            body = response.text()
            if not body:
                return
            encoded_len = len(body.encode("utf-8", "ignore"))
            if captured_bytes + encoded_len > max_total_bytes:
                return
            payloads.append(body)
            captured_bytes += encoded_len
        except Exception:
            return

    page.on("response", on_response)
    try:
        posts = _ORIGINAL_SCAN_SEARCH(page, group, query, max_posts)
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

    if not posts or not payloads:
        return posts

    group_url = demand.base._canonical_group_url(str(group.get("url") or ""))
    resolved = 0
    for post in posts:
        current_url = str(post.get("url") or "")
        if canonical_direct(current_url, group_url) or _is_actionable_facebook_link(current_url, group_url):
            continue
        direct = resolve_from_graphql_payloads(str(post.get("text") or ""), group_url, payloads)
        if direct:
            post["url"] = direct
            post["link_quality"] = "DIRECT"
            post["link_source"] = "GRAPHQL"
            resolved += 1
    if resolved:
        print(f"    graphql post links: CAPTURED {resolved}/{len(posts)}")
    else:
        print(f"    graphql post links: 0/{len(posts)}")
    return posts


def _has_exact_link(lead) -> bool:
    group_url = str(lead.get("group_url") or "")
    url = str(lead.get("url") or "")
    action_url = str(lead.get("action_url") or "")
    return bool(
        canonical_direct(url, group_url)
        or _is_actionable_facebook_link(url, group_url)
        or _is_actionable_facebook_link(action_url, group_url)
    )


def _notify_actionable(leads):
    if not leads:
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_DISABLED: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return

    target = leads[:10]
    unresolved = [lead for lead in target if not _has_exact_link(lead)]
    if unresolved:
        print(f"Resolving exact Facebook post links: {len(unresolved)} unresolved...")
        resolve_latest_leads(target)

        still_unresolved = [lead for lead in target if not _has_exact_link(lead)]
        if still_unresolved:
            print(f"Trying Facebook Copy link menu: {len(still_unresolved)} unresolved...")
            resolve_unresolved_with_copy_menu(target)

        try:
            demand.OUTPUT_PATH.write_text(
                json.dumps(leads, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print("LINK_SAVE_WARNING", exc)

    sent = 0
    exact_count = 0
    for lead in target:
        group_url = str(lead.get("group_url") or "")
        url = str(lead.get("url") or "").strip()
        action_url = str(lead.get("action_url") or "").strip()
        direct = canonical_direct(url, group_url)

        if direct:
            lead["url"] = direct
            lead["link_quality"] = "DIRECT"
            exact_url = direct
            exact_label = "DIRECT POST"
        elif _is_actionable_facebook_link(url, group_url):
            exact_url = url
            exact_label = "COPIED POST LINK"
        elif _is_actionable_facebook_link(action_url, group_url):
            exact_url = action_url
            exact_label = "COPIED POST LINK"
        else:
            exact_url = ""
            exact_label = ""

        if exact_url:
            exact_count += 1

        text = demand.base._clean_text(lead.get("text"))
        if len(text) > 900:
            text = text[:897] + "..."

        lines = [
            f"🎯 BAY-S FACEBOOK LEAD | {lead.get('classification','')}",
            f"Intent: {lead.get('display_intent','')} | I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}",
            f"Grup: {lead.get('group','')}",
        ]
        if lead.get("author"):
            lines.append(f"Yazar: {lead.get('author')}")
        if lead.get("contact_phone"):
            lines.append(f"Telefon: {lead.get('contact_phone')}")
        lines.extend(["", text, ""])

        if exact_url:
            lines.extend([f"Link türü: {exact_label}", exact_url])
        else:
            lines.append("Link: DOĞRUDAN POST LİNKİ ÇIKARILAMADI")

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "\n".join(lines)[:3900],
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if response.status_code == 200:
            sent += 1
        else:
            print("TELEGRAM_ERROR", response.status_code, response.text[:250])

    if sent:
        print(f"TELEGRAM_SENT: {sent} lead message(s) | exact post links: {exact_count}/{len(target)}")


def main() -> int:
    # First try the visible card while it is present. In parallel, capture GraphQL
    # search responses so post IDs can still be recovered when Facebook exposes no
    # permalink/menu route in the rendered DOM.
    demand._resolve_post_permalink = _resolve_post_permalink_live
    demand._scan_search = _scan_search_with_graphql
    demand.base.notify_telegram = _notify_actionable
    return demand.main()


if __name__ == "__main__":
    raise SystemExit(main())
