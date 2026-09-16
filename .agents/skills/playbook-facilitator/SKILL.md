---
name: playbook-facilitator
description: Converts a Stage 3 Technical Design document and the final implemented codebase into an operational Stage 6 Playbook document in docs/playbooks/plb_<ID>_<slug>.md. Bridges theory to reality, summarizing actual architecture, operational commands, troubleshooting, and spec deviations.
---

# playbook-facilitator

## Purpose
This skill operates at **Stage 6 (Playbook)** of the development lifecycle. It takes a Stage 3 Technical Design document (`docs/design/des_<ID>_<slug>.md`) and the *actual deployed Python code*, synthesizing them into an operational reality guide in `docs/playbooks/plb_<ID>_<slug>.md`.

Because implementations often deviate slightly from original designs (e.g. edge-case handling, parameter tweaks, API response nuances), this skill acts as a technical writer bridging the gap between theory and reality.

## When to Activate
- When a feature, solver, or refactor has been implemented and tested.
- When transitioning from implementation to deployment/operations.
- When asked to "generate the playbook" or "document how to run and troubleshoot this feature".

## Operational Constraints (CRITICAL)
- **Zero-Shell Mandate**: Do not use `run_command` to alter code during playbook drafting (only `python scripts/ard_builder.py` is permitted).
- **DAG Lineage Rule**: The Playbook document MUST link back to the source Design in its OKF `sources` array: `sources: ["docs/design/des_<ID>_<slug>.md"]`.
- **Reality Check Mandate**: Inspect the actual source code (via `view_file` or `grep_search`) to ensure the Playbook reflects the real deployed code, not just aspirational design notes.

## Execution Steps

### 1. Analyze Design Spec & Implemented Code
- Read `docs/design/des_<ID>_<slug>.md`.
- Inspect the corresponding source files in `analytics/`, `automation/`, `clients/`, or `ui/`.
- Identify any deviations or runtime adjustments made during development.

### 2. Formulate Playbook Content
- Architecture summary (what was actually built).
- Operational instructions (CLI flags, Streamlit UI buttons, configuration parameters in `config.yaml`).
- Monitoring & Telemetry (log files, metrics, CPN journal entries).
- Troubleshooting Guide (common error codes, compensation steps, rollback).
- Design Deviations (exact differences between design spec and deployed code).

### 3. Write Playbook Document
Write `docs/playbooks/plb_<ID>_<slug>.md` using the template below.

### 4. Rebuild ARD Manifest
Run `python scripts/ard_builder.py`.

---

## Content Body Template

```markdown
---
type: Playbook
title: "[#<ID>] <Title> - Operational Playbook"
description: "<Operational guide covering deployment, configuration, runtime monitoring, and troubleshooting>"
tags: [playbook, python, <domain>, <tech>]
status: Active
sources: ["docs/design/des_<ID>_<slug>.md"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:playbook-facilitator"
---

# Playbook [#<ID>]: <Title>

## 0. Frontloader (DAG Context)
> **Metadata for Operations & Maintenance**
> - **Origin Design**: [`docs/design/des_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_<ID>_<slug>.md)
> - **Origin Issue**: [`docs/issues/iss_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_<ID>_<slug>.md)
> - **Current Stage**: Stage 6 (Playbook)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **URN**: urn:air:clydewatts1:rubies_rangers:docs:plb_<ID>_<slug>

---

## 1. Architecture & Implemented Reality
<Summary of what was deployed into production, listing primary modules and contracts.>

- **Primary Modules**:
  - [`module_a.py`](file:///path/to/module_a.py)
  - [`module_b.py`](file:///path/to/module_b.py)

---

## 2. Operational Guide & Usage

### 2.1 Configuration (`config.yaml`)
```yaml
subsystem:
  parameter_name: value
```

### 2.2 CLI Execution
```bash
python -m automation.challenge_runner --gameweek 5 --sims 1000 --dry-run
```

### 2.3 Trading Desk UI Access
- Desk: `⚔️ Quantitative Solvers` (or relevant desk)
- Tab: `<Tab Name>`

---

## 3. Monitoring, Diagnostics & Telemetry
- Log outputs: `logs/diagnostics/`
- Key metrics: Duration ms, simulation convergence, API status codes.

---

## 4. Troubleshooting & Failure Recovery

| Symptom / Error | Immediate Cause | Recovery Action |
| :--- | :--- | :--- |
| **HTTP 403 Forbidden** | Expired FPL token | Click "🔄 Refresh FPL Session" in Autonomous CPN Desk |
| **Budget Invariant Error** | Squad cost > cap | Check player pricing in `config.yaml` or data cache |

---

## 5. Implementation Deviations from Design Spec
- **Deviation 1**: ...
- **Deviation 2**: ...
```
