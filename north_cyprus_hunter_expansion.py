import shard_runner
import north_cyprus_hunter  # ensure dedicated shard exists
from telegram_known_public_groups import KNOWN_GROUPS


cfg = shard_runner.SHARDS.get("north_cyprus_hunter", {})

# Reuse the verified public group universe in the main Hunter too, not only the
# separate Buyer Catcher. This costs no Exa calls.
telegram = cfg.setdefault("telegram", set())
telegram.update(KNOWN_GROUPS)

# source_crawler_v2 adds these live directories to DISCOVERY_CATALOGS at import
# time. Including their names here makes the Hunter actually crawl them.
catalogs = cfg.setdefault("catalogs", set())
catalogs.update({
    "TeleGid Cyprus",
    "SNC Community Hub",
    "Emigrants 360 Cyprus",
    "NewCY Cyprus Chat Directory",
    "KiprInfo Cyprus Chat Mirror",
})

# Keep the same single paid Exa call, but widen what that call asks for. This is
# retrieval coverage, not additional spend.
base_query = str(cfg.get("exa_query", ""))
multilingual = (
    " Also search Polish, Ukrainian, Swedish, Norwegian, Danish, Italian, Spanish, Portuguese, Czech, Estonian, Arabic, "
    "Hebrew and Kazakh buyer wording. Include Cypr Polnocny/Cypr Północny, Pivnichnyi Kipr/Північний Кіпр, Norra Cypern, "
    "Nord-Kypros, Nordcypern, Cipro Nord/Cipro del Nord, Chipre del Norte, Chipre do Norte, Severni Kypr/Severní Kypr, "
    "Pohja-Kupros/Põhja-Küpros, قبرص الشمالية, צפון קפריסין/קפריסין הצפונית and Солтүстік Кипр. Look for first-person "
    "phrases equivalent to want to buy, looking for a house/apartment/villa, price, budget, owner direct, installment, "
    "resale, title deed and which area/project is best. Prioritize genuine person posts/comments, not agency pages."
)
if multilingual.strip() not in base_query:
    cfg["exa_query"] = base_query + multilingual

print(
    f"NC_HUNTER_EXPANSION telegram={len(cfg.get('telegram', []))} "
    f"catalogs={len(cfg.get('catalogs', []))} exa_calls={cfg.get('exa_calls', 0)}"
)
