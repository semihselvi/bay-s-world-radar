from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import facebook_group_scanner as base


POST_KEYS = ("multi_permalinks", "story_fbid", "post_id", "top_level_post_id", "mf_story_key")
POST_ID_RE = re.compile(
    r"(?:top_level_post_id|mf_story_key|story_fbid|post_id)[\\\"'=:\\s%]+(?:%22|\\\")?(\\d{6,})",
    re.I,
)
PATH_POST_RE = re.compile(r"/groups/([^/?#]+)/(?:(?:posts)|(?:permalink))/(\\d+)", re.I)
ESCAPED_PATH_RE = re.compile(r"/groups/([^/\\?&#]+)(?:\\?/|/)(?:posts|permalink)(?:\\?/|/)(\\d+)", re.I)


def _group_segment(group_url: str) -> str:
    match = re.search(r"/groups/([^/?#]+)/?", group_url or "", re.I)
    return match.group(1) if match else ""


def canonical_direct(url: str, group_url: str, depth: int = 0) -> str:
    if not url or depth > 3:
        return ""
    value = html.unescape(str(url)).replace("\\/", "/")
    try:
        parts = urlsplit(value)
        if "facebook.com" not in parts.netloc.casefold():
            return ""
        group_id = _group_segment(group_url)
        match = PATH_POST_RE.search(parts.path)
        if match:
            return f"https://www.facebook.com/groups/{match.group(1)}/posts/{match.group(2)}/"
        query = parse_qs(parts.query)
        for key in POST_KEYS:
            post_id = (query.get(key) or [""])[0]
            if group_id and str(post_id).isdigit():
                return f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"
        for key in ("u", "href", "next", "redirect", "url"):
            nested = (query.get(key) or [""])[0]
            if nested:
                direct = canonical_direct(unquote(str(nested)), group_url, depth + 1)
                if direct:
                    return direct
    except Exception:
        pass
    return ""


def _direct_from_blob(blob: str, group_url: str) -> str:
    if not blob:
        return ""
    group_id = _group_segment(group_url)
    raw = html.unescape(str(blob)).replace("\\/", "/").replace("&quot;", '"')

    match = PATH_POST_RE.search(raw) or ESCAPED_PATH_RE.search(raw)
    if match:
        return f"https://www.facebook.com/groups/{match.group(1)}/posts/{match.group(2)}/"

    if group_id:
        for _ in range(2):
            match = POST_ID_RE.search(raw)
            if match:
                return f"https://www.facebook.com/groups/{group_id}/posts/{match.group(1)}/"
            raw = unquote(raw)
    return ""


def _collect_matching_evidence(page, text: str) -> dict[str, Any]:
    needle = base._clean_text(text)[:260]
    if not needle:
        return {"hrefs": [], "html": [], "time_hrefs": []}
    try:
        return page.evaluate(
            """({needle}) => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const target = norm(needle);
                const prefix = target.slice(0, Math.min(105, target.length));
                const msgSel = '[data-ad-rendering-role="story_message"], [data-ad-preview="message"], [data-ad-comet-preview="message"]';
                const matched = [];
                const seen = new Set();

                const accept = (el) => {
                    if (!el || seen.has(el)) return;
                    const txt = norm(el.innerText || '');
                    if (!txt) return;
                    const short = txt.slice(0, Math.min(105, txt.length));
                    if (txt.includes(prefix) || target.includes(short)) {
                        seen.add(el);
                        matched.push(el);
                    }
                };

                document.querySelectorAll(msgSel).forEach((msg) => {
                    const txt = norm(msg.innerText || '');
                    const short = txt.slice(0, Math.min(105, txt.length));
                    if (txt.includes(prefix) || target.includes(short)) {
                        let el = msg.closest('div[role="article"]') || msg.parentElement;
                        accept(el);
                        for (let i = 0; i < 5 && el; i++, el = el.parentElement) accept(el);
                    }
                });

                const hrefs = [];
                const htmls = [];
                const timeHrefs = [];
                const timeRx = /^(?:\d+\s*(?:s|m|h|d|w|sn|dk|sa|saat|gün|gun|hafta|hr|hrs|min|mins|day|days)|just now|yesterday|az önce|dün|now)$/i;

                for (const container of matched.slice(0, 8)) {
                    if (container.outerHTML) htmls.push(container.outerHTML.slice(0, 180000));
                    for (const a of container.querySelectorAll('a[href]')) {
                        const href = a.href || '';
                        if (!href) continue;
                        hrefs.push(href);
                        const label = norm([a.innerText, a.getAttribute('aria-label'), a.getAttribute('title')].filter(Boolean).join(' '));
                        if (timeRx.test(label) || /posts|permalink|story_fbid|multi_permalinks|post_id/i.test(href)) {
                            timeHrefs.push(href);
                        }
                    }
                }
                return {
                    hrefs: [...new Set(hrefs)].slice(0, 250),
                    html: htmls.slice(0, 8),
                    time_hrefs: [...new Set(timeHrefs)].slice(0, 30)
                };
            }""",
            {"needle": needle},
        )
    except Exception:
        return {"hrefs": [], "html": [], "time_hrefs": []}


