from __future__ import annotations

import os

import requests

import facebook_demand_search as demand


def _lead_search_phrase(text: str) -> str:
    """Build a distinctive Facebook group-search phrase from the actual lead text."""
    clean = demand.base._clean_text(text)
    if not clean:
        return ""

    # Use enough of the real post to make Facebook's group search narrow to the
    # specific lead, instead of the old broad queries such as `arıyorum`.
    words = clean.split()
    phrase = " ".join(words[:18])
    if len(phrase) > 150:
        phrase = phrase[:150].rsplit(" ", 1)[0]
    return phrase.strip()


def _lead_exact_search_url(lead) -> str:
    group_url = str(lead.get("group_url") or "")
    phrase = _lead_search_phrase(str(lead.get("text") or ""))
    if not group_url or not phrase:
        return ""
    return demand._group_search_url(group_url, phrase)


def _notify_actionable(leads):
    if not leads:
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_DISABLED: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return

    sent = 0
    for lead in leads[:10]:
        direct = demand._canonical_direct_post_url(
            str(lead.get("url") or ""),
            str(lead.get("group_url") or ""),
        )

        phrase = _lead_search_phrase(str(lead.get("text") or ""))
        exact_search = _lead_exact_search_url(lead)
        fallback = exact_search or str(lead.get("search_url") or lead.get("url") or "")
        link = direct or fallback
        link_label = "DIRECT POST" if direct else "LEAD TEXT SEARCH"

        text = demand.base._clean_text(lead.get("text"))
        if len(text) > 900:
            text = text[:897] + "..."

        lines = [
            f"🎯 BAY-S FACEBOOK LEAD | {lead.get('classification','')}",
            f"Intent: {lead.get('display_intent','')} | I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}",
            f"Grup: {lead.get('group','')}",
        ]
        if lead.get("contact_phone"):
            lines.append(f"Telefon: {lead.get('contact_phone')}")
        lines.extend([
            "",
            text,
            "",
            f"Link türü: {link_label}",
        ])
        if not direct and phrase:
            lines.append(f"Facebook'ta bul: {phrase}")
        lines.append(link)

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
        print(f"TELEGRAM_SENT: {sent} actionable lead message(s)")


def main() -> int:
    # Keep the demand scanner logic unchanged; only replace Telegram formatting.
    # If Facebook does not expose a stable post permalink, the fallback now searches
    # the group using a distinctive phrase copied from that exact lead text.
    demand.base.notify_telegram = _notify_actionable
    return demand.main()


if __name__ == "__main__":
    raise SystemExit(main())
