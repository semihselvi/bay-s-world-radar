# BAY-S Radar XL

Radar XL is an **isolated experimental branch** for the next discovery/orchestration stack. It does not replace, import into, schedule, or write to the current production World Radar.

## Goal

Find **real buyer / relocation / investment intent**, not maximum content volume.

Primary target for the first lab stage: **North Cyprus** in English, Turkish and Russian.

## Architecture

```text
Agent Reach
  ├─ X/Twitter search
  ├─ Reddit search
  └─ YouTube discovery
        │
        ├───────────────┐
        │               │
Firecrawl Search        │
  └─ open web/community │
        │               │
        └──────┬────────┘
               ▼
        Normalized Candidate
               │
               ▼
        Browser Use fallback
   (only when a specific URL cannot be read)
               │
               ▼
      Multilingual hard filters
               │
               ▼
        HOT / WARM / NOISE
               │
               ▼
             Dedupe
               │
               ▼
      JSON lab manifest / panel feed
               │
        ┌──────┴────────┐
        ▼               ▼
   Hermes review   Telegram / CRM
    (optional)      (explicit opt-in)
```

## Provider roles

### Agent Reach

Agent Reach is treated as a **capability/router layer**, not a magic lead API. Radar XL uses the upstream tools Agent Reach currently routes to:

- `twitter-cli` for X/Twitter search
- `rdt-cli` or OpenCLI for Reddit
- `yt-dlp` for YouTube discovery
- `agent-reach doctor --json` for health/capability checks

No cookie or login automation is performed by Radar XL. Authenticated channels are available only when the environment has already been configured by the operator.

### Firecrawl

Firecrawl is a **cost-guarded discovery/page-reading layer**. It is disabled by default and requires both:

- `RADAR_XL_FIRECRAWL_ENABLED=1`
- `RADAR_XL_FIRECRAWL_MAX_QUERIES=N` where `N > 0`
- `FIRECRAWL_API_KEY`

The default query budget is **0**, so a checkout of Radar XL cannot spend Firecrawl credits accidentally.

### Browser Use

Browser Use is a **high-cost fallback**, never the default discovery engine. It is invoked only for a specific URL whose extracted text is too small to classify.

It is disabled by default and requires:

- `RADAR_XL_BROWSER_USE_ENABLED=1`
- `RADAR_XL_BROWSER_USE_MAX_TASKS=N` where `N > 0`
- `BROWSER_USE_API_KEY`

The default task budget is **0**.

### Hermes Agent

Hermes is an **optional supervisor/orchestration layer**. Radar XL does not depend on Hermes.

When `RADAR_XL_HERMES_ENABLED=1` and `hermes` is installed, it receives only the isolated JSON manifest and can review the result set. The bridge explicitly tells Hermes not to modify production Radar, GitHub, Telegram, CRM, Firestore or external accounts.

## Buyer classification

The first classifier is deterministic and free. It looks for:

- explicit purchase intent
- North Cyprus location context
- property context
- budget
- owner-direct requirements
- transaction signals
- relocation intent
- investment intent

Hard-noise patterns include:

- realtor/broker identity without first-person buying intent
- seller/listing language
- rentals
- jobs/earnings spam
- SMM/social-service spam
- moderation notices
- unrelated foreign-market promotions

Undated results cannot be promoted directly to HOT; they are downgraded to WARM until date verification exists.

## Isolation rules

1. Production World Radar files are not imported or edited by Radar XL.
2. No schedule is enabled automatically.
3. `RADAR_XL_DRY_RUN=1` is the default.
4. XL Telegram uses **separate secret names**: `RADAR_XL_TELEGRAM_BOT_TOKEN` and `RADAR_XL_TELEGRAM_CHAT_ID`.
5. CRM webhook is disabled unless `RADAR_XL_CRM_ENABLED=1` and `RADAR_XL_CRM_WEBHOOK_URL` are set.
6. Firecrawl and Browser Use both default to a zero-cost budget.
7. No outreach, posting, form submission, purchasing or account changes are allowed in Browser Use tasks.

## Local test

```bash
python -m pip install -r requirements-radar-xl.txt
python -m radar_xl.selftest
```

A live lab run is:

```bash
RADAR_XL_DRY_RUN=1 \
RADAR_XL_AGENT_REACH_ENABLED=1 \
python -m radar_xl.run
```

If Agent Reach/upstream tools are not configured, the provider simply returns no data rather than modifying the machine or asking for credentials.

## Success metric

Radar XL is not judged by number of pages/posts collected. The key metrics are:

- genuine HOT/WARM buyer leads found
- precision after human review
- unique/contactable lead rate
- false-positive rate from agents/sellers/jobs/rentals/promotions
- incremental leads not found by the current Radar
- cost per usable incremental lead

Only after these metrics are good should any Radar XL component be considered for production integration.
