from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


# ---------------------------------------------------------------------------
# North Cyprus intent quality guard
# ---------------------------------------------------------------------------

# Listing-style Russian rental ads often start with "АРЕНДА" / "Долгосрочная
# аренда" and then give a concrete property plus a price. Currency is commonly
# written either before or after the amount ("€550" / "550€"). The separate
# demand guard below prevents a genuine "Ищу ... аренду" request from being
# treated as supply.
_RENTAL_LISTING_RE = re.compile(
    r"(?:"
    r"(?:^|\s)(?:долгосрочн\w*\s+)?аренд\w*\b.{0,320}"
    r"(?:[€£$]\s*\d[\d\s,.]*|\d[\d\s,.]*\s*[€£$])|"
    r"(?:[€£$]\s*\d[\d\s,.]*|\d[\d\s,.]*\s*[€£$]).{0,180}"
    r"(?:\bпосуточн\w*\b|/\s*мес\b|\bмесяц\b|\bсутк\w*\b|"
    r"\bсвободн\w*\b|\bдоступн\w*\b).{0,180}\b(?:аренд\w*|долгосрок\w*)\b"
    r")",
    re.I | re.S,
)

# Some supply ads do not contain a price at all. A post that literally opens as
# "Аренда <property>" and has no renter-demand verb is still inventory/supply.
# This exact pattern caused a reviewed false positive for Four Seasons.
_RENTAL_SUPPLY_STYLE_RE = re.compile(
    r"^\s*(?:(?:долгосрочн\w*|посуточн\w*)\s+)?аренд\w*\b",
    re.I | re.S,
)

_RENTAL_DEMAND_RE = re.compile(
    r"(?:"
    r"\bищу\b|\bищем\b|\bхочу\s+снять\b|\bхотим\s+снять\b|\bсниму\b|\bснимем\b|"
    r"\blooking\s+to\s+rent\b|\blooking\s+for\b|\bwant(?:ing)?\s+to\s+rent\b|\bneed\b|"
    r"\bar[ıi]yorum\b|\bkiralamak\s+istiyorum\b|\bkiralamak\s+istiyoruz\b"
    r")",
    re.I | re.S,
)

_SHORT_STAY_DEMAND_RE = re.compile(
    r"(?:"
    r"\bна\s+\d+\s+(?:день|дня|дней|сутки|суток|ночь|ночи|ночей|недел\w*)\b|"
    r"\bна\s+сутки\b|\bна\s+один\s+день\b|\bпосуточн\w*\b|"
    r"\bс\s+\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\s+по\s+\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b|"
    r"\bfor\s+\d+\s+(?:day|days|night|nights|week|weeks)\b|"
    r"\bfor\s+one\s+(?:day|night|week)\b|\bshort[\s-]?term\b|"
    r"\b1\s+g[üu]nl[üu][ğg][üu]ne\b|\b\d+\s+g[üu]n(?:l[üu][ğg][üu]ne)?\b"
    r")",
    re.I | re.S,
)

_POST_PURCHASE_RE = re.compile(
    r"(?:"
    r"\bполучил(?:а|и)?\s+разрешени\w*\s+на\s+покупк\w*\b|"
    r"\bразрешени\w*\s+на\s+покупк\w*\s+(?:уже\s+)?получен\w*\b|"
    r"\bтитул\w*\s+(?:еще|ещё\s+)?не\s+готов\w*\b|\bжд[её]м\s+титул\w*\b|\bжду\s+титул\w*\b|"
    r"\bпошл[аи]\s+в\s+tapu\b|\bпошли\s+в\s+тапу\b|"
    r"\balready\s+(?:bought|purchased)\b|\bwaiting\s+for\s+(?:the\s+)?(?:title|deed)\b|"
    r"\bsat[ıi]n\s+alma\s+izn(?:i|ini)\s+ald[ıi][mk]\b|\bko[çc]an\s+bekliyorum\b|\btapu\s+bekliyorum\b"
    r")",
    re.I | re.S,
)

_ACTIVE_NEW_BUY_RE = re.compile(
    r"(?:"
    r"\bкуплю\b|\bхочу\s+купить\b|\bхотим\s+купить\b|\bищу\b.{0,90}\b(?:для\s+покупки|на\s+покупку|купить)\b|"
    r"\blooking\s+to\s+buy\b|\bwant(?:ing)?\s+to\s+buy\b|\bplanning\s+to\s+buy\b|\bready\s+to\s+buy\b|"
    r"\bsat[ıi]n\s+almak\s+istiyorum\b|\bsat[ıi]n\s+alaca[ğg][ıi]m\b"
    r")",
    re.I | re.S,
)


