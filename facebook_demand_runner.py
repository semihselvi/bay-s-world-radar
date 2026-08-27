from __future__ import annotations

import json
import os

import requests

import facebook_demand_search as demand
from facebook_post_link_resolver import canonical_direct, resolve_latest_leads


def _notify_actionable(leads):
    if not leads:
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_DISABLED: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return

    # Facebook's group-search page often hides the actual permalink in React data or
    # behind a timestamp route. Resolve it with the logged-in browser before sending
    # the alert. Do not pretend a broad search URL is the post itself.
    target = leads[:10]
    unresolved = [
        lead for lead in target
        if not canonical_direct(str(lead.get("url") or ""), str(lead.get("group_url") or ""))
    ]
    if unresolved:
        print(f"Resolving exact Facebook post links: {len(unresolved)} unresolved...")
        resolve_latest_leads(target)
        try:
            demand.OUTPUT_PATH.write_text(
                json.dumps(leads, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print("LINK_SAVE_WARNING", exc)

    sent = 0
    direct_count = 0
    for lead in target:
        direct = canonical_direct(
            str(lead.get("url") or ""),
            str(lead.get("group_url") or ""),
        )
        if direct:
            lead["url"] = direct
            lead["link_quality"] = "DIRECT"
            direct_count += 1

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

        if direct:
            lines.extend(["Link türü: DIRECT POST", direct])
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
        print(f"TELEGRAM_SENT: {sent} lead message(s) | direct links: {direct_count}/{len(target)}")


def main() -> int:
    demand.base.notify_telegram = _notify_actionable
    return demand.main()


if __name__ == "__main__":
    raise SystemExit(main())
