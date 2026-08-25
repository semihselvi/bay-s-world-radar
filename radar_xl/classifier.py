from __future__ import annotations

import re

from radar_xl.models import Candidate, ClassifiedCandidate


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


PROPERTY_CONTEXT = [
    "property", "real estate", "apartment", "flat", "villa", "house", "studio", "penthouse",
    "daire", "ev", "villa", "konut", "gayrimenkul", "stüdyo", "rezidans",
    "квартира", "вилла", "дом", "недвижимость", "студия", "апартаменты",
]

NC_CONTEXT = [
    "north cyprus", "northern cyprus", "trnc", "kktc", "iskele", "iskеле", "long beach",
    "kyrenia", "famagusta", "gazimagusa", "gazimağusa", "yenibogazici", "yeniboğaziçi", "bogaz", "boğaz", "otuken", "ötüken",
    "kuzey kıbrıs", "kuzey kibris", "iskele", "girne", "mağusa", "magusa",
    "северный кипр", "искеле", "лонг бич", "кирения", "фамагуста", "боаз", "отюкен", "ени богазичи",
]

EXPLICIT_BUY = [
    "looking to buy", "want to buy", "wanting to buy", "ready to buy", "need to buy", "buying a property",
    "buy an apartment", "buy a villa", "purchase a property", "purchase an apartment", "purchase a villa",
    "ev almak istiyorum", "daire almak istiyorum", "satın almak istiyorum", "satın alacağım", "satın almayı düşünüyorum",
    "daire arıyorum", "villa arıyorum", "ev arıyorum", "yatırım için daire arıyorum", "almak için arıyorum",
    "хочу купить", "куплю", "ищу квартиру", "ищу виллу", "ищу дом", "ищу на покупку", "готов купить", "хотим купить",
]

RELOCATION_INTENT = [
    "moving to north cyprus", "move to north cyprus", "relocating to north cyprus", "relocate to north cyprus",
    "moving to cyprus", "relocating to cyprus", "planning to move", "planning to relocate",
    "kuzey kıbrıs'a taşın", "kuzey kibrisa taşın", "kıbrıs'a taşın", "kibrisa taşın", "yerleşmek istiyorum",
    "переезжаю на северный кипр", "переехать на северный кипр", "планирую переезд", "хочу переехать",
]

INVESTMENT_INTENT = [
    "investment property", "looking for investment property", "property investment", "invest in north cyprus",
    "yatırım için", "yatırımlık daire", "gayrimenkul yatırımı",
    "для инвестиций", "инвестиционная недвижимость", "инвестировать в недвижимость",
]

OWNER_DIRECT = [
    "owner only", "direct from owner", "from owner", "no agents", "without agents",
    "sahibinden", "emlakçı olmadan", "komisyonsuz",
    "от собственника", "без агентов", "без риелторов", "напрямую от собственника",
]

BUDGET_SIGNALS = [
    r"(?:£|€|\$)\s?\d[\d,.\s]*(?:k|m)?",
    r"\b\d{2,3}\s?(?:k|thousand)\b",
    r"\bбюджет\b",
    r"\bbudget\b",
    r"\bbütçe\b",
]

TRANSACTION_SIGNALS = [
    "payment plan", "down payment", "deposit", "mortgage", "viewing", "reservation", "title deed", "lawyer",
    "ödeme planı", "peşinat", "taksit", "kapora", "tapu", "koçan", "kocan",
    "рассрочка", "первоначальный взнос", "депозит", "ипотека", "просмотр", "титул", "оформление",
]

AGENT_SIGNALS = [
    "realtor", "real estate agent", "property consultant", "property advisor", "sales consultant", "broker",
    "emlakçı", "emlakci", "gayrimenkul danışmanı", "gayrimenkul danismani", "satış danışmanı", "satis danismani",
    "риелтор", "риэлтор", "агент по недвижимости", "брокер", "консультант по недвижимости",
]

SELLER_AD_SIGNALS = [
    "for sale", "now for sale", "available for sale", "starting from", "prices from", "contact us", "dm for details",
    "satılık", "satilik", "satışta", "fiyatı", "fiyati", "detay için", "bilgi için", "iletişim",
    "продается", "продаю", "в продаже", "цена от", "пишите в личку", "подробности в лс", "звоните",
]

RENTAL_SIGNALS = [
    "for rent", "renting", "long term rent", "daily rent", "kiralık", "kiralik", "günlük kiralık", "gunluk kiralik",
    "сдается", "сдам", "аренда", "подселение", "на подселение",
]

JOB_SPAM = [
    "we are hiring", "hiring now", "job opportunity", "remote job", "earn money", "make money online",
    "iş ilanı", "işe alım", "personel aranıyor", "kazanç fırsatı",
    "ищем сотрудника", "ищем водителя", "работа", "вакансия", "заработок", "подработка",
]

