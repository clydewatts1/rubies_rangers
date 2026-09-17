---
name: issue-ingestion-parser
description: Acts as Transition T_INGEST in the Agentic Coloured Petri Net (CPN), parsing raw concepts from P_BACKLOG into structured, OKF-compliant Issue tokens in P_ISSUE_READY. Establishes the genesis node of the artifact provenance trace with a unique sequential tracking ID.
---

# issue-ingestion-parser

## Purpose
This skill fires as **Transition $T_{\text{INGEST}}$** in the **Agentic Coloured Petri Net (CPN)**. Its primary job is to act as a stateful translation layer between raw human input in $P_{\text{BACKLOG}}$ (ideas, bugs, features, solver improvements) and the deterministic, OKF-governed Rubies Rangers repository, depositing a strongly-typed `IssueToken` into $P_{\text{ISSUE\_READY}}$.

By assigning a Unique Tracking ID and chaining directly into the OKF and ARD builder skills, it establishes the root node for the artifact's immutable provenance trace. The token's `TrackColor` controls its routing across the CPN:
- **Track A (Deep Architecture)**: Routed to $T_{\text{BRAINSTORM}} \rightarrow P_{\text{BRAINSTORM\_POOL}}$ (full 6-stage lifecycle).
- **Track B (Fast-Track Feature)**: Bypasses brainstorming, routing directly to $T_{\text{DESIGN}} \rightarrow P_{\text{DESIGN\_READY}}$.
- **Track C (Express Hotfix)**: Fast-tracks directly to $T_{\text{TASKIFY}} \rightarrow P_{\text{TASK\_QUEUE}}$.

## When to Activate
- When a human user provides a new idea, feature request, bug report, or abstract goal in the chat prompt.
- When tasked with beginning a new track of work that does not yet have a formal Issue document.
- When mirroring an external ticket or GitHub issue into the local repository for agentic discovery.

## Operational Constraints (CRITICAL)
- **Zero-Shell Mandate**: Do not use `run_command` unless explicitly ordered (except for running `python scripts/ard_builder.py`). Rely on direct file inspection tools (`view_file`). Never run unconstrained `list_dir` on large directories.
- **Root Node Rule**: Issues are the genesis of the development lifecycle. Their OKF frontmatter `sources` array MUST be empty (`[]`) **unless** the issue is explicitly derived from an audit, review, or regression in an existing artifact—in which case `sources` MUST reference the originating artifact and the issue tag set MUST include `derived` or `audit`.
- **Ambiguity Halt**: If the user's prompt is a vague idea lacking clear success metrics, you must halt and ask clarifying questions before generating the document to establish concrete goals. Do not hallucinate acceptance criteria.

## Execution Steps

### 1. Parse, Categorize, and Extract
Analyze the user's request. **If the prompt is too brief or lacks clear success metrics, trigger the Ambiguity Halt and ask the user clarifying questions first.** Once clear, determine its category (`idea`, `bug`, `feature`, `solver`, or `architecture`) and extract:
- **Core Concept/Problem**: What is the mathematical concept, business need, or technical bug?
- **Goals**: What does success look like?
- **Acceptance Criteria**: What are the specific, binary (pass/fail) conditions that must be met to close this issue?
- **Track Classification**: Track A (Full 6 stages), Track B (Fast-Track 4 stages), or Track C (Express hotfix).

### 2. Allocate the Tracking ID (Concurrency-Safe)

> **Idempotency Check**: Before allocating a new ID, scan `docs/issues/` for any `iss_<next_ID>_*.md` file matching the topic. If one exists, this is a resumed run—reuse the existing file rather than allocating a new ID.

To maintain the CPN Lineage Trace, every track of work gets a sequential, 3-digit integer ID:
- Read the highest integer in `docs/issues/` or `docs/issues/last_issue_number.md` (defaulting to `001` if empty), increment it by 1, and write the new value back to `docs/issues/last_issue_number.md`.
- **Filename Format**: `docs/issues/iss_<ID>_<slug>.md` (e.g., `docs/issues/iss_001_transfer_popover.md`)
- **URN Format**: `urn:air:clydewatts1:rubies_rangers:docs:iss_<ID>_<slug>`

### 3. Draft the Content
Draft the Markdown body of the issue using the Context, Goals, and Acceptance Criteria extracted in Step 1. You must strictly follow the Data Contract provided in the template below.

### 4. Add OKF Header
Add a valid OKF YAML frontmatter block to the top of the new issue document:
```yaml
---
type: Issue
title: "[#<ID>] <Title>"
description: "<Brief 1-2 sentence description>"
tags: [<category>, <domain>, <tech>]
status: Open
sources: []
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:issue-ingestion-parser"
---
```

### 5. Rebuild ARD Manifest
Run the manifest builder to register the new issue in the local ARD catalog:
```bash
python scripts/ard_builder.py
```

### 6. Update the Issue Index
Append an entry to `docs/issues/index.md`:
```markdown
* [[#<ID>] <Title>](iss_<ID>_<slug>.md) - <description>.
```

### 7. Completion & Hard Stop (Stage Gate)
Present the logged Issue summary and ID to the user.
- **HARD STOP**: Do NOT automatically advance to Stage 2 (Brainstorm) or begin drafting `brn_<ID>_<slug>.md`.
- **WAIT FOR EXPLICIT COMMAND**: Only advance if the user explicitly orders `"proceed to brainstorm"` or executes `/brainstorm-facilitator`.

---

## Content Body Template

```markdown
# Issue [#<ID>]: <Title>

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#<ID>] -> [Brainstorm] -> Design -> Plan -> Tasks -> Playbook
> - **Execution Track**: Track A (Full 6-Stage) | Track B (Fast-Track 4-Stage) | Track C (Express Hotfix)
> - **Priority**: P0-Critical | P1-High | P2-Medium | P3-Low
> - **Estimated Complexity**: S | M | L | XL
> - **URN**: urn:air:clydewatts1:rubies_rangers:docs:iss_<ID>_<slug>

## 1. Context & Concept (The Why)
<Clear explanation of the mathematical concept, the current state, the pain point, or the feature request.>

## 2. Goals & Objectives
- <High-level goal 1>
- <High-level goal 2>

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [ ] <Criterion 1 (Must be testable/binary)>
- [ ] <Criterion 2>
- [ ] <Criterion 3>

## 4. Technical Constraints & Context
<Any known limitations, mathematical formulas, required frameworks, or specific files related to the issue.>
```
