from __future__ import annotations

import re

import local_home_buyer_radar_v2 as radar


COUNTRY_PATTERNS = {
    "germany_home": r"germany|deutschland|german|berlin|m[üu]nchen|munich|hamburg|frankfurt|k[öo]ln|cologne|d[üu]sseldorf|stuttgart|leipzig|n[üu]rnberg",
    "netherlands_home": r"netherlands|nederland|dutch|amsterdam|rotterdam|den\s+haag|the\s+hague|utrecht|eindhoven|haarlem|almere|groningen",
    "belgium_home": r"belgium|belgi[ëe]|belgique|belgian|brussels|brussel|bruxelles|antwerp|antwerpen|gent|ghent|leuven|brugge|li[eè]ge|charleroi",
    "switzerland_home": r"switzerland|schweiz|suisse|svizzera|swiss|z[üu]rich|zurich|geneva|gen[èe]ve|lausanne|basel|bern|luzern|lucerne|zug",
    "spain": r"spain|spanien|spanje|espagne",
    "portugal": r"portugal",
    "italy": r"italy|italien|italië|italie",
    "france": r"france|frankreich|frankrijk|frankryk",
    "greece": r"greece|griechenland|griekenland|gr[èe]ce",
    "cyprus": r"cyprus|zypern|chypre",
    "north_cyprus": r"north(?:ern)?\s+cyprus|nordzypern|chypre\s+du\s+nord|noord[- ]cyprus",
    "turkey": r"turkey|türkei|turkije|turquie",
    "uae": r"dubai|uae|united\s+arab\s+emirates",
    "montenegro": r"montenegro",
    "croatia": r"croatia|kroatien|kroatië|croatie",
    "austria": r"austria|österreich|oesterreich",
    "poland": r"poland|polen|polska|pologne",
}


def _min_distance(a: re.Pattern, b: re.Pattern, text: str) -> int | None:
    aa = list(a.finditer(text))
    bb = list(b.finditer(text))
    if not aa or not bb:
        return None
    return min(abs(x.start() - y.start()) for x in aa for y in bb)


def _foreign_regex(profile: str) -> re.Pattern:
    parts = [pattern for key, pattern in COUNTRY_PATTERNS.items() if key != profile]
    return re.compile(r"(?:" + "|".join(parts) + r")", re.I)


def destination_precision_guard(profile: str, text: str) -> bool:
    """Return True when the purchase is more clearly aimed at another country.

    Examples:
      - "I live in Germany and want to buy in Spain" -> reject Germany-home lane.
      - "I live in Spain and want to buy in Berlin" -> keep Germany-home lane.

    The closest geographic marker to the purchase action wins. This avoids treating
    a person's residence country as the property destination.
    """
    action = radar.PURCHASE_ACTION_RE
    target = re.compile(r"(?:" + COUNTRY_PATTERNS[profile] + r")", re.I)
    foreign = _foreign_regex(profile)

    foreign_distance = _min_distance(action, foreign, text)
    if foreign_distance is None or foreign_distance > 95:
        return False

    target_distance = _min_distance(action, target, text)
    if target_distance is None:
        return True

    # Require a meaningful advantage before rejecting mixed-country discussions.
    return foreign_distance + 5 < target_distance


radar._wrong_purchase_country = destination_precision_guard

classify_v2 = radar.classify_v2
extract_requirements = radar.extract_requirements
semantic_key = radar.semantic_key
selected_queries = radar.selected_queries


def run():
    return radar.run()


if __name__ == "__main__":
    run()
