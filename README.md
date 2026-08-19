# BAY-S WORLD RADAR

Global property buyer-intent intelligence engine.

This repository is completely separate from `bay-s-lead-radar`.

## Current engine

- Global market matrix
- English / Turkish / Russian plus European-language intent phrases
- Reddit RSS discovery
- Google News RSS discovery for discussion/context discovery
- Exa web discovery across public forums, expat communities, Golden Visa discussions and indexed Telegram/community pages
- 24-hour freshness filter
- Duplicate protection
- Seller / agency / listing noise filtering
- Intent, credibility and market-fit scoring
- HOT / WARM classification
- Partner routing
- Firestore storage
- Telegram notification
- GitHub Actions scheduling

## GitHub Secrets

The workflow reads:

- `EXA_API_KEY`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Run manually

GitHub → Actions → **BAY-S World Radar** → Run workflow.
