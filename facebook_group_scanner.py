from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from north_cyprus_intent_classifier import classify_intent, display_intent, is_buyer_catcher_eligible


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

CONFIG_PATH = ROOT / "facebook_groups.json"

_local_root = Path(os.getenv("LOCALAPPDATA") or str(Path.home()))
STATE_DIR = Path(os.getenv("BAYS_FACEBOOK_STATE_DIR") or (_local_root / "BAY-S" / "WorldRadar"))
PROFILE_DIR = Path(os.getenv("FACEBOOK_PROFILE_DIR") or (STATE_DIR / "facebook-profile"))
SEEN_PATH = STATE_DIR / "facebook_seen.json"
LATEST_PATH = ROOT / "facebook_leads_latest.json"
DISCOVERED_PATH = ROOT / "facebook_groups_discovered.json"

FACEBOOK_HOME = "https://www.facebook.com/"
FACEBOOK_GROUPS_FEED = "https://www.facebook.com/groups/feed/"

SKIP_GROUP_SEGMENTS = {
    "feed", "discover", "create", "notifications", "groups", "your_groups",
}

TIME_PATTERNS = [
    (re.compile(r"\b(\d+)\s*(?:m|min|mins|minute|minutes|dk|dak|dakika|мин)\b", re.I), lambda n: n / 60),
    (re.compile(r"\b(\d+)\s*(?:h|hr|hrs|hour|hours|sa|saat|std\.?|stunde|stunden|ч)\b", re.I), float),
    (re.compile(r"\b(\d+)\s*(?:d|day|days|gün|gun|tag|tage|д)\b", re.I), lambda n: n * 24.0),
]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def _canonical_facebook_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if "facebook.com" not in parts.netloc.lower():
            return url
        allowed = {"story_fbid", "id", "multi_permalinks"}
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k in allowed]
        return urlunsplit(("https", "www.facebook.com", parts.path, urlencode(query), ""))
    except Exception:
        return url


def _canonical_group_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        match = re.search(r"/groups/([^/?#]+)", parts.path, re.I)
        if not match:
            return ""
        segment = match.group(1)
        if segment.casefold() in SKIP_GROUP_SEGMENTS:
            return ""
        return f"https://www.facebook.com/groups/{segment}/"
    except Exception:
        return ""


def _with_chronological_sort(url: str) -> str:
    if "sorting_setting=" in url:
        return url
    return url + ("&" if "?" in url else "?") + "sorting_setting=CHRONOLOGICAL"


def _default_config() -> dict[str, Any]:
    return {
        "settings": {
            "scroll_rounds": 5,
            "scroll_pause_seconds": 2.5,
            "max_posts_per_group": 25,
            "max_age_hours": 72,
            "sort_newest": True,
            "notify_telegram": True,
        },
        "groups": [
            {
                "name": "Northern Cyprus Forum",
                "url": "https://www.facebook.com/groups/323875321020382/",
                "enabled": True,
            }
        ],
    }


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        config = _default_config()
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Cannot read {CONFIG_PATH.name}: {exc}") from exc
    if not isinstance(data.get("groups"), list):
        raise RuntimeError(f"{CONFIG_PATH.name} must contain a 'groups' list.")
    data.setdefault("settings", {})
    defaults = _default_config()["settings"]
    for key, value in defaults.items():
        data["settings"].setdefault(key, value)
    return data


def load_seen() -> dict[str, float]:
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}


def save_seen(seen: dict[str, float]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    compact = dict(sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:3000])
    SEEN_PATH.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")


def _post_key(post: dict[str, Any]) -> str:
    basis = post.get("url") or _clean_text(post.get("text"))[:1200]
    return hashlib.sha256(str(basis).encode("utf-8", "ignore")).hexdigest()


def _extract_age_hours(signals: list[str]) -> float | None:
    combined = " | ".join(_clean_text(s) for s in signals if s)
    low = combined.casefold()
    if any(x in low for x in ("just now", "az önce", "gerade eben", "только что")):
        return 0.0
    if any(x in low for x in ("yesterday", "dün", "gestern", "вчера")):
        return 24.0
    candidates: list[float] = []
    for pattern, convert in TIME_PATTERNS:
        for match in pattern.finditer(combined):
            try:
                candidates.append(float(convert(int(match.group(1)))))
            except Exception:
                pass
    return min(candidates) if candidates else None


