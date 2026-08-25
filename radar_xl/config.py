from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


# Radar XL never sends or writes into production systems unless explicitly enabled.
DRY_RUN = env_bool("RADAR_XL_DRY_RUN", True)
TELEGRAM_ENABLED = env_bool("RADAR_XL_TELEGRAM_ENABLED", False)
FIRESTORE_ENABLED = env_bool("RADAR_XL_FIRESTORE_ENABLED", False)
HERMES_ENABLED = env_bool("RADAR_XL_HERMES_ENABLED", False)
BROWSER_USE_ENABLED = env_bool("RADAR_XL_BROWSER_USE_ENABLED", False)
FIRECRAWL_ENABLED = env_bool("RADAR_XL_FIRECRAWL_ENABLED", False)
AGENT_REACH_ENABLED = env_bool("RADAR_XL_AGENT_REACH_ENABLED", True)

RESULTS_PER_QUERY = env_int("RADAR_XL_RESULTS_PER_QUERY", 10, minimum=1, maximum=50)
MAX_QUERIES_PER_PROVIDER = env_int("RADAR_XL_MAX_QUERIES_PER_PROVIDER", 12, minimum=1, maximum=100)
FIRECRAWL_MAX_QUERIES = env_int("RADAR_XL_FIRECRAWL_MAX_QUERIES", 0, minimum=0, maximum=20)
BROWSER_USE_MAX_TASKS = env_int("RADAR_XL_BROWSER_USE_MAX_TASKS", 0, minimum=0, maximum=10)

BUYER_QUERIES: dict[str, list[str]] = {
    "en": [
        '"North Cyprus" "looking to buy" property',
        '"North Cyprus" "want to buy" apartment',
        '"North Cyprus" "need a villa"',
        '"North Cyprus" "owner only" property',
        '"Iskele" "looking to buy" apartment',
        '"Kyrenia" "looking to buy" apartment',
        '"North Cyprus" relocating property',
        '"North Cyprus" investment property budget',
    ],
    "tr": [
        '"Kuzey Kıbrıs" "ev almak istiyorum"',
        '"Kuzey Kıbrıs" "daire arıyorum"',
        '"İskele" "satın almak istiyorum" daire',
        '"Girne" "satın almak istiyorum" daire',
        '"Kuzey Kıbrıs" sahibinden villa arıyorum',
        '"Kuzey Kıbrıs" yatırım için daire arıyorum',
    ],
    "ru": [
        '"Северный Кипр" "хочу купить" квартиру',
        '"Северный Кипр" "ищу квартиру" покупка',
        '"Северный Кипр" "куплю квартиру"',
        '"Искеле" "хочу купить" квартиру',
        '"Кирения" "хочу купить" квартиру',
        '"Северный Кипр" "от собственника" квартира',
        '"Северный Кипр" "ищу виллу"',
    ],
}

# Open/community surfaces only. Developer/listing sites are intentionally not the main discovery target here.
FIRECRAWL_INCLUDE_DOMAINS = [
    "reddit.com",
    "x.com",
    "youtube.com",
    "expat.com",
    "expatforum.com",
    "forum-eu.com",
    "awd.ru",
    "kibkom.com",
    "cyprusliving.org",
]

OUTPUT_DIR = os.getenv("RADAR_XL_OUTPUT_DIR", "radar_xl_output")
