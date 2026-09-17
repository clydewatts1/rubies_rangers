---
type: Issue
title: "[#023] FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions"
description: "Consume FotMob public endpoints to calculate true finishing skill delta (xGOT - xG), detect out-of-position tactical deployments, and verify pre-kickoff lineups."
tags: [issue, feature, fotmob, xgot, finishing, spatial, lineups, client]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#023]: FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#023] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_023_fotmob_xgot_spatial_positions`

---

## 1. Context & Concept (The Why)
In `docs/brainstorm/additional_metrics.md`, the #1 leading forward metric identified was **Finishing Skill Delta ($\text{xGOT} - \text{xG}$)**:
- $xG$ measures chance quality before the ball is struck.
- $xGOT$ (Expected Goals on Target) measures shot quality after leaving the boot (velocity, corner placement).
- A positive delta separates clinical ball-strikers (e.g. Son, Haaland) from wasteful volume shooters.

Furthermore, nominal FPL positions often misclassify tactical reality. A player listed as a Defender in FPL may play as an advanced wingback or inverted midfielder, while a Midfielder may operate as a central striker. FotMob exposes public match JSON endpoints containing:
1. Granular shot-by-shot $xGOT$ metrics.
2. Actual matchday player pitch coordinates $(x, y)$ reflecting true average formation positions.
3. Rapid official lineup announcements 60 to 75 minutes before kickoff.

---

## 2. Goals & Objectives
- Develop `clients/fotmob_client.py` querying FotMob public REST endpoints with disk caching.
- Calculate season-level and rolling 5-match Finishing Skill Delta $(\text{xGOT} - \text{xG})$ per attacking asset.
- Ingest spatial pitch coordinates to identify Out-Of-Position (OOP) attacking advantages.
- Provide a pre-deadline lineup verification check in Matchday Center / Autonomous Operations.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] `clients/fotmob_client.py` fetches match details and player shot records with graceful error handling and local caching.
- [ ] Name normalization resolves FotMob player identifiers to standard FPL player IDs.
- [ ] Finishing Delta $(\text{xGOT} - \text{xG})$ is computed and passed to `analytics/xp_model.py`'s `forward_metrics` weights.
- [ ] OOP detector flags nominal defenders playing in attacking third $(x > 66\%)$ and nominal midfielders playing as central forwards.
- [ ] Pytest suite validates metric calculation and endpoint parsing using mocked response payloads.

---

## 4. Technical Constraints & Context
- Free public API without official authentication keys; client must include standard user-agent headers and backoff retry logic.
- Avoid real-time request spamming; all matchday payloads cached for $\ge 6$ hours post-match.
