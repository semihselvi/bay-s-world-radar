import hybrid_engine
from telegram_member_reader import collect_member_telegram

_original_direct_discovery = hybrid_engine.direct_discovery


def direct_discovery_with_member_telegram():
    items, counts = _original_direct_discovery()
    member_items = collect_member_telegram()
    items.extend(member_items)
    counts["Telegram Member"] = len(member_items)
    return items, counts


hybrid_engine.direct_discovery = direct_discovery_with_member_telegram

if __name__ == "__main__":
    hybrid_engine.run()
