from __future__ import annotations

import facebook_radar_v2 as v2
from facebook_intent_adapter import classify_facebook_intent


ORIGINAL_INTENT_CLASSIFIER = v2.base.classify_intent


def _facebook_classifier(item):
    return classify_facebook_intent(item, ORIGINAL_INTENT_CLASSIFIER)


def main() -> int:
    # Apply only to the Facebook scanner process. The shared/core classifier file is untouched.
    v2.base.classify_intent = _facebook_classifier
    return v2.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_RADAR_V3_ERROR: {exc}")
        raise SystemExit(1)
