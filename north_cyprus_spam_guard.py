import re

import north_cyprus_focus as nf


_original_promotional_service_ad = nf._promotional_service_ad

# Real buyer language observed in live North Cyprus groups. These are layered
# here so every guarded Hunter / Recall / Catcher / Recovery lane sees them
# without loosening the generic seller filters.
RUSSIAN_STRONG_BUYER_PATTERNS = [
    r"\bсрочно\s+ищу(?:\s+на\s+покупку)?\b",
    r"\bищу\s+на\s+покупку\b",
    r"\bищу\s+(?:на\s+покупку\s+)?(?:отдельно\s*стоящую|отдельностоящую)?\s*вилл",
    r"\bнужна\s+(?:отдельно\s*стоящая|отдельностоящая)?\s*вилл",
    r"\bкуплю\s+(?:отдельно\s*стоящую|отдельностоящую)?\s*вилл",
    r"\bищу\s+.*\bтолько\s+от\s+собственника\b",
]

RUSSIAN_REQUEST_BUYER_PATTERNS = [
    r"\bтолько\s+от\s+собственника\b",
    r"\bот\s+собственника\b",
    r"\bбез\s+агент(?:ов|ств)?\b",
    r"\bна\s+покупку\b",
]

RUSSIAN_NC_LOCATION_PATTERNS = [
    r"\bискеле\b",
    r"\bбоаз\b",
    r"\bбогаз\b",
    r"\bотюкен\b",
    r"\bотукен\b",
    r"\bйени\s*боазичи\b",
    r"\bени\s*боазичи\b",
    r"\bйенибоазичи\b",
    r"\bенибоазичи\b",
    r"\bгазимагуса\b",
    r"\bфамагуста\b",
    r"\bгирне\b",
    r"\bэсентепе\b",
    r"\bтатлысу\b",
    r"\bбафра\b",
    r"\bлапта\b",
    r"\bалсанджак\b",
    r"\bкараогланоглу\b",
]

RUSSIAN_CONCRETE_BUYER_PATTERNS = [
    r"\bсрочно\b",
    r"\bтолько\s+от\s+собственника\b",
    r"\bот\s+собственника\b",
    r"\bотдельно\s*стоящ(?:ая|ую|ей)\b",
    r"\bотдельностоящ(?:ая|ую|ей)\b",
]

for _pattern in RUSSIAN_STRONG_BUYER_PATTERNS:
    if _pattern not in nf.STRONG_BUYER_PATTERNS:
        nf.STRONG_BUYER_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_REQUEST_BUYER_PATTERNS:
    if _pattern not in nf.REQUEST_BUYER_PATTERNS:
        nf.REQUEST_BUYER_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_NC_LOCATION_PATTERNS:
    if _pattern not in nf.NC_LOCATION_PATTERNS:
        nf.NC_LOCATION_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_CONCRETE_BUYER_PATTERNS:
    if _pattern not in nf.CONCRETE_PATTERNS:
        nf.CONCRETE_PATTERNS.append(_pattern)


RECRUITMENT_PATTERNS = [
    r"join\s+snc\s+field\s+operatives",
    r"field representatives?",
    r"offline/online field representatives?",
    r"skills we(?:'|’)re looking for",
    r"roles may include",
    r"strictly commission[- ]based",
    r"not salaried",
    r"work,? learn and earn",
    r"sales\s*&\s*communication",
    r"customer\s*&\s*client relations",
    r"it\s*&\s*digital skills",
    r"photography,? video\s*&\s*content creation",
    r"ads management\s*&\s*lead generation",
    r"apartment viewings",
    r"assisting clients",
    r"sourcing apartments directly from owners",
    r"generating leads",
    r"helping close deals",
    r"name:\s*.*location:\s*.*skills",
    r"limited spots available",
    r"@snccenter02\b",
]


def promotional_service_or_recruitment_ad(text):
    if _original_promotional_service_ad(text):
        return True

    # Clear recruitment copy is never a buyer lead even when it contains
    # apartment/viewing/owner/lead/close-deal language.
    if re.search(
        r"join\s+snc\s+field\s+operatives|field representatives?|strictly commission[- ]based|not salaried",
        text,
        re.I,
    ):
        return True

    hits = sum(1 for pattern in RECRUITMENT_PATTERNS if re.search(pattern, text, re.I | re.S))
    return hits >= 3


nf._promotional_service_ad = promotional_service_or_recruitment_ad
