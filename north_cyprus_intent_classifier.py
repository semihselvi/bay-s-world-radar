from __future__ import annotations

import re
from typing import Any

BUYER = "BUYER"
TENANT = "TENANT"
OWNER = "OWNER"
AGENT = "AGENT"
SERVICE = "SERVICE"
FINANCIAL = "FINANCIAL"
SPAM = "SPAM"
UNKNOWN = "UNKNOWN"

BUYER_TENANT_CLASSES = {BUYER, TENANT}


def _norm(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"https?://\S+", " ", text)
    return " ".join(text.split())


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def _count(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.I | re.S))


BUY_PATTERNS = [
    r"\blooking\s+to\s+buy\b", r"\bwant(?:ing)?\s+to\s+buy\b", r"\bready\s+to\s+buy\b",
    r"\bneed\s+to\s+buy\b", r"\bpurchase\s+(?:a\s+)?(?:property|apartment|flat|villa|house)\b",
    r"\bbuy\s+(?:an?\s+)?(?:property|apartment|flat|villa|house|studio)\b",
    r"\bsat[ıi]n\s+almak\s+istiyorum\b", r"\bsat[ıi]n\s+alaca[ğg][ıi]m\b", r"\balmak\s+istiyorum\b",
    r"\b(?:ev|daire|villa|konut)\s+(?:sat[ıi]n\s+)?almak\b",
    r"\bхочу\s+купить\b", r"\bкуплю\b", r"\bищу\s+на\s+покупку\b",
    r"\bищу\b.{0,80}\b(?:купить|для\s+покупки)\b", r"\bготов(?:а|ы)?\s+купить\b", r"\bхотим\s+купить\b",
    r"\bпокупк\w*\b",
]

TENANT_PATTERNS = [
    r"\blooking\s+to\s+rent\b", r"\bwant(?:ing)?\s+to\s+rent\b", r"\bneed\s+(?:a|an)\s+.*\b(?:to\s+rent|rental)\b",
    r"\bneed\s+(?:a|an)\s+(?:apartment|flat|villa|house|studio)\b.{0,80}\b(?:rent|rental|month|week)\b",
    r"\bkiral[ıi]k\s+(?:ev|daire|villa|st[üu]dyo)?\s*ar[ıi]yorum\b", r"\bkiralamak\s+istiyorum\b",
    r"\buzun\s+d[öo]nem\b.{0,80}\bar[ıi]yorum\b", r"\bg[üu]nl[üu]k\b.{0,80}\bar[ıi]yorum\b",
    r"\bхочу\s+снять\b", r"\bсниму\b", r"\bищу\b.{0,80}\b(?:в\s+аренду|для\s+аренды|снять)\b",
    r"\bнужн(?:а|ы)\b.{0,80}\b(?:в\s+аренду|на\s+долгий\s+срок|на\s+долгосрок|на\s+\d+\s+(?:дн|недел|месяц))",
    r"\bищу\s+(?:квартир\w*|апартамент\w*|дом\w*|вилл\w*|студи\w*|\d\s*\+\s*\d)\b.{0,120}\b(?:долгосроч|долгий\s+срок|долгосрок|помесяч|на\s+месяц|аренд)",
    r"\bищу\b.{0,100}\b(?:долгий\s+срок|долгосрок|долгосроч|помесяч|с\s+\d{1,2}\s+по\s+\d{1,2})\b",
    r"\bна\s+долгосрок\b", r"\bдолгосрочн\w*\s+аренд\w*\b",
    r"\bнужн(?:а|ы)\s+(?:квартир\w*|апартамент\w*|дом\w*|вилл\w*)\b.{0,80}\bв\s+аренду\b",
]

# Strong direction markers are kept separate so "от собственника" never decides
# BUYER/TENANT/OWNER by itself. Supply verbs beat rental-duration words, while a
# rental marker beats ambiguous "ищу квартиру" when no purchase verb is present.
SUPPLY_DIRECTION_PATTERNS = [
    r"\bi(?:'m| am)\s+(?:selling|renting\s+out)\b", r"\bwe\s+are\s+(?:selling|renting\s+out)\b",
    r"\b(?:evimi|dairemi|villam[ıi])\s+(?:sat[ıi]yorum|kiral[ıi]yorum)\b",
    r"\bпродаю\b", r"\bпродам\b", r"\bпрода[её]тся\b", r"\bпродажа\b",
    r"\bсдам\b", r"\bсдаю\b", r"\bсда[её]тся\b",
]

