# BAY-S World Radar source registry
# Based on the manually researched and live-checked source list supplied by Semih.
# US/Australia property markets are intentionally excluded.

REDDIT_SUBREDDITS = [
    "goldenvisa",
    "ExpatFIRE",
    "expats",
    "AmerExit",              # outbound / relocation intent, not US property market
    "CitizenshipInvestment",
    "beleggen",
    "germany",
]

TELEGRAM_PUBLIC_CHANNELS = [
    "cyprusy",
    "velesproperty",
    "btinvestnorthcyprus",
    "sadeceemlakoto",
    "VillaEdelweissMontenegro",
    "Montenegrosupreme",
    "prian_property",
    "hayatestate_online",
    "astonspassport",
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

DIRECT_INDEX_SOURCES = [
    {"name":"MoneySavingExpert", "url":"https://forums.moneysavingexpert.com/categories/house-buying-renting-selling", "domain":"forums.moneysavingexpert.com", "market":"uk"},
    {"name":"Expat.com Italy", "url":"https://www.expat.com/en/forum/europe/italy/", "domain":"expat.com", "market":"italy"},
    {"name":"Expat.com Cyprus", "url":"https://www.expat.com/en/forum/europe/cyprus/", "domain":"expat.com", "market":"cyprus"},
    {"name":"Expat.com Montenegro", "url":"https://www.expat.com/en/forum/europe/montenegro/", "domain":"expat.com", "market":"montenegro"},
    {"name":"Investisseurs Heureux", "url":"https://www.investisseurs-heureux.fr/f26", "domain":"investisseurs-heureux.fr", "market":"france"},
    {"name":"PIM.be", "url":"https://forum.pim.be/", "domain":"forum.pim.be", "market":"belgium"},
    {"name":"Forum AWD Overseas Property", "url":"https://forum.awd.ru/viewforum.php?f=1391", "domain":"forum.awd.ru", "market":"global"},
    {"name":"Forum-EU", "url":"https://forum-eu.com/", "domain":"forum-eu.com", "market":"global"},
    {"name":"MontenegroExpats", "url":"https://www.montenegroexpats.com/expat-communities", "domain":"montenegroexpats.com", "market":"montenegro"},
    {"name":"Ilancik", "url":"https://ilancik.com/en/", "domain":"ilancik.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"Northern Cyprus Property", "url":"https://northern-cyprus-property.com/tr/", "domain":"northern-cyprus-property.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"TEKCE Cyprus", "url":"https://tekce.com/tr/emlak-kibris", "domain":"tekce.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"101evler", "url":"https://www.101evler.com/", "domain":"101evler.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"HangiEv", "url":"https://www.hangiev.com/", "domain":"hangiev.com", "market":"north_cyprus", "discovery_only":True},
    {"name":"Prian", "url":"https://prian.ru/", "domain":"prian.ru", "market":"global", "discovery_only":True},
    {"name":"Realting", "url":"https://realting.com/", "domain":"realting.com", "market":"global", "discovery_only":True},
    {"name":"MIPIF Almaty", "url":"https://almaty.mipif.com/", "domain":"almaty.mipif.com", "market":"kazakhstan", "discovery_only":True},
]

DIRECT_TOPIC_SOURCES = [
    {"name":"FinanzaOnline", "url":"https://forum.finanzaonline.com/threads/investimento-immobiliare-allestero.1973944/", "market":"italy"},
    {"name":"Propit", "url":"https://www.propit.it/threads/120-000-euro-da-investire-meglio-immobile-in-italia-o-all-estero-per-rendita.51914/", "market":"italy"},
    {"name":"Wertpapier-Forum", "url":"https://www.wertpapier-forum.de/topic/68620-immobilienkauf-als-geldanlage-%E2%80%93-erste-%C3%BCberlegungen-feedback-erbeten/", "market":"germany"},
    {"name":"AuswandererForum", "url":"https://www.auswandererforum.de/threads/27018-haus-kaufen-in-spanien", "market":"germany"},
    {"name":"WiWi-TReFF", "url":"https://www.wiwi-treff.de/Immobilien/Hauskauf/Haus-im-Ausland-kaufen/Diskussion-97126", "market":"germany"},
    {"name":"Finary Community", "url":"https://community.finary.com/t/investir-dans-limmobilier-en-france-depuis-letranger/37245", "market":"france"},
    {"name":"Tweakers", "url":"https://gathering.tweakers.net/forum/list_messages/2142686", "market":"netherlands"},
    {"name":"AllesAmerika", "url":"https://forum.allesamerika.com/viewtopic.php?t=79933", "market":"netherlands"},
    {"name":"Forum-EU Portugal Golden Visa", "url":"https://forum-eu.com/topic/18440-%D0%B7%D0%BE%D0%BB%D0%BE%D1%82%D0%B0%D1%8F-%D0%B2%D0%B8%D0%B7%D0%B0-%D0%B2-%D0%BF%D0%BE%D1%80%D1%82%D1%83%D0%B3%D0%B0%D0%BB%D0%B8%D0%B8-%D0%BE%D1%82%D0%B7%D1%8B%D0%B2%D1%8B-%D0%BF%D0%BE%D0%B4%D0%B2%D0%BE%D0%B4%D0%BD%D1%8B%D0%B5-%D0%BA%D0%B0%D0%BC/", "market":"portugal"},
]

DISCOVERY_CATALOGS = [
    "https://telegid.me/catalog/kipr",
    "https://telegid.me/catalog/chernogoriya/budva",
    "https://tlgrm.ru/channels/@velesproperty",
]

# Reddit direct RSS is 403 from GitHub Actions, so Reddit is intentionally gap-filled through Exa.
EXA_GAPFILL_DOMAINS = [
    "reddit.com",
    "facebook.com",
    "internations.org",
    "meetup.com",
    "expatforum.com",
    "telegid.me",
    "tlgrm.ru",
    "investeerders.nl",
]
