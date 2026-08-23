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
    r"\bкуплю\s+(?:отдельно\s*стоящую|отдельностоящую)?\s*вилл",
    r"\bищу\s+.*\bтолько\s+от\s+собственника\b",
]

RUSSIAN_REQUEST_BUYER_PATTERNS = [
    r"\bтолько\s+от\s+собственника\b",
    r"\bот\s+собственника\b",
    r"\bбез\s+агент(?:ов|ств)?\b",
    r"\bна\s+покупку\b",
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


def promotional_service_or_recruitment_ad(text):
    if _original_promotional_service_ad(text):
        return True

    # Group administration / permission changes are hard rejects even if a
    # stitched/replied context elsewhere contains property words.
    if any(re.search(pattern, text, re.I | re.S) for pattern in MODERATION_NOTICE_PATTERNS):
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

    # A direct money-making pitch plus DM CTA is enough to reject. A single
    # mention of income/earnings remains allowed because genuine property buyers
    # may discuss rental income or investment returns.
    earning_hits = sum(1 for pattern in EARNING_SPAM_PATTERNS if re.search(pattern, text, re.I | re.S))
    if re.search(r"\bхочешь\s+узнать\s+.*\bзаработ", text, re.I | re.S) and re.search(r"\bпиши\s+.*\b(?:лс|личку)\b", text, re.I | re.S):
        return True
    return earning_hits >= 2


nf._promotional_service_ad = promotional_service_or_recruitment_ad
