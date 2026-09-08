from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from radar_xl import config
from radar_xl.classifier import classify
from radar_xl.dedupe import dedupe
from radar_xl.hermes_bridge import HermesBridge
from radar_xl.models import Candidate, ClassifiedCandidate
from radar_xl.providers.agent_reach import AgentReachProvider
from radar_xl.providers.browser_use import BrowserUseProvider
from radar_xl.providers.firecrawl import FirecrawlProvider
from radar_xl.sinks import send_crm_webhook, send_telegram, write_json


def _query_plan() -> list[tuple[str, str]]:
    """Round-robin languages so one language cannot consume the whole provider budget."""
    buckets = {lang: list(items) for lang, items in config.BUYER_QUERIES.items()}
    plan: list[tuple[str, str]] = []
    while any(buckets.values()):
        for lang in ("en", "tr", "ru"):
            if buckets.get(lang):
                plan.append((lang, buckets[lang].pop(0)))
    return plan


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # Twitter-style and other common textual timestamps.
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _freshness_adjust(item: ClassifiedCandidate, lookback_hours: int) -> ClassifiedCandidate:
    published = _parse_date(item.candidate.published_at)
    if published is None:
        item.candidate.metadata["date_verified"] = False
        # An undated item must never jump straight to HOT in the lab.
        if item.classification == "HOT":
            item.classification = "WARM"
            item.score = max(48, item.score - 12)
            item.reasons.append("date_unverified_downgrade")
        return item

    item.candidate.metadata["date_verified"] = True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    if published < cutoff:
        item.classification = "NOISE"
        item.reject_reason = "older_than_lookback"
        item.score = 0
    return item


def _browser_enrich(candidates: list[Candidate], browser: BrowserUseProvider) -> None:
    """Use Browser Use only when a URL was found but normal extraction returned too little text."""
    if not browser.available:
        return
    for candidate in candidates:
        if not browser.available:
            break
        if not candidate.url or len((candidate.text or "").strip()) >= 80:
            continue
        result = browser.extract_url(candidate.url)
        output = result.get("output") if result.get("ok") else None
        if not isinstance(output, dict):
            continue
        candidate.title = str(output.get("title") or candidate.title)
        candidate.author = str(output.get("author") or candidate.author)
        candidate.text = str(output.get("text") or candidate.text)
        candidate.published_at = str(output.get("published_at") or candidate.published_at)
        candidate.metadata["browser_use_fallback"] = True
        candidate.metadata["browser_use_task_id"] = result.get("task_id", "")


def run() -> dict:
    started = datetime.now(timezone.utc)
    lookback_hours = config.env_int("RADAR_XL_LOOKBACK_HOURS", 168, minimum=1, maximum=24 * 90)
    queries = _query_plan()

    agent_reach = AgentReachProvider()
    firecrawl = FirecrawlProvider()
    browser = BrowserUseProvider()

    raw: list[Candidate] = []
    provider_counts: dict[str, int] = {}

    before = len(raw)
    raw.extend(agent_reach.collect(queries))
    provider_counts["agent_reach"] = len(raw) - before

    before = len(raw)
    raw.extend(firecrawl.collect(queries))
    provider_counts["firecrawl"] = len(raw) - before

    _browser_enrich(raw, browser)
    provider_counts["browser_use_tasks"] = browser.used_tasks

    classified = [_freshness_adjust(classify(candidate), lookback_hours) for candidate in raw]
    unique = dedupe(classified)
    unique.sort(key=lambda x: (x.classification == "HOT", x.classification == "WARM", x.score), reverse=True)

    results = [item.as_dict() for item in unique]
    stats = {
        "raw": len(raw),
        "unique": len(unique),
        "hot": sum(1 for x in unique if x.classification == "HOT"),
        "warm": sum(1 for x in unique if x.classification == "WARM"),
        "noise": sum(1 for x in unique if x.classification == "NOISE"),
        "providers": provider_counts,
        "lookback_hours": lookback_hours,
    }

    manifest = {
        "system": "BAY-S Radar XL",
        "mode": "isolated_lab",
        "production_radar_touched": False,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": config.DRY_RUN,
        "provider_status": {
            "agent_reach": bool(agent_reach.status.get("available")),
            "firecrawl": firecrawl.available,
            "browser_use": browser.available or browser.used_tasks > 0,
            "hermes": HermesBridge().available,
        },
        "stats": stats,
        "results": results,
    }

    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(config.OUTPUT_DIR) / f"radar-xl-{stamp}.json"
    write_json(output_path, manifest)

    hermes = HermesBridge()
    if hermes.available:
        manifest["hermes_review"] = hermes.review_manifest(output_path)
        write_json(output_path, manifest)

    # No external writes in dry-run mode. XL uses its own Telegram credentials when enabled.
    if not config.DRY_RUN:
        manifest["telegram"] = send_telegram(manifest)
        manifest["crm"] = send_crm_webhook(manifest)
        write_json(output_path, manifest)

    print(json.dumps({"output": str(output_path), "stats": stats}, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    run()
