"""Retired duplicate North Cyprus hunter lane.

North Cyprus buyer monitoring is now handled by the dedicated Buyer Catcher and
bay-s-lead-radar V5.5. Keeping this scheduled lane active created duplicate/noisy
alerts from permissive recall rules. The workflow may still invoke this file, but
it deliberately performs no scan and sends no Telegram message.
"""


if __name__ == "__main__":
    print("NORTH_CYPRUS_HUNTER_RETIRED use Buyer Catcher + Lead Radar V5.5")
