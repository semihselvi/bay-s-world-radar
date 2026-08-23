from datetime import datetime, timezone

import youtube_radar as yr
import youtube_comment_expansion  # patches replies, watchlist ranking and full dedupe

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

# Workflow still caps discovery calls. Keep core market phrases every day and
# rotate languages/projects through the remaining slots instead of always using
# only the first entries of the original list.
original=_uniq(list(yr.DISCOVERY_QUERIES) + EXTRA)
core_keys={x.casefold() for x in CORE}
rotating=[x for x in original if x.casefold() not in core_keys]
yr.DISCOVERY_QUERIES=_uniq(CORE + _rotate(rotating, 32))

if __name__ == "__main__":
    yr.run()
