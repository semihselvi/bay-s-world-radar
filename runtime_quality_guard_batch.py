from __future__ import annotations

import re
from urllib.parse import urlsplit

import runtime_quality_guard as base

# ---------------------------------------------------------------------------
# Shared NC quality additions
# ---------------------------------------------------------------------------

# One-month rentals are short stays for our routing purposes. Keep two-month and
# longer requests unchanged so existing long-term logic is not broadened.
_EXTRA_ONE_MONTH_SHORT_STAY_RE = re.compile(
    r"(?:"
    r"\bна\s+(?:(?:1|один)\s+)?месяц\b|"
    r"\bfor\s+(?:1|one)\s+month\b|"
    r"\b1\s+ayl[ıi][ğg][ıi]na\b"
    r")",
    re.I | re.S,
)
base._SHORT_STAY_DEMAND_RE = re.compile(
    rf"(?:{base._SHORT_STAY_DEMAND_RE.pattern}|{_EXTRA_ONE_MONTH_SHORT_STAY_RE.pattern})",
    re.I | re.S,
)

_NON_PROPERTY_GOODS_RE = re.compile(
    r"(?:"
    r"\bробот[-\s]?пылесос\w*\b|\bпылесос\w*\b|\bшкольн\w*\s+форм\w*\b|"
    r"\bтелефон\w*\b|\bсмартфон\w*\b|\bноутбук\w*\b|\bвелосипед\w*\b|"
    r"\bколяск\w*\b|\bхолодильник\w*\b|\bтелевизор\w*\b|\bмебел\w*\b|"
    r"\brobot\s+vacuum\b|\bschool\s+uniform\b|\bokul\s+formas[ıi]\b|\brobot\s+s[üu]p[üu]rge\b"
    r")",
    re.I | re.S,
)

# Purchase object may be written as a property noun, a unit configuration (1+1),
# or a well-known residential project. This still keeps the object close to the
# purchase verb so Russian "дома" meaning "at home" cannot fake a house purchase.
_RU_PROPERTY_OBJECT = (
    r"(?:недвижимост\w*|квартир\w*|апартамент\w*|вилл\w*|"
    r"дом(?:\b|ом\b|у\b|е\b)|участ\w*|земл\w*|жиль[её]\w*|"
    r"[0-6]\s*\+\s*[0-3]|caesar\s+resort|royal\s+sun(?:\s+elite)?|"
    r"grand\s+sapphire|four\s+seasons|riverside\s+life|isatis|elysium)"
)

_DIRECT_PROPERTY_BUY_RE = re.compile(
    rf"(?:"
    rf"\bкуплю\b.{{0,110}}\b{_RU_PROPERTY_OBJECT}\b|"
    rf"\b(?:хочу|хотим|планирую|планируем|рассматриваю|рассматриваем|думаю|думаем)\b"
    rf".{{0,90}}\b(?:купить|покупк\w*)\b(?:.{{0,100}}\b{_RU_PROPERTY_OBJECT}\b)?|"
    r"\b(?:looking|planning|want(?:ing)?|ready|considering)\b.{0,70}\b(?:buy|buying|purchase)\b|"
    r"\b(?:sat[ıi]n\s+almak\s+istiyorum|sat[ıi]n\s+alaca[ğg][ıi]m|ev\s+almak\s+istiyorum|daire\s+almak\s+istiyorum)\b"
    r")",
    re.I | re.S,
)

# Research-stage users remain eligible when they explicitly place themselves in
# the purchase decision. A generic mention such as "before buying housing" in a
# joke/discussion is not enough.
_ACTIVE_OR_PERSONAL_RESEARCH_BUY_RE = re.compile(
    rf"(?:{_DIRECT_PROPERTY_BUY_RE.pattern}|"
    r"\b(?:я|мы)\b.{0,100}\b(?:стоит\s+ли|можно\s+ли|безопасн\w*\s+ли|как)\b"
    r".{0,100}\b(?:купить|покупк\w*)\b|"
    r"\b(?:can|should|how\s+can)\s+(?:i|we)\b.{0,80}\b(?:buy|purchase)\b|"
    r"\b(?:ben|biz)\b.{0,90}\b(?:sat[ıi]n\s+al|alabilir|almal[ıi])\b"
    r")",
    re.I | re.S,
)


