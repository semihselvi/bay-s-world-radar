import north_cyprus_focus as nf


def _extend(target, values):
    for value in values:
        if value not in target:
            target.append(value)


_extend(nf.NC_LOCATION_PATTERNS, [
    r"قبرس شمالی",
    r"قبرس شمالى",
    r"قبرس شمالي",
    r"ایسکله",
    r"اسکله",
    r"گیرنه",
    r"فاماگوستا",
])

_extend(nf.PROPERTY_PATTERNS, [
    r"ملک",
    r"آپارتمان",
    r"اپارتمان",
    r"خانه",
    r"ویلا",
    r"زمین",
])

_extend(nf.STRONG_BUYER_PATTERNS, [
    r"می.?خواهم .*بخرم",
    r"می.?خوام .*بخرم",
    r"قصد خرید .*دارم",
    r"دنبال .*برای خرید .*هستم",
    r"دنبال (?:آپارتمان|اپارتمان|خانه|ویلا|ملک) هستم",
    r"می.?خواهم (?:آپارتمان|اپارتمان|خانه|ویلا|ملک) بخرم",
    r"خرید (?:آپارتمان|اپارتمان|خانه|ویلا|ملک).*(?:قبرس شمالی|ایسکله|اسکله|گیرنه)",
])

_extend(nf.REQUEST_BUYER_PATTERNS, [
    r"قیمت چنده",
    r"قیمت .*چقدر",
    r"چه قیمتی",
    r"شرایط اقساط",
    r"اقساطی",
    r"پیش پرداخت",
    r"بودجه.*(?:پوند|یورو|دلار)",
    r"مستقیم از مالک",
    r"بدون واسطه",
    r"فروش مجدد",
])

_extend(nf.CONCRETE_PATTERNS, [
    r"بودجه",
    r"پیش پرداخت",
    r"اقساط",
    r"پوند",
    r"یورو",
    r"دلار",
])

_extend(nf.PERSONAL_PATTERNS, [
    r"من ",
    r"ما ",
    r"می.?خواهم",
    r"می.?خوام",
    r"دنبال .*هستم",
])
