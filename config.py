import os

COLLECTION = os.getenv("WORLD_FIRESTORE_COLLECTION", "bay_s_world_leads")
SCAN_LOG_COLLECTION = os.getenv("WORLD_FIRESTORE_SCAN_COLLECTION", "bay_s_world_scans")
LOOKBACK_HOURS = int(os.getenv("WORLD_LOOKBACK_HOURS", "24"))
MAX_RESULTS_PER_SOURCE = int(os.getenv("WORLD_MAX_RESULTS_PER_SOURCE", "15"))
EXA_NUM_RESULTS = int(os.getenv("WORLD_EXA_NUM_RESULTS", "15"))
EXA_MAX_CALLS = int(os.getenv("WORLD_EXA_MAX_CALLS", "6"))

MARKETS = {
    "north_cyprus": [
        "North Cyprus", "Northern Cyprus", "NorthCyprus", "Kuzey Kıbrıs", "Kuzey Kibris",
        "Северный Кипр", "Nordzypern", "TRNC", "KKTC", "Iskele", "İskele", "Yeni Iskele",
        "Long Beach", "Kyrenia", "Girne", "Esentepe", "Lapta", "Yeniboğaziçi", "Yenibogazici",
        "Famagusta", "Gazimağusa", "Gazimagusa", "Tatlısu", "Tatlisu", "Bafra", "Boğaz", "Bogaz",
        "Dipkarpaz", "Bahçeli", "Bahceli", "Küçük Erenköy", "Kucuk Erenkoy", "Çatalköy", "Catalkoy",
        "Alsancak", "Karşıyaka", "Karsiyaka", "Bellapais", "Beylerbeyi", "Ozanköy", "Ozankoy",
        "Lefke", "Güzelyurt", "Guzelyurt", "Geçitkale", "Gecitkale"
    ],
    "turkey": ["Turkey", "Türkiye", "Antalya", "Alanya", "Mersin", "Istanbul", "İstanbul", "Izmir", "İzmir", "Bodrum", "Fethiye", "Muğla"],
    "montenegro": ["Montenegro", "Budva", "Kotor", "Tivat", "Podgorica", "Bar", "Herceg Novi", "Karadağ", "Черногория"],
    "greece": ["Greece", "Athens", "Thessaloniki", "Crete", "Rhodes", "Corfu", "Piraeus", "Greek Golden Visa"],
    "portugal": ["Portugal", "Lisbon", "Porto", "Algarve", "Madeira", "Portugal Golden Visa"],
    "spain": ["Spain", "Madrid", "Barcelona", "Malaga", "Alicante", "Valencia", "Marbella"],
    "italy": ["Italy", "Rome", "Milan", "Sicily", "Puglia", "Tuscany", "Italian property"],
    "cyprus": ["Cyprus", "Republic of Cyprus", "Paphos", "Limassol", "Larnaca", "Nicosia"],
    "germany": ["Germany", "Deutschland", "Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne", "Köln"],
    "netherlands": ["Netherlands", "Amsterdam", "Rotterdam", "The Hague", "Utrecht"],
    "belgium": ["Belgium", "Brussels", "Antwerp", "Ghent"],
    "france": ["France", "Paris", "Nice", "Cannes", "Marseille", "Lyon"],
    "lithuania": ["Lithuania", "Vilnius", "Kaunas", "Klaipeda"],
    "russia": ["Russia", "Россия", "Москва", "Санкт-Петербург"],
    "kazakhstan": ["Kazakhstan", "Казахстан", "Almaty", "Алматы", "Astana", "Астана"],
    "uk": ["United Kingdom", "UK", "England", "London", "Manchester", "Birmingham", "Liverpool", "Leeds", "Brighton"],
    "poland": ["Poland", "Warsaw", "Krakow", "Gdansk", "Wroclaw"],
    "czech_republic": ["Czech Republic", "Czechia", "Prague", "Brno"],
    "austria": ["Austria", "Vienna", "Salzburg", "Innsbruck"],
}

INTENT_PHRASES = [
    "looking to buy", "want to buy", "planning to buy", "ready to buy", "looking for property",
    "looking for an apartment", "looking for a house", "looking for a villa", "property wanted",
    "where should I buy", "which area should I buy", "buying property", "investment property",
    "property investment", "cash buyer", "property budget", "moving to", "relocating to",
    "viewing property", "property viewing", "make an offer", "mortgage", "deposit", "lawyer",
    "title deed", "payment plan", "due diligence", "reservation", "second home", "holiday home", "retirement home",
    "golden visa", "residency by investment", "property for residency",
    "ev almak istiyorum", "daire almak istiyorum", "satın almak istiyorum", "ev arıyorum", "daire arıyorum", "villa arıyorum", "arsa arıyorum", "yatırım için ev", "Kıbrıs'a taşınmak", "hangi bölgede ev alınır",
    "хочу купить", "хотим купить", "ищу квартиру", "ищу апартамент", "ищу виллу", "ищу дом", "ищу недвижимость", "куплю квартиру", "куплю недвижимость", "готов купить", "планирую купить", "недвижимость за рубежом", "инвестиции в недвижимость", "переезд", "переезжаем", "ВНЖ",
    "haus kaufen", "wohnung kaufen", "immobilie kaufen", "villa kaufen", "suche immobilie", "suche wohnung", "suche haus", "nach nordzypern ziehen", "auswandern nach nordzypern",
    "acheter une maison", "acheter un appartement", "acheter un bien immobilier", "huis kopen", "woning kopen", "vastgoed kopen", "αγορά ακινήτου",
    "قصد خرید", "دنبال خرید", "خرید ملک"
]

EXCLUDE_PHRASES = [
    "contact us", "call us", "whatsapp us", "dm for details", "our properties", "our projects", "property developer", "real estate agency", "estate agent", "realtor", "broker", "listing page", "available units", "new project", "developer", "we sell", "commission", "property portal", "for rent", "kiralık", "сдам", "сдается", "продам", "продается", "агентство", "застройщик", "риэлтор"
]

NEGATIVE_PHRASES = [
    "already bought", "we bought", "i bought", "already purchased", "purchase completed", "not buying", "no longer looking", "renting instead", "satın aldım", "aldık", "almaktan vazgeç", "купил", "купили", "передумал"
]

ROUTES = {
    "north_cyprus": "Prime Kıbrıs", "turkey": "Turkey Partner", "greece": "Golden Visa Partner", "portugal": "Golden Visa Partner", "cyprus": "Golden Visa Partner",
    "germany": "Germany Partner", "netherlands": "Netherlands Partner", "france": "France Partner", "montenegro": "Partner Network", "uk": "Partner Network", "belgium": "Partner Network", "lithuania": "Partner Network", "italy": "Partner Network", "spain": "Partner Network", "russia": "Partner Network", "kazakhstan": "Partner Network", "poland": "Partner Network", "czech_republic": "Partner Network", "austria": "Partner Network"
}