SERVICE_SPAM = [
    "instagram followers", "telegram followers", "tiktok followers", "social media service", "seo service", "marketing service",
    "takipçi", "beğeni", "izlenme satın", "sosyal medya hizmeti",
    "подписчики instagram", "накрутка", "лайки", "просмотры", "smm",
]

MODERATION_NOTICES = [
    "users cannot send media", "only admins can post", "read-only group", "links are not allowed",
    "kullanıcılar medya gönderemez", "sadece yöneticiler mesaj gönderebilir",
    "пользователи не смогут отправлять", "только администраторы могут писать", "запрещено отправлять ссылки",
]

FOREIGN_MARKET_PROMO = [
    "oman residency", "muscat projects", "dubai property", "uae property", "georgia property", "montenegro property",
    "оман недвижимость", "дубай недвижимость", "грузия недвижимость", "черногория недвижимость",
]



def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(p in text for p in phrases)


def _count(text: str, phrases: list[str]) -> int:
    return sum(1 for p in phrases if p in text)


def classify(candidate: Candidate) -> ClassifiedCandidate:
    text = _norm(" ".join([candidate.title, candidate.text, candidate.author]))
    own_text = _norm(" ".join([candidate.title, candidate.text]))

    if not own_text:
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="empty_text")

    if _contains_any(own_text, MODERATION_NOTICES):
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="moderation_notice")
    if _contains_any(own_text, JOB_SPAM):
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="job_or_earnings_spam")
    if _contains_any(own_text, SERVICE_SPAM):
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="service_spam")
    if _contains_any(own_text, FOREIGN_MARKET_PROMO) and not _contains_any(own_text, NC_CONTEXT):
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="foreign_market_promo")

    explicit_buy = _count(own_text, EXPLICIT_BUY)
    relocation = _count(own_text, RELOCATION_INTENT)
    investment = _count(own_text, INVESTMENT_INTENT)
    property_context = _contains_any(text, PROPERTY_CONTEXT)
    nc_context = _contains_any(text, NC_CONTEXT)
    owner_direct = _contains_any(own_text, OWNER_DIRECT)
    budget = any(re.search(pattern, own_text, flags=re.I) for pattern in BUDGET_SIGNALS)
    transaction = _contains_any(own_text, TRANSACTION_SIGNALS)
    agent = _contains_any(text, AGENT_SIGNALS)
    seller_ad = _contains_any(own_text, SELLER_AD_SIGNALS)
    rental = _contains_any(own_text, RENTAL_SIGNALS)

    # Direct professional/seller identity is a strong rejection unless the post clearly describes the author's own purchase.
    first_person_buy = explicit_buy > 0 and any(
        p in own_text
        for p in [
            "i ", "i'm", "we ", "my ", "our ", "ben ", "biz ", "benim ", "bizim ",
            "хочу ", "ищу ", "куплю", "мы ", "мой ", "наш ",
        ]
    )
    if agent and not first_person_buy:
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="agent_or_broker")

    if rental and explicit_buy == 0 and investment == 0:
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="rental_not_buyer")

    if seller_ad and explicit_buy == 0 and relocation == 0 and investment == 0:
        return ClassifiedCandidate(candidate, "NOISE", 0, reject_reason="seller_or_listing")

    score = 0
    reasons: list[str] = []

    if explicit_buy:
        score += min(48, 30 + explicit_buy * 8)
        reasons.append("explicit_purchase_intent")
    if relocation:
        score += min(24, 14 + relocation * 5)
        reasons.append("relocation_intent")
    if investment:
        score += min(24, 14 + investment * 5)
        reasons.append("investment_intent")
    if property_context:
        score += 12
        reasons.append("property_context")
    if nc_context:
        score += 15
        reasons.append("north_cyprus_context")
    if owner_direct:
        score += 12
        reasons.append("owner_direct")
    if budget:
        score += 10
        reasons.append("budget_signal")
    if transaction:
        score += 8
        reasons.append("transaction_signal")

    # Seller/ad language is a penalty, not always a hard reject: users can quote a listing while asking to buy.
    if seller_ad:
        score -= 18
        reasons.append("seller_language_penalty")
    if agent:
        score -= 25
        reasons.append("agent_language_penalty")

    score = max(0, min(100, score))

    if explicit_buy and property_context and nc_context and score >= 70:
        label = "HOT"
    elif score >= 48 and (explicit_buy or relocation or investment) and (property_context or nc_context):
        label = "WARM"
    else:
        label = "NOISE"

    reject_reason = "" if label != "NOISE" else "insufficient_buyer_intent"
    return ClassifiedCandidate(candidate, label, score, reasons=reasons, reject_reason=reject_reason)
