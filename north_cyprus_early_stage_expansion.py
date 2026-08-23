import north_cyprus_focus as nf


def _extend(target, values):
    for value in values:
        if value not in target:
            target.append(value)


# These questions frequently happen shortly before a property purchase. They are
# intentionally request/early signals, not standalone HOT signals: the normal NC
# context + human/question checks still apply.
_extend(nf.REQUEST_BUYER_PATTERNS, [
    # English legal / purchase due diligence
    r"\bcan foreigners buy\b", r"\bcan (?:i|we) buy (?:property|a house|an apartment|a villa)\b",
    r"\bpermission to purchase\b", r"\bpurchase permission\b", r"\bproperty purchase permit\b", r"\b\bptp\b",
    r"\bhow many properties can (?:a )?foreigner buy\b", r"\bforeign buyer limit\b",
    r"\bwhich title deed\b", r"\btitle deed types?\b", r"\bturkish title\b", r"\bexchange title\b", r"\btmd title\b",
    r"\bwhat taxes .*buy", r"\bpurchase tax\b", r"\btransfer (?:tax|fee)\b", r"\bstamp duty\b", r"\bvat .*property\b",
    r"\bneed a lawyer.*(?:buy|property)\b", r"\bwhich lawyer.*property\b", r"\bconveyancing\b",
    r"\bis .* developer reliable\b", r"\bdeveloper reliable\b", r"\btrusted developer\b", r"\bdeveloper reviews?\b",
    r"\bconstruction delay\b", r"\bhandover delay\b", r"\bcompletion delay\b",
    r"\boff[- ]?plan (?:safe|risk|worth)\b", r"\bresale (?:or|vs|versus) off[- ]?plan\b",
    r"\bcan i get residency.*(?:buy|property|house|apartment)\b", r"\bresidency by property\b",
    # Turkish
    r"\byabanc[ıi]lar .*ev alabilir mi\b", r"\byabanc[ıi] .*gayrimenkul alabilir mi\b",
    r"\bsat[ıi]n alma izni\b", r"\bmal edinme izni\b", r"\bka[çc] tane .*alabilir\b",
    r"\bko[çc]an t[üu]rleri\b", r"\bhangi ko[çc]an\b", r"\bt[üu]rk ko[çc]an\b", r"\be[şs]de[ğg]er ko[çc]an\b",
    r"\bev al[ıi]rken vergi\b", r"\btapu harc[ıi]\b", r"\bdamga pulu\b", r"\bkdv .*gayrimenkul\b",
    r"\bavukat gerekli mi\b", r"\bhangi avukat\b", r"\bm[üu]teahhit g[üu]venilir mi\b", r"\bfirma g[üu]venilir mi\b",
    r"\bteslim gecik", r"\bproje gecik", r"\bproje zaman[ıi]nda teslim\b",
    r"\bprojeden mi ikinci el mi\b", r"\bikinci el mi s[ıi]f[ıi]r m[ıi]\b",
    r"\bev alarak oturum\b", r"\bgayrimenkul ile oturum\b",
    # Russian
    r"\bможет ли иностранец купить\b", r"\bиностранц.*купить недвижимост\b", r"\bразрешение на покупку\b",
    r"\bсколько объектов.*иностранец\b", r"\bкакой титул\b", r"\bтипы титул\b", r"\bтурецкий титул\b", r"\bexchange title\b",
    r"\bналог.*при покупке\b", r"\bналоги.*недвижимост\b", r"\bгербов.*сбор\b", r"\bндс.*недвижимост\b",
    r"\bнужен ли адвокат\b", r"\bкакого адвоката\b", r"\bнадежн.*застройщик\b", r"\bкакой застройщик надеж\b",
    r"\bзадержк.*сдач", r"\bзадержк.*проект", r"\bвторичка или новостройка\b",
    r"\bвнж.*покупк.*недвижимост\b", r"\bвнж.*недвижимост\b",
    # German / Polish / Persian / Arabic
    r"\bd[üu]rfen ausl[äa]nder.*immobilie.*kaufen\b", r"\bkaufgenehmigung\b", r"\bwelcher titel.*immobilie\b",
    r"\bwelche steuern.*immobilienkauf\b", r"\bwelcher bautr[äa]ger.*zuverl[äa]ssig\b",
    r"\bczy cudzoziemiec.*kupi[ćc].*nieruchomo\b", r"\bzezwolenie na zakup\b", r"\bjaki tytu[łl].*nieruchomo\b",
    r"آیا خارجی.*می.?تواند.*ملک.*بخر", r"مجوز خرید", r"سند ملک", r"مالیات.*خرید ملک", r"سازنده.*معتبر",
    r"هل يستطيع الأجنبي.*شراء.*عقار", r"تصريح شراء", r"سند الملكية", r"ضرائب.*شراء.*عقار", r"مطور.*موثوق",
])

_extend(nf.EARLY_BUYER_PATTERNS, [
    r"\bcomparing .* north cyprus\b", r"\bnorth cyprus .* compared (?:with|to)\b",
    r"\bshould (?:i|we) buy in (?:iskele|girne|esentepe|long beach)\b",
    r"\bwhich is better .* (?:iskele|girne|esentepe|long beach)\b",
    r"\b[İi]skele mi .*girne\b", r"\bgirne mi .*[İi]skele\b",
    r"\bискеле или гирне\b", r"\bгирне или искеле\b",
    r"\blong beach.*(?:good|safe).*investment\b", r"\blong beach.*yat[ıi]r[ıi]m.*(?:iyi|mant[ıi]kl[ıi])\b",
    r"\bстоит ли.*long beach.*инвест\b",
])

_extend(nf.CONCRETE_PATTERNS, [
    r"\bpermission to purchase\b", r"\bpurchase permit\b", r"\bsat[ıi]n alma izni\b", r"\bmal edinme izni\b",
    r"\bразрешение на покупку\b", r"\btransfer fee\b", r"\bstamp duty\b", r"\btapu harc[ıi]\b", r"\bdamga pulu\b",
])