AMBIGUOUS_DEMAND_PATTERNS = [
    r"\blooking\s+for\s+(?:an?\s+)?(?:apartment|flat|villa|house|studio)\b",
    r"\b(?:ev|daire|villa|st[üu]dyo)\s+ar[ıi]yorum\b",
    r"\bищу\s+(?:квартир\w*|апартамент\w*|дом\w*|вилл\w*|студи\w*)\b",
    r"\bнужн(?:а|ы)\s+(?:квартир\w*|апартамент\w*|дом\w*|вилл\w*|студи\w*)\b",
]

OWNER_SUPPLY_PATTERNS = [
    r"\bfor\s+sale\b", r"\bfor\s+rent\b", r"\bi(?:'m| am)\s+(?:selling|renting\s+out)\b",
    r"\bmy\s+(?:apartment|flat|villa|house|studio)\b.{0,50}\b(?:for\s+sale|for\s+rent|available)\b",
    r"\bsat[ıi]l[ıi]k\b", r"\bkiral[ıi]k\b", r"\b(?:evimi|dairemi|villam[ıi])\s+(?:sat[ıi]yorum|kiral[ıi]yorum)\b",
    r"\bпродаю\b", r"\bпродам\b", r"\bпрода[её]тся\b", r"\bсдам\b", r"\bсдаю\b", r"\bсда[её]тся\b",
    r"\bмоя\s+(?:квартир\w*|вилл\w*|недвижимост\w*)\b.{0,60}\b(?:прода|сда)",
]

AGENT_TEXT_PATTERNS = [
    r"\brealtor\b", r"\breal\s+estate\s+agent\b", r"\bproperty\s+(?:consultant|advisor)\b", r"\bbroker\b",
    r"\bemlak[çc][ıi]\b", r"\bgayrimenkul\s+dan[ıi][şs]man", r"\bportf[öo]y\b",
    r"\bриелтор\b", r"\bриэлтор\b", r"\bагент\s+по\s+недвижимости\b", r"\bагентство\s+недвижимости\b",
    r"\bесть\s+(?:квартиры|апартаменты|виллы)\b", r"\bavailable\s+units?\b", r"\bmultiple\s+units?\b",
]

PROPERTY_PATTERNS = [
    r"\bproperty\b", r"\breal\s+estate\b", r"\bapartment\b", r"\bflat\b", r"\bvilla\b", r"\bhouse\b", r"\bstudio\b",
    r"\b[0-6]\s*\+\s*[0-3]\b",
    r"\bdaire\b", r"\bev\b", r"\bkonut\b", r"\bgayrimenkul\b", r"\bst[üu]dyo\b", r"\bvilla\b",
    r"\bквартир\w*\b", r"\bапартамент\w*\b", r"\bвилл\w*\b", r"\bдом\w*\b", r"\bстуди\w*\b", r"\bнедвижимост\w*\b",
]

NC_PATTERNS = [
    r"\bnorth(?:ern)?\s+cyprus\b", r"\btrnc\b", r"\bkktc\b", r"\biskele\b", r"\blong\s+beach\b",
    r"\bkyrenia\b", r"\bfamagust\w*\b", r"\bgazima[ğg]usa\b", r"\bgirne\b", r"\besentepe\b", r"\bbafra\b",
    r"\bkuzey\s+k[ıi]br[ıi]s\b", r"\bma[ğg]usa\b", r"\byenibo[ğg]azi[çc]i\b", r"\bbo[ğg]az\b", r"\b[öo]t[üu]ken\b",
    r"\bkarao[ğg]lano[ğg]lu\b", r"\bkaraoglanoglu\b", r"\balsancak\b",
    r"\bсеверн\w*\s+кипр\w*\b", r"\bcaesar\s+resort\b", r"\bgrand\s+sapphire\b", r"\broyal\s+sun\b", r"\briverside\s+life\b", r"\bisatis\b", r"\belysium\b", r"\bk['’]?saba\b",
    r"\bискел\w*\b", r"\bлонг\s+бич\b", r"\bкирени\w*\b", r"\bфамагуст\w*\b", r"\bгирн\w*\b", r"\bэсентеп\w*\b", r"\bбафр\w*\b", r"\bбоаз\w*\b", r"\bотюкен\w*\b",
    r"\bкараогланоглу\b", r"\bалсанджак\b",
]

