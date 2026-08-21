import re
from urllib.parse import urlparse

import main
import world_engine

# High-recall rules for North Cyprus. We still require a fresh public/user
# discussion and reject obvious agents, listings and rentals.
ALLOWED_USER_DOMAINS = {
    "reddit.com", "expat.com", "expatforum.com", "kibkomnorthcyprusforum.com",
    "britishexpats.com", "tripadvisor.com", "facebook.com", "t.me",
    "telegid.me", "tlgrm.ru", "turkishliving.com",
}

NC_SOURCE_HINTS = (
    "northcyprus", "northerncyprus", "snchubtalkroom", "searchnorthcyprus",
    "meetinnorthcyprus", "cyprusy",
)

NC_LOCATION_PATTERNS = [
    r"\bnorth(?:ern)? cyprus\b", r"\btrnc\b", r"\bkuzey k[ıi]br[ıi]s\b",
    r"\bnordzypern\b", r"\bсеверн(?:ый|ого)\s+кипр\b", r"\b[İi]skele\b",
    r"\blong beach\b", r"\bgirne\b", r"\bkyrenia\b", r"\besentepe\b",
    r"\blapta\b", r"\bfamagusta\b", r"\bgazima[ğg]usa\b",
    r"\byenibo[ğg]azi[çc]i\b", r"\btatl[ıi]su\b", r"\bbafra\b",
    r"\bbah[çc]eli\b", r"\bk[üu][çc][üu]k erenk[öo]y\b", r"\b[çc]atalk[öo]y\b",
    r"\balsancak\b", r"\bkar[şs][ıi]yaka\b", r"\bbellapais\b",
    r"\bbeylerbeyi\b", r"\bozank[öo]y\b", r"\blefke\b", r"\bg[üu]zelyurt\b",
    r"\bbo[ğg]az\b",
]

PROPERTY_PATTERNS = [
    r"\bproperty\b", r"\bhouse\b", r"\bhome\b", r"\bflat\b", r"\bapartment\b",
    r"\bvilla\b", r"\btownhouse\b", r"\bland\b", r"\bplot\b",
    r"\bev\b", r"\bdaire\b", r"\barsa\b", r"\bgayrimenkul\b",
    r"\bквартир", r"\bапартамент", r"\bдом\b", r"\bвилл", r"\bнедвижимост",
    r"\bwohnung\b", r"\bhaus\b", r"\bimmobil", r"\bmaison\b",
    r"\bappartement\b", r"\bbien immobilier\b", r"\bhuis\b", r"\bwoning\b",
    r"\bvastgoed\b", r"خانه", r"آپارتمان", r"ویلا", r"ملک",
]

STRONG_BUYER_PATTERNS = [
    r"\blooking to buy\b", r"\bwant(?:ing)? to buy\b", r"\bplanning to buy\b",
    r"\bready to buy\b", r"\btrying to buy\b", r"\bconsidering buying\b",
    r"\bthinking (?:about|of) buying\b", r"\bhouse hunting\b",
    r"\blooking for (?:a |an )?(?:house|home|flat|apartment|villa|property) to buy\b",
    r"\bmake an offer\b", r"\bput in an offer\b", r"\bcash buyer\b",
    r"\bev almak istiyorum\b", r"\bdaire almak istiyorum\b", r"\bvilla almak istiyorum\b",
    r"\bsat[ıi]n almak istiyorum\b", r"\bev ar[ıi]yorum\b", r"\bdaire ar[ıi]yorum\b",
    r"\bvilla ar[ıi]yorum\b", r"\bgayrimenkul almak\b",
    r"\byat[ıi]r[ıi]m i[çc]in (?:ev|daire|gayrimenkul)\b",
    r"\bхочу купить\b", r"\bхотим купить\b", r"\bищу квартиру\b",
    r"\bищу апартамент", r"\bищу дом\b", r"\bищу виллу\b",
    r"\bищу недвижимость\b", r"\bкуплю недвижимость\b", r"\bпланирую купить\b",
    r"\bготов(?:а|ы)? купить\b", r"\bich m[öo]chte .* kaufen\b",
    r"\bwir m[öo]chten .* kaufen\b", r"\bich will .* kaufen\b",
    r"\bwohnung kaufen\b", r"\bhaus kaufen\b", r"\bimmobilie kaufen\b",
    r"\bvilla kaufen\b", r"\bsuche .* zum kauf\b", r"\bje veux acheter\b",
    r"\bnous voulons acheter\b", r"\bacheter (?:une |un )?(?:maison|appartement|bien immobilier)\b",
    r"\bik wil .* kopen\b", r"\bwij willen .* kopen\b", r"\bhuis kopen\b",
    r"\bwoning kopen\b", r"\bvastgoed kopen\b", r"می ?خواهم .* بخرم",
    r"قصد خرید", r"دنبال خرید", r"خرید ملک",
]

EARLY_BUYER_PATTERNS = [
    r"\bmoving to\b", r"\brelocating to\b", r"\bplanning to move\b",
    r"\bsecond home\b", r"\bholiday home\b", r"\bretirement home\b",
    r"\bwhere should (?:i|we) buy\b", r"\bwhich area should (?:i|we) buy\b",
    r"\bcan anyone recommend .* (?:property|house|apartment|villa)\b",
    r"\bwhere can (?:i|we) find .* (?:property|house|apartment|villa)\b",
    r"\bk[ıi]br[ıi]s'?a ta[şs][ıi]n", r"\bhangi b[öo]lgede ev al",
    r"\bпереезд\b", r"\bпереезжа", r"\bкуда лучше купить\b",
    r"\bnach nordzypern ziehen\b", r"\bauswandern nach nordzypern\b",
]

