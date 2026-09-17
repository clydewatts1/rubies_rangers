"""
---
type: Tool
title: "OKF Frontmatter Backfill Utility"
description: "Script to retroactively add OKF frontmatter to legacy markdown documents in docs/."
tags: [tooling, discovery, python, cli]
status: Active
sources: []
generated:
  at: "2026-09-16T22:30:00Z"
  by: "agent:antigravity"
---
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCS_META = {
    "docs/fantasy_football_as_a_hedge_fund_manager.md": {
        "type": "Architecture",
        "title": "The Quant Manager's Manifesto: Approaching Fantasy Football as a Quantitative Hedge Fund",
        "description": "Quantitative strategy whitepaper applying Modern Portfolio Theory, Multi-Factor Alpha, Real Options, and Adversarial Game Theory to 38-period FPL optimization.",
        "tags": ["architecture", "strategy", "moneyball", "portfolio", "optimization", "monte-carlo"],
        "status": "Active",
        "sources": []
    },
    "docs/brainstorm/additional_metrics.md": {
        "type": "Brainstorm",
        "title": "[#001] Objective, Free & Bias-Free Forward-Looking Predictive Metrics",
        "description": "Advanced feature engineering and leading predictive metrics across weather, tactics, and Moneyball alpha.",
        "tags": ["brainstorm", "tactics", "weather", "moneyball", "odds"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/autonomous_execution_pipeline.md": {
        "type": "Brainstorm",
        "title": "[#002] Autonomous Execution Pipeline & Robotic Manager",
        "description": "Timed Coloured Petri Net (TCPN) autonomous robotic manager architecture with Saga submission loops.",
        "tags": ["brainstorm", "cpn", "saga", "automation", "runner"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/codebase_modularization_roadmap.md": {
        "type": "Brainstorm",
        "title": "[#003] Codebase Modularization & Two-Stage Architectural Decoupling",
        "description": "Modular refactor decomposing app.py into domain packages: analytics, clients, ui, and automation.",
        "tags": ["brainstorm", "architecture", "process", "refactor"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/fpl_challenge_optimization_engine.md": {
        "type": "Brainstorm",
        "title": "[#004] FPL Challenge Quantitative Optimization Engine",
        "description": "Mathematical formulation and candidate screening for dynamic weekly FPL Challenge tournament formats.",
        "tags": ["brainstorm", "challenge", "optimization", "milp", "knapsack"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/long_term_chip_allocation_strategy.md": {
        "type": "Brainstorm",
        "title": "[#005] Long-Term Chip Allocation Strategy & Optimal Stochastic Timing",
        "description": "Dynamic programming and Bellman optimality for timing Free Hit, Wildcard, Bench Boost, and Triple Captain chips.",
        "tags": ["brainstorm", "chips", "strategy", "optimization", "monte-carlo"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/macro_match_jitter_covariance.md": {
        "type": "Brainstorm",
        "title": "[#006] Macro Match-State Jitter & Teammate Covariance Modeling",
        "description": "Full covariance matrix simulation modeling match-state blowouts, game script correlation, and variance.",
        "tags": ["brainstorm", "monte-carlo", "optimization", "tactics"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/modularization.md": {
        "type": "Brainstorm",
        "title": "[#007] Modularization Pointer & Architecture Index",
        "description": "Canonical redirect and architecture index for domain modularization.",
        "tags": ["brainstorm", "architecture", "process"],
        "status": "Legacy",
        "sources": ["docs/brainstorm/codebase_modularization_roadmap.md"]
    },
    "docs/brainstorm/multi_user_team_sandbox_architecture.md": {
        "type": "Brainstorm",
        "title": "[#008] Multi-User, Multi-Team & Pre-Season Sandbox Architecture",
        "description": "Multi-profile sandbox architecture supporting isolated managerial portfolios and test rosters.",
        "tags": ["brainstorm", "portfolio", "strategy", "architecture"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/shane_human_metrics.md": {
        "type": "Brainstorm",
        "title": "[#009] Shane's Human Domain Metrics & Tacit Knowledge Formalization",
        "description": "Translating subjective domain scouting heuristics into formal quantitative signals.",
        "tags": ["brainstorm", "scout", "tactics", "moneyball"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/strategic_framework_phase_0.md": {
        "type": "Brainstorm",
        "title": "[#010] Strategic Framework Phase 0 - Foundational Data & Portfolio Ingestion",
        "description": "Multi-gameweek transfer planning, bank optimization, and rolling horizon setup.",
        "tags": ["brainstorm", "portfolio", "transfers", "strategy"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/strategic_portfolio_asset_management.md": {
        "type": "Brainstorm",
        "title": "[#011] Macro-Strategic Portfolio & Asset Management Framework",
        "description": "Managing FPL squads as dynamic investment portfolios with cash buffers and capital preservation.",
        "tags": ["brainstorm", "portfolio", "balance-sheet", "strategy", "transfers"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/two_stage_optimization_measures_inclusion_exclusion.md": {
        "type": "Brainstorm",
        "title": "[#012] Two-Stage Optimization: Measure Inclusion & Exclusion Criteria",
        "description": "Feature selection and mathematical weighting for Multi-Objective MILP and Monte Carlo Tournament stages.",
        "tags": ["brainstorm", "optimization", "milp", "monte-carlo", "tactics"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/two_stage_screen_and_simulate.md": {
        "type": "Brainstorm",
        "title": "[#013] Two-Stage 'Screen & Simulate' Optimization Architecture",
        "description": "Chained MILP Stage 1 screening knapsack with Stage 2 2,500-draw Monte Carlo tournament.",
        "tags": ["brainstorm", "optimization", "milp", "monte-carlo", "transfers"],
        "status": "Legacy",
        "sources": []
    },
    "docs/brainstorm/venue_home_away_impact.md": {
        "type": "Brainstorm",
        "title": "[#014] Team & Positional Venue Impact (Home vs. Away) Modeling",
        "description": "Quantifying pitch dimensions, home venue bias, crowd noise, and venue FDR multipliers.",
        "tags": ["brainstorm", "venue", "tactics", "fdr", "odds"],
        "status": "Legacy",
        "sources": []
    },
}

def apply_okf_frontmatter():
    for rel_path, meta in DOCS_META.items():
        file_path = REPO_ROOT / rel_path
        if not file_path.exists():
            print(f"Skipping missing {rel_path}")
            continue

        content = file_path.read_text(encoding="utf-8")
        if content.lstrip("\ufeff").startswith("---"):
            print(f"Already has frontmatter: {rel_path}")
            continue

        frontmatter_lines = [
            "---",
            f"type: {meta['type']}",
            f"title: \"{meta['title']}\"",
            f"description: \"{meta['description']}\"",
            f"tags: [{', '.join(meta['tags'])}]",
            f"status: {meta['status']}",
            f"sources: {meta['sources']}",
            "generated:",
            "  at: \"2026-09-16T22:30:00Z\"",
            "  by: \"agent:backfill_okf\"",
            "---",
            ""
        ]
        new_content = "\n".join(frontmatter_lines) + content
        file_path.write_text(new_content, encoding="utf-8")
        print(f"Added OKF frontmatter to {rel_path}")

if __name__ == "__main__":
    apply_okf_frontmatter()
