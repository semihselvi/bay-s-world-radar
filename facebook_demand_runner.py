from __future__ import annotations

import os

import requests

import facebook_demand_search as demand


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
        fallback = str(lead.get("search_url") or lead.get("url") or "")
        link = direct or fallback
        link_label = "DIRECT POST" if direct else "GROUP SEARCH"

        text = demand.base._clean_text(lead.get("text"))
        if len(text) > 900:
            text = text[:897] + "..."

        lines = [
            f"🎯 BAY-S FACEBOOK LEAD | {lead.get('classification','')}",
            f"Intent: {lead.get('display_intent','')} | I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}",
            f"Grup: {lead.get('group','')}",
            f"Arama: {lead.get('search_query','')}",
        ]
        if lead.get("contact_phone"):
            lines.append(f"Telefon: {lead.get('contact_phone')}")
        lines.extend([
            "",
            text,
            "",
            f"Link türü: {link_label}",
            link,
        ])

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
    # Keep the demand scanner logic unchanged; only replace Telegram formatting so
    # fallback links open the exact group search used to find the lead instead of
    # dumping the user on the group homepage.
    demand.base.notify_telegram = _notify_actionable
    return demand.main()


if __name__ == "__main__":
    raise SystemExit(main())