FINANCIAL_DIRECT_PATTERNS = [
    r"\b(?:хочу\s+купить|куплю|покупаю|ищу\s+продавца)\s+usdt\b",
    r"\busdt\b.{0,80}\b(?:продавц|обмен|купить|покупаю|наличн)\b",
    r"\b(?:европейск\w*|зарубежн\w*)\s+(?:счет|сч[её]т)\w*\b",
    r"\bищу\s+человека\b.{0,100}\b(?:счет|сч[её]т)\w*\b",
    r"\bпереведу\s+всю\s+сумму\b", r"\bотблагодарю\b.{0,100}\b(?:счет|сч[её]т|перевод)\b",
    r"\bcrypto\s+exchange\b", r"\bbuy\s+usdt\b", r"\bneed\s+(?:a\s+)?(?:european|foreign)\s+bank\s+account\b",
    r"\bbank\s+account\b.{0,80}\btransfer\b",
    r"\bkripto\b.{0,50}\b(?:almak|satmak|bozdur|transfer)\b", r"\bbanka\s+hesab[ıi]\b.{0,80}\btransfer\b",
]

SERVICE_PATTERNS = [
    r"\bcleaning\s+(?:service|services|lady|person)\b", r"\bneed\s+(?:a\s+)?cleaner\b", r"\blooking\s+for\s+(?:a\s+)?cleaner\b",
    r"\btemizlik\s+(?:hizmeti|[çc]i|personeli)\b", r"\btemizlik[çc]i\s+ar[ıi]yorum\b",
    r"\bуборк\w*\b", r"\bклинин\w*\b",
    r"\bprivate\s+(?:english|math)\s+lesson", r"\benglish\s+tutor\b", r"\bözel\s+ders\b", r"\bрепетитор\w*\b",
    r"\bwater\s+purif", r"\bwater\s+filter", r"\bsu\s+ar[ıi]t", r"\bфильтр\w*\s+для\s+воды\b", r"\bочистк\w*\s+воды\b",
    r"\btemu\b", r"\bshein\b", r"\bbestsecret\b", r"\bдоставк\w*\b.{0,80}\b(?:temu|shein|amazon|zara)\b",
    r"\bcargo\b", r"\bkargo\b", r"\bкурьер\w*\b", r"\btaxi\b", r"\btransfer\s+service\b",
    r"\bваканси\w*\b", r"\bподработк\w*\b", r"\bищем\s+(?:водителя|сотрудника)\b", r"\bjob\s+offer\b", r"\bhiring\b",
]

SPAM_PATTERNS = [
    r"\bпередержк\w*\b", r"\bветеринар\w*\b", r"\bглист\w*\b", r"\bблох\w*\b",
    r"\bнайден\w*\s+на\s+улице\b", r"\bщен(?:ок|ки|ка)\b", r"\bкот[её]н(?:ок|ки|ка)\b", r"\bприют\w*\b",
    r"\busers\s+cannot\s+send\s+media\b", r"\bonly\s+admins?\s+can\s+post\b",
    r"\bпользовател\w*\b.{0,80}\bне\s+смогут\s+отправлять\b", r"\bтолько\s+администратор\w*\b.{0,50}\bписать\b",
    r"\bsmm\b", r"\bbuy\s+followers\b", r"\binstagram\s+followers\b", r"\bнакрутк\w*\b",
]

REPLY_PRICE_PATTERNS = [
    r"^\s*(?:price|fiyat|цена)\s*\??\s*$",
    r"\b(?:available|availability|any\s+units?|who\s+is\s+selling|кто\s+прода[её]т|есть\s+у\s+кого|varsa\s+yaz)\b",
]
SALE_CONTEXT_PATTERNS = [
    r"\bfor\s+sale\b", r"\bsat[ıi]l[ıi]k\b", r"\bпрода[её]тся\b", r"\bв\s+продаже\b", r"\bprice\b", r"\bцена\b",
]
RENT_CONTEXT_PATTERNS = [
    r"\bfor\s+rent\b", r"\bkiral[ıi]k\b", r"\bсда[её]тся\b", r"\bаренд\w*\b", r"\bmonthly\b", r"\bдолгосроч\w*\b", r"\bдолгосрок\b",
]

