from __future__ import annotations

from radar_xl.classifier import classify
from radar_xl.dedupe import dedupe
from radar_xl.models import Candidate


CASES = [
    (
        "ru_hot_buyer",
        Candidate(
            source="fixture",
            source_kind="telegram-like",
            url="https://example.test/1",
            text="Хочу купить квартиру 2+1 в Фамагусте, важно близко к университету. От собственника.",
            author="buyer1",
            published_at="2026-08-25T08:00:00+00:00",
            language="ru",
        ),
        "HOT",
    ),
    (
        "en_seller_ad",
        Candidate(
            source="fixture",
            source_kind="x",
            url="https://example.test/2",
            text="For sale: luxury apartment in North Cyprus, prices from £129,000. DM for details.",
            author="property_agent",
            language="en",
        ),
        "NOISE",
    ),
    (
        "tr_relocation",
        Candidate(
            source="fixture",
            source_kind="reddit",
            url="https://example.test/3",
            text="Kuzey Kıbrıs'a taşınmayı düşünüyorum. Girne'de ev almak istiyorum, bütçe yaklaşık £150k.",
            author="user3",
            language="tr",
        ),
        "HOT",
    ),
    (
        "ru_job_spam",
        Candidate(
            source="fixture",
            source_kind="social",
            url="https://example.test/4",
            text="Ищем водителя. Работа на Северном Кипре, хороший заработок, пишите в личку.",
            author="jobs",
            language="ru",
        ),
        "NOISE",
    ),
    (
        "moderation_notice",
        Candidate(
            source="fixture",
            source_kind="social",
            url="https://example.test/5",
            text="Пользователи не смогут отправлять медиа и ссылки. Только администраторы могут писать.",
            author="admin",
            language="ru",
        ),
        "NOISE",
    ),
]


def main() -> None:
    failed = []
    classified = []
    for name, candidate, expected in CASES:
        result = classify(candidate)
        classified.append(result)
        if result.classification != expected:
            failed.append((name, expected, result.classification, result.score, result.reject_reason))

    # Dedupe must collapse an exact URL duplicate and retain the stronger one.
    duplicate = classify(
        Candidate(
            source="fixture2",
            source_kind="x",
            url="https://example.test/1?tracking=abc",
            text="Хочу купить квартиру 2+1 в Фамагусте. От собственника.",
            author="buyer1",
            language="ru",
        )
    )
    unique = dedupe(classified + [duplicate])
    if len(unique) != len(classified):
        failed.append(("dedupe", len(classified), len(unique), 0, "unexpected_count"))

    if failed:
        raise SystemExit("RADAR_XL_SELFTEST_FAILED " + repr(failed))
    print(f"RADAR_XL_SELFTEST_OK cases={len(CASES)} unique={len(unique)}")


if __name__ == "__main__":
    main()
