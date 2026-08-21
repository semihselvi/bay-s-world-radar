# BAY-S World Radar source registry v3
# Expanded from the manually researched source list + verified target-country communities.
# US/Australia property markets are intentionally excluded.

# Reddit is not crawled directly from GitHub Actions (403). These communities are
# explicitly named inside Exa gap-fill queries so discovery stays targeted.
REDDIT_SUBREDDITS = [
    "goldenvisa",
    "ExpatFIRE",
    "expats",
    "AmerExit",              # outbound / relocation intent only, not US property
    "CitizenshipInvestment",
    "beleggen",
    "germany",
    "PortugalExpats",
    "ItalyExpat",
    "montenegro",
    "cyprus",
    "NorthCyprus",
    "eupersonalfinance",
    "greece",
    "askspain",
]

TELEGRAM_PUBLIC_CHANNELS = [
    # North Cyprus - community/discovery first, seller-only channels intentionally avoided
    "cyprusy",
    "searchnorthcyprus",
    "snchubTalkroom",
    "meetinnorthcyprus",
    "northcyprus29",
    "velesproperty",
    "btinvestnorthcyprus",
    "sadeceemlakoto",
    # Montenegro
    "VillaEdelweissMontenegro",
    "Montenegrosupreme",
    # Russia/CIS / global overseas property
    "prian_property",
    "hayatestate_online",
    "astonspassport",
    # Cross-border investment
    "indemochat",
]

TELEGRAM_INVITE_REFERENCES = [
    "https://t.me/+WZluIebsLjwxYTFk",
    "https://t.me/+Rxo-Uo74TL5kZGFi",
]

WHATSAPP_REFERENCES = [
    "https://chat.whatsapp.com/CEBlpmf0L319Qq3UGCGZ3c",
    "https://chat.whatsapp.com/IZ65IfzolaMJmajI578LTw",
]

FACEBOOK_GROUP_REFERENCES = [
    "https://www.facebook.com/groups/1287822358267595/",
    "https://www.facebook.com/groups/372771683412684/",
    "https://www.facebook.com/groups/1587640852047583/",
    "https://www.facebook.com/groups/expatslivinginitaly/",
    "https://www.facebook.com/groups/1664682947124386/",
    "https://www.facebook.com/groups/montenegroexpatgroup/",
    "https://www.facebook.com/groups/575513866275666/",
    "https://www.facebook.com/groups/greekresidency/",
]