def install_nc_intent_guard() -> None:
    """Patch the shared NC direction classifier before Catcher/Recovery import it."""
    import north_cyprus_intent_classifier as nc

    if getattr(nc, "_bay_s_runtime_quality_guard", False):
        return

    original = nc.classify_intent

    def guarded(item):
        own = nc._norm(item.get("text"))
        context = nc._norm(
            " ".join(str(item.get(k, "")) for k in ("text", "reply_context", "telegram_chat", "title"))
        )
        req = nc.extract_requirements(item)
        property_signal = nc._matches(context, nc.PROPERTY_PATTERNS)
        nc_signal = nc._matches(context, nc.NC_PATTERNS)

        # A customer who already has purchase permission / is waiting for title
        # is after-sale/legal help, not a fresh buyer lead. A new explicit buy
        # request in the same message still wins.
        if _POST_PURCHASE_RE.search(own) and not _ACTIVE_NEW_BUY_RE.search(own):
            return nc._result(
                nc.UNKNOWN,
                [],
                94,
                ["existing_purchase_after_sale"],
                req,
            )

        # Listing-style rental copy can contain "долгосрочная аренда" and used
        # to look like tenant intent. Price/listing wording with no demand verb
        # is supply and must be routed away from buyer/tenant alerts.
        if (
            property_signal
            and (_RENTAL_LISTING_RE.search(own) or _RENTAL_SUPPLY_STYLE_RE.search(own))
            and not _RENTAL_DEMAND_RE.search(own)
        ):
            return nc._result(
                nc.OWNER,
                [],
                95,
                ["rental_listing_supply"],
                req,
            )

        # Explicit short-stay demand such as "Ищу дом ... на 1 день" or a
        # concrete date range is rental, not ambiguous purchase demand.
        if (
            property_signal
            and nc_signal
            and _RENTAL_DEMAND_RE.search(own)
            and _SHORT_STAY_DEMAND_RE.search(own)
            and not _ACTIVE_NEW_BUY_RE.search(own)
        ):
            prefs = list(req.get("preferences") or [])
            if "SHORT_TERM" not in prefs:
                prefs.append("SHORT_TERM")
            req["preferences"] = prefs
            return nc._result(
                nc.TENANT,
                ["SHORT_TERM_TENANT"],
                92,
                ["explicit_short_stay_demand", "property_context", "north_cyprus_context"],
                req,
            )

        return original(item)

    nc._bay_s_original_classify_intent = original
    nc.classify_intent = guarded
    nc._bay_s_runtime_quality_guard = True


# ---------------------------------------------------------------------------
# WORLD shard quality guard
# ---------------------------------------------------------------------------

_NC_TARGET_RE = re.compile(
    r"(?:"
    r"\bnorth(?:ern)?\s+cyprus\b|\btrnc\b|\bkktc\b|\bkuzey\s+k[ıi]br[ıi]s\b|\bnordzypern\b|"
    r"\bсеверн\w*\s+кипр\w*\b|\bkyrenia\b|\bgirne\b|\biskele\b|\bİskele\b|\bискел\w*\b|"
    r"\blong\s+beach\b|\bfamagust\w*\b|\bgazima[ğg]usa\b|\besentepe\b|\bbafra\b|"
    r"\bcaesar\s+resort\b|\bgrand\s+sapphire\b|\broyal\s+sun\b|\bisatis\b|\belysium\b"
    r")",
    re.I,
)

_GOLDEN_PROPERTY_BUY_RE = re.compile(
    r"(?:"
    r"\b(?:buy|buying|purchase|purchasing|acquire|acquiring)\b.{0,110}\b(?:property|real\s+estate|apartment|flat|house|villa|home)\b|"
    r"\b(?:property|real\s+estate|apartment|flat|house|villa|home)\b.{0,110}\b(?:buy|buying|purchase|purchasing|acquire|acquiring)\b|"
    r"\b(?:comprare|acquistare)\b.{0,100}\b(?:casa|appartamento|immobile|propriet[àa])\b|"
    r"\bcomprar\b.{0,100}\b(?:casa|apartamento|vivienda|inmueble|im[oó]vel)\b|"
    r"\bacheter\b.{0,100}\b(?:maison|appartement|bien\s+immobilier)\b|"
    r"\bkaufen\b.{0,100}\b(?:immobilie|wohnung|haus)\b|"
    r"\bкупить\b.{0,100}\b(?:недвижимост\w*|квартир\w*|дом\w*|вилл\w*)\b|"
    r"\b(?:golden\s+visa|residen(?:ce|cy)\s+by\s+investment)\b.{0,180}\b(?:property|real\s+estate|house|apartment|villa|purchase|buy)\b"
    r")",
    re.I | re.S,
)