PERSONAL_PATTERNS = [
    r"\bI\b", r"\bI'm\b", r"\bI am\b", r"\bmy\b", r"\bwe\b", r"\bwe're\b",
    r"\bwe are\b", r"\bour\b", r"\bben\b", r"\bbiz\b", r"\bbenim\b", r"\bbizim\b",
    r"\bя\b", r"\bмы\b", r"\bмой\b", r"\bнаш\b", r"\bхочу\b", r"\bищу\b",
    r"\bich\b", r"\bwir\b", r"\bmein", r"\bunser", r"\bje\b", r"\bnous\b",
    r"\bmon\b", r"\bnotre\b", r"\bik\b", r"\bwij\b", r"\bmijn\b", r"\bons\b",
    r"من", r"ما", r"\banyone\b", r"\bcan anyone\b", r"\bdoes anyone\b",
]

CONCRETE_PATTERNS = [
    r"(?:€|£|\$|₺|₽)\s?\d[\d,.\s]*(?:k|m)?", r"\b\d{2,3}\s?[km]\b",
    r"\bbudget\b", r"\bb[üu]t[çc]e\b", r"\bбюджет\b", r"\bdeposit\b",
    r"\bmortgage\b", r"\bviewing\b", r"\boffer\b", r"\blawyer\b",
    r"\btitle deed\b", r"\bpayment plan\b", r"\bcompletion\b", r"\bcash\b",
    r"\bипотек", r"\bвзнос\b", r"\bnakit\b", r"\bkapora\b", r"\bko[çc]an\b",
    r"\bkaufpreis\b", r"\beigenkapital\b", r"\bfinanzierung\b",
]

SELLER_PATTERNS = [
    "contact us", "call us", "whatsapp us", "dm for details", "our properties",
    "our projects", "estate agent", "real estate agency", "realtor", "broker",
    "developer", "available units", "new project", "we sell", "commission",
    "for sale", "satılık", "satilik", "продается", "продам", "агентство",
    "застройщик", "риэлтор", "immobilienmakler", "makler", "jetzt verfügbar",
    "برای مشاوره", "تماس بگیرید",
]

RENTAL_PATTERNS = [
    "for rent", "to rent", "rental wanted", "kiralık", "kiralik", "сдам",
    "сдается", "аренда", "mieten", "zur miete", "à louer", "te huur", "اجاره",
]


def _text(item):
    return " ".join(str(item.get(k, "")) for k in ("title", "text", "author", "telegram_chat")).strip()


def _domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _matches(text, patterns):
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _count(text, patterns):
    return sum(1 for pattern in patterns if re.search(pattern, text, re.I))


def _allowed_source(item):
    domain = _domain(item.get("url", ""))
    return any(domain == x or domain.endswith("." + x) for x in ALLOWED_USER_DOMAINS)


def _nc_context(item, text):
    low = f"{item.get('url','')} {item.get('title','')} {item.get('source_bucket','')} {text}".lower()
    normalized = low.replace("_", "").replace("-", "")
    if any(hint.replace("_", "").replace("-", "") in normalized for hint in NC_SOURCE_HINTS):
        return True
    return _matches(text, NC_LOCATION_PATTERNS)


def keep_candidate(item, cutoff):
    if not item.get("url") or not _allowed_source(item):
        return False, "non_user_source"

    published = world_engine.resolved_published(item)
    if published is None:
        return False, "date_unverified"
    if published < cutoff:
        return False, "older_than_24h"

    text = _text(item)
    if not _nc_context(item, text):
        return False, "not_north_cyprus"
    if _matches(text, RENTAL_PATTERNS):
        return False, "negative_or_rental"

    seller_hits = sum(1 for phrase in SELLER_PATTERNS if phrase.lower() in text.lower())
    strong = _matches(text, STRONG_BUYER_PATTERNS)
    early = _matches(text, EARLY_BUYER_PATTERNS)
    personal = _matches(text, PERSONAL_PATTERNS)
    prop = _matches(text, PROPERTY_PATTERNS)

    if seller_hits >= 2 and not (strong and personal):
        return False, "seller_agent"
    if not prop:
        return False, "no_buyer_intent"
    if not personal:
        return False, "not_enough_user_discussion_signal"
    if not strong and not early:
        return False, "no_buyer_intent"
    return True, "candidate"


def buyer_scores(item):
    text = _text(item)
    strong_hits = _count(text, STRONG_BUYER_PATTERNS)
    early_hits = _count(text, EARLY_BUYER_PATTERNS)
    concrete_hits = _count(text, CONCRETE_PATTERNS)
    property_hits = _count(text, PROPERTY_PATTERNS)
    personal = _matches(text, PERSONAL_PATTERNS)
    strong = strong_hits > 0
    early = early_hits > 0
    concrete = concrete_hits > 0

    intent = 60 + min(22, strong_hits * 10) + min(10, early_hits * 5) + min(8, concrete_hits * 4)
    credibility = 62 + (8 if item.get("author") else 0) + min(12, main.discussion_likelihood(item) * 2) + (6 if concrete else 0)
    fit = 88 if _nc_context(item, text) else 70

    intent = min(100, intent)
    credibility = min(100, credibility)
    fit = min(100, fit)

    if strong and concrete and personal and intent >= 82 and credibility >= 70:
        label = "HOT"
    elif personal and (strong or early) and property_hits >= 1 and intent >= 65:
        # Early-stage genuine North Cyprus buyers are useful even without a posted budget.
        label = "WARM"
    else:
        label = "REVIEW"
    return intent, credibility, fit, label
