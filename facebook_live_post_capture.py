from __future__ import annotations

from typing import Any

import facebook_group_scanner as base
from facebook_post_link_resolver import canonical_direct
from facebook_post_menu_resolver import (
    _click_copy_link_menu_item,
    _find_article_and_click_menu,
    _is_actionable_facebook_link,
    _read_clipboard,
)


def resolve_live_post_link(page, post: dict[str, Any], group: dict[str, Any]) -> str:
    """Resolve the exact post link while the matching Facebook result card is still visible.

    Re-opening a group search later is unreliable because Facebook can reorder or omit
    results. This resolver runs immediately during the scan, against the exact result
    card that produced the lead, and uses the card menu's Copy link action when the
    normal permalink is not exposed in the DOM.
    """
    group_url = base._canonical_group_url(str(group.get("url") or post.get("group_url") or ""))
    current = canonical_direct(str(post.get("url") or ""), group_url)
    if current:
        return current

    text = base._clean_text(post.get("text"))
    if not group_url or not text:
        return ""

    try:
        page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://www.facebook.com",
        )
    except Exception:
        pass

    try:
        # Clear stale clipboard content so we never mistake an old copied URL for
        # the current lead's post URL.
        try:
            page.evaluate("navigator.clipboard.writeText('')")
        except Exception:
            pass

        menu = _find_article_and_click_menu(page, text)
        if not (menu.get("found") and menu.get("clicked")):
            return ""

        page.wait_for_timeout(650)
        clicked_copy, _labels = _click_copy_link_menu_item(page)
        if not clicked_copy:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return ""

        page.wait_for_timeout(450)
        copied = _read_clipboard(page)
        if not _is_actionable_facebook_link(copied, group_url):
            return ""

        return canonical_direct(copied, group_url) or copied
    except Exception:
        return ""
    finally:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
