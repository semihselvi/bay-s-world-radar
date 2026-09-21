from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

import facebook_group_scanner as base


ROOT = Path(__file__).resolve().parent
LEADS = ROOT / "facebook_demand_leads_latest.json"


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip().lower()


def main() -> int:
    if not LEADS.exists():
        print("No facebook_demand_leads_latest.json found.")
        return 1

    leads = json.loads(LEADS.read_text(encoding="utf-8"))
    unresolved = [x for x in leads if str(x.get("link_quality") or "").upper() != "DIRECT"]
    if not unresolved:
        print("No unresolved leads found.")
        return 0

    # Prefer the known short Magusa example if present because it is easy to match.
    lead = None
    for item in unresolved:
        txt = _norm(str(item.get("text") or ""))
        if "mağusada sahibinden kiralık daire arıyorum aylık ödemeli" in txt:
            lead = item
            break
    lead = lead or unresolved[0]

    search_url = str(lead.get("search_url") or lead.get("url") or "")
    text = base._clean_text(lead.get("text"))
    print("DEBUG LEAD:", text[:220])
    print("SEARCH URL:", search_url)

    with sync_playwright() as pw:
        context = base._launch_context(pw, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            base.ensure_facebook_login(page)
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            page.wait_for_timeout(3000)

            found = False
            for round_no in range(5):
                info = page.evaluate(
                    """({needle}) => {
                        const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        const target = norm(needle);
                        const prefix = target.slice(0, Math.min(95, target.length));
                        const msgSel = '[data-ad-rendering-role="story_message"], [data-ad-preview="message"], [data-ad-comet-preview="message"]';
                        let msg = null;
                        for (const el of document.querySelectorAll(msgSel)) {
                            const t = norm(el.innerText || '');
                            if (t.includes(prefix) || target.includes(t.slice(0, Math.min(95, t.length)))) { msg = el; break; }
                        }
                        if (!msg) return {found:false};
                        const article = msg.closest('div[role="article"]') || msg.parentElement;
                        if (!article) return {found:false};
                        const ar = article.getBoundingClientRect();
                        const buttons = [];
                        let i = 0;
                        for (const el of article.querySelectorAll('button,[role="button"],[aria-haspopup="menu"]')) {
                            const r = el.getBoundingClientRect();
                            const label = norm([el.getAttribute('aria-label')||'', el.getAttribute('title')||'', el.innerText||''].join(' '));
                            buttons.push({
                                i:i++, label, tag:el.tagName, popup:el.getAttribute('aria-haspopup')||'',
                                svg:!!el.querySelector('svg'), x:Math.round(r.x), y:Math.round(r.y),
                                w:Math.round(r.width), h:Math.round(r.height),
                                relx:Math.round(r.x-ar.x), rely:Math.round(r.y-ar.y)
                            });
                        }
                        return {found:true, article:{x:Math.round(ar.x),y:Math.round(ar.y),w:Math.round(ar.width),h:Math.round(ar.height)}, buttons};
                    }""",
                    {"needle": text[:260]},
                )
                if info.get("found"):
                    found = True
                    print("POST_CARD_FOUND")
                    print("ARTICLE", info.get("article"))
                    buttons = info.get("buttons") or []
                    print(f"BUTTON_COUNT={len(buttons)}")
                    for b in buttons[:40]:
                        print(f"BTN {b['i']:02d} rel=({b['relx']},{b['rely']}) size={b['w']}x{b['h']} popup={b['popup']!r} svg={b['svg']} label={b['label']!r}")

                    # Click only the most likely top-right menu button. Do not click Like/Comment/Share.
                    result = page.evaluate(
                        """({needle}) => {
                            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                            const target = norm(needle); const prefix = target.slice(0,Math.min(95,target.length));
                            const msgSel='[data-ad-rendering-role="story_message"],[data-ad-preview="message"],[data-ad-comet-preview="message"]';
                            let msg=null; for(const el of document.querySelectorAll(msgSel)){const t=norm(el.innerText||''); if(t.includes(prefix)||target.includes(t.slice(0,Math.min(95,t.length)))){msg=el;break;}}
                            if(!msg) return {clicked:false,why:'no-msg'};
                            const article=msg.closest('div[role="article"]')||msg.parentElement; if(!article) return {clicked:false,why:'no-article'};
                            const ar=article.getBoundingClientRect();
                            const reject=/(like|beğen|begen|comment|yorum|share|paylaş|paylas|reply|yanıt|yanit|see more|daha fazlas)/i;
                            const c=[];
                            for(const el of article.querySelectorAll('button,[role="button"],[aria-haspopup="menu"]')){
                                const r=el.getBoundingClientRect(); const label=norm([el.getAttribute('aria-label')||'',el.getAttribute('title')||'',el.innerText||''].join(' '));
                                if(reject.test(label)) continue;
                                const relx=r.x-ar.x, rely=r.y-ar.y;
                                let score=0;
                                if(el.getAttribute('aria-haspopup')==='menu') score+=200;
                                if(/more|options|actions|seçenek|secenek|işlem|islem/.test(label)) score+=180;
                                if(relx>ar.width*0.55 && rely<ar.height*0.28) score+=80;
                                if(el.querySelector('svg') && !label) score+=20;
                                if(r.width>0 && r.width<=60 && r.height>0 && r.height<=60) score+=15;
                                if(score>0) c.push({el,score,label,relx,rely});
                            }
                            c.sort((a,b)=>b.score-a.score || b.relx-a.relx);
                            if(!c.length) return {clicked:false,why:'no-candidate'};
                            const best=c[0]; best.el.scrollIntoView({block:'center'}); best.el.click();
                            return {clicked:true,score:best.score,label:best.label,relx:Math.round(best.relx),rely:Math.round(best.rely)};
                        }""",
                        {"needle": text[:260]},
                    )
                    print("MENU_CANDIDATE_CLICK", result)
                    page.wait_for_timeout(900)
                    menu = page.evaluate(
                        """() => {
                            const norm=(s)=>(s||'').replace(/\s+/g,' ').trim();
                            const out=[];
                            for(const el of document.querySelectorAll('[role="menuitem"],[role="menu"] [role="button"],[role="menu"] button,[role="dialog"] [role="button"]')){
                                const label=norm([el.innerText||'',el.getAttribute('aria-label')||'',el.getAttribute('title')||''].join(' '));
                                if(label) out.push(label);
                            }
                            return [...new Set(out)].slice(0,80);
                        }"""
                    )
                    print("MENU_LABELS_BEGIN")
                    for x in menu:
                        print("MENU:", x)
                    print("MENU_LABELS_END")
                    try: page.keyboard.press("Escape")
                    except Exception: pass
                    break
                page.mouse.wheel(0, 2600)
                page.wait_for_timeout(1500)

            if not found:
                print("POST_CARD_NOT_FOUND")
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
