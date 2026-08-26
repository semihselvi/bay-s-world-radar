import re

import north_cyprus_focus as nf
import north_cyprus_language_expansion  # patches multilingual location/property/buyer patterns


_original_promotional_service_ad = nf._promotional_service_ad

# Real buyer language observed in live North Cyprus groups. These are layered
# here so every guarded Hunter / Recall / Catcher / Recovery lane sees them
# without loosening the generic seller filters.
RUSSIAN_STRONG_BUYER_PATTERNS = [
    r"\bсрочно\s+ищу(?:\s+на\s+покупку)?\b",
    r"\bищу\s+на\s+покупку\b",
    r"\bищу\s+(?:на\s+покупку\s+)?(?:отдельно\s*стоящую|отдельностоящую)?\s*вилл",
    r"\bнужна\s+(?:отдельно\s*стоящая|отдельностоящая)?\s*вилл",
    r"\bкуплю\s+(?:квартир\w*|апартамент\w*|дом\w*|вилл\w*|студи\w*|недвижимост\w*)\b",
    r"\bищу\s+.*\bтолько\s+от\s+собственника\b",
    r"\bищу\s+.*\b(?:купить|для\s+покупки)\b",
    r"\bклиент\s+ищет\b",
]

RUSSIAN_REQUEST_BUYER_PATTERNS = [
    r"\bтолько\s+от\s+собственника\b",
    r"\bот\s+собственника\b",
    r"\bбез\s+агент(?:ов|ств)?\b",
    r"\bна\s+покупку\b",
    r"\bклиент\s+ищет\b",
]

RUSSIAN_NC_LOCATION_PATTERNS = [
    r"\bискеле\b",
    r"\bбоаз\b",
    r"\bбогаз\b",
    r"\bотюкен\b",
    r"\bотукен\b",
    r"\bйени\s*боазичи\b",
    r"\bени\s*боазичи\b",
    r"\bйенибоазичи\b",
    r"\bенибоазичи\b",
    r"\bгазимагуса\b",
    r"\bфамагуста\b",
    r"\bгирне\b",
    r"\bэсентепе\b",
    r"\bтатлысу\b",
    r"\bбафра\b",
    r"\bлапта\b",
    r"\bалсанджак\b",
    r"\bкараогланоглу\b",
]

RUSSIAN_CONCRETE_BUYER_PATTERNS = [
    r"\bсрочно\b",
    r"\bтолько\s+от\s+собственника\b",
    r"\bот\s+собственника\b",
    r"\bотдельно\s*стоящ(?:ая|ую|ей)\b",
    r"\bотдельностоящ(?:ая|ую|ей)\b",
]

for _pattern in RUSSIAN_STRONG_BUYER_PATTERNS:
    if _pattern not in nf.STRONG_BUYER_PATTERNS:
        nf.STRONG_BUYER_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_REQUEST_BUYER_PATTERNS:
    if _pattern not in nf.REQUEST_BUYER_PATTERNS:
        nf.REQUEST_BUYER_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_NC_LOCATION_PATTERNS:
    if _pattern not in nf.NC_LOCATION_PATTERNS:
        nf.NC_LOCATION_PATTERNS.append(_pattern)

for _pattern in RUSSIAN_CONCRETE_BUYER_PATTERNS:
    if _pattern not in nf.CONCRETE_PATTERNS:
        nf.CONCRETE_PATTERNS.append(_pattern)


RECRUITMENT_PATTERNS = [
    r"join\s+snc\s+field\s+operatives",
    r"field representatives?",
    r"offline/online field representatives?",
    r"skills we(?:'|’)re looking for",
    r"roles may include",
    r"strictly commission[- ]based",
    r"not salaried",
    r"work,? learn and earn",
    r"sales\s*&\s*communication",
    r"customer\s*&\s*client relations",
    r"it\s*&\s*digital skills",
    r"photography,? video\s*&\s*content creation",
    r"ads management\s*&\s*lead generation",
    r"apartment viewings",
    r"assisting clients",
    r"sourcing apartments directly from owners",
    r"generating leads",
    r"helping close deals",
    r"name:\s*.*location:\s*.*skills",
    r"limited spots available",
    r"@snccenter02\b",
]

