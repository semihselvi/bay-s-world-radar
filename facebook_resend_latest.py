from __future__ import annotations

import json

import facebook_demand_runner as runner
import facebook_demand_search as demand


def main() -> int:
    if not demand.OUTPUT_PATH.exists():
        print(f"No latest lead file found: {demand.OUTPUT_PATH}")
        return 1

    try:
        leads = json.loads(demand.OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read latest leads: {exc}")
        return 1

    if not isinstance(leads, list) or not leads:
        print("No leads available to resend.")
        return 0

    print(f"Resending {min(len(leads), 10)} latest Facebook lead(s) with actionable links...")
    runner._notify_actionable(leads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