_COMMERCIAL_PROVIDER_RE = re.compile(
    r"(?:"
    r"\brelocation\s+(?:group|company|agency|service|services)\b|\breal\s+estate\s+(?:agency|agent)\b|"
    r"\brealtor\b|\bproperty\s+(?:agency|consultant|advisor)\b|\blaw\s+firm\b|"
    r"\bimmigration\s+(?:agency|consultant|company)\b"
    r")",
    re.I,
)

# Forum pages mix the user's post with site-generated recommendation modules.
# Those modules contain phrases such as "Buying a property in Italy" and were
# being mistaken for the user's own purchase intent. Only the thread-local text
# before those modules is allowed to qualify a WORLD lead.
_FORUM_BOILERPLATE_MARKERS = (
    "see also",
    "looking for your dream home",
    "essential services for your expat journey",
    "other discussions on housing",
    "articles to help you in your expat project",
    "find more topics on the",
    "further reading",
)


def _lead_local_primary(item: dict) -> str:
    title = str(item.get("title") or "")
    body = str(item.get("text") or "")
    folded = body.casefold()
    cut = len(body)
    for marker in _FORUM_BOILERPLATE_MARKERS:
        idx = folded.find(marker)
        # Avoid clipping a genuine very short user sentence that happens to use
        # the words "see also". Forum modules occur after navigation/post text.
        if idx >= 250:
            cut = min(cut, idx)
    body = body[:cut][:1800]
    return f"{title}. {body}"


def canonical_world_url(url: str) -> str:
    """Collapse forum post anchors so one thread cannot notify twice."""
    raw = str(url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw
    host = parsed.netloc.casefold().removeprefix("www.")
    # Expat and other forum index pages commonly surface both the thread URL and
    # the same thread with #post-id. Fragment identity is not a separate lead.
    if parsed.fragment and (
        "expat.com" in host
        or "moneysavingexpert.com" in host
        or "/forum/" in parsed.path.casefold()
        or "/discussion/" in parsed.path.casefold()
    ):
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
    return raw


def world_target_rejection(item: dict) -> str:
    bucket = str(item.get("source_bucket") or "").casefold()
    title = str(item.get("title") or "")
    author = str(item.get("author") or "")
    primary = _lead_local_primary(item)

    if "shard_north_cyprus_cis_" in bucket:
        if not _NC_TARGET_RE.search(primary):
            return "north_cyprus_cis_off_target"

    if "shard_golden_south_" in bucket:
        if _COMMERCIAL_PROVIDER_RE.search(f"{title} {author}"):
            return "golden_south_commercial_provider"
        if not _GOLDEN_PROPERTY_BUY_RE.search(primary):
            return "golden_south_no_property_purchase"

    return ""


def install_world_shard_guard() -> None:
    """Patch WORLD shard filtering/dedupe before shard_runner is imported."""
    import main

    if getattr(main, "_bay_s_world_runtime_quality_guard", False):
        return

    original_keep = main.keep_candidate
    original_dedupe = main.dedupe_key

    def guarded_keep(item, cutoff):
        keep, reason = original_keep(item, cutoff)
        if not keep:
            return keep, reason
        reject = world_target_rejection(item)
        if reject:
            return False, reject
        return True, reason

    def guarded_dedupe(item):
        url = str(item.get("url") or "")
        canonical = canonical_world_url(url)
        if canonical == url:
            return original_dedupe(item)
        clone = dict(item)
        clone["url"] = canonical
        return original_dedupe(clone)

    main._bay_s_original_keep_candidate = original_keep
    main._bay_s_original_dedupe_key = original_dedupe
    main.keep_candidate = guarded_keep
    main.dedupe_key = guarded_dedupe
    main._bay_s_world_runtime_quality_guard = True