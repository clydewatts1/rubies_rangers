---
type: Issue
title: "[#015] Autonomous Challenge Coloured Petri Net (CPN) Pipeline & Standalone Runner"
description: "Autonomous Challenge CPN architecture with modular picker service, model validator, Saga retry loop, and zero-FastAPI CLI runner."
tags: [issue, challenge, cpn, saga, automation, runner]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#015]: Autonomous Challenge Coloured Petri Net (CPN) Pipeline & Standalone Runner

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P0-Critical
> - **Estimated Complexity**: XL
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_015_challenge_cpn_autonomous_runner`

---

## 1. Context & Concept (The Why)
FPL Challenge has dynamic weekly constraints and rolling deadlines requiring an autonomous, self-healing Petri Net pipeline capable of submitting lineups without reliance on a long-running web API server.

---

## 2. Goals & Objectives
- Decompose challenge picker into a modular, functional service shared between UI and CPN.
- Implement Quantitative Model Validator auditing squads against config.yaml rules before submission.
- Build autonomous Challenge CPN with Saga verification and exponential backoff retry.
- Create standalone CLI runner (automation/challenge_runner.py) with zero FastAPI dependencies.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] Modular ChallengePicker in analytics/challenge/picker.py
- [x] ChallengeModelValidator verifying budget, club caps, and tail monotonicity
- [x] Autonomous CPN package in automation/challenge_cpn/ with append-only JSONL journal
- [x] Standalone CLI runner automation/challenge_runner.py passing --dry-run tests
- [x] 32 automated tests passing cleanly in pytest

---

## 4. Technical Constraints & Context
Zero FastAPI dependency; supports dry-run memory simulation and live authenticated dispatch.