# Telegram group administration / moderation notices. These can be posted by a
# human admin account and therefore look like normal user messages to Telethon,
# but they carry zero buyer intent. Keep patterns action-oriented and narrow so
# ordinary discussion about sending a link or photo is not suppressed.
MODERATION_NOTICE_PATTERNS = [
    # Russian
    r"\bс этого момента\b.*\bвсе пользователи\b",
    r"\bпользовател(?:и|ям)\b.*\bне смогут\b.*\bотправлять\b",
    r"\bне смогут отправлять\b.*\b(?:медиа|фото|видео|файлы|ссылки)\b",
    r"\bзапрещено отправлять\b.*\b(?:медиа|фото|видео|файлы|ссылки)\b",
    r"\bтолько администратор(?:ы|ам)?\b.*\b(?:отправлять|писать)\b",
    r"\bгруппа\b.*\b(?:закрыта для сообщений|только для чтения)\b",
    # English
    r"\ball (?:users|members)\b.*\b(?:cannot|can't|won't be able to) send\b.*\b(?:media|photos?|videos?|files?|links?)\b",
    r"\bonly admins? can (?:send|post|write)\b",
    r"\bgroup (?:is|has been) (?:set to )?read[- ]only\b",
    # Turkish
    r"\btüm (?:kullanıcılar|üyeler)\b.*\b(?:medya|fotoğraf|video|dosya|link|bağlantı)\b.*\bgönderemeyecek\b",
    r"\b(?:medya|fotoğraf|video|dosya|link|bağlantı) gönderimi\b.*\b(?:yasaklandı|kapatıldı|durduruldu)\b",
    r"\byalnızca yöneticiler\b.*\b(?:mesaj|medya|link|bağlantı) gönderebilir\b",
]

# Generic money-making / side-income DM bait. Keep this narrow so legitimate
# property investment discussions about rental income, yield or ROI are not blocked.
EARNING_SPAM_PATTERNS = [
    r"\bхочешь\s+узнать\s+(?:интересн\w+\s+)?способ\s+заработка\b",
    r"\bинтересн\w+\s+способ\s+заработка\b",
    r"\bспособ\s+заработка\b",
    r"\bзаработок\s+(?:без\s+вложений|из\s+дома|онлайн)\b",
    r"\bкак\s+заработать\b",
    r"\bхочешь\s+зарабатывать\b",
    r"\bпиши\s+(?:мне\s+)?в\s+(?:лс|личку)\b",
    r"\bнапиши\s+(?:мне\s+)?в\s+(?:лс|личку)\b",
]

# High-volume job spam observed in North Cyprus chat groups. These messages often
# contain money figures and personal wording, which can accidentally satisfy the
# generic concrete/personal gates unless rejected before buyer scoring.
JOB_SPAM_PATTERNS = [
    r"\bнужен\s+водитель\b",
    r"\bнужен\s+человек\b",
    r"\bработа\s+(?:в|по)\s+(?:твоем|вашем|месту|городу)\b",
    r"\bваканси\w*\b",
    r"\bшабашк\w*\b",
    r"\bоплата\s+\d[\d\s.,]*(?:доллар|руб|тысяч|₽|\$)?\b",
    r"\b\d+\s*(?:тысяч|доллар(?:ов)?|руб(?:лей)?)\s+(?:за|в)\s+\d+\s*час",
    r"\bработа\s+без\s+опыта\b",
    r"\bподработка\b",
    r"\bежедневн\w*\s+оплата\b",
    r"\bhiring\b",
    r"\bvacanc(?:y|ies)\b",
    r"\bdaily pay\b",
    r"\bjob offer\b",
]

# SMM/follower/engagement services are unrelated to property buyer intent. Farsi
# variants matter because large Iranian North Cyprus groups contain this traffic.
SOCIAL_MEDIA_SERVICE_PATTERNS = [
    r"خدمات\s+(?:حرفه.?ای|تخصصی).*اینستاگرام",
    r"خدمات.*شبکه.?های\s+اجتماعی",
    r"فالوور\s+(?:واقعی|فیک)",
    r"لایک\s+و\s+ویو",
    r"افزایش\s+تعامل",
    r"اینستاگرام",
    r"تلگرام",
    r"تیک.?تاک",
    r"یوتیوب",
    r"\bsmm\b",
    r"\bsocial media (?:service|services|marketing)\b",
    r"\bbuy followers\b",
    r"\binstagram followers\b",
    r"\btelegram members\b",
    r"\bнакрут(?:ка|ить).*подписчик",
    r"\bпродвижение.*(?:instagram|telegram|tiktok|youtube)\b",
]