def _direct_from_loaded_page(page, group_url: str) -> str:
    direct = canonical_direct(page.url, group_url)
    if direct:
        return direct
    try:
        candidates = page.evaluate(
            """() => {
                const out = [];
                const canonical = document.querySelector('link[rel="canonical"]');
                if (canonical && canonical.href) out.push(canonical.href);
                for (const sel of ['meta[property="og:url"]','meta[name="twitter:url"]']) {
                    const el = document.querySelector(sel);
                    if (el && el.content) out.push(el.content);
                }
                for (const a of document.querySelectorAll('a[href*="/groups/"][href*="/posts/"],a[href*="/permalink/"]')) {
                    if (a.href) out.push(a.href);
                }
                return [...new Set(out)].slice(0,30);
            }"""
        )
    except Exception:
        candidates = []
    for value in candidates or []:
        direct = canonical_direct(str(value), group_url)
        if direct:
            return direct
    try:
        return _direct_from_blob(page.content(), group_url)
    except Exception:
        return ""


def _resolve_by_clicking_post_route(context, search_url: str, text: str, group_url: str, max_scrolls: int = 5) -> str:
    """Last-resort resolver: click the matched post's timestamp/date/comment route and inspect the opened route.

    Facebook frequently keeps the real permalink out of the visible DOM on group-search
    results. In that layout the timestamp is a React/SPA link. Reading hrefs is not
    enough, so this routine uses a disposable page, finds the exact post card by text,
    clicks the most post-specific route, then reads the resulting URL/canonical data.
    """
    needle = base._clean_text(text)[:260]
    if not needle or not search_url:
        return ""

    temp = None
    try:
        temp = context.new_page()
        try:
            temp.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        temp.wait_for_timeout(2800)

        for round_no in range(max_scrolls):
            pages_before = set(context.pages)
            try:
                clicked = temp.evaluate(
                    """({needle}) => {
                        const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        const target = norm(needle);
                        const prefix = target.slice(0, Math.min(105, target.length));
                        const msgSel = '[data-ad-rendering-role="story_message"], [data-ad-preview="message"], [data-ad-comet-preview="message"]';
                        let article = null;

                        for (const msg of document.querySelectorAll(msgSel)) {
                            const txt = norm(msg.innerText || '');
                            const short = txt.slice(0, Math.min(105, txt.length));
                            if (txt.includes(prefix) || target.includes(short)) {
                                article = msg.closest('div[role="article"]') || msg.parentElement;
                                break;
                            }
                        }
                        if (!article) return {found:false, clicked:false, label:'', href:'', score:0};

                        const monthRx = /(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik|january|february|march|april|may|june|july|august|september|october|november|december)/i;
                        const timeRx = /(^|\s)(\d+\s*(sn|dk|sa|saat|gün|gun|hafta|min|mins|h|hr|hrs|d|day|days|w)|az önce|dün|just now|yesterday)(\s|$)/i;
                        const commentRx = /(yorum|comment|comments|yanıt|reply|replies)/i;
                        const candidates = [];

                        const nodes = article.querySelectorAll('a[href], a[role="link"], [role="link"]');
                        nodes.forEach((el, idx) => {
                            const href = el.href || el.getAttribute('href') || '';
                            const label = norm([
                                el.innerText || '',
                                el.getAttribute('aria-label') || '',
                                el.getAttribute('title') || ''
                            ].join(' '));
                            let score = 0;
                            if (/\/groups\/[^/]+\/(posts|permalink)\//i.test(href)) score += 140;
                            if (/story_fbid|multi_permalinks|post_id|top_level_post_id/i.test(href)) score += 130;
                            if (monthRx.test(label)) score += 95;
                            if (timeRx.test(label)) score += 90;
                            if (/\d{1,2}[:.]\d{2}/.test(label)) score += 75;
                            if (commentRx.test(label)) score += 55;
                            if (/facebook\.com\/groups\//i.test(href)) score += 10;
                            if (score > 0) candidates.push({el, idx, href, label, score});
                        });
                        candidates.sort((a,b) => b.score - a.score);
                        if (!candidates.length) return {found:true, clicked:false, label:'', href:'', score:0};

                        const best = candidates[0];
                        try {
                            if (best.el.tagName === 'A') best.el.setAttribute('target', '_self');
                            best.el.scrollIntoView({block:'center'});
                            best.el.click();
                            return {found:true, clicked:true, label:best.label, href:best.href, score:best.score};
                        } catch (e) {
                            return {found:true, clicked:false, label:best.label, href:best.href, score:best.score};
                        }
                    }""",
                    {"needle": needle},
                )
            except Exception:
                clicked = {"found": False, "clicked": False}

            if clicked.get("found"):
                href = str(clicked.get("href") or "")
                direct = canonical_direct(href, group_url)
                if direct:
                    return direct

                if clicked.get("clicked"):
                    temp.wait_for_timeout(1800)
                    # The route may replace the current search page or open a new tab.
                    for candidate_page in reversed(context.pages):
                        if candidate_page in pages_before and candidate_page is not temp:
                            continue
                        try:
                            candidate_page.wait_for_timeout(250)
                        except Exception:
                            pass
                        direct = _direct_from_loaded_page(candidate_page, group_url)
                        if direct:
                            return direct

                    direct = _direct_from_loaded_page(temp, group_url)
                    if direct:
                        return direct

                    # Restore search results before another attempt/scroll.
                    try:
                        temp.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                        temp.wait_for_timeout(2200)
                    except Exception:
                        pass

            if round_no + 1 < max_scrolls:
                try:
                    temp.mouse.wheel(0, 2600)
                    temp.wait_for_timeout(1500)
                except Exception:
                    pass
        return ""
    finally:
        if temp is not None:
            try:
                temp.close()
            except Exception:
                pass


