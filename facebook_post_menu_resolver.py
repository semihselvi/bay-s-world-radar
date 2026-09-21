from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import facebook_group_scanner as base
from facebook_post_link_resolver import canonical_direct


def _is_actionable_facebook_link(url: str, group_url: str) -> bool:
    """Accept a copied Facebook post/share URL that opens one exact item.

    Facebook's Copy link action can return a /share/... URL instead of the canonical
    /groups/<id>/posts/<id>/ form. That is still useful because it opens the exact
    post, unlike a group homepage/search page.
    """
    value = str(url or "").strip()
    if not value:
        return False
    try:
        parts = urlsplit(value)
    except Exception:
        return False
    if "facebook.com" not in parts.netloc.casefold():
        return False
    path = (parts.path or "").rstrip("/").casefold()
    query = (parts.query or "").casefold()
    if not path or path in {"", "/", "/groups"}:
        return False
    if "/search" in path or path.endswith("/search"):
        return False
    if path in {"/groups/feed", "/groups/joins"}:
        return False

    direct = canonical_direct(value, group_url)
    if direct:
        return True

    exact_markers = (
        "/share/p/",
        "/share/v/",
        "/share/r/",
        "/permalink/",
        "/posts/",
        "/photo/",
        "/reel/",
        "/videos/",
    )
    if any(marker in path for marker in exact_markers):
        return True
    if any(key in query for key in ("story_fbid=", "post_id=", "fbid=", "multi_permalinks=")):
        return True
    return False


def _find_article_and_click_menu(page, text: str) -> dict[str, Any]:
    needle = base._clean_text(text)[:280]
    if not needle:
        return {"found": False, "clicked": False, "labels": []}
    try:
        return page.evaluate(
            """({needle}) => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const target = norm(needle);
                const prefix = target.slice(0, Math.min(110, target.length));
                const msgSel = '[data-ad-rendering-role="story_message"], [data-ad-preview="message"], [data-ad-comet-preview="message"]';
                let article = null;

                for (const msg of document.querySelectorAll(msgSel)) {
                    const txt = norm(msg.innerText || '');
                    const short = txt.slice(0, Math.min(110, txt.length));
                    if (txt.includes(prefix) || target.includes(short)) {
                        article = msg.closest('div[role="article"]') || msg.parentElement;
                        break;
                    }
                }
                if (!article) {
                    for (const node of document.querySelectorAll('div[role="article"]')) {
                        const txt = norm(node.innerText || '');
                        if (txt.includes(prefix)) {
                            article = node;
                            break;
                        }
                    }
                }
                if (!article) return {found:false, clicked:false, labels:[]};

                const candidates = [];
                const labels = [];
                const rx = /(actions for this post|post actions|more actions|more options|options for this post|bu gönderideki işlemler|bu gonderideki islemler|bu gönderi için eylemler|bu gonderi icin eylemler|diğer seçenekler|diger secenekler|seçenekler|secenekler)/i;
                const reject = /(daha fazlasını gör|daha fazlasini gor|see more|more comments|daha fazla yorum)/i;
                const nodes = article.querySelectorAll('button, [role="button"], [aria-haspopup="menu"]');
                nodes.forEach((el, idx) => {
                    const label = norm([
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('title') || '',
                        el.innerText || ''
                    ].join(' '));
                    if (label) labels.push(label);
                    if (reject.test(label)) return;
                    let score = 0;
                    if (el.getAttribute('aria-haspopup') === 'menu') score += 120;
                    if (rx.test(label)) score += 160;
                    if ((el.innerText || '').trim() === '' && el.querySelector('svg')) score += 18;
                    if (score > 0) candidates.push({el, idx, label, score});
                });
                candidates.sort((a,b) => b.score - a.score);
                if (!candidates.length) return {found:true, clicked:false, labels:[...new Set(labels)].slice(0,40)};
                const best = candidates[0];
                try {
                    best.el.scrollIntoView({block:'center'});
                    best.el.click();
                    return {found:true, clicked:true, label:best.label, labels:[...new Set(labels)].slice(0,40)};
                } catch (e) {
                    return {found:true, clicked:false, label:best.label, labels:[...new Set(labels)].slice(0,40)};
                }
            }""",
            {"needle": needle},
        )
    except Exception:
        return {"found": False, "clicked": False, "labels": []}