def _pick_permalink(links: list[dict[str, str]], group_url: str) -> str:
    group_key = re.search(r"/groups/([^/]+)/", group_url)
    group_segment = group_key.group(1) if group_key else ""
    scored: list[tuple[int, str]] = []
    for item in links:
        href = item.get("href", "")
        if "facebook.com" not in href:
            continue
        score = 0
        if "/posts/" in href:
            score += 10
        if "/permalink/" in href:
            score += 9
        if "story_fbid=" in href:
            score += 8
        if group_segment and f"/groups/{group_segment}/" in href:
            score += 3
        if score:
            scored.append((score, _canonical_facebook_url(href)))
    return max(scored, default=(0, ""))[1]


def _pick_author(links: list[dict[str, str]]) -> str:
    for item in links:
        text = _clean_text(item.get("text") or item.get("aria"))
        href = item.get("href", "")
        if not (2 <= len(text) <= 80):
            continue
        if any(bad in text.casefold() for bad in ("like", "comment", "share", "beğen", "yorum", "paylaş")):
            continue
        if "/user/" in href or "profile.php" in href or re.search(r"facebook\.com/[^/?#]+/?$", href):
            return text
    return ""


def _article_link_metadata(article) -> list[dict[str, str]]:
    try:
        return article.locator("a[href]").evaluate_all(
            """els => els.map(a => ({
                href: a.href || '',
                text: (a.innerText || '').trim(),
                aria: a.getAttribute('aria-label') || '',
                title: a.getAttribute('title') || ''
            }))"""
        )
    except Exception:
        return []


def _collect_posts(page: Page, group: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    group_name = _clean_text(group.get("name")) or "Facebook Group"
    group_url = _canonical_group_url(str(group.get("url") or ""))
    selector = 'div[role="feed"] div[role="article"]'
    articles = page.locator(selector)
    if articles.count() == 0:
        articles = page.locator('div[role="article"]')

    posts: list[dict[str, Any]] = []
    seen_local: set[str] = set()
    count = min(articles.count(), max(limit * 2, limit))
    for index in range(count):
        if len(posts) >= limit:
            break
        article = articles.nth(index)
        try:
            text = _clean_text(article.inner_text(timeout=1800))
        except Exception:
            continue
        if len(text) < 30:
            continue

        links = _article_link_metadata(article)
        permalink = _pick_permalink(links, group_url)
        author = _pick_author(links)

        time_signals: list[str] = []
        for link in links[:30]:
            time_signals.extend([link.get("text", ""), link.get("aria", ""), link.get("title", "")])
        age_hours = _extract_age_hours(time_signals)

        local_key = permalink or hashlib.sha1(text[:900].encode("utf-8", "ignore")).hexdigest()
        if local_key in seen_local:
            continue
        seen_local.add(local_key)

        posts.append(
            {
                "source": "Facebook",
                "group": group_name,
                "group_url": group_url,
                "url": permalink or group_url,
                "author": author,
                "text": text,
                "age_hours": age_hours,
            }
        )
    return posts


def _credibility_score(intent: dict[str, Any], post: dict[str, Any]) -> int:
    req = intent.get("requirements") or {}
    score = 55
    if post.get("author"):
        score += 5
    if req.get("regions"):
        score += 10
    if req.get("property_type"):
        score += 8
    if req.get("budget"):
        score += 10
    if req.get("move_window"):
        score += 8
    if req.get("preferences"):
        score += 4
    text = _clean_text(post.get("text"))
    if re.search(r"(?:£|€|\$|₺)\s*\d|\b\d{2,3}\s*(?:k|000)\b", text, re.I):
        score += 5
    return min(98, score)


def _classify_post(post: dict[str, Any]) -> dict[str, Any] | None:
    item = {
        "text": post.get("text", ""),
        "title": f"{post.get('group', '')} | North Cyprus Facebook group",
        "author": post.get("author", ""),
        "source": "Facebook",
        "url": post.get("url", ""),
    }
    intent = classify_intent(item)
    if not is_buyer_catcher_eligible(intent):
        return None

    intent_score = int(intent.get("intent_confidence") or 0)
    credibility = _credibility_score(intent, post)
    market_fit = 95

    if intent_score >= 85 and credibility >= 70:
        label = "HOT"
    elif intent_score >= 70:
        label = "WARM"
    else:
        return None

    result = dict(post)
    result.update(intent)
    result.update(
        {
            "classification": label,
            "intent_score": intent_score,
            "credibility_score": credibility,
            "market_fit_score": market_fit,
            "display_intent": display_intent(intent),
        }
    )
    return result


def _telegram_message(leads: list[dict[str, Any]]) -> str:
    lines = [f"🎯 BAY-S FACEBOOK RADAR | {len(leads)} YENİ ADAY"]
    for lead in leads[:10]:
        req = lead.get("requirements") or {}
        details: list[str] = []
        if req.get("regions"):
            details.append("Bölge: " + ", ".join(req["regions"][:3]))
        if req.get("property_type"):
            details.append("Mülk: " + str(req["property_type"]))
        if req.get("budget"):
            details.append("Bütçe: " + str(req["budget"]))
        if req.get("move_window"):
            details.append("Zaman: " + str(req["move_window"]))
        lines.append("")
        lines.append(
            f"{lead['classification']} | {lead.get('display_intent','')} | "
            f"I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']}"
        )
        lines.append(f"Grup: {lead.get('group','')}")
        if details:
            lines.append(" | ".join(details))
        text = _clean_text(lead.get("text"))
        if len(text) > 430:
            text = text[:427] + "..."
        lines.append(text)
        if lead.get("url"):
            lines.append(str(lead["url"]))
    return "\n".join(lines)


def notify_telegram(leads: list[dict[str, Any]]) -> None:
    if not leads:
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_DISABLED: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return
    message = _telegram_message(leads)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:3900], "disable_web_page_preview": True},
            timeout=20,
        )
        if response.status_code == 200:
            print("TELEGRAM_SENT")
        else:
            print("TELEGRAM_ERROR", response.status_code, response.text[:250])
    except Exception as exc:
        print("TELEGRAM_ERROR", exc)


