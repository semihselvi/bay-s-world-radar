from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import facebook_group_scanner as base


RAW_POSTS: dict[str, dict[str, Any]] = {}
INTENT_COUNTS: Counter[str] = Counter()
ORIGINAL_CLASSIFY = base._classify_post


def _intent_label(intent: dict[str, Any]) -> str:
    """Return the classifier label using the current classifier schema."""
    return str(
        intent.get("intent_class")
        or intent.get("intent")
        or intent.get("intent_type")
        or "UNKNOWN"
    )


def _robust_dom_candidates(page) -> list[dict[str, Any]]:
    """Extract visible Facebook post-like containers using several current DOM signals."""
    try:
        return page.evaluate(
            """() => {
                const nodes = [];
                const seen = new Set();

                const add = (el) => {
                    if (!el || seen.has(el)) return;
                    const text = (el.innerText || '').trim();
                    if (text.length < 30 || text.length > 15000) return;
                    seen.add(el);
                    nodes.push(el);
                };

                document.querySelectorAll('div[role="article"]').forEach(add);

                const messageSelectors = [
                    '[data-ad-rendering-role="story_message"]',
                    '[data-ad-preview="message"]',
                    '[data-ad-comet-preview="message"]'
                ];
                document.querySelectorAll(messageSelectors.join(',')).forEach((msg) => {
                    const article = msg.closest('div[role="article"]');
                    if (article) {
                        add(article);
                        return;
                    }
                    let el = msg;
                    for (let i = 0; i < 9 && el; i++, el = el.parentElement) {
                        const t = (el.innerText || '').trim();
                        const hasPostLink = el.querySelector && el.querySelector(
                            'a[href*="/groups/"][href*="/posts/"], a[href*="/permalink/"]'
                        );
                        if (hasPostLink && t.length >= 30 && t.length <= 15000) {
                            add(el);
                            break;
                        }
                    }
                });

                document.querySelectorAll(
                    'a[href*="/groups/"][href*="/posts/"], a[href*="/permalink/"]'
                ).forEach((a) => {
                    const article = a.closest('div[role="article"]');
                    if (article) {
                        add(article);
                        return;
                    }
                    let el = a;
                    for (let i = 0; i < 10 && el; i++, el = el.parentElement) {
                        const t = (el.innerText || '').trim();
                        if (t.length >= 30 && t.length <= 15000) {
                            add(el);
                            break;
                        }
                    }
                });

                return nodes.slice(0, 120).map((el) => ({
                    text: (el.innerText || '').trim(),
                    links: Array.from(el.querySelectorAll('a[href]')).slice(0, 80).map((a) => ({
                        href: a.href || '',
                        text: (a.innerText || '').trim(),
                        aria: a.getAttribute('aria-label') || '',
                        title: a.getAttribute('title') || ''
                    }))
                }));
            }"""
        )
    except Exception:
        return []


