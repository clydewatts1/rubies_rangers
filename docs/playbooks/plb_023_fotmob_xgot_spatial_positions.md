---
type: Playbook
title: "[#023] FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions - Operational Playbook"
description: "Operational playbook and architectural store for FotMob Expected Goals on Target (xGOT), finishing skill delta (xGOT - xG), goalkeeper goals prevented, confirmed lineups, and XPModel integration."
tags: [playbook, python, fotmob, xgot, finishing, lineups, goalkeeper, analytics, xp]
status: Active
sources: ["docs/design/des_023_fotmob_xgot_spatial_positions.md"]
generated:
  at: "2026-09-17T21:34:00Z"
  by: "agent:playbook-facilitator"
---

# Playbook [#023]: FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Operations & Maintenance**
> - **Origin Place**: `P_VERIFICATION`
> - **Current Transition**: `T_PLAYBOOK`
> - **Next Place**: `P_COMMITTED_PLAYBOOK`
> - **CPN Lineage**: Issue [#023] -> Design [des_023] -> Tasks [tsk_023] -> Code [P_VERIFICATION] -> Playbook [plb_023]
> - **Origin Design**: [`docs/design/des_023_fotmob_xgot_spatial_positions.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_023_fotmob_xgot_spatial_positions.md)
> - **Origin Issue**: [`docs/issues/iss_023_fotmob_xgot_spatial_positions.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_023_fotmob_xgot_spatial_positions.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:plb_023_fotmob_xgot_spatial_positions`

---

## 1. Architectural Store & Design Decisions (The Why)

### 1.1 Post-Shot Trajectory vs Pre-Shot Chance Quality
Pre-shot Expected Goals ($xG$) quantifies the historical conversion probability of a shot from a given spatial coordinate before ball strike. However, elite finishers (e.g., Erling Haaland, Son Heung-min, Bukayo Saka, Mohamed Salah) exhibit consistent skill in ball placement—steering shots into side netting and upper corners away from the goalkeeper.

**Expected Goals on Target ($xGOT$)** models post-shot trajectory, factoring in ball speed, elevation, and post-strike spatial placement. The differential:
$$\Delta_{\text{finish}} = xGOT - xG$$

serves as the definitive forward metric separating clinical ball-strikers from wasteful volume shooters.

### 1.2 Mathematical Formulation

1. **Finishing Skill Multiplier Calibration**:
   $$\Delta_{\text{finish}, i} = xGOT_i - xG_i$$
   $$\gamma_{\text{finish}, i} = 1.0 + \text{clip}\left( 0.10 \cdot \Delta_{\text{finish}, i}, -0.15, +0.20 \right)$$
   $$xG_{\text{match}, i} \leftarrow xG_{\text{match}, i} \cdot \gamma_{\text{finish}, i}$$
   $$P(\text{Goal}_i) = 1.0 - \exp\left(-xG_{\text{match}, i}\right)$$

2. **Goalkeeper Shot-Stopping Fallback**:
   When FBref StatBomb metrics are offline or missing for newly transferred goalkeepers, FotMob's `_goals_prevented.json` and `_save_percentage.json` feeds provide fallback save modeling:
   $$\mathbb{E}[\text{Saves}] = \frac{\eta_{\text{fotmob}}}{1.0 - \eta_{\text{fotmob}}} \cdot \lambda_{\text{opp}} \cdot \left( \frac{\text{mins}}{90} \right)$$
   $$P(\text{CS}_{\text{effective}}) = \exp\left( -\max\left(0.30, \lambda_{\text{opp}} - \frac{\text{GP}_{\text{fotmob}}}{4.0}\right) \right)$$

---

## 2. Implemented Reality & Primary Modules

```text
rubies_rangers/
├── clients/
│   └── fotmob_client.py                   # FotMob public REST client, formulas, and 24-hour disk cache
├── analytics/
│   └── xp_model.py                       # XPModel forward metrics finishing delta modulation
└── tests/
    └── test_fotmob_client.py              # 12 unit & integration tests
```

### 2.1 Key Classes & Functions (`clients/fotmob_client.py`)
- `FotMobPlayerStats`: Frozen dataclass containing `web_name`, `team_name`, `team_code`, `xg`, `xgot`, `finishing_delta`, `goals_prevented`, `save_pct`, and timestamp.
- `FotMobLineup`: Frozen dataclass representing verified matchday lineups and formations.
- `compute_finishing_multiplier(finishing_delta)`: Vector-ready formula computing $1.0 + 0.10 \cdot \Delta_{\text{finish}}$, strictly clamped between $[0.85, 1.20]$.
- `FotMobClient`: Consumes high-speed JSON endpoints on `https://data.fotmob.com/stats/47/season/36781/` (`expected_goalsontarget.json`, `expected_goals.json`, `_goals_prevented.json`) with 24-hour disk caching at `.fotmob_cache.json` and baseline store fallback.

---

## 3. Operational Verification & Telemetry

### 3.1 Verification Commands
```bash
# Run FotMob test suite
python -m pytest tests/test_fotmob_client.py -v

# Run full cross-client regression test suite
python -m pytest tests/test_clubelo_client.py tests/test_odds_client.py tests/test_injury_client.py tests/test_fbref_client.py tests/test_fotmob_client.py -v
```

### 3.2 Telemetry Outputs in `XPModel.calculate_player_xp()`
- `fotmob_finishing_delta`: Floating-point $xGOT - xG$ delta.
- `fotmob_xgot`: Season-total post-shot Expected Goals on Target.
- `fotmob_xg`: Season-total pre-shot Expected Goals.
- `forward_multiplier`: Modulated z-score multiplier reflecting finishing skill and talismanic share.
