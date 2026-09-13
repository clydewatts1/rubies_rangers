# Brainstorm: Multi-User, Multi-Team & Pre-Season Sandbox Architecture
## Generalizing Rubies Rangers into an Arbitrary-Manager Quantitative Portfolio Platform

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `config.yaml`, `config_manager.py`, `clients/fpl_client.py`, `analytics/team_manager.py`, `analytics/xp_model.py`, `automation/cpn/engine.py`, `ui/tabs/`, `app.py`  
**Related Rules**: 
- [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md) (Sections 1 & 4: Unconstrained Solvers & Game-Theoretic Portfolio Analysis)
- [`.agents/rules/python_standards.md`](../../.agents/rules/python_standards.md) (Separation of Concerns, Strict Typing, Immutability)

---

## Executive Summary

Currently, **Rubies Rangers** contains several hardcoded couplings to a single manager identity:
* **FPL Entry ID**: `6173410` (Clyde Watts / Rubies Rangers) hardcoded in `config.yaml`, `trackers/league.py`, `app.py`, and tab components.
* **Default Squad**: A static 15-player roster embedded directly in `config.yaml` (`Roefs`, `Verbruggen`, `Pedro Porro`, etc.).
* **Single Active State**: `st.session_state["active_squad"]` in `app.py` supports only one active roster at a time.
* **CPN Runtime Singleton**: The autonomous Petri net pipeline assumes a single team configuration and execution target.

At the start of an FPL season (GW1 Pre-Season) and across tournament leagues, managers require the ability to:
1. **Experiment with Multiple Hypothetical Squad Drafts**: Test fundamentally different structural philosophies side-by-side (e.g., *Haaland + Salah Heavy*, *Spread Depth / 5-Midfield Elite*, *Differential Punt Portfolio*).
2. **Support Multiple Real Users / Accounts**: Manage separate real teams (e.g., personal primary entry, family/friend entries, work league teams) without editing configuration files or source code.
3. **Compare Multi-Team Monte Carlo Distributions**: Project and compare cumulative expected points ($xP$), downside tail risk ($P_{10}$), ceiling potential ($P_{90}$), and captaincy rotation matrices across candidate drafts.
4. **Isolate Autonomous CPN Workflows**: Enable the Kurt Jensen TCPN pipeline to target any arbitrary user profile or run in headless batch simulation across multiple sandbox teams.

This proposal designs a **Multi-Tenant Profile & Pre-Season Sandbox Architecture** that decouples user identity from the underlying optimization and simulation engines.

---