def _click_copy_link_menu_item(page) -> tuple[bool, list[str]]:
    try:
        result = page.evaluate(
            """() => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const copyRx = /^(copy link|copy post link|linki kopyala|bağlantıyı kopyala|baglantiyi kopyala)$/i;
                const seen = [];
                const nodes = document.querySelectorAll('[role="menuitem"], [role="menu"] [role="button"], [role="menu"] button, [role="dialog"] [role="button"]');
                for (const el of nodes) {
                    const label = norm([
                        el.innerText || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('title') || ''
                    ].join(' '));
                    if (label) seen.push(label);
                    if (copyRx.test(label)) {
                        try {
                            el.click();
                            return {clicked:true, labels:[...new Set(seen)].slice(0,50)};
                        } catch (e) {}
                    }
                }
                return {clicked:false, labels:[...new Set(seen)].slice(0,50)};
            }"""
        )
        return bool(result.get("clicked")), list(result.get("labels") or [])
    except Exception:
        return False, []


def _read_clipboard(page) -> str:
    try:
        value = page.evaluate("navigator.clipboard.readText()")
        return str(value or "").strip()
    except Exception:
        return ""


def resolve_one_by_copy_menu(context, lead: dict[str, Any], max_scrolls: int = 5) -> str:
    group_url = base._canonical_group_url(str(lead.get("group_url") or ""))
    search_url = str(lead.get("search_url") or lead.get("url") or "")
    text = base._clean_text(lead.get("text"))
    if not group_url or not search_url or not text:
        return ""

    try:
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://www.facebook.com",
        )
    except Exception:
        pass

    page = None
    try:
        page = context.new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        page.wait_for_timeout(2800)

        for round_no in range(max_scrolls):
            menu = _find_article_and_click_menu(page, text)
            if menu.get("found") and menu.get("clicked"):
                page.wait_for_timeout(700)
                clicked_copy, labels = _click_copy_link_menu_item(page)
                if clicked_copy:
                    page.wait_for_timeout(500)
                    copied = _read_clipboard(page)
                    if _is_actionable_facebook_link(copied, group_url):
                        direct = canonical_direct(copied, group_url)
                        return direct or copied
                # Close any menu so another scroll/attempt starts cleanly.
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
            if round_no + 1 < max_scrolls:
                page.mouse.wheel(0, 2600)
                page.wait_for_timeout(1500)
        return ""
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass


def resolve_unresolved_with_copy_menu(leads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    unresolved = [
        lead for lead in leads
        if not canonical_direct(str(lead.get("url") or ""), str(lead.get("group_url") or ""))
        and not _is_actionable_facebook_link(str(lead.get("action_url") or ""), str(lead.get("group_url") or ""))
    ]
    if not unresolved:
        return leads, 0

    from playwright.sync_api import sync_playwright

    resolved = 0
    with sync_playwright() as playwright:
        context = base._launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            base.ensure_facebook_login(page)
            for index, lead in enumerate(unresolved, start=1):
                copied = resolve_one_by_copy_menu(context, lead)
                if copied:
                    direct = canonical_direct(copied, str(lead.get("group_url") or ""))
                    lead["action_url"] = direct or copied
                    lead["link_quality"] = "DIRECT" if direct else "COPIED_POST_LINK"
                    resolved += 1
                    print(f"  Copy-link {index}/{len(unresolved)}: RESOLVED")
                else:
                    print(f"  Copy-link {index}/{len(unresolved)}: UNRESOLVED")
        finally:
            context.close()
    return leads, resolved