def _collect_posts_v2(page, group: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    group_name = base._clean_text(group.get("name")) or "Facebook Group"
    group_url = base._canonical_group_url(str(group.get("url") or ""))
    candidates = _robust_dom_candidates(page)

    posts: list[dict[str, Any]] = []
    seen_local: set[str] = set()
    for candidate in candidates:
        if len(posts) >= limit:
            break
        text = base._clean_text(candidate.get("text"))
        if len(text) < 30:
            continue
        links = candidate.get("links") or []
        permalink = base._pick_permalink(links, group_url)
        author = base._pick_author(links)

        time_signals: list[str] = []
        for link in links[:40]:
            time_signals.extend([link.get("text", ""), link.get("aria", ""), link.get("title", "")])
        age_hours = base._extract_age_hours(time_signals)

        local_key = permalink or hashlib.sha1(text[:1000].encode("utf-8", "ignore")).hexdigest()
        if local_key in seen_local:
            continue
        seen_local.add(local_key)
        post = {
            "source": "Facebook",
            "group": group_name,
            "group_url": group_url,
            "url": permalink or group_url,
            "author": author,
            "text": text,
            "age_hours": age_hours,
        }
        posts.append(post)
        RAW_POSTS[f"{group_name}|{local_key}"] = post

    return posts


def _scan_group_v2(page, group: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    name = base._clean_text(group.get("name")) or "Facebook Group"
    raw_url = str(group.get("url") or "")
    url = base._canonical_group_url(raw_url)
    if not url:
        print(f"SKIP invalid group URL: {raw_url}")
        return []

    sort_newest = settings.get("sort_newest", True)
    target = base._with_chronological_sort(url) if sort_newest else url
    print(f"\nScanning: {name}")
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"  Initial navigation warning: {type(exc).__name__}")
    page.wait_for_timeout(3500)

    try:
        page_text = base._clean_text(page.locator("body").inner_text(timeout=3000))
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

    rounds = max(6, int(settings.get("scroll_rounds", 5)))
    pause = max(1.2, float(settings.get("scroll_pause_seconds", 2.5)))
    limit = max(1, int(group.get("max_posts") or settings.get("max_posts_per_group", 25)))

    collected: dict[str, dict[str, Any]] = {}
    retried_normal = False
    for round_no in range(rounds):
        batch = _collect_posts_v2(page, group, limit)
        for post in batch:
            key = post.get("url") or hashlib.sha1(post.get("text", "").encode("utf-8", "ignore")).hexdigest()
            collected[key] = post
            if len(collected) >= limit:
                break

        print(f"  Scroll {round_no + 1}/{rounds} - DOM candidates: {len(batch)} - posts seen: {len(collected)}")
        if len(collected) >= limit:
            break

        if sort_newest and not retried_normal and round_no >= 1 and len(collected) == 0:
            retried_normal = True
            print("  No posts found with chronological URL; retrying normal group feed...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            page.wait_for_timeout(3500)
            continue

        page.mouse.wheel(0, 3200)
        page.wait_for_timeout(int(pause * 1000))

    print(f"  Collected: {len(collected)}")
    return list(collected.values())[:limit]


def _classify_with_stats(post: dict[str, Any]) -> dict[str, Any] | None:
    item = {
        "text": post.get("text", ""),
        "title": f"{post.get('group', '')} | North Cyprus Facebook group",
        "author": post.get("author", ""),
        "source": "Facebook",
        "url": post.get("url", ""),
    }
    try:
        intent = base.classify_intent(item)
        label = _intent_label(intent)
        confidence = int(intent.get("intent_confidence") or 0)
    except Exception:
        label = "CLASSIFIER_ERROR"
        confidence = 0
    INTENT_COUNTS[label] += 1

    return ORIGINAL_CLASSIFY(post)


def _write_debug() -> None:
    rows: list[dict[str, Any]] = []
    for post in RAW_POSTS.values():
        item = {
            "text": post.get("text", ""),
            "title": f"{post.get('group', '')} | North Cyprus Facebook group",
            "author": post.get("author", ""),
            "source": "Facebook",
            "url": post.get("url", ""),
        }
        try:
            intent = base.classify_intent(item)
            row = dict(post)
            row["debug_intent"] = _intent_label(intent)
            row["debug_confidence"] = intent.get("intent_confidence") or 0
            row["debug_requirements"] = intent.get("requirements") or {}
            rows.append(row)
        except Exception as exc:
            row = dict(post)
            row["debug_error"] = str(exc)
            rows.append(row)

    path = base.ROOT / "facebook_posts_debug_latest.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw/debug posts: {path}")
    print(f"Debug rows saved: {len(rows)}")

    if rows:
        print("\nDEBUG SAMPLE POSTS")
        for index, row in enumerate(rows[:12], start=1):
            text = base._clean_text(row.get("text"))
            if len(text) > 500:
                text = text[:497] + "..."
            print(
                f"[{index}] {row.get('group','')} | "
                f"{row.get('debug_intent','UNKNOWN')} | C{row.get('debug_confidence',0)}"
            )
            print(" ", text)


def main() -> int:
    base._collect_posts = _collect_posts_v2
    base._scan_group = _scan_group_v2
    base._classify_post = _classify_with_stats
    code = base.main()
    _write_debug()
    if INTENT_COUNTS:
        summary = " | ".join(f"{k}={v}" for k, v in INTENT_COUNTS.most_common())
        print(f"Intent summary: {summary}")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_RADAR_V2_ERROR: {exc}")
        raise SystemExit(1)