## 1. Domain Modeling: Profiles, Squad Manifests & Sandboxes

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                  MULTI-USER / MULTI-TEAM DOMAIN ARCHITECTURE                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         ManagerProfile                              │   │
│   │  • profile_id: str ("clyde_primary", "draft_haaland_salah", ...)     │   │
│   │  • display_name: str ("Rubies Rangers", "GW1 Template Draft", ...)   │   │
│   │  • profile_type: ProfileType (LIVE_FPL | SANDBOX_EXPERIMENT)         │   │
│   │  • fpl_entry_id: Optional[int] (e.g., 6173410 or None)               │   │
│   │  • auth_env_prefix: Optional[str] (e.g., "FPL_AUTH_CLYDE_")          │   │
│   │  • mini_league_ids: list[int]                                        │   │
│   │  • active_manifest_id: str                                           │   │
│   └──────────────────────────────────┬───────────────────────────────────┘   │
│                                      │ 1 : N                                 │
│                                      ▼                                       │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                          SquadManifest                               │   │
│   │  • manifest_id: str (UUID / Slug)                                    │   │
│   │  • label: str ("Base Draft v1", "Wildcard Draft B", ...)             │   │
│   │  • gameweek: int (1..38)                                             │   │
│   │  • bank_balance: float (e.g., 0.5 £M)                                │   │
│   │  • free_transfers: int (1..5)                                        │   │
│   │  • chips_remaining: set[ChipType] (WC1, WC2, FH, TC, BB)             │   │
│   │  • players: tuple[SquadPlayer, ...] (15 frozen player contracts)     │   │
│   │  • locked_picks: set[int] (pinned core players)                      │   │
│   │  • excluded_picks: set[int] (blacklisted players)                    │   │
│   │  • is_immutable_snapshot: bool                                       │   │
│   └──────────────────────────────────┬───────────────────────────────────┘   │
│                                      │ Evaluated By                          │
│                                      ▼                                       │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │            Analytical Engines & Autonomous CPN Runtime               │   │
│   │  • Monte Carlo Engine (Tail Risk P10/P50/P90)                        │   │
│   │  • Dynamic Linear Programming (MILP Roster Solver)                   │   │
│   │  • Kurt Jensen TCPN Engine (Isolated Marking M(p) per Profile)       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Strongly Typed Data Contracts (`analytics/profile_contracts.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProfileType(str, Enum):
    LIVE_FPL = "LIVE_FPL"            # Authenticated or public live FPL entry
    SANDBOX_EXPERIMENT = "SANDBOX"   # Hypothetical / pre-season experimental draft


class ChipType(str, Enum):
    WC1 = "3b_wildcard_1"
    WC2 = "3b_wildcard_2"
    FREE_HIT = "freehit"
    TRIPLE_CAPTAIN = "3xc"
    BENCH_BOOST = "bboost"


@dataclass(frozen=True)
class SquadPlayer:
    """Represents a single player within an immutable squad roster."""
    element_id: int
    web_name: str
    position_id: int               # 1=GKP, 2=DEF, 3=MID, 4=FWD
    club_id: int
    purchase_price_e6: int         # Tenths of £M (e.g., 100 for £10.0M)
    selling_price_e6: int
    is_starter: bool
    multiplier: int = 1            # 1=normal, 2=captain, 3=triple captain, 0=bench


@dataclass(frozen=True)
class SquadManifest:
    """Immutable 15-player team configuration for a given gameweek snapshot."""
    manifest_id: str
    manager_profile_id: str
    label: str
    gameweek: int
    bank_balance: float
    free_transfers: int
    chips_remaining: tuple[ChipType, ...]
    players: tuple[SquadPlayer, ...]
    locked_element_ids: tuple[int, ...] = ()
    excluded_element_ids: tuple[int, ...] = ()

    def get_player_names(self) -> list[str]:
        return [p.web_name for p in self.players]

    def total_budget(self) -> float:
        return sum(p.selling_price_e6 / 10.0 for p in self.players) + self.bank_balance


@dataclass(frozen=True)
class ManagerProfile:
    """Top-level manager entity supporting live synchronization or sandbox drafting."""
    profile_id: str
    display_name: str
    profile_type: ProfileType
    fpl_entry_id: Optional[int] = None
    auth_env_prefix: Optional[str] = None
    mini_league_ids: tuple[int, ...] = ()
    calibration_profile: str = "tuned"
    manifest_ids: tuple[str, ...] = ()
    active_manifest_id: Optional[str] = None
```

---

## 2. Configuration Store & Migration Strategy (`config.yaml`)

To preserve **100% backward compatibility** with existing scripts, the root `system.default_entry_id` and `system.default_squad` remain as fallback defaults, while introducing a `profiles` registry:

```yaml
system:
  target_gameweek: 1
  # Backward-compatible fallback defaults
  default_entry_id: 6173410
  default_bank: 0.0
  default_league_id: 325320
  active_profile_id: "clyde_rubies_rangers"

# ==============================================================================
# Multi-User & Pre-Season Sandbox Profile Registry
# ==============================================================================
profiles:
  clyde_rubies_rangers:
    display_name: "Rubies Rangers (Clyde Watts)"
    profile_type: "LIVE_FPL"
    fpl_entry_id: 6173410
    auth_env_prefix: "FPL_CLYDE_"
    mini_league_ids: [325320]
    calibration_profile: "tuned"
    default_bank: 3.7
    initial_squad:
      - Roefs
      - Verbruggen
      - Pedro Porro
      - Senesi
      - "Guéhi"
      - Robinson
      - Thiaw
      - Foden
      - "Ødegaard"
      - Mbeumo
      - Cherki
      - Rogers
      - "João Pedro"
      - Isak
      - Solanke

  preseason_gw1_haaland_salah:
    display_name: "GW1 Draft: Haaland + Salah Super-Premiums"
    profile_type: "SANDBOX"
    fpl_entry_id: null
    calibration_profile: "tuned"
    default_bank: 0.0
    initial_squad:
      - Pickford
      - Turner
      - Alexander-Arnold
      - Gabriel
      - Robinson
      - Faes
      - Harwood-Bellis
      - Salah
      - Palmer
      - Eze
      - Rogers
      - Winks
      - Haaland
      - "João Pedro"
      - Armstrong

  preseason_gw1_balanced_depth:
    display_name: "GW1 Draft: Balanced Midfield & Bench Depth"
    profile_type: "SANDBOX"
    fpl_entry_id: null
    calibration_profile: "tuned"
    default_bank: 0.5
    initial_squad:
      - Raya
      - Valdimarsson
      - Gvardiol
      - Saliba
      - Pedro Porro
      - Konsa
      - Barco
      - Saka
      - Foden
      - Palmer
      - Gordon
      - Nkunku
      - Watkins
      - Isak
      - "João Pedro"

  guest_competitor_preview:
    display_name: "Competitor Scout: Rival Team"
    profile_type: "LIVE_FPL"
    fpl_entry_id: 998877
    auth_env_prefix: null
    mini_league_ids: []
    calibration_profile: "adversarial_chase"
```

---

## 3. Pre-Season Multi-Team Experimentation Engine

At the start of the season, managers do not have previous gameweek momentum. Strategic variance is dominated by **portfolio balance**:
* **Budget Allocation Ratio**: Defense (£M) vs. Midfield (£M) vs. Forwards (£M).
* **Bench Capital Waste**: Subsidizing £4.0M fodder vs. £5.0M rotation assets.
* **Captaincy Handoff Matrix**: Complementary home fixture pairings across the first 6–8 gameweeks.

### Multi-Draft Tournament & Comparison Matrix

We design a dedicated comparison engine (`analytics/preseason_comparator.py`):

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     PRE-SEASON DRAFT COMPARISON MATRIX                       │
├──────────────────────┬──────────────────────┬────────────────────────────────┤
│ Metric               │ Draft A (Haaland+Mo) │ Draft B (Balanced Deep Mid)   │
├──────────────────────┼──────────────────────┼────────────────────────────────┤
│ Total Team Value     │ £100.0M              │ £99.5M (£0.5M Bank)            │
│ 6-GW Cumulative xP   │ 342.6 pts            │ 356.1 pts (+13.5)              │
│ Downside Floor (P10) │ 288.4 pts            │ 312.0 pts (+23.6)              │
│ Upside Ceiling (P90) │ 405.2 pts            │ 401.8 pts (-3.4)               │
│ Captaincy Viability  │ 98.2% elite coverage │ 84.1% coverage                 │
│ Bench Reliability    │ 12.1% bench pts lost │ 28.4% auto-sub coverage        │
│ Fixture Swing GW6    │ High Risk (0 FTs)    │ High Agility (Flex Transfers)  │
└──────────────────────┴──────────────────────┴────────────────────────────────┘
```

#### Key Capabilities:
1. **Side-by-Side Monte Carlo Distributions**: Runs 10,000 simulations per candidate draft under joint match covariance and minutes volatility, plotting comparative CDF curves ($P_{10}, P_{50}, P_{90}$).
2. **Captaincy Synchronizer**: Evaluates whether the draft has at least one top-tier captain choice ($xP > 6.0$) with home advantage in each gameweek from GW1 to GW8.
3. **Price Point Flexibility Metric**: Quantifies how easily the draft can pivot to emerging template players with $\le 1$ transfer without taking point hits.

---

## 4. Multi-Tenant Autonomous CPN Runtime

To support arbitrary users and sandbox teams, the **Kurt Jensen TCPN Runtime** (`automation/cpn/`) is generalized:

### A. Marking Isolation
Rather than using a global marking registry, each execution cycle accepts an isolated `CPNMarkingRegistry`:
```python
class CPNEngine:
    def __init__(
        self,
        manager_profile: ManagerProfile,
        fpl_client: FPLClient,
        solver_engine: Any,
        legal_formations: set[tuple[int, int, int]]
    ) -> None:
        self.profile = manager_profile
        self.fpl_client = fpl_client
        self.solver_engine = solver_engine
        self.legal_formations = legal_formations
        # Unique marking registry per profile
        self.marking = CPNMarkingRegistry()
```

### B. Dry-Run & Sandbox Guards
If `manager_profile.profile_type == ProfileType.SANDBOX`:
* The transition coroutines `t_dispatch_transfers` and `t_dispatch_lineup` automatically engage **Simulated Dispatch Mode** (bypassing outbound network requests).
* Synthetic source reconciliation verifies the mock server state against the candidate plan, generating a valid cryptographic confirmation hash without mutating any real FPL squad.

### C. Isolated Diagnostic Journals
Event logs are written to user-partitioned paths:
```text
logs/cpn/journal_{profile_id}_gw{gameweek}.jsonl
```
Preventing cross-contamination of audit trails across different users or sandbox experiments.

---

## 5. UI/UX Architecture: Streamlit Sidebar & Sandbox Workbench

```text
┌─────────────────────────────────────────────────────────┐
│ SIDEBAR: PROFILE & SQUAD SWITCHER                       │
├─────────────────────────────────────────────────────────┤
│ Active Profile:                                         │
│ [ 👤 Rubies Rangers (6173410)                     ▼ ]   │
│   • 👤 Rubies Rangers (Clyde Watts - 6173410)           │
│   • 🧪 GW1 Draft: Haaland + Salah Super-Premiums        │
│   • 🧪 GW1 Draft: Balanced Midfield & Bench Depth       │
│   • ➕ Create / Import New Manager Profile...            │
├─────────────────────────────────────────────────────────┤
│ [📥 Sync Live FPL Picks]  [📋 Clone to New Draft]       │
├─────────────────────────────────────────────────────────┤
│ Active Roster (15 Players) - Bank: £0.5M                │
│ Raya, Valdimarsson | Gvardiol, Saliba, Porro, ...       │
└─────────────────────────────────────────────────────────┘
```

### New UI Components:
1. **Global Profile Switcher (Top of Sidebar)**:
   - Instant dropdown switching between any configured profile or sandbox draft.
   - Updates `st.session_state["active_profile"]` and `st.session_state["active_squad"]`.
2. **"Quick Import from FPL Entry ID" Modal**:
   - Enter any public FPL Team ID (e.g. `123456`).
   - Fetches the published 15-player squad, manager name, overall rank, and mini-leagues.
   - Saves it as a new profile in seconds.
3. **Pre-Season Draft Studio Tab**:
   - Visual pitch layout with drag-and-drop or select-to-swap interface.
   - Live budget tracker (£100.0M ceiling) with real-time 3-players-per-club quota enforcement.
   - Instant 1-click comparison with other saved drafts.

---

## 6. Implementation Roadmap & Milestones

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASED GENERALIZATION ROADMAP                            │
├─────────┬───────────────────────────────┬───────────────────────────────────┤
│ Phase   │ Subsystem Focus               │ Key Deliverables                  │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ Phase 1 │ Profile Contracts & Config    │ • `profile_contracts.py` types    │
│         │                               │ • Multi-profile YAML schema       │
│         │                               │ • ProfileManager helper class     │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ Phase 2 │ UI Profile Switcher & Sync    │ • Sidebar profile dropdown        │
│         │                               │ • Import any FPL Team ID button   │
│         │                               │ • Session state auto-hydration    │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ Phase 3 │ Pre-Season Draft Sandbox      │ • `DraftManager` & Draft Studio   │
│         │                               │ • Multi-draft side-by-side table  │
│         │                               │ • Joint Monte Carlo CDF graphs    │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ Phase 4 │ Multi-Tenant CPN Engine       │ • Profile-aware CPNEngine         │
│         │                               │ • Isolated diagnostic journals    │
│         │                               │ • Batch simulation runner         │
└─────────┴───────────────────────────────┴───────────────────────────────────┘
```

---

## 7. Security & Credential Isolation

* **Zero Secret Leakage**: No passwords or tokens are stored in `config.yaml` or Git repositories.
* **Environment Prefixing**: Each live profile specifies an optional `auth_env_prefix` (e.g. `FPL_CLYDE_EMAIL`, `FPL_CLYDE_PASSWORD` vs `FPL_TEAM2_EMAIL`).
* **Public Read-Only Mode**: If a profile lacks login credentials, all analytics (squad sync, Monte Carlo, leagues, solver) operate seamlessly via public FPL endpoints without authentication. Mutating transfers and live CPN dispatch are automatically locked.

---

## Conclusion & Next Steps

Decoupling the platform from a hardcoded user identity transforms Rubies Rangers from a single-team tool into an **institutional-grade multi-portfolio FPL optimization platform**. 

Managers can prepare for GW1 by stress-testing 5 different draft configurations under identical stochastic conditions, while concurrently monitoring real teams throughout the season.
