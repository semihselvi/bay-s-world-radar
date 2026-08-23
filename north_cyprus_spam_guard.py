import re

import north_cyprus_focus as nf


_original_promotional_service_ad = nf._promotional_service_ad

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
