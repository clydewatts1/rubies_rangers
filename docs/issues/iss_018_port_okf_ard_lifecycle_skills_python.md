---
type: Issue
title: "[#018] Port and Adapt OKF/ARD Engineering Lifecycle Skills for Python"
description: "Port 6-stage engineering lifecycle skills and ARD zero-crawl discovery from Go to native Python, pytest, and NumPy/pandas."
tags: [issue, tooling, process, registry, discovery, python]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#018]: Port and Adapt OKF/ARD Engineering Lifecycle Skills for Python

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P0-Critical
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_018_port_okf_ard_lifecycle_skills_python`

---

## 1. Context & Concept (The Why)
Rubies Rangers requires the same rigorous 6-stage provenance DAG and sub-millisecond ARD catalog search that proved successful in PNC_KAN_GREASAN, adapted natively for Python engineering, Moneyball strategy, and pytest.

---

## 2. Goals & Objectives
- Port 14 agentic skills into .agents/skills/ adapting Go patterns to Python docstring OKF frontmatter.
- Build scripts/ard_builder.py and scripts/ard_search.py for zero-crawl manifest indexing.
- Implement .agents/skills/code-frontmatter-generator/scripts/validate_code_okf.py for doc and code frontmatter auditing.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] 14 agentic skills installed in .agents/skills/
- [x] ard.yaml and master ard.json indexing docs, analytics, automation, clients, ui, and tests
- [x] scripts/ard_search.py returning sub-millisecond search results
- [x] validate_code_okf.py passing 100% on docs directory

---

## 4. Technical Constraints & Context
Cross-platform Windows/Linux compatibility; UTF-8 stdout reconfiguration.