# Foreign-market property advertisements can be posted inside a North Cyprus
# community. The group title alone must not turn an Oman/Dubai/etc sales ad into
# a North Cyprus buyer. Keep this focused on clearly promotional combinations.
FOREIGN_PROPERTY_PROMO_PATTERNS = [
    r"اقامت\s+عمان.*خرید\s+ملک",
    r"عمان.*(?:پروژه|پروژه.?های|پیش.?فروش|اقساط|مالکیت\s*۱۰۰|مالکیت\s*100|مسقط)",
    r"مسقط.*(?:خرید\s+ملک|پروژه|پیش.?فروش|مالکیت|اقساط)",
    r"\boman\b.*\b(?:residency|property|project|off[- ]plan|installment)\b",
    r"\bmuscat\b.*\b(?:property|project|off[- ]plan|ownership|installment)\b",
]

# Pet adoption/foster posts frequently use Russian phrases such as "ищут дом".
# That wording must never be treated as a house-search signal when it appears
# together with veterinary/foster/animal-care context.
PET_ADOPTION_PATTERNS = [
    r"\bищ(?:ет|ут)\s+(?:новый\s+)?дом\b",
    r"\bпередержк\w*\b",
    r"\bветеринар\w*\b",
    r"\bглист\w*\b",
    r"\bблох\w*\b",
    r"\b(?:найден|найдены|нашли)\b.*\bна\s+улиц\w*\b",
    r"\b(?:щенок|щенки|котенок|котята|собак\w*|кошк\w*)\b",
    r"\b(?:приют|сахиплендир|sahiplendir|yuva arıyor|geçici yuva|veteriner|iç dış parazit)\b",
    r"\b(?:adopt(?:ion)?|foster|forever home|veterinar(?:y|ian)|dewormed|fleas?|pupp(?:y|ies)|kittens?)\b",
]

# Retail parcel/cargo delivery advertisements can mention cities, prices and
# "home" products, which otherwise look concrete enough for buyer scoring.
# Require a delivery action plus retail/logistics context; do not reject a normal
# property discussion that only says "delivery date".
DELIVERY_SERVICE_PATTERNS = [
    r"\bдоставк\w*\s+до\s+(?:вашего|твоего)?\s*город\w*\b",
    r"\bмогу\s+достав(?:ить|лять)\b",
    r"\b(?:temu|shein|zara|amazon|bestsecret)\b",
    r"\bonline\s+stores?\b",
    r"\bдо\s+\d+(?:[.,]\d+)?\s*кг\b",
    r"\b(?:посылк\w*|курьер\w*|cargo|parcel|courier)\b",
    r"\b(?:kargo|kurye|paket teslimat|alışveriş teslimat)\b",
]

# Requests for a stranger with a European/foreign bank account to receive or
# transfer funds are financial intermediary requests, not property buyer leads.
# Require an account signal plus transfer/reward/help language so genuine buyer
# questions about paying for property from abroad are not suppressed.
FINANCIAL_INTERMEDIARY_PATTERNS = [
    r"\b(?:европейск|зарубежн|иностранн)\w*\s+(?:банк\w*\s+)?счет\w*\b",
    r"\bищу\s+человек\w*\b.*\bсчет\w*\b",
    r"\bготов\w*\s+помочь\s+с\s+(?:зарубежн|европейск|иностранн)\w*\s+счет\w*\b",
    r"\bпереведу\s+всю\s+сумм\w*\b",
    r"\bперевести\s+всю\s+сумм\w*\b",
    r"\bудобн\w*\s+способ\w*\b",
    r"\bотблагодар\w*\b",
    r"\b(?:european|foreign|overseas)\s+(?:bank\s+)?account\b",
    r"\b(?:send|transfer)\s+the\s+(?:full|whole)\s+amount\b",
    r"\b(?:avrupa|yurt dışı|yurtdışı)\s+(?:banka\s+)?hesab\w*\b",
    r"\b(?:tüm|bütün)\s+(?:tutarı|parayı)\s+(?:hemen\s+)?(?:gönder|aktar)\w*\b",
]