# Direct latest/index sources. These are free HTTP scans and therefore the main
# expansion layer. include_path keeps navigation/profile/upload links out.
DIRECT_INDEX_SOURCES = [
    # North Cyprus - dedicated live forum added before the broad Cyprus forum
    {"name":"Expat.com North Cyprus", "url":"https://www.expat.com/en/forum/europe/cyprus/north-cyprus/", "domain":"expat.com", "market":"north_cyprus", "include_path":["/en/forum/europe/cyprus/north-cyprus/"]},

    # UK
    {"name":"MoneySavingExpert", "url":"https://forums.moneysavingexpert.com/categories/house-buying-renting-selling", "domain":"forums.moneysavingexpert.com", "market":"uk", "include_path":["/discussion/"]},

    # South Europe / Golden Visa / relocation
    {"name":"Expat.com Greece", "url":"https://www.expat.com/en/forum/europe/greece/", "domain":"expat.com", "market":"greece", "include_path":["/en/forum/europe/greece/"]},
    {"name":"Expat.com Portugal", "url":"https://www.expat.com/en/forum/europe/portugal/", "domain":"expat.com", "market":"portugal", "include_path":["/en/forum/europe/portugal/"]},
    {"name":"Expat.com Spain", "url":"https://www.expat.com/en/forum/europe/spain/", "domain":"expat.com", "market":"spain", "include_path":["/en/forum/europe/spain/"]},
    {"name":"Expat.com Italy", "url":"https://www.expat.com/en/forum/europe/italy/", "domain":"expat.com", "market":"italy", "include_path":["/en/forum/europe/italy/"]},
    {"name":"Expat.com Cyprus", "url":"https://www.expat.com/en/forum/europe/cyprus/", "domain":"expat.com", "market":"cyprus", "include_path":["/en/forum/europe/cyprus/"]},
    {"name":"Expat.com Montenegro", "url":"https://www.expat.com/en/forum/europe/montenegro/", "domain":"expat.com", "market":"montenegro", "include_path":["/en/forum/europe/montenegro/"]},
    {"name":"Expat.com Turkey", "url":"https://www.expat.com/en/forum/middle-east/turkey/", "domain":"expat.com", "market":"turkey", "include_path":["/en/forum/middle-east/turkey/"]},

    # Western Europe
    {"name":"Expat.com Germany", "url":"https://www.expat.com/en/forum/europe/germany/", "domain":"expat.com", "market":"germany", "include_path":["/en/forum/europe/germany/"]},
    {"name":"Expat.com France", "url":"https://www.expat.com/en/forum/europe/france/", "domain":"expat.com", "market":"france", "include_path":["/en/forum/europe/france/"]},
    {"name":"Expat.com Netherlands", "url":"https://www.expat.com/en/forum/europe/netherlands/", "domain":"expat.com", "market":"netherlands", "include_path":["/en/forum/europe/netherlands/"]},
    {"name":"Expat.com Belgium", "url":"https://www.expat.com/en/forum/europe/belgium/", "domain":"expat.com", "market":"belgium", "include_path":["/en/forum/europe/belgium/"]},
    {"name":"Investisseurs Heureux", "url":"https://www.investisseurs-heureux.fr/f26", "domain":"investisseurs-heureux.fr", "market":"france"},
    {"name":"Finary Immobilier", "url":"https://community.finary.com/c/immobilier/6", "domain":"community.finary.com", "market":"france", "include_path":["/t/"]},
    {"name":"PIM.be", "url":"https://forum.pim.be/", "domain":"forum.pim.be", "market":"belgium", "include_path":["topic-"]},

    # Central Europe - direct-only expansion, no extra Exa cost
    {"name":"Expat.com Austria", "url":"https://www.expat.com/en/forum/europe/austria/", "domain":"expat.com", "market":"austria", "include_path":["/en/forum/europe/austria/"]},
    {"name":"Expat.com Switzerland", "url":"https://www.expat.com/en/forum/europe/switzerland/", "domain":"expat.com", "market":"switzerland", "include_path":["/en/forum/europe/switzerland/"]},
    {"name":"Expat.com Poland", "url":"https://www.expat.com/en/forum/europe/poland/", "domain":"expat.com", "market":"poland", "include_path":["/en/forum/europe/poland/"]},
    {"name":"Expat.com Czech Republic", "url":"https://www.expat.com/en/forum/europe/czech-republic/", "domain":"expat.com", "market":"czech_republic", "include_path":["/en/forum/europe/czech-republic/"]},
    {"name":"Expat.com Lithuania", "url":"https://www.expat.com/en/forum/europe/lithuania/", "domain":"expat.com", "market":"lithuania", "include_path":["/en/forum/europe/lithuania/"]},

    # Russia/CIS
    {"name":"Forum AWD Overseas Property", "url":"https://forum.awd.ru/viewforum.php?f=1391", "domain":"forum.awd.ru", "market":"global", "include_path":["viewtopic.php"]},
    {"name":"Forum-EU", "url":"https://forum-eu.com/", "domain":"forum-eu.com", "market":"global", "include_path":["/topic/"]},

    # Discovery-only portals: useful for ecosystem discovery, never accepted as buyer leads.
    {"name":"Ilancik", "url":"https://ilancik.com/en/", "domain":"ilancik.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"Northern Cyprus Property", "url":"https://northern-cyprus-property.com/tr/", "domain":"northern-cyprus-property.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"TEKCE Cyprus", "url":"https://tekce.com/tr/emlak-kibris", "domain":"tekce.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"101evler", "url":"https://www.101evler.com/", "domain":"101evler.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"HangiEv", "url":"https://www.hangiev.com/", "domain":"hangiev.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"Prian", "url":"https://prian.ru/", "domain":"prian.ru", "market":"global", "discovery_only":True},
    {"name":"Realting", "url":"https://realting.com/", "domain":"realting.com", "market":"global", "discovery_only":True},
    {"name":"MIPIF Almaty", "url":"https://almaty.mipif.com/", "domain":"almaty.mipif.com", "market":"kazakhstan", "discovery_only":True},
]

# Legacy / exact discussions are retained as reference but no longer used by the
# production shards when a live index/category is available.
DIRECT_TOPIC_SOURCES = [
    {"name":"Wertpapier-Forum", "url":"https://www.wertpapier-forum.de/topic/68620-immobilienkauf-als-geldanlage-%E2%80%93-erste-%C3%BCberlegungen-feedback-erbeten/", "market":"germany"},
    {"name":"Forum-EU Portugal Golden Visa", "url":"https://forum-eu.com/topic/18440-%D0%B7%D0%BE%D0%BB%D0%BE%D1%82%D0%B0%D1%8F-%D0%B2%D0%B8%D0%B7%D0%B0-%D0%B2-%D0%BF%D0%BE%D1%80%D1%82%D1%83%D0%B3%D0%B0%D0%BB%D0%B8%D0%B8-%D0%BE%D1%82%D0%B7%D1%8B%D0%B2%D1%8B-%D0%BF%D0%BE%D0%B4%D0%B2%D0%BE%D0%B4%D0%BD%D1%8B%D0%B5-%D0%BA%D0%B0%D0%BC/", "market":"portugal"},
]

# Catalogs are scanned for NEW public Telegram usernames. Private invite links
# are never auto-joined. The SNC channel is also used as a live directory because
# it links to its public community/talkroom channels.
DISCOVERY_CATALOGS = [
    {"name":"TeleGid Cyprus", "url":"https://telegid.me/catalog/kipr", "market":"north_cyprus"},
    {"name":"SNC Community Hub", "url":"https://t.me/s/searchnorthcyprus", "market":"north_cyprus"},
    {"name":"TeleGid Montenegro", "url":"https://telegid.me/catalog/chernogoriya/budva", "market":"montenegro"},
    {"name":"MontenegroExpats Communities", "url":"https://www.montenegroexpats.com/expat-communities", "market":"montenegro"},
]

# Domains that are useful but block GitHub direct crawling are handled only by Exa.
EXA_GAPFILL_DOMAINS = [
    "reddit.com",
    "facebook.com",
    "internations.org",
    "meetup.com",
    "expatforum.com",
    "telegid.me",
    "tlgrm.ru",
    "kibkomnorthcyprusforum.com",
    "britishexpats.com",
    "tripadvisor.com",
    "turkishliving.com",
    "forum.finanzaonline.com",
    "propit.it",
    "auswandererforum.de",
    "wiwi-treff.de",
    "tweakers.net",
    "wertpapier-forum.de",
    "forum.allesamerika.com",
    "investeerders.nl",
]