LONG_TERM_PATTERNS = [
    r"\blong[\s-]?term\b", r"\bmonthly\b", r"\bfor\s+\d+\s+months?\b",
    r"\buzun\s+d[öo]nem\b", r"\bayl[ıi]k\s+[öo]deme\b",
    r"\bдолгосроч\w*\b", r"\bдолгий\s+срок\b", r"\bдолгосрок\b", r"\bпомесячн\w*\b", r"\bна\s+(?:год|\d+\s+месяц)",
]
SHORT_TERM_PATTERNS = [
    r"\bshort[\s-]?term\b", r"\bdaily\b", r"\bweekly\b", r"\bfor\s+\d+\s+days?\b",
    r"\bg[üu]nl[üu]k\b", r"\bhaftal[ıi]k\b",
    r"\bкраткосроч\w*\b", r"\bпосуточн\w*\b", r"\bна\s+\d+\s+(?:дн|день|дней|недел)",
    r"\bс\s+\d{1,2}\s+по\s+\d{1,2}\b",
]
SHARED_PATTERNS = [
    r"\broommate\b", r"\bflatmate\b", r"\bshare\s+(?:an?\s+)?(?:apartment|flat|house)\b",
    r"\bev\s+arkada[şs][ıi]\b", r"\bbirlikte\s+kirala",
    r"\bищу\s+(?:соседа|соседку)\b", r"\bподселен\w*\b", r"\bвместе\s+снять\b", r"\bсовместн\w*\s+аренд",
]
MULTI_UNIT_PATTERNS = [
    r"\bmultiple\s+(?:apartments?|units?|flats?)\b", r"\b(?:two|three|four|\d+)\s+(?:apartments?|units?|flats?)\b",
    r"\bbirden\s+fazla\s+(?:daire|ev|konut)\b", r"\b(?:iki|üç|uc|\d+)\s+(?:daire|ev)\b",
    r"\bнесколько\s+(?:квартир|апартамент|студи)\w*\b", r"\b(?:две|три|четыре|\d+)\s+(?:квартир|апартамент|студи)\w*\b",
    r"\b(?:3\+1|2\+1|1\+1)\b.{0,80}\b(?:рядом|близко|nearby|yak[ıi]n)\b.{0,80}\b(?:квартир|units?|daire)",
]

OWNER_DIRECT_PATTERNS = [
    r"\bowner\s+only\b", r"\bdirect\s+from\s+owner\b", r"\bfrom\s+owner\b", r"\bno\s+agents?\b",
    r"\bsahibinden\b", r"\bemlak[çc][ıi]\s+olmadan\b",
    r"\bот\s+собственника\b", r"\bбез\s+(?:агентов|риелторов)\b",
]
FURNISHED_PATTERNS = [r"\bfurnished\b", r"\be[şs]yal[ıi]\b", r"\bмеблирован\w*\b", r"\bс\s+мебелью\b"]
UNFURNISHED_PATTERNS = [r"\bunfurnished\b", r"\be[şs]yas[ıi]z\b", r"\bбез\s+мебели\b"]
URGENT_PATTERNS = [r"\burgent\b", r"\basap\b", r"\bacil\b", r"\bсрочно\b"]
READY_TITLE_PATTERNS = [
    r"\bready\s+(?:title|deed)\b", r"\btitle\s+ready\b", r"\bdeed\s+ready\b",
    r"\btapu\s+haz[ıi]r\b", r"\bko[çc]an\s+haz[ıi]r\b",
    r"\bготов\w*\s+титул\w*\b", r"\bтитул\w*\s+готов\w*\b",
]
GROUND_FLOOR_PATTERNS = [
    r"\bground\s+floor\b", r"\bzemin\s+kat\b", r"\bgiri[şs]\s+kat\b",
    r"\bнулев\w*\s+этаж\w*\b", r"\bна\s+первом\s+этаже\b",
]
CAESAR_ACCEPTED_PATTERNS = [
    r"\bcaesar\s+resort\b.{0,80}\b(?:acceptable|ok|works?|consider|suitable)\b",
    r"\b(?:acceptable|ok|works?|consider|suitable)\b.{0,80}\bcaesar\s+resort\b",
    r"\bcaesar\s+resort\b.{0,80}\b(?:рассмотр\w*|подход\w*|можно|устро\w*)\b",
    r"\b(?:рассмотр\w*|подход\w*|можно|устро\w*)\b.{0,80}\bcaesar\s+resort\b",
    r"\bcaesar\s+resort\b.{0,80}\b(?:olur|uygun|d[üu][şs][üu]nebilirim)\b",
]
PREFERENCE_PATTERNS = [
    ("NEAR_UNIVERSITY", [r"\bnear\s+(?:the\s+)?university\b", r"\b[üu]niversiteye\s+yak[ıi]n\b", r"\bблиз\w*\s+к\s+университет\w*\b"]),
    ("CENTRAL", [r"\bcity\s+cent(?:er|re)\b", r"\bmerkez\b", r"\bцентр\w*\b"]),
    ("SEA", [r"\bnear\s+(?:the\s+)?sea\b", r"\bsea\s+view\b", r"\bdenize\s+yak[ıi]n\b", r"\bморе\b"]),
]

