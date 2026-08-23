import north_cyprus_focus as nf


def _extend(target, values):
    for value in values:
        if value not in target:
            target.append(value)


# Market/location names used by target audiences. Without these, a genuine buyer
# message can pass language intent checks yet fail the North-Cyprus context gate.
_extend(nf.NC_LOCATION_PATTERNS, [
    r"\bchypre du nord\b", r"\bnoord[- ]cyprus\b", r"\bcypr p[óo]łnocn(?:y|ego|ym)\b",
    r"\bпівнічн(?:ий|ого)\s+кіпр\b", r"\bnorra cypern\b", r"\bnord[- ]kypros\b", r"\bnordcypern\b",
    r"\bcipro(?: del)? nord\b", r"\bchipre del norte\b", r"\bchipre do norte\b", r"\bsevern[íi] kypr\b",
    r"\bp[õo]hja[- ]k[üu]pros\b", r"شمال قبرص", r"قبرص الشمالية", r"قبرص الشماليه",
    r"צפון קפריסין", r"קפריסין הצפונית", r"\bсолтүстік кипр\b",
])

_extend(nf.PROPERTY_PATTERNS, [
    r"\bmieszkan", r"\bdom\b", r"\bnieruchomo", r"\bwilla\b", r"\bквартир", r"\bбудинок\b", r"\bвілл", r"\bнерухом",
    r"\bbostad\b", r"\bl[äa]genhet\b", r"\bfastighet\b", r"\bbolig\b", r"\bleilighet\b", r"\blejlighed\b",
    r"\bcasa\b", r"\bappartament", r"\bimmobile\b", r"\bpiso\b", r"\binmueble\b", r"\bapartamento\b",
    r"\bim[óo]vel\b", r"\bmoradia\b", r"\bbyt\b", r"\bd[ůu]m\b", r"\bnemovitost", r"\bkorter\b", r"\bmaja\b", r"\bkinnisvara\b",
    r"شقة", r"عقار", r"فيلا", r"منزل", r"דירה", r"בית", r"וילה", r"נכס", r"\bпәтер\b", r"\bүй\b",
])

