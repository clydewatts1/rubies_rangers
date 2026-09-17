---
type: Issue
title: "[#011] Macro-Strategic Portfolio & Asset Management Framework"
description: "Managing FPL squads as dynamic investment portfolios with cash buffers and capital preservation."
tags: [issue, portfolio, balance-sheet, strategy, transfers]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#011]: Macro-Strategic Portfolio & Asset Management Framework

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_011_strategic_portfolio_asset_management`

---

## 1. Context & Concept (The Why)
FPL teams should be managed as financial balance sheets: capital allocated across assets (premium, mid-priced, enablers) with dynamic cash buffers to exploit rapid market repricing and fixture swings.

---

## 2. Goals & Objectives
- Formulate Portfolio Balance Sheet metrics (AUM, Cash-in-Bank, FT option values).
- Model liquidity buffers and capital preservation under transfer hit constraints.
- Build dedicated Portfolio & Balance Sheet trading desk.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] ui/components/ticker.py providing persistent portfolio telemetry strip
- [x] ui/tabs/tab_strategic_balance_sheet.py displaying asset allocation and cash buffer health
- [x] Automated unit tests validating portfolio balance sheet accounting

---

## 4. Technical Constraints & Context
Strict dark-mode financial terminal styling adhering to ui_ux_standards.md.