REGION_MAP = [
    ("Long Beach", [r"\blong\s+beach\b", r"\bлонг\s+бич\b"]),
    ("İskele", [r"\biskele\b", r"\bискел\w*\b"]),
    ("Gazimağusa", [r"\bfamagust\w*\b", r"\bgazima[ğg]usa\b", r"\bma[ğg]usa\b", r"\bфамагуст\w*\b"]),
    ("Girne", [r"\bkyrenia\b", r"\bgirne\b", r"\bкирени\w*\b", r"\bгирн\w*\b"]),
    ("Karaoğlanoğlu", [r"\bkarao[ğg]lano[ğg]lu\b", r"\bkaraoglanoglu\b", r"\bкараогланоглу\b"]),
    ("Alsancak", [r"\balsancak\b", r"\bалсанджак\b"]),
    ("Esentepe", [r"\besentepe\b", r"\bэсентеп\w*\b"]),
    ("Bafra", [r"\bbafra\b", r"\bбафр\w*\b"]),
    ("Yeniboğaziçi", [r"\byenibo[ğg]azi[çc]i\b", r"\bени\s*богазич\w*\b"]),
    ("Boğaz", [r"\bbo[ğg]az\b", r"\bбоаз\w*\b"]),
    ("Ötüken", [r"\b[öo]t[üu]ken\b", r"\bотюкен\w*\b"]),
]


def _property_type(text: str) -> str:
    rooms = []
    for raw in re.findall(r"\b([0-6]\s*\+\s*[0-3])\b", text):
        room = raw.replace(" ", "")
        if room not in rooms:
            rooms.append(room)
    if len(rooms) >= 2:
        return "_OR_".join(rooms[:3])
    if len(rooms) == 1:
        return rooms[0]

    mapping = [
        ("STUDIO", [r"\bstudio\b", r"\bst[üu]dyo\b", r"\bстуди\w*\b"]),
        ("VILLA", [r"\bvilla\b", r"\bвилл\w*\b"]),
        ("APARTMENT", [r"\bapartment\b", r"\bflat\b", r"\bdaire\b", r"\bквартир\w*\b", r"\bапартамент\w*\b"]),
        ("HOUSE", [r"\bhouse\b", r"\bev\b", r"\bдом\w*\b"]),
    ]
    kinds = [label for label, pats in mapping if _matches(text, pats)]
    return "/".join(dict.fromkeys(kinds))