def resolve_on_search_page(page, lead: dict[str, Any], max_scrolls: int = 4) -> str:
    group_url = base._canonical_group_url(str(lead.get("group_url") or ""))
    current = canonical_direct(str(lead.get("url") or ""), group_url)
    if current:
        return current

    search_url = str(lead.get("search_url") or lead.get("url") or "")
    text = base._clean_text(lead.get("text"))
    if not search_url or not text:
        return ""

    try:
        if page.url != search_url:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
    except Exception:
        pass

    for round_no in range(max_scrolls):
        evidence = _collect_matching_evidence(page, text)

        for href in evidence.get("hrefs", []) or []:
            direct = canonical_direct(str(href), group_url)
            if direct:
                return direct

        for blob in evidence.get("html", []) or []:
            direct = _direct_from_blob(str(blob), group_url)
            if direct:
                return direct

        # Some timestamp/share routes only become the real permalink after navigation.
        for href in (evidence.get("time_hrefs", []) or [])[:8]:
            if not href or "facebook.com" not in str(href).casefold():
                continue
            temp = None
            try:
                temp = page.context.new_page()
                temp.goto(str(href), wait_until="domcontentloaded", timeout=30000)
                temp.wait_for_timeout(1200)
                direct = _direct_from_loaded_page(temp, group_url)
                if direct:
                    return direct
            except Exception:
                pass
            finally:
                if temp is not None:
                    try:
                        temp.close()
                    except Exception:
                        pass

        if round_no + 1 < max_scrolls:
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(1600)

    # Last resort: actually click the post's timestamp/date/comment route. This is
    # intentionally done in a disposable page so the scanner's main page stays safe.
    return _resolve_by_clicking_post_route(page.context, search_url, text, group_url, max_scrolls=5)


def resolve_latest_leads(leads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not leads:
        return leads, 0
    from playwright.sync_api import sync_playwright

    resolved = 0
    with sync_playwright() as playwright:
        context = base._launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            base.ensure_facebook_login(page)
            for index, lead in enumerate(leads, start=1):
                group_url = base._canonical_group_url(str(lead.get("group_url") or ""))
                existing = canonical_direct(str(lead.get("url") or ""), group_url)
                if existing:
                    lead["url"] = existing
                    lead["link_quality"] = "DIRECT"
                    resolved += 1
                    print(f"  Link {index}/{len(leads)}: DIRECT (already known)")
                    continue
                direct = resolve_on_search_page(page, lead)
                if direct:
                    lead["url"] = direct
                    lead["link_quality"] = "DIRECT"
                    resolved += 1
                    print(f"  Link {index}/{len(leads)}: DIRECT")
                else:
                    lead["link_quality"] = "UNRESOLVED"
                    print(f"  Link {index}/{len(leads)}: UNRESOLVED")
        finally:
            context.close()
    return leads, resolved
