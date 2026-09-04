# BAY-S Facebook Group Radar

This module scans only Facebook groups that are visible to the Facebook account you log into manually in the dedicated browser profile. It does not automate comments, DMs, friend requests, or member-list scraping.

## First setup on Windows

1. Pull the repository/branch to your Windows machine.
2. Run `facebook_setup.bat` once.
3. Run `facebook_discover_groups.bat` if you want to list groups visible in your Facebook Groups feed.
4. The first time Chrome opens, log in to Facebook manually and complete any verification. The session is stored in a dedicated BAY-S browser profile under your local app-data directory; your password is not stored in this repository.
5. Add the groups you want to scan to `facebook_groups.json` and set `enabled` to `true`.
6. Run `facebook_radar.bat`.

## Current configured group

`Northern Cyprus Forum`

`https://www.facebook.com/groups/323875321020382/`

## What it does

- Opens a persistent Chrome/Edge browser session locally.
- Visits each enabled Facebook group at a conservative pace.
- Reads recent visible post text and best-effort post permalinks.
- Reuses `north_cyprus_intent_classifier.py` so OWNER/AGENT/SPAM content is rejected and BUYER/TENANT intent is kept.
- Produces `HOT` / `WARM` scores using intent, credibility, and North Cyprus market fit.
- De-duplicates alerts across runs.
- Saves latest leads to `facebook_leads_latest.json`.
- Sends new leads to Telegram when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are available in `.env` or the environment.

## Discovering your joined groups

Run:

```bat
facebook_discover_groups.bat
```

The scanner opens `https://www.facebook.com/groups/feed/`, collects group links visible there, and writes them to:

`facebook_groups_discovered.json`

Discovered groups are disabled by default. Copy only the groups you actually want to monitor into `facebook_groups.json`.

## Configuration

Example:

```json
{
  "settings": {
    "scroll_rounds": 5,
    "scroll_pause_seconds": 2.5,
    "max_posts_per_group": 25,
    "max_age_hours": 72,
    "sort_newest": true,
    "notify_telegram": true
  },
  "groups": [
    {
      "name": "Northern Cyprus Forum",
      "url": "https://www.facebook.com/groups/323875321020382/",
      "enabled": true
    }
  ]
}
```

## Notes

Facebook changes its page structure frequently, so selectors may occasionally need adjustment. The scanner deliberately uses visible browser content rather than attempting to bypass group privacy, login requirements, or access controls.

Use a small number of relevant groups and keep scan frequency moderate. The purpose is to surface genuine buyer/tenant intent for manual review, not to bulk-harvest profiles or send automated outreach.