def install_nc_intent_guard() -> None:
    base.install_nc_intent_guard()

    import north_cyprus_intent_classifier as nc

    if getattr(nc, "_bay_s_batch_quality_guard", False):
        return

    original = nc.classify_intent

    def guarded(item):
        own = nc._norm(item.get("text"))

        # An incidental property word must not convert a flea-market purchase
        # into a real-estate lead.
        if _NON_PROPERTY_GOODS_RE.search(own) and not _DIRECT_PROPERTY_BUY_RE.search(own):
            req = nc.extract_requirements(item)
            return nc._result(nc.UNKNOWN, [], 99, ["nonproperty_goods_purchase"], req)

        result = original(item)

        # The base classifier intentionally has a broad Russian purchase noun
        # pattern. For buyer alerts, require personal purchase/research voice so
        # jokes, news commentary and generic "before purchase" discussion do not
        # become fresh buyers.
        if result.get("intent_class") == nc.BUYER and not _ACTIVE_OR_PERSONAL_RESEARCH_BUY_RE.search(own):
            return nc._result(
                nc.UNKNOWN,
                [],
                92,
                ["purchase_mention_without_personal_buyer_voice"],
                result.get("requirements") or nc.extract_requirements(item),
            )
        return result

    nc._bay_s_batch_original_classify_intent = original
    nc.classify_intent = guarded
    nc._bay_s_batch_quality_guard = True


# ---------------------------------------------------------------------------
# Golden South / Expat.com precision additions
# ---------------------------------------------------------------------------

_GOLDEN_EXPAT_TITLE_BUY_RE = re.compile(
    r"(?:"
    r"\blooking\s+to\s+buy\b|\bwant(?:ing)?\s+to\s+buy\b|\bbuying\s+(?:a\s+)?(?:home|house|property|apartment|flat|villa)\b|"
    r"\bpurchas(?:e|ing)\s+(?:a\s+)?(?:home|house|property|apartment|flat|villa)\b|"
    r"\b(?:home|house|property|apartment|flat|villa)\b.{0,40}\b(?:buy|purchase)\b"
    r")",
    re.I | re.S,
)

_GOLDEN_EXPAT_PERSONAL_BUY_RE = re.compile(
    r"(?:"
    r"\b(?:i|we|i'm|we're|i\s+am|we\s+are)\b.{0,90}"
    r"\b(?:want|plan|planning|consider|considering|looking|ready|hope|hoping)\b.{0,80}"
    r"\b(?:buy|buying|purchase|purchasing|acquire|acquiring)\b.{0,120}"
    r"\b(?:property|real\s+estate|apartment|flat|house|villa|home)\b|"
    r"\b(?:i|we)\b.{0,90}\b(?:buy|purchase)\b.{0,100}\b(?:property|apartment|flat|house|villa|home)\b"
    r")",
    re.I | re.S,
)

_base_world_target_rejection = base.world_target_rejection


def world_target_rejection(item: dict) -> str:
    prior = _base_world_target_rejection(item)
    bucket = str(item.get("source_bucket") or "").casefold()
    url = str(item.get("url") or "")

    if "shard_golden_south_direct" not in bucket:
        return prior

    try:
        host = urlsplit(url).netloc.casefold().removeprefix("www.")
    except Exception:
        host = ""
    if "expat.com" not in host:
        return prior

    if prior == "golden_south_commercial_provider":
        return prior

    title = str(item.get("title") or "")
    primary = base._lead_local_primary(item)

    # Expat forum pages append "See also / Buying a property..." and related
    # housing links to unrelated relocation threads. For this source, either the
    # thread title itself must be a purchase request or the user's primary post
    # must contain first-person property-purchase intent.
    if not _GOLDEN_EXPAT_TITLE_BUY_RE.search(title) and not _GOLDEN_EXPAT_PERSONAL_BUY_RE.search(primary):
        return "golden_south_expat_no_personal_property_purchase"

    return prior


def install_world_shard_guard() -> None:
    # base.install_world_shard_guard resolves world_target_rejection from its
    # module globals at runtime, so patch that global before installing it.
    base.world_target_rejection = world_target_rejection
    base.install_world_shard_guard()


canonical_world_url = base.canonical_world_url
