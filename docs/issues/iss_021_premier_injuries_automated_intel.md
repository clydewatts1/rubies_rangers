---
type: Issue
title: "[#021] Automated Premier Injuries Scraper for Pre-Deadline Availability Intel"
description: "Automate ingestion of press conference injury status, diagnosis, and return dates from Premier Injuries into Shane's Domain Intel desk, eliminating manual override latency."
tags: [issue, feature, injuries, scraper, intel, domain, availability]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#021]: Automated Premier Injuries Scraper for Pre-Deadline Availability Intel

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#021] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_021_premier_injuries_automated_intel`

---

## 1. Context & Concept (The Why)
A major bottleneck in weekly FPL management is availability uncertainty. Official FPL news flags and `chance_of_playing_next_round` values often lag behind Friday 1:30 PM manager press conferences by 12 to 24 hours. Consequently, managers are forced to manually enter overrides in Shane's Domain Intel desk (`analytics/domain_intel.py`).

Premier Injuries (`premierinjuries.com`) is the gold-standard public tracker for Premier League injury intelligence. It publishes medical diagnosis details, direct quotes from press conferences, and explicit potential return dates/gameweeks within minutes of press conferences concluding. Automating the scraping of this public data will provide pre-deadline minutes and availability probabilities ($p_{\text{fit}}$) hours before the official FPL game updates.

---

## 2. Goals & Objectives
- Build a robust scraper (`clients/injury_client.py`) using `requests` and `BeautifulSoup` to parse Premier Injuries club injury tables.
- Extract structured injury records: player name, club, injury type, condition status, potential return date, and latest press conference quote.
- Map extracted status to Shane's Domain Intel availability enum (`CONFIRMED_OUT_0`, `HEAVY_DOUBT_25`, `COIN_FLIP_50`, `MILD_DOUBT_75`, `CLEARED_FIT_100`).
- Provide an automated bridge into `analytics/domain_intel.py` with automatic TTL expiration.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] `clients/injury_client.py` reliably fetches and parses public injury tables from Premier Injuries with 2-hour disk caching.
- [ ] Fuzzy name normalization bridges Premier Injuries naming formats to standard FPL player IDs.
- [ ] Status mapping algorithm categorizes injury descriptions into standard availability probabilities ($p_{\text{fit}}$).
- [ ] UI integration in Shane's Domain Intel tab displays live scraped injury records and allows 1-click override synchronization.
- [ ] Pytest suite validates scraping logic against cached HTML fixtures with zero network dependency during CI.

---

## 4. Technical Constraints & Context
- Zero API fees; public HTML parsing with polite rate limiting and realistic User-Agent headers.
- Graceful failure: if the scrape fails, existing FPL API injury status remains untouched as fallback.