def _budget(text: str) -> str:
    patterns = [
        r"(?:£|€|\$)\s?\d[\d\s,.]*(?:k|m)?",
        r"\b\d[\d\s,.]*(?:k)?\s?(?:gbp|eur|usd|pounds?|euros?|dollars?)\b",
        r"\b(?:budget|bütçe|бюджет)\s*[:\-]?\s*((?:£|€|\$)?\s?\d[\d\s,.]*(?:k|m)?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return (m.group(1) if m.lastindex else m.group(0)).strip()
    return ""


def _move_window(text: str) -> str:
    patterns = [
        r"\bс\s+\d{1,2}\s+по\s+\d{1,2}\s+[а-яa-zçğıöşü]+\b",
        r"\b\d{1,2}\s*[-–]\s*\d{1,2}\s+(?:september|october|november|december|eyl[üu]l|ekim|kas[ıi]m|aral[ıi]k)\b",
        r"\b(?:this|next)\s+month\b", r"\bbu\s+ay\b", r"\bgelecek\s+ay\b",
        r"\bв\s+этом\s+месяце\b", r"\bв\s+следующем\s+месяце\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0).strip()
    return ""


def _regions(text: str) -> list[str]:
    out = []
    for label, pats in REGION_MAP:
        if _matches(text, pats):
            out.append(label)
    return out


def extract_requirements(item: dict[str, Any]) -> dict[str, Any]:
    own = _norm(item.get("text"))
    context = _norm(" ".join(str(item.get(k, "")) for k in ("text", "reply_context", "telegram_chat", "title")))
    prefs = []
    if _matches(own, OWNER_DIRECT_PATTERNS):
        prefs.append("OWNER_DIRECT")
    if _matches(own, FURNISHED_PATTERNS):
        prefs.append("FURNISHED")
    if _matches(own, UNFURNISHED_PATTERNS):
        prefs.append("UNFURNISHED")
    for label, pats in PREFERENCE_PATTERNS:
        if _matches(own, pats):
            prefs.append(label)
    if _matches(own, LONG_TERM_PATTERNS):
        prefs.append("LONG_TERM")
    if _matches(own, SHORT_TERM_PATTERNS):
        prefs.append("SHORT_TERM")
    if _matches(own, URGENT_PATTERNS):
        prefs.append("URGENT")
    if _matches(own, READY_TITLE_PATTERNS):
        prefs.append("READY_TITLE")
    if _matches(own, GROUND_FLOOR_PATTERNS):
        prefs.append("GROUND_FLOOR")
    if _matches(own, CAESAR_ACCEPTED_PATTERNS):
        prefs.append("CAESAR_RESORT_ACCEPTED")
    regions = _regions(context)
    if "Karaoğlanoğlu" in regions and "Alsancak" in regions:
        prefs.append("KARAOGLANOGLU_ALSANCAK")
    return {
        "regions": regions,
        "property_type": _property_type(own or context),
        "budget": _budget(own),
        "move_window": _move_window(own),
        "preferences": list(dict.fromkeys(prefs)),
    }


def _tenant_result(item: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    own = _norm(item.get("text"))
    subtypes = []
    if _matches(own, LONG_TERM_PATTERNS):
        subtypes.append("LONG_TERM_TENANT")
    if _matches(own, SHORT_TERM_PATTERNS):
        subtypes.append("SHORT_TERM_TENANT")
    if _matches(own, SHARED_PATTERNS):
        subtypes.append("SHARED_RENTAL")
    if _matches(own, MULTI_UNIT_PATTERNS):
        subtypes.append("MULTI_UNIT_RENTAL")
    confidence = 72 + (8 if req["regions"] else 0) + (5 if req["property_type"] else 0) + (5 if req["budget"] else 0)
    confidence += 6 if req["move_window"] else 0
    if "LONG_TERM_TENANT" in subtypes or "SHORT_TERM_TENANT" in subtypes:
        confidence += 5
    if "MULTI_UNIT_RENTAL" in subtypes:
        confidence += 4
    if "SHARED_RENTAL" in subtypes:
        confidence = min(confidence, 78)
    if "URGENT" in req["preferences"]:
        confidence += 3
    if "OWNER_DIRECT" in req["preferences"]:
        confidence += 3
    return _result(TENANT, subtypes, min(99, confidence), ["explicit_rental_direction", "property_context", "north_cyprus_context"], req)


def classify_intent(item: dict[str, Any]) -> dict[str, Any]:
    own = _norm(item.get("text"))
    context = _norm(" ".join(str(item.get(k, "")) for k in ("text", "reply_context", "telegram_chat", "title")))
    req = extract_requirements(item)
    property_signal = _matches(context, PROPERTY_PATTERNS)
    nc_signal = _matches(context, NC_PATTERNS)

    explicit_buy = _matches(own, BUY_PATTERNS)
    explicit_tenant = _matches(own, TENANT_PATTERNS)
    ambiguous_demand = _matches(own, AMBIGUOUS_DEMAND_PATTERNS)
    owner_supply = _matches(own, OWNER_SUPPLY_PATTERNS)
    supply_direction = _matches(own, SUPPLY_DIRECTION_PATTERNS)
    explicit_agent = _matches(_norm(" ".join([str(item.get("author", "")), own])), AGENT_TEXT_PATTERNS)
    publisher_type = str(item.get("publisher_type") or "").upper().strip()

    if _matches(own, FINANCIAL_DIRECT_PATTERNS) and not (explicit_buy and property_signal):
        return _result(FINANCIAL, [], 99, ["financial_transaction"], req)
    if _matches(own, SERVICE_PATTERNS) and not (explicit_buy or explicit_tenant):
        return _result(SERVICE, [], 96, ["service_or_job"], req)
    if _matches(own, SPAM_PATTERNS):
        return _result(SPAM, [], 98, ["spam_or_nonproperty"], req)

    if publisher_type in {"AGENT", "INVENTORY_SOURCE"} or item.get("suspected_agent") or explicit_agent:
        return _result(AGENT, [], max(90, int(item.get("publisher_confidence") or 0)), ["publisher_agent"], req)

    # Supply direction has priority over rental-duration words. Example:
    # "Сдам квартиру на долгосрок" is OWNER, while "Ищу квартиру на долгосрок"
    # is TENANT. "от собственника" never determines the direction on its own.
    if supply_direction and property_signal:
        conf = max(88, int(item.get("publisher_confidence") or 0)) if publisher_type == "OWNER" else 86
        return _result(OWNER, [], conf, ["property_supply_direction"], req)

    # Rental direction wins over ambiguous housing demand when there is no explicit
    # purchase verb. This prevents long-term rental searches from becoming BUYER.
    if explicit_tenant and not explicit_buy and property_signal and nc_signal:
        return _tenant_result(item, req)

    if explicit_buy and property_signal and nc_signal:
        confidence = 74
        reasons = ["explicit_purchase_direction", "property_context", "north_cyprus_context"]
        confidence += 8 if req["regions"] else 0
        confidence += 6 if req["property_type"] else 0
        confidence += 6 if req["budget"] else 0
        confidence += 5 if "OWNER_DIRECT" in req["preferences"] else 0
        confidence += 4 if req["move_window"] else 0
        confidence += 3 if "URGENT" in req["preferences"] else 0
        return _result(BUYER, [], min(99, confidence), reasons, req)

    if explicit_tenant and property_signal and nc_signal:
        return _tenant_result(item, req)

    if _matches(own, SHARED_PATTERNS) and property_signal and nc_signal:
        return _result(TENANT, ["SHARED_RENTAL"], 68, ["shared_rental_direction", "property_context", "north_cyprus_context"], req)

    reply = _norm(item.get("reply_context"))
    if reply and _matches(own, REPLY_PRICE_PATTERNS) and property_signal and nc_signal:
        if _matches(reply, RENT_CONTEXT_PATTERNS):
            return _result(TENANT, [], 70, ["reply_context_rental_request", "property_context", "north_cyprus_context"], req)
        if _matches(reply, SALE_CONTEXT_PATTERNS):
            return _result(BUYER, [], 70, ["reply_context_purchase_request", "property_context", "north_cyprus_context"], req)

    if owner_supply and property_signal:
        conf = max(86, int(item.get("publisher_confidence") or 0)) if publisher_type == "OWNER" else 82
        return _result(OWNER, [], conf, ["property_supply_direction"], req)

    # "Ищу квартиру от собственника" is demand, but without buy/rent direction it
    # is intentionally UNKNOWN. Owner-direct wording is a preference, not a sale.
    if ambiguous_demand and property_signal and nc_signal:
        return _result(UNKNOWN, [], 62 if "OWNER_DIRECT" in req["preferences"] else 58, ["housing_demand_direction_ambiguous"], req)

    return _result(UNKNOWN, [], 30 if (property_signal and nc_signal) else 0, ["insufficient_direction"], req)


def _result(intent_class: str, subtypes: list[str], confidence: int, reasons: list[str], requirements: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_class": intent_class,
        "intent_subtypes": list(dict.fromkeys(subtypes)),
        "intent_confidence": int(max(0, min(100, confidence))),
        "intent_reasons": reasons,
        "requirements": requirements,
    }


def is_buyer_catcher_eligible(intent: dict[str, Any]) -> bool:
    return intent.get("intent_class") in BUYER_TENANT_CLASSES


def display_intent(intent_or_lead: dict[str, Any]) -> str:
    intent_class = str(intent_or_lead.get("intent_class") or "UNKNOWN")
    subtypes = list(intent_or_lead.get("intent_subtypes") or [])
    if intent_class == TENANT and subtypes:
        ordered = [x for x in ("LONG_TERM_TENANT", "SHORT_TERM_TENANT", "MULTI_UNIT_RENTAL", "SHARED_RENTAL") if x in subtypes]
        return " + ".join(ordered) if ordered else TENANT
    return intent_class
