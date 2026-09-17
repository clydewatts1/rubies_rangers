---
type: Issue
title: "[#008] Multi-User, Multi-Team & Pre-Season Sandbox Architecture"
description: "Multi-profile sandbox architecture supporting isolated managerial portfolios and test rosters."
tags: [issue, portfolio, strategy, architecture]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#008]: Multi-User, Multi-Team & Pre-Season Sandbox Architecture

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_008_multi_user_team_sandbox_architecture`

---

## 1. Context & Concept (The Why)
Rubies Rangers was originally coupled to a single hardcoded FPL manager entry ID. Multi-manager syndicate optimization and pre-season draft sandboxes require isolated session state and profile switching.

---

## 2. Goals & Objectives
- Implement ProfileManager supporting arbitrary FPL manager profiles with independent credentials.
- Provide pre-season sandbox roster builder for drafting squads before Gameweek 1.
- Persist profile state safely in session state and config files.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] analytics/profile_manager.py implementing profile storage and switching
- [x] Streamlit sidebar profile switcher dynamically updating active portfolio across all desks
- [x] Automated test suite verifying multi-profile isolation and persistence

---

## 4. Technical Constraints & Context
Zero credential leaking; sensitive tokens stored in auth manager or environment.
