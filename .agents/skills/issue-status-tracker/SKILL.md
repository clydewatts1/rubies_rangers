---
name: issue-status-tracker
description: Acts as Observer / Marking Inspector Omega_STATUS in the Agentic Coloured Petri Net (CPN). Queries scripts/issue_status.py using ARD and OKF document metadata to determine the exact lifecycle stage, CPN marking, and next eligible transitions for issues with zero source code scanning, saving >98% tokens.
---

# issue-status-tracker

## Purpose
`issue-status-tracker` acts as the **Observer / Marking Inspector $\Omega_{\text{STATUS}}$** in the **Agentic Coloured Petri Net (CPN)** lifecycle. 

Instead of reading source code, running expensive folder crawls, or guessing whether a feature is complete, this skill executes `python scripts/issue_status.py` to inspect the repository's Agentic Resource Discovery (ARD) catalog and OKF frontmatter metadata. It deterministically computes:
1. The **current active CPN place** ($P_{\text{ISSUE\_READY}}$, $P_{\text{BRAINSTORM\_POOL}}$, $P_{\text{DESIGN\_READY}}$, $P_{\text{PLAN\_READY}}$, $P_{\text{TASK\_QUEUE}}$, or $P_{\text{COMMITTED\_PLAYBOOK}}$).
2. The **unbroken lineage trace** of committed lifecycle documents (`iss_` $\rightarrow$ `brn_` $\rightarrow$ `des_` $\rightarrow$ `pln_` $\rightarrow$ `tsk_` $\rightarrow$ `plb_`).
3. The **next eligible CPN transition** and recommended agent skill (e.g. $T_{\text{DESIGN}}$ via `design-facilitator`).
4. The **global net marking vector** $M_k$ across all active issues in the repository.

## When to Activate
- When the user asks:
  - *"What is the status of issue #X?"*
  - *"What issues are in progress or ready to work on?"*
  - *"Show me all issues waiting for design / implementation."*
  - *"What is the current CPN marking or roadmap status?"*
- When an autonomous coordinator or agent needs to pick the next issue to work on.

## Operational Constraints (CRITICAL)
- **Zero-Code-Crawl Mandate**: **NEVER** use `grep_search`, `list_dir`, or `view_file` on application code in `analytics/`, `automation/`, `clients/`, or `ui/` to deduce if an issue is resolved or implemented. Always run `python scripts/issue_status.py`.
- **Sub-50ms Execution**: Status lookup requires only a single CLI invocation consuming ~150–500 tokens, preserving 98%+ of the context window.
- **Formally Grounded**: The state of an issue is strictly defined by the presence of verified OKF lifecycle documents on disk, not aspirational code edits.

---

## Execution Steps

### 1. Single Issue Inspection
To check a specific issue (e.g. `#001` or `#018`), execute:
```bash
python scripts/issue_status.py --id <ID>
```
For machine-readable JSON:
```bash
python scripts/issue_status.py --id <ID> --json
```

### 2. Portfolio-Wide Status Table
To inspect all issues across the entire repository:
```bash
python scripts/issue_status.py --all
```

### 3. Filter by Specific Lifecycle Stage
To find all issues currently waiting at a specific stage ($1 \le S \le 6$):
```bash
python scripts/issue_status.py --stage 1   # Issues awaiting Brainstorm (P_ISSUE_READY)
python scripts/issue_status.py --stage 2   # Issues awaiting Design (P_BRAINSTORM_POOL)
python scripts/issue_status.py --stage 3   # Issues awaiting Implementation Plan (P_DESIGN_READY)
python scripts/issue_status.py --stage 4   # Issues awaiting Task Harness (P_PLAN_READY)
python scripts/issue_status.py --stage 5   # Issues ready for Coding/Testing (P_TASK_QUEUE)
python scripts/issue_status.py --stage 6   # Fully verified/in-operations (P_COMMITTED_PLAYBOOK)
```

### 4. Global CPN Marking Vector
To get the aggregate token distribution across all CPN places:
```bash
python scripts/issue_status.py --marking
```

---

## Output Interpretation & Action Routing

| Current Place | Highest Doc | Next Net Transition | Recommended Next Action / Skill |
| :--- | :--- | :--- | :--- |
| **`P_ISSUE_READY`** (S1) | `docs/issues/iss_<ID>_*.md` | $T_{\text{BRAINSTORM}}$ or $T_{\text{DESIGN}}$ | Run `/brainstorm-facilitator` (single-shot), `/ideate` (sparring), or `/design-facilitator` (Fast-Track B) |
| **`P_BRAINSTORM_POOL`** (S2) | `docs/brainstorm/brn_<ID>_*.md` | $T_{\text{DESIGN}}$ | Run `/design-facilitator` to produce formal design spec |
| **`P_DESIGN_READY`** (S3) | `docs/design/des_<ID>_*.md` | $T_{\text{SPEC_TO_PLAN}}$ | Run `/spec-to-plan` or composite `/design-to-task` |
| **`P_PLAN_READY`** (S4) | `docs/plans/pln_<ID>_*.md` | $T_{\text{PLAN_TO_TASK}}$ | Run `/plan-to-task` to compile micro-tasks ($\le 80$ lines) |
| **`P_TASK_QUEUE`** (S5) | `docs/tasks/tsk_<ID>_*.md` | $T_{\text{CODE}} \rightarrow T_{\text{VERIFY}}$ | Execute coding tasks followed by pytest verification |
| **`P_COMMITTED_PLAYBOOK`** (S6) | `docs/playbooks/plb_<ID>_*.md` | *Completed* | Issue is deployed, documented, and in operational reality |
