import os

import main
import shard_runner
import north_cyprus_focus

# Dedicated North Cyprus shard. It uses a wider buyer-intent net than the general
# World Radar while keeping seller/rental filtering strict.
shard_runner.SHARDS["north_cyprus_hunter"] = {
    "index_names": {
        "Expat.com North Cyprus",
    },
    "topic_names": set(),
    "telegram": {
        "cyprusy",
        "searchnorthcyprus",
        "snchubTalkroom",
        "meetinnorthcyprus",
        "northcyprus29",
    },
    "catalogs": {"TeleGid Cyprus", "SNC Community Hub"},
    "member": True,
    "exa_calls": 1,
    "exa_query": (
        "past 7 days real person first-person discussion about actually buying a home, apartment, "
        "villa, land or investment property in North Cyprus, Northern Cyprus, TRNC, Iskele, Long Beach, "
        "Kyrenia, Girne, Esentepe, Famagusta, Gazimagusa, Lapta, Tatlisu, Bahceli or Bafra; include people "
        "asking where to buy, what area, title deed, lawyer, mortgage, deposit, viewing, offer, payment plan, "
        "budget, relocation, retirement or second home; English Turkish Russian German French Dutch Persian; "
        "prioritize genuine forum, Reddit, Facebook group and Telegram community posts; exclude agents, brokers, "
        "developers, listings, advertising, rental-only requests, guides and news"
    ),
    "exa_domains": [
        "reddit.com",
        "expat.com",
        "expatforum.com",
        "kibkomnorthcyprusforum.com",
        "britishexpats.com",
        "tripadvisor.com",
        "facebook.com",
        "t.me",
        "turkishliving.com",
    ],
    "reddit_focus": ["NorthCyprus", "cyprus", "expats", "ExpatFIRE", "AmerExit"],
}

# Override only for this process. Other World Radar shards keep their current filters.
main.keep_candidate = north_cyprus_focus.keep_candidate
main.buyer_scores = north_cyprus_focus.buyer_scores

_original_market_for = main.market_for


def north_cyprus_market_for(text, bucket_name="", url="", title=""):
    market = _original_market_for(text, bucket_name, url, title)
    # Every source in this dedicated shard is North-Cyprus-focused. The fallback
    # only applies when the generic classifier cannot resolve a market at all.
    return "north_cyprus" if market == "unknown" else market


main.market_for = north_cyprus_market_for

if __name__ == "__main__":
    os.environ["WORLD_RADAR_SHARD"] = "north_cyprus_hunter"
    shard_runner.SHARD = "north_cyprus_hunter"
    shard_runner.run()
