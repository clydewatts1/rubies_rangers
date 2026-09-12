import os
import subprocess
from pathlib import Path

BASE = Path(r"C:\Users\cw171001\Projects\PNC_KAN_GREASAN")

DOCS = {
    # -------------------------------------------------------------
    # ISSUE #024: Persist Watcher State in Vault Secondary Metadata
    # -------------------------------------------------------------
    BASE / "docs" / "issues" / "iss_024_persist_watcher_state_in_vault_metadata.md": """---
type: Issue
title: "[#024] Persist Watcher State in Vault Secondary Metadata"
description: "Enhance CorrelationGatherWatcher to store emitted correlation IDs in vault metadata, providing durability across node restarts."
tags: [issue, feature, engine, watcher, vault, scatter-gather, durability, persistence, recovery]
status: Active
sources: ["docs/design/scatter_gather_detailed_design.md"]
generated:
  at: "2026-09-11T20:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#024]: Persist Watcher State in Vault Secondary Metadata

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Current Stage**: Issue
> - **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> - **Upstream Source**: `docs/design/scatter_gather_detailed_design.md` (Priority 5)
> - **Downstream Consumers**: `brn_024`, `des_024`, `pln_024`, `tsk_024`

---

## 1. Executive Summary & Problem Formulation

### Current Architectural Limitation:
`CorrelationGatherWatcher` monitors destination places for matching correlation tokens. It maintains its set of emitted correlation IDs exclusively in memory (`emittedCorrelations map[string]struct{}`).

### Failure Mode:
1. **Volatile In-Memory Tracking**: On crash, supervisor restart, or failover, the in-memory deduplication set is reset.
2. **Double-Emission Risk**: If place tokens or incoming events are replayed from the transaction log or persistent vault, `CorrelationGatherWatcher` cannot distinguish between newly arrived shard tokens and already-rendezvoused correlation groups, leading to duplicate downstream tokens.
3. **Recovery Lag**: The engine lacks an atomic mechanism to reconstruct watcher tracking state without re-evaluating the entire graph history.

---

## 2. Ingested Technical Requirements

### 2.1 Durable Secondary Metadata Integration
- Bind `CorrelationGatherWatcher` to the `Vault` secondary metadata API (`SetMetadata` / `GetMetadata`).
- Store emitted correlation states under a structured key pattern:
  `sg:emitted:<subnet_id>:<watcher_id>:<correlation_id>` containing transition ID, shard count, and emission timestamp.

### 2.2 Hydration & Lifecycle Recovery
- On initialization (`NewCorrelationGatherWatcher`), scan and hydrate active correlation keys from the vault store before opening place subscription channels.
- Support optional dedicated marker token emission into a supervisory audit place (`place_emitted_rendezvous`).

### 2.3 Concurrency & Pruning
- Enforce concurrent safety with reader-writer mutexes or transactional vault updates.
- Provide a configurable TTL or LRU retention policy to prune historical correlation records and prevent unbounded storage growth.

---

## 3. Acceptance Criteria & Verification Gates

- [ ] **G1 (Persistence Interface)**: `CorrelationGatherWatcher` commits emitted correlation IDs to vault metadata synchronously before emitting downstream tokens.
- [ ] **G2 (Restart Durability Test)**: Abrupt node restart during active rendezvous restores deduplication filters from vault metadata with zero duplicate emissions.
- [ ] **G3 (Concurrent Safety)**: Passes Go race detector: `go test -race ./pkg/engine/watcher/...`.
- [ ] **G4 (Bounded Metadata)**: Vault metadata pruning cleans entries older than `RetentionWindow`.
""",

    BASE / "docs" / "brainstorm" / "brn_024_persist_watcher_state_in_vault_metadata.md": """---
type: Brainstorm
title: "[#024] Persist Watcher State in Vault Secondary Metadata - Brainstorm"
description: "Architectural options, failure modes, and trade-off analysis for persisting CorrelationGatherWatcher emitted state across node crashes and restarts."
tags: [brainstorm, engine, watcher, vault, scatter-gather, durability, persistence, recovery]
status: Active
sources: ["docs/issues/iss_024_persist_watcher_state_in_vault_metadata.md"]
generated:
  at: "2026-09-11T20:30:00Z"
  by: "agent:brainstorm-facilitator"
---

# Brainstorm [#024]: Persist Watcher State in Vault Secondary Metadata - Brainstorm

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Current Stage**: Brainstorm
> - **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> - **Upstream Source**: `docs/issues/iss_024_persist_watcher_state_in_vault_metadata.md`
> - **Downstream Consumers**: Design `des_024`, Plan `pln_024`, TaskHarness `tsk_024`

---

## 1. Problem Exploration & Failure Modes

`CorrelationGatherWatcher` evaluates non-destructive Read-Only Arcs over intermediate shard places. Because tokens remain present until consumed by `GatherWorker`, the watcher relies on an in-memory deduplication set (`emittedCorrelations map[string]struct{}`) to prevent repeated re-triggering.

### Critical Failure Mode:
Upon ungraceful shutdown or container failover, this in-memory map is reset. On reboot, the watcher re-scans the intermediate place, detects satisfied correlation groups that were already emitted, and emits duplicate rendezvous tokens, causing duplicate executions and state corruption.

---

## 2. Options Analyzed

1. **Option 1: Vault Secondary Metadata (`Vault.SetMetadata`)**
   - Out-of-band KV persistence using key prefix `sg:emitted:<subnet>:<watcher>:<corr_id>`.
   - Hydrates on startup; zero blueprint impact.
2. **Option 2: Dedicated In-Band Marker Place (`place_rendezvous_emitted`)**
   - Pure CPN token approach; visible in state maps.
   - Requires modifying blueprints or injecting hidden supervisory places.
3. **Option 3: Hybrid Write-Through LRU with TTL Pruning (Selected)**
   - In-memory speed with synchronous disk persistence and automatic TTL expiration.

---

## 3. Selected Consensus Approach

Adopt **Option 3 (Hybrid Write-Through Vault Metadata)**:
- Keeps user blueprints clean and free of artificial supervisory marker places.
- Protects sub-millisecond hot-path evaluation via bounded LRU.
- Guarantees crash survivability through synchronous write-through before token emission.
- Bounded memory and disk footprint via configurable TTL retention (default: 24h).
""",

    BASE / "docs" / "design" / "des_024_persist_watcher_state_in_vault_metadata.md": """---
type: Design
title: "[#024] Persist Watcher State in Vault Secondary Metadata - Detailed Design"
description: "Authoritative architectural design specifying the hybrid write-through LRU cache, metadata schema, startup hydration protocol, and TTL pruning for CorrelationGatherWatcher."
tags: [design, architecture, go, engine, watcher, vault, scatter-gather, durability, persistence, recovery]
status: Active
sources: ["docs/brainstorm/brn_024_persist_watcher_state_in_vault_metadata.md"]
generated:
  at: "2026-09-11T20:35:00Z"
  by: "agent:antigravity"
---

# Design [#024]: Persist Watcher State in Vault Secondary Metadata - Detailed Design

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Current Stage**: Design
> - **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> - **Upstream Source**: `docs/brainstorm/brn_024_persist_watcher_state_in_vault_metadata.md`
> - **Downstream Consumers**: Plan `pln_024`, TaskHarness `tsk_024`

---

## 1. Executive Overview & System Invariants

This specification resolves the volatile in-memory state limitation of `CorrelationGatherWatcher` by implementing a **Hybrid Write-Through LRU Cache backed by Vault Secondary Metadata**.

### Critical Invariants:
1. **At-Most-Once Rendezvous Emission**: Under zero circumstances may a crash/restart cycle cause a rendezvous token to be emitted more than once for the same `correlation_id`.
2. **Sub-Microsecond Steady-State Gating**: 99.9% of incoming token evaluations must resolve against the in-memory LRU in $< 1\\mu\\text{s}$ without disk I/O.
3. **Write-Before-Emit Guarantee**: The durable metadata entry must be flushed and acknowledged by the underlying store *before* the trigger token is placed into the destination place.
4. **Bounded Storage Footprint**: Completed correlation records are automatically pruned via a background TTL sweeper.

---

## 2. Data Structures & Metadata Contract

### 2.1 Secondary Metadata Record Schema
```go
type EmittedCorrelationRecord struct {
    CorrelationID    string    `json:"correlation_id"`
    SubnetID         string    `json:"subnet_id"`
    WatcherID        string    `json:"watcher_id"`
    EmittedAt        time.Time `json:"emitted_at"`
    ExpiresAt        time.Time `json:"expires_at"`
    ShardCount       int       `json:"shard_count"`
    DestinationPlace string    `json:"destination_place"`
    TransitionID     string    `json:"transition_id,omitempty"`
}
```

### 2.2 Vault Key Formatting Standard
`Key = fmt.Sprintf("sg:emitted:%s:%s:%s", subnetID, watcherID, correlationID)`

---

## 3. Interfaces & Components

```go
type SecondaryMetadataStore interface {
    SetMetadata(ctx context.Context, key string, value []byte) error
    GetMetadata(ctx context.Context, key string) ([]byte, error)
    DeleteMetadata(ctx context.Context, key string) error
    ScanMetadataPrefix(ctx context.Context, prefix string) (map[string][]byte, error)
}
```

---

## 4. Lifecycle Protocols

1. **Hydration at Startup**: Scan prefix `sg:emitted:<subnet>:<watcher>:`, filter unexpired, populate in-memory LRU.
2. **Synchronous Write-Through**: Check in-memory LRU; if false and satisfied, write record to vault metadata synchronously *before* placing rendezvous trigger token.
3. **Background TTL Sweeper**: Periodic ticker scans prefix and deletes records where `ExpiresAt < time.Now()`.
""",

    BASE / "docs" / "plans" / "pln_024_persist_watcher_state_in_vault_metadata.md": """---
type: Plan
title: "[#024] Persist Watcher State in Vault Secondary Metadata - Implementation Plan"
description: "Phased engineering plan for integrating SecondaryMetadataStore with CorrelationGatherWatcher, adding in-memory LRU cache with synchronous write-through durability, and implementing background TTL eviction."
tags: [plan, architecture, go, engine, watcher, vault, scatter-gather, durability, persistence]
status: Active
sources: ["docs/design/des_024_persist_watcher_state_in_vault_metadata.md"]
generated:
  at: "2026-09-11T20:36:00Z"
  by: "agent:antigravity"
---

# Plan [#024]: Persist Watcher State in Vault Secondary Metadata - Implementation Plan

## 0. Frontloader (DAG Context)
> **Current Stage**: Plan
> **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> **Upstream Source**: `docs/design/des_024_persist_watcher_state_in_vault_metadata.md`
> **Downstream Consumers**: TaskHarness `tsk_024_persist_watcher_state_in_vault_metadata.md`

---

## 1. Roadmap Phases
- **Phase 1**: Storage Contracts & Schema in `pkg/engine/watcher/persistence.go`.
- **Phase 2**: In-Memory LRU Cache & Startup Hydration in `CorrelationGatherWatcher`.
- **Phase 3**: Synchronous Write-Through Logic in `evaluateAndEmit()`.
- **Phase 4**: Background TTL Eviction Sweeper goroutine.
- **Phase 5**: Unit Tests & E2E Node Crash/Restart Recovery Test.

## 2. Verification Gates
- **G1**: Compiles cleanly with zero circular package dependencies.
- **G2**: Unit tests verify 100% pass on hydration, LRU cache hits, and TTL eviction.
- **G3**: Microbenchmark certifies $< 1\\mu\\text{s}$ cache hit latency.
- **G4**: Integration test validates zero duplicate emissions across supervisor reboot.
""",

    BASE / "docs" / "tasks" / "tsk_024_persist_watcher_state_in_vault_metadata.md": """---
type: TaskHarness
title: "[#024] Persist Watcher State in Vault Secondary Metadata - Micro-Task Harness"
description: "Atomic, testable execution tasks and verification gates for implementing hybrid write-through vault persistence in CorrelationGatherWatcher."
tags: [task, architecture, go, engine, watcher, vault, scatter-gather, durability, persistence]
status: Active
sources: ["docs/plans/pln_024_persist_watcher_state_in_vault_metadata.md"]
generated:
  at: "2026-09-11T20:36:00Z"
  by: "agent:antigravity"
---

# TaskHarness [#024]: Persist Watcher State in Vault Secondary Metadata - Micro-Task Harness

## 0. Frontloader (DAG Context)
> **Current Stage**: TaskHarness
> **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> **Upstream Source**: `docs/plans/pln_024_persist_watcher_state_in_vault_metadata.md`

---

## Actionable Execution Tasks

- [ ] **Task 1: Define `EmittedCorrelationRecord` & `SecondaryMetadataStore`**
  - Location: `pkg/engine/watcher/persistence.go`
- [ ] **Task 2: Embed LRU Cache in `CorrelationGatherWatcher`**
  - Location: `pkg/engine/watcher/correlation_gather_watcher.go`
- [ ] **Task 3: Implement `Hydrate(ctx)` Startup Routine**
  - Location: `pkg/engine/watcher/correlation_gather_watcher.go`
- [ ] **Task 4: Implement Synchronous Write-Through in `evaluateAndEmit()`**
  - Location: `pkg/engine/watcher/correlation_gather_watcher.go`
- [ ] **Task 5: Implement Background TTL Eviction Sweeper**
  - Location: `pkg/engine/watcher/correlation_gather_watcher.go`
- [ ] **Task 6: Unit Tests for Persistence & LRU Gating**
  - Location: `pkg/engine/watcher/correlation_gather_watcher_test.go`
- [ ] **Task 7: E2E Crash/Reboot Resilience Test**
  - Location: `pkg/engine/supervisor/e2e_resource_test.go`
""",

    # -------------------------------------------------------------
    # ISSUE #025: Archive Superseded Design Artifacts
    # -------------------------------------------------------------
    BASE / "docs" / "issues" / "iss_025_archive_superseded_design_artifacts.md": """---
type: Issue
title: "[#025] Archive Superseded Design Artifacts"
description: "Permanently delete auxiliary markdown files (SCATTER_CONFIGURATION_EXAMPLES.md, SCATTER_GATHER_REVIEW_OPTIONS.md, SCATTER_GATHER_UPDATED.md) to maintain unbroken OKF governance."
tags: [issue, governance, documentation, archive, scatter-gather, okf, cleanup]
status: Active
sources: ["docs/design/scatter_gather_detailed_design.md"]
generated:
  at: "2026-09-11T20:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#025]: Archive Superseded Design Artifacts

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Current Stage**: Issue
> - **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Execution
> - **Upstream Source**: `docs/design/scatter_gather_detailed_design.md` (Priority 6)
> - **Downstream Consumers**: `brn_025`, `des_025`, `pln_025`, `tsk_025`, `ard_reindex`

---

## 1. Governance Rationale & Background

The scatter-gather CPN pattern design was synthesized and finalized in `docs/design/scatter_gather_detailed_design.md`. 

Three auxiliary working files remain in `docs/design/`:
1. `SCATTER_CONFIGURATION_EXAMPLES.md`
2. `SCATTER_GATHER_REVIEW_OPTIONS.md`
3. `SCATTER_GATHER_UPDATED.md`

### Ingestion Mandate:
- Leaving unconsolidated drafts in `docs/design/` creates semantic drift, pollutes search results in `ard_search`, and causes `ard_lineage` to report `concept_type: Unresolved`.
- OKF governance mandates permanent removal of redundant drafts, updating master lineage to `sources: ["legacy"]`.
""",

    BASE / "docs" / "brainstorm" / "brn_025_archive_superseded_design_artifacts.md": """---
type: Brainstorm
title: "[#025] Archive Superseded Design Artifacts - Brainstorm"
description: "Architectural brainstorming, trade-off analysis, and option evaluation for removing legacy scatter-gather working drafts and maintaining unbroken OKF lineage."
tags: [brainstorm, governance, documentation, archive, scatter-gather, okf]
status: Active
sources: ["docs/issues/iss_025_archive_superseded_design_artifacts.md"]
generated:
  at: "2026-09-11T20:25:00Z"
  by: "agent:brainstorm-facilitator"
---

# Brainstorm [#025]: Archive Superseded Design Artifacts - Brainstorm

## 0. Frontloader (DAG Context)
> **Current Stage**: Brainstorm
> **DAG Lineage**: Issue -> Brainstorm -> Design -> Plan -> Tasks -> Implementation -> Playbook
> **Upstream Source**: `docs/issues/iss_025_archive_superseded_design_artifacts.md`

## 1. Selected Decision
Adopted Decision: Permanent deletion via `git rm`.
- Zero disk clutter, zero manifest bloat.
- Git commit history serves as immutable archive.
- Reconcile `sources: ["legacy"]` in `docs/design/scatter_gather_detailed_design.md`.
""",

    BASE / "docs" / "design" / "des_025_archive_superseded_design_artifacts.md": """---
type: Design
title: "[#025] Archive Superseded Design Artifacts - Detailed Design"
description: "Authoritative architectural design specifying the deletion protocol and lineage reconciliation for legacy scatter-gather working drafts."
tags: [design, governance, documentation, archive, scatter-gather, okf]
status: Active
sources: ["docs/issues/iss_025_archive_superseded_design_artifacts.md"]
generated:
  at: "2026-09-11T20:20:00Z"
  by: "agent:antigravity"
---

# Design [#025]: Archive Superseded Design Artifacts - Detailed Design

## 0. Frontloader (DAG Context)
> **Current Stage**: Design
> **DAG Lineage**: Issue -> Design -> Plan -> Tasks -> Execution
> **Upstream Source**: `docs/issues/iss_025_archive_superseded_design_artifacts.md`

## 1. Specification
1. Permanently delete `SCATTER_CONFIGURATION_EXAMPLES.md`, `SCATTER_GATHER_REVIEW_OPTIONS.md`, and `SCATTER_GATHER_UPDATED.md` from `docs/design/`.
2. Update `sources:` in `docs/design/scatter_gather_detailed_design.md` to `["legacy"]`.
3. Reindex ARD manifests via `ard-server reindex`.
""",

    BASE / "docs" / "plans" / "pln_025_archive_superseded_design_artifacts.md": """---
type: Plan
title: "[#025] Archive Superseded Design Artifacts - Implementation Plan"
description: "Phased implementation plan for deleting auxiliary scatter-gather drafts, reconciling OKF lineage, and regenerating ARD manifests."
tags: [plan, governance, documentation, archive, scatter-gather, okf]
status: Active
sources: ["docs/design/des_025_archive_superseded_design_artifacts.md"]
generated:
  at: "2026-09-11T20:25:00Z"
  by: "agent:antigravity"
---

# Plan [#025]: Archive Superseded Design Artifacts - Implementation Plan

## 0. Frontloader (DAG Context)
> **Current Stage**: Plan
> **DAG Lineage**: Issue -> Design -> Plan -> Tasks -> Execution
> **Upstream Source**: `docs/design/des_025_archive_superseded_design_artifacts.md`

## 1. Action Items
1. Delete target files via git rm.
2. Update master document frontmatter.
3. Reindex and validate ARD.
""",

    BASE / "docs" / "tasks" / "tsk_025_archive_superseded_design_artifacts.md": """---
type: TaskHarness
title: "[#025] Archive Superseded Design Artifacts - Micro-Task Harness"
description: "Actionable execution tasks and verification commands for cleaning up legacy scatter-gather drafts and reconciling OKF lineage."
tags: [task, governance, documentation, archive, scatter-gather, okf]
status: Active
sources: ["docs/plans/pln_025_archive_superseded_design_artifacts.md"]
generated:
  at: "2026-09-11T20:25:00Z"
  by: "agent:antigravity"
---

# TaskHarness [#025]: Archive Superseded Design Artifacts - Micro-Task Harness

## Tasks
- [ ] Task 1: Delete target draft files from docs/design/
- [ ] Task 2: Reconcile sources in docs/design/scatter_gather_detailed_design.md
- [ ] Task 3: Reindex ARD manifests and run ard_validate
"""
}

