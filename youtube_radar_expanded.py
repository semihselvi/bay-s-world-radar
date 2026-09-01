from datetime import datetime, timezone
import re

import youtube_radar as yr
import youtube_comment_expansion as yce  # patches replies, watchlist ranking and full dedupe

CORE = [
    "North Cyprus property",
    "Northern Cyprus real estate",
    "Iskele Long Beach property",
    "Kuzey Kıbrıs emlak",
    "Северный Кипр недвижимость",
    "Северный Кипр квартира",
]

EXTRA = [
    "North Cyprus apartment price",
    "North Cyprus property resale",
    "Long Beach Iskele apartment price",
    "Girne Kyrenia property price",
    "Esentepe North Cyprus villa",
    "Kuzey Kıbrıs daire fiyatları",
    "İskele Long Beach satılık daire",
    "Kuzey Kıbrıs sahibinden daire",
    "Северный Кипр купить квартиру",
    "Северный Кипр вторичка",
    "Северный Кипр рассрочка недвижимость",
    "Северный Кипр Long Beach квартира",
    "Nordzypern Immobilie kaufen",
    "Nordzypern Wohnung kaufen",
    "Chypre du Nord immobilier",
    "Noord Cyprus vastgoed kopen",
    "Cypr Północny nieruchomości",
    "Cypr Północny mieszkanie kupić",
    "Північний Кіпр нерухомість",
    "Північний Кіпр купити квартиру",
    "شمال قبرص عقارات",
    "شمال قبرص شراء شقة",
    "قبرس شمالی خرید ملک",
    "قبرس شمالی خرید آپارتمان",
    "צפון קפריסין נדלן",
    "Caesar Resort North Cyprus resale",
    "Grand Sapphire North Cyprus resale",
    "Isatis Elysium North Cyprus",
    "Isatis Fiora North Cyprus",
    "Isatis Orchard North Cyprus",
    "Royal Sun Long Beach resale",
    "Riverside Life North Cyprus resale",
]


def _uniq(values):
    out=[]; seen=set()
    for value in values:
        key=value.casefold()
        if key in seen:
            continue
        seen.add(key); out.append(value)
    return out


def _rotate(values, count):
    if len(values) <= count:
        return values[:]
    now=datetime.now(timezone.utc)
    slot=now.timetuple().tm_yday
    start=(slot*count) % len(values)
    return [values[(start+i)%len(values)] for i in range(count)]


# Discovery is an enrichment step; scanning the existing watchlist is the lead-producing
# step. A transient Firestore persistence problem must not make the whole YouTube lane
# red or prevent us from scanning comments already on the watchlist.
_base_discover_videos = yr.discover_videos


def _safe_discover_videos(deep=False):
    try:
        return _base_discover_videos(deep=deep)
    except Exception as exc:
        print("YOUTUBE_DISCOVERY_DEGRADED", repr(exc))
        try:
            yr.main.notify_telegram(
                "⚠️ BAY-S YOUTUBE discovery geçici olarak atlandı. Mevcut video watchlist yorum taraması devam ediyor."
            )
        except Exception:
            pass
        return 0


yr.discover_videos = _safe_discover_videos

# Final precision gate. The expanded rescue classifier used to allow any question
# mark on a property video to become a lead. That admitted resident/opinion comments
# such as "why are you lying, we have lived here for four years". A YouTube lead now
# needs an actual buyer/request/engagement signal in the comment itself.
_base_classify = yr.classify_comment

RESIDENT_OPINION_RE = re.compile(
    r"(?:"
    r"\b(?:i|we)\s+(?:live|have\s+lived|been\s+living)\s+(?:here|in\s+(?:north|northern)\s+cyprus)\b|"
    r"\b(?:living|lived)\s+here\s+for\s+\d+\s+years?\b|"
    r"\b(?:я|мы)\s+(?:живу|живем|живём|живём\s+здесь|живем\s+здесь)\b|"
    r"\bжив[её]м\s+здесь\s+\d+\s+(?:год|года|лет)\b|"
    r"\bburada\s+(?:yaşıyorum|yasiyorum|yaşıyoruz|yasiyoruz)\b"
    r")",
    re.I,
)
OPINION_ONLY_RE = re.compile(
    r"(?:\binflation\b|\bprices?\s+(?:went|gone)\s+up\b|\btaxes?\b|\belectricity\b|\bwater\b|"
    r"инфляц\w*|подорожал\w*|электроэнерг\w*|налог\w*|цены?,?\s+как|"
    r"enflasyon|elektrik|su\s+faturas|vergiler?)",
    re.I,
)


def _has_actionable_comment_signal(text):
    if yr._matches(text, yr.STRONG_BUYER_PATTERNS):
        return True
    if yr._matches(text, yr.REQUEST_PATTERNS):
        return True
    return any(re.search(pattern, text, re.I) for pattern in yce.ENGAGEMENT)


def _precision_classify(item):
    own = " ".join(str(item.get("text", "")).split())
    if not own:
        return None
    actionable = _has_actionable_comment_signal(own)
    if not actionable:
        return None
    if (RESIDENT_OPINION_RE.search(own) or OPINION_ONLY_RE.search(own)) and not yr._matches(own, yr.STRONG_BUYER_PATTERNS):
        return None
    return _base_classify(item)


yr.classify_comment = _precision_classify

# Workflow still caps discovery calls. Keep core market phrases every day and
# rotate languages/projects through the remaining slots instead of always using
# only the first entries of the original list.
original=_uniq(list(yr.DISCOVERY_QUERIES) + EXTRA)
core_keys={x.casefold() for x in CORE}
rotating=[x for x in original if x.casefold() not in core_keys]
yr.DISCOVERY_QUERIES=_uniq(CORE + _rotate(rotating, 32))

if __name__ == "__main__":
    yr.run()
