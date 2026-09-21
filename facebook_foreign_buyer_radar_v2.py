from __future__ import annotations

import facebook_foreign_buyer_radar as radar


# Property-specific purchase queries. The previous English query, "looking to buy",
# was too broad and mostly returned cars, medication and services. Keep one precise
# query per language so Facebook traffic remains low while the downstream classifier
# still decides whether the poster is a genuine end buyer.
radar.QUERY_SPECS = [
    {"query": "buy property", "language": "EN"},
    {"query": "купить недвижимость", "language": "RU"},
    {"query": "Immobilie kaufen", "language": "DE"},
]


if __name__ == "__main__":
    raise SystemExit(radar.main())