# Strong direct buyer intent across additional target languages.
_extend(nf.STRONG_BUYER_PATTERNS, [
    r"\bchc[ęe](?:my)? kupi[ćc]\b", r"\bszukam (?:mieszkania|domu|willi|nieruchomości)\b", r"\bplanuj[ęe] kupi[ćc]\b",
    r"\bхочу купити\b", r"\bхочемо купити\b", r"\bшукаю (?:квартиру|будинок|віллу|нерухомість)\b", r"\bпланую купити\b",
    r"\bvill köpa\b", r"\bfunderar på att köpa\b", r"\bletar efter (?:bostad|lägenhet|hus|villa|fastighet)\b", r"\bköpa (?:bostad|lägenhet|hus|villa|fastighet)\b",
    r"\bønsker å kjøpe\b", r"\bvil kjøpe\b", r"\bleter etter (?:bolig|leilighet|hus|villa)\b", r"\bønsker at købe\b", r"\bvil købe\b", r"\bkøbe (?:bolig|lejlighed|hus|villa)\b",
    r"\bvoglio comprare\b", r"\bvorrei comprare\b", r"\bcerco (?:casa|appartamento|villa|immobile)\b", r"\bacquistare (?:casa|appartamento|immobile)\b",
    r"\bquiero comprar\b", r"\bbusco (?:piso|casa|apartamento|villa|inmueble)\b", r"\bcomprar (?:piso|casa|apartamento|villa|inmueble)\b",
    r"\bquero comprar\b", r"\bprocuro (?:casa|apartamento|moradia|imóvel)\b", r"\bcomprar (?:casa|apartamento|moradia|imóvel)\b",
    r"\bchci koupit\b", r"\bhled[áa]m (?:byt|dům|vilu|nemovitost)\b", r"\bsoovin osta\b", r"\btahan osta\b", r"\botsin (?:korterit|maja|villat|kinnisvara)\b",
    r"أريد شراء", r"اريد شراء", r"أبحث عن (?:شقة|عقار|فيلا|منزل)", r"ابحث عن (?:شقة|عقار|فيلا|منزل)", r"أرغب في شراء",
    r"רוצה לקנות", r"מעוניין(?:ת)? לקנות", r"מחפש(?:ת)? (?:דירה|בית|וילה|נכס)", r"сатып алғым келеді", r"пәтер іздеймін", r"үй іздеймін",
    # Proxy buyers: the poster is asking for a parent/partner/friend who is a real buyer.
    r"\bmy (?:mother|mom|father|dad|parents?|husband|wife|partner|friend|father[- ]in[- ]law|mother[- ]in[- ]law) (?:wants?|is looking|plans?) to buy\b",
    r"\b(?:mother|mom|father|dad|parents?|husband|wife|partner|friend|father[- ]in[- ]law|mother[- ]in[- ]law).*looking to buy\b",
    r"\b(?:annem|babam|eşim|esim|arkadaşım|arkadasim|ailem).*(?:sat[ıi]n almak istiyor|ev almak istiyor|daire arıyor|villa arıyor)\b",
    r"\b(?:моя |мой |мои )?(?:мама|папа|родители|муж|жена|друг|подруга).*(?:хочет|хотят|планирует|планируют).*(?:купить|приобрести)\b",
    r"\b(?:мама|папа|родители|муж|жена|друг|подруга).*ищ(?:ет|ут).*(?:квартир|дом|вилл|недвижимост)\b",
    r"\b(?:meine mutter|mein vater|meine eltern|mein mann|meine frau|mein freund|meine freundin).*(?:will|wollen|möchte|möchten).*(?:kaufen|wohnung|haus|immobilie)\b",
    r"\b(?:ma mère|mon père|mes parents|mon mari|ma femme|mon ami|mon amie).*(?:veut|veulent|souhaite|souhaitent).*(?:acheter|maison|appartement|bien)\b",
    r"\b(?:moja mama|mój tata|moi rodzice|mój mąż|moja żona|mój znajomy).*(?:chce|chcą).*(?:kupić|mieszkanie|dom|nieruchomo)\b",
])

_extend(nf.REQUEST_BUYER_PATTERNS, [
    r"\bjaki (?:rejon|projekt).*kupi", r"\bile kosztuje", r"\bcena.*(?:mieszkan|dom|willa)",
    r"\bякий район.*куп", r"\bскільки коштує", r"\bціна.*(?:квартир|будинок|вілл)",
    r"\bvilket område.*köp", r"\bvad kostar", r"\bpris.*(?:bostad|lägenhet|hus|villa)",
    r"\bhvilket område.*kjøp", r"\bhva koster", r"\bpris.*(?:bolig|leilighet|hus|villa)",
    r"\bquanto costa", r"\bprezzo.*(?:casa|appartamento|villa)", r"\bcu[áa]nto cuesta", r"\bprecio.*(?:piso|casa|apartamento|villa)",
    r"\bquanto custa", r"\bpre[çc]o.*(?:casa|apartamento|moradia)", r"\bmis maksab", r"\bhind.*(?:korter|maja|kinnisvara)",
    r"كم سعر", r"ما سعر", r"السعر.*(?:شقة|عقار|فيلا)", r"כמה עולה", r"מחיר.*(?:דירה|בית|וילה|נכס)",
])

_extend(nf.PERSONAL_PATTERNS, [
    r"\bja\b", r"\bmy\b", r"\bchc[ęe]\b", r"\bszukam\b", r"\bя\b", r"\bми\b", r"\bхочу\b", r"\bшукаю\b", r"\bмоя\b",
    r"\bjag\b", r"\bvi\b", r"\bmin\b", r"\bjeg\b", r"\bio\b", r"\bnoi\b", r"\bmi\b", r"\bnosotros\b", r"\beu\b", r"\bn[óo]s\b",
    r"\bmina\b", r"\bmeie\b", r"\bsoovin\b", r"\botsin\b", r"أنا", r"نحن", r"أريد", r"ابحث", r"أبحث", r"אני", r"אנחנו", r"רוצה", r"מחפש",
])