def _is_login_page(page: Page) -> bool:
    try:
        if "/login" in page.url:
            return True
        return page.locator('input[name="email"]').count() > 0 and page.locator('input[name="pass"]').count() > 0
    except Exception:
        return False


def ensure_facebook_login(page: Page) -> None:
    print("Facebook session check...")
    page.goto(FACEBOOK_HOME, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    if not _is_login_page(page):
        return
    print("")
    print("Facebook login is required.")
    print("1) Log in manually in the Chrome window.")
    print("2) Complete any verification Facebook asks for.")
    input("3) When your Facebook home page is open, press ENTER here: ")
    page.goto(FACEBOOK_GROUPS_FEED, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    if _is_login_page(page):
        raise RuntimeError("Facebook login was not completed. Run the scanner again after logging in.")


def _launch_context(playwright, headless: bool = False) -> BrowserContext:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    requested = os.getenv("FACEBOOK_BROWSER_CHANNEL", "chrome").strip()
    channels = [requested] + [x for x in ("chrome", "msedge") if x != requested]
    last_error: Exception | None = None
    for channel in channels:
        try:
            print(f"Opening browser channel: {channel}")
            return playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel=channel,
                headless=headless,
                viewport={"width": 1440, "height": 1000},
                args=["--disable-notifications"],
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        "Could not open Chrome/Edge with the dedicated BAY-S Facebook profile. "
        f"Last error: {last_error}"
    )


def _scan_group(page: Page, group: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    name = _clean_text(group.get("name")) or "Facebook Group"
    raw_url = str(group.get("url") or "")
    url = _canonical_group_url(raw_url)
    if not url:
        print(f"SKIP invalid group URL: {raw_url}")
        return []

    target = _with_chronological_sort(url) if settings.get("sort_newest", True) else url
    print(f"\nScanning: {name}")
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeoutError:
        print("  Page load timed out; trying visible content anyway.")
    page.wait_for_timeout(3000)

    try:
        page_text = _clean_text(page.locator("body").inner_text(timeout=3000))
    except Exception:
        page_text = ""
    unavailable_markers = (
        "this content isn't available",
        "bu içeriğe şu anda ulaşılamıyor",
        "content isn't available right now",
    )
    if any(x in page_text.casefold() for x in unavailable_markers):
        print("  Group is not accessible with the current Facebook account.")
        return []

    rounds = max(1, int(settings.get("scroll_rounds", 5)))
    pause = max(0.8, float(settings.get("scroll_pause_seconds", 2.5)))
    limit = max(1, int(group.get("max_posts") or settings.get("max_posts_per_group", 25)))

    collected: dict[str, dict[str, Any]] = {}
    for round_no in range(rounds):
        for post in _collect_posts(page, group, limit):
            key = post.get("url") or hashlib.sha1(post.get("text", "").encode("utf-8", "ignore")).hexdigest()
            collected[key] = post
            if len(collected) >= limit:
                break
        if len(collected) >= limit:
            break
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(int(pause * 1000))
        print(f"  Scroll {round_no + 1}/{rounds} - posts seen: {len(collected)}")

    print(f"  Collected: {len(collected)}")
    return list(collected.values())[:limit]


def discover_groups(page: Page) -> list[dict[str, Any]]:
    print("Discovering Facebook groups visible in your Groups feed...")
    page.goto(FACEBOOK_GROUPS_FEED, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    found: dict[str, str] = {}
    for round_no in range(8):
        links = page.locator('a[href*="/groups/"]').evaluate_all(
            """els => els.map(a => ({
                href: a.href || '',
                text: (a.innerText || '').trim(),
                aria: a.getAttribute('aria-label') || ''
            }))"""
        )
        for item in links:
            url = _canonical_group_url(item.get("href", ""))
            if not url:
                continue
            name = _clean_text(item.get("text") or item.get("aria"))
            if not name or len(name) > 120:
                continue
            low = name.casefold()
            if low in {"groups", "your groups", "gruplar", "grupların", "discover"}:
                continue
            found.setdefault(url, name)
        page.mouse.wheel(0, 4500)
        page.wait_for_timeout(1800)
        print(f"  Discover scroll {round_no + 1}/8 - groups found: {len(found)}")

    groups = [{"name": name, "url": url, "enabled": False} for url, name in sorted(found.items(), key=lambda x: x[1].casefold())]
    DISCOVERED_PATH.write_text(
        json.dumps({"groups": groups}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved {len(groups)} groups to: {DISCOVERED_PATH}")
    print("These are disabled by default. Copy the groups you want into facebook_groups.json and set enabled=true.")
    return groups


def run_scan(context: BrowserContext, config: dict[str, Any]) -> list[dict[str, Any]]:
    settings = config["settings"]
    groups = [g for g in config["groups"] if g.get("enabled", True)]
    if not groups:
        print("No enabled Facebook groups in facebook_groups.json.")
        return []

    page = context.pages[0] if context.pages else context.new_page()
    ensure_facebook_login(page)

    max_age = float(settings.get("max_age_hours", 72))
    seen = load_seen()
    now = time.time()
    new_leads: list[dict[str, Any]] = []

    for group in groups:
        posts = _scan_group(page, group, settings)
        for post in posts:
            age = post.get("age_hours")
            if age is not None and age > max_age:
                continue
            lead = _classify_post(post)
            if not lead:
                continue
            key = _post_key(lead)
            if key in seen:
                continue
            seen[key] = now
            new_leads.append(lead)

    new_leads.sort(
        key=lambda x: (
            x.get("classification") == "HOT",
            int(x.get("intent_score") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )
    save_seen(seen)
    LATEST_PATH.write_text(json.dumps(new_leads, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"BAY-S FACEBOOK RADAR COMPLETE | New HOT/WARM: {len(new_leads)}")
    print(f"Latest output: {LATEST_PATH}")
    for lead in new_leads[:10]:
        print(
            f"{lead['classification']} | {lead.get('display_intent')} | "
            f"I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | "
            f"{lead.get('group')}"
        )
        print(" ", _clean_text(lead.get("text"))[:220])
        print(" ", lead.get("url"))
    if settings.get("notify_telegram", True):
        notify_telegram(new_leads)
    return new_leads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BAY-S Facebook Group Radar")
    parser.add_argument("--discover", action="store_true", help="Discover groups visible in the logged-in Facebook account.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Use only after login has been saved.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    with sync_playwright() as playwright:
        context = _launch_context(playwright, headless=args.headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if args.discover:
                ensure_facebook_login(page)
                discover_groups(page)
            else:
                run_scan(context, config)
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_RADAR_ERROR: {exc}")
        raise SystemExit(1)