def promotional_service_or_recruitment_ad(text):
    if _original_promotional_service_ad(text):
        return True

    # Group administration / permission changes are hard rejects even if a
    # stitched/replied context elsewhere contains property words.
    if any(re.search(pattern, text, re.I | re.S) for pattern in MODERATION_NOTICE_PATTERNS):
        return True

    # Pet/foster posts can say "ищут дом" (looking for a home). Only reject when
    # the home wording appears with multiple animal-care/adoption signals.
    pet_hits = sum(1 for pattern in PET_ADOPTION_PATTERNS if re.search(pattern, text, re.I | re.S))
    if pet_hits >= 2 and re.search(
        r"\b(?:ищ(?:ет|ут)\s+(?:новый\s+)?дом|передержк\w*|ветеринар\w*|щенок|щенки|котенок|котята|adopt(?:ion)?|foster|yuva arıyor|sahiplendir)\b",
        text,
        re.I | re.S,
    ):
        return True

    # Parcel/cargo ads: direct delivery language plus retail brand/logistics
    # context. A standalone property "delivery date" is intentionally allowed.
    delivery_hits = sum(1 for pattern in DELIVERY_SERVICE_PATTERNS if re.search(pattern, text, re.I | re.S))
    retail_or_cargo = re.search(
        r"\b(?:temu|shein|zara|amazon|bestsecret|online\s+stores?|посылк\w*|курьер\w*|cargo|parcel|courier|kargo|kurye)\b",
        text,
        re.I | re.S,
    )
    delivery_action = re.search(
        r"\b(?:доставк\w*\s+до|могу\s+достав(?:ить|лять)|до\s+\d+(?:[.,]\d+)?\s*кг|deliver\w*|kargo|kurye|paket teslimat|alışveriş teslimat)\b",
        text,
        re.I | re.S,
    )
    if delivery_hits >= 2 and retail_or_cargo and delivery_action:
        return True

    # Financial/payment intermediary template. This catches repeated account-
    # transfer requests even when different Telegram accounts post the template.
    financial_hits = sum(1 for pattern in FINANCIAL_INTERMEDIARY_PATTERNS if re.search(pattern, text, re.I | re.S))
    account_signal = re.search(
        r"\b(?:(?:европейск|зарубежн|иностранн)\w*\s+(?:банк\w*\s+)?счет\w*|(?:european|foreign|overseas)\s+(?:bank\s+)?account|(?:avrupa|yurt dışı|yurtdışı)\s+(?:banka\s+)?hesab\w*)\b",
        text,
        re.I | re.S,
    )
    transfer_or_reward = re.search(
        r"\b(?:переведу\s+всю\s+сумм\w*|отблагодар\w*|(?:send|transfer)\s+the\s+(?:full|whole)\s+amount|(?:tüm|bütün)\s+(?:tutarı|parayı)\s+(?:hemen\s+)?(?:gönder|aktar)\w*)\b",
        text,
        re.I | re.S,
    )
    if account_signal and transfer_or_reward and financial_hits >= 2:
        return True

    # Clear recruitment copy is never a buyer lead even when it contains
    # apartment/viewing/owner/lead/close-deal language.
    if re.search(
        r"join\s+snc\s+field\s+operatives|field representatives?|strictly commission[- ]based|not salaried",
        text,
        re.I,
    ):
        return True

    recruitment_hits = sum(1 for pattern in RECRUITMENT_PATTERNS if re.search(pattern, text, re.I | re.S))
    if recruitment_hits >= 3:
        return True

    # Job spam is usually a cluster of role + pay + work wording. A direct job
    # marker (driver/vacancy/шабашка) plus one more signal is enough to reject.
    job_hits = sum(1 for pattern in JOB_SPAM_PATTERNS if re.search(pattern, text, re.I | re.S))
    if job_hits >= 2 or (
        re.search(r"\b(?:нужен\s+водитель|ваканси\w*|шабашк\w*|подработка|job offer|hiring)\b", text, re.I)
        and job_hits >= 1
    ):
        return True

    # Social-media services need multiple service/product markers so an ordinary
    # sentence mentioning Instagram or Telegram is not rejected by itself.
    social_hits = sum(1 for pattern in SOCIAL_MEDIA_SERVICE_PATTERNS if re.search(pattern, text, re.I | re.S))
    if social_hits >= 3:
        return True
    if re.search(r"خدمات.*(?:اینستاگرام|تلگرام|شبکه.?های\s+اجتماعی)", text, re.I | re.S) and social_hits >= 2:
        return True

    # Explicit foreign-market property/residency promotion is not a North Cyprus
    # buyer even when it contains phrases equivalent to "buy property".
    if any(re.search(pattern, text, re.I | re.S) for pattern in FOREIGN_PROPERTY_PROMO_PATTERNS):
        return True

    # A direct money-making pitch plus DM CTA is enough to reject. A single
    # mention of income/earnings remains allowed because genuine property buyers
    # may discuss rental income or investment returns.
    earning_hits = sum(1 for pattern in EARNING_SPAM_PATTERNS if re.search(pattern, text, re.I | re.S))
    if re.search(r"\bхочешь\s+узнать\s+.*\bзаработ", text, re.I | re.S) and re.search(r"\bпиши\s+.*\b(?:лс|личку)\b", text, re.I | re.S):
        return True
    return earning_hits >= 2


nf._promotional_service_ad = promotional_service_or_recruitment_ad