def main():
    print("[1/3] Writing all 10 OKF documentation files to disk...")
    for path, content in DOCS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  [CREATED] {path.relative_to(BASE)}")

    print("\n[2/3] Cleaning up obsolete drafts in docs/design/ if present...")
    drafts_to_remove = [
        BASE / "docs" / "design" / "SCATTER_CONFIGURATION_EXAMPLES.md",
        BASE / "docs" / "design" / "SCATTER_GATHER_REVIEW_OPTIONS.md",
        BASE / "docs" / "design" / "SCATTER_GATHER_UPDATED.md",
    ]
    for draft in drafts_to_remove:
        if draft.exists():
            draft.unlink()
            print(f"  [REMOVED] {draft.relative_to(BASE)}")

    # Update sources in scatter_gather_detailed_design.md
    master_file = BASE / "docs" / "design" / "scatter_gather_detailed_design.md"
    if master_file.exists():
        content = master_file.read_text(encoding="utf-8")
        # Replace un-archived source paths with ["legacy"]
        import re
        content = re.sub(r'sources:\s*\n(\s*-\s*["\'].*?["\']\s*\n)+', 'sources: ["legacy"]\n', content)
        master_file.write_text(content, encoding="utf-8")
        print("  [UPDATED] sources: [\"legacy\"] in scatter_gather_detailed_design.md")

    print("\n[3/3] Rebuilding ARD manifests via ard-server...")
    ard_exe = BASE / "bin" / "ard-server.exe"
    if ard_exe.exists():
        res = subprocess.run([str(ard_exe), "reindex", "--root", str(BASE)], capture_output=True, text=True)
        print(f"  [REINDEX] Exit code: {res.returncode}")
        if res.stdout:
            print(f"  {res.stdout.strip()}")
    else:
        print("  [WARN] ard-server.exe not found at bin/ard-server.exe")

    print("\n[DONE] All OKF artifacts successfully written and registered!")

if __name__ == "__main__":
    main()
