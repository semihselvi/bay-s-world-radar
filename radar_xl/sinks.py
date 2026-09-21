from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from radar_xl import config


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def send_telegram(payload: dict[str, Any]) -> dict[str, Any]:
    """Use XL-specific credentials only; never reuse production secret names implicitly."""
    if not config.TELEGRAM_ENABLED:
        return {"ok": False, "reason": "disabled"}
    token = os.getenv("RADAR_XL_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("RADAR_XL_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"ok": False, "reason": "missing_xl_credentials"}

    leads = [x for x in payload.get("results", []) if x.get("classification") in {"HOT", "WARM"}]
    lines = [f"🧪 BAY-S RADAR XL LAB | {len(leads)} HOT/WARM"]
    for item in leads[:10]:
        lines.append(
            f"{item.get('classification')} {item.get('score')} | {item.get('source')} | "
            f"{item.get('author','')} | {(item.get('title') or item.get('text',''))[:140]} | {item.get('url','')}"
        )
    if not leads:
        lines.append("Yeni HOT/WARM aday yok.")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "\n".join(lines)[:3900]},
            timeout=20,
        )
        return {"ok": response.status_code == 200, "status": response.status_code}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def send_crm_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    url = os.getenv("RADAR_XL_CRM_WEBHOOK_URL", "").strip()
    enabled = os.getenv("RADAR_XL_CRM_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not url:
        return {"ok": False, "reason": "disabled"}
    leads = [x for x in payload.get("results", []) if x.get("classification") in {"HOT", "WARM"}]
    if not leads:
        return {"ok": True, "sent": 0}
    try:
        response = requests.post(url, json={"source": "bay-s-radar-xl", "leads": leads}, timeout=30)
        return {"ok": 200 <= response.status_code < 300, "status": response.status_code, "sent": len(leads)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
