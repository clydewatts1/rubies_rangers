"""
Rubies Rangers FPL Set-Piece & Penalty Hierarchy Matrix
Monitors designated penalty takers, direct free-kick specialists, and corner deliverers across the Premier League.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
import pandas as pd
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from clients.fpl_client import FPLClient

DEFAULT_SQUAD = [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]

console = Console()


def _fmt_order(order) -> str:
    if pd.isna(order) or order is None:
        return "[dim]-[/dim]"
    o = int(order)
    suffix = "1st" if o == 1 else ("2nd" if o == 2 else ("3rd" if o == 3 else f"{o}th"))
    if o == 1:
        return f"[bold green]{suffix}[/bold green]"
    elif o == 2:
        return f"[yellow]{suffix}[/yellow]"
    return f"[dim]{suffix}[/dim]"


def run_setpiece_tracker(club: Optional[str] = None, role: str = "all", force_refresh: bool = False):
    """Run comprehensive Premier League Set-Piece & Penalty Hierarchy report."""
    client = FPLClient()
    if force_refresh:
        client.get_bootstrap_data(force_refresh=True)

    df = client.get_set_piece_hierarchy(club_name=club)
    players_df = client.get_players_df()

    title = f"Premier League Set-Piece & Penalty Hierarchy ({role.upper()})"
    if club:
        title += f" — {club.title()}"

    console.print(Panel.fit(
        f"[bold gold1]{title}[/bold gold1]\n"
        f"[dim]Tracking primary (1st), secondary (2nd), and tertiary (3rd) dead-ball specialists.[/dim]\n"
        f"[dim]Moneyball Philosophy: A penalty is worth ~0.79 xG (+25% to +35% floor); a £6.0m player on penalties is mathematically worth as much as a £7.5m open-play attacker.[/dim]",
        border_style="cyan"
    ))

    # 1. Rubies Rangers Squad Dead-Ball Spotlight
    squad_sp = df[df["web_name"].isin(DEFAULT_SQUAD)].copy()
    if not squad_sp.empty and not club:
        squad_table = Table(title="[bold gold1]★ Rubies Rangers — Squad Dead-Ball Specialists[/bold gold1]", border_style="dim")
        squad_table.add_column("Pos", width=5)
        squad_table.add_column("Player", width=16)
        squad_table.add_column("Club", width=13)
        squad_table.add_column("Cost", justify="right", width=7)
        squad_table.add_column("⚽ Penalty", justify="center", width=12)
        squad_table.add_column("🎯 Direct FK", justify="center", width=12)
        squad_table.add_column("🚩 Corner/Ind", justify="center", width=15)
        squad_table.add_column("Score", justify="right", width=8)
        squad_table.add_column("Moneyball Tactical Valuation", width=34)

        for _, r in squad_sp.iterrows():
            # Describe tactical valuation
            notes = []
            if r.get("penalties_order") == 1:
                notes.append("[bold green]Club #1 Penalty Taker (~0.79 xG/spot kick)[/bold green]")
            elif r.get("penalties_order") == 2:
                notes.append("[yellow]Secondary Penalty Cover[/yellow]")

            if r.get("direct_freekicks_order") == 1:
                notes.append("[bold cyan]Primary Direct FK Specialist[/bold cyan]")
            if r.get("corners_and_indirect_freekicks_order") == 1:
                notes.append("[bold cyan]Primary Corner Delivery (High xA)[/bold cyan]")

            tactical_str = " | ".join(notes) if notes else "Secondary Dead-Ball Cover"

            squad_table.add_row(
                r["position_name"],
                r["web_name"],
                r["club_name"],
                f"£{r['now_cost']:.1f}m",
                _fmt_order(r.get("penalties_order")),
                _fmt_order(r.get("direct_freekicks_order")),
                _fmt_order(r.get("corners_and_indirect_freekicks_order")),
                f"{float(r.get('setpiece_moneyball_score', r.get('moneyball_score', 0.0))):.2f}",
                tactical_str
            )
        console.print(squad_table)

    # Filter role if requested
    filtered_df = df.copy()
    if role == "penalties":
        filtered_df = filtered_df[filtered_df["penalties_order"].notna()]
    elif role == "freekicks":
        filtered_df = filtered_df[filtered_df["direct_freekicks_order"].notna()]
    elif role == "corners":
        filtered_df = filtered_df[filtered_df["corners_and_indirect_freekicks_order"].notna()]

    # 2. League-wide Set-Piece Hierarchy Table
    league_table = Table(title=f"[bold cyan]Premier League Set-Piece Matrix ({len(filtered_df)} Specialists)[/bold cyan]", border_style="dim")
    league_table.add_column("Club", width=14)
    league_table.add_column("Player", width=16)
    league_table.add_column("Pos", width=5)
    league_table.add_column("Cost", justify="right", width=7)
    league_table.add_column("⚽ Penalty", justify="center", width=12)
    league_table.add_column("🎯 Direct FK", justify="center", width=12)
    league_table.add_column("🚩 Corner/Ind", justify="center", width=15)
    league_table.add_column("Score", justify="right", width=8)
    league_table.add_column("Squad Status", width=16)

    for _, r in filtered_df.iterrows():
        is_in_squad = any(
            r["web_name"].lower() == s.lower() or s.lower() in r["web_name"].lower()
            for s in DEFAULT_SQUAD
        )
        squad_badge = "[bold gold1]★ Rubies Rangers[/bold gold1]" if is_in_squad else ""

        league_table.add_row(
            r["club_name"],
            r["web_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            _fmt_order(r.get("penalties_order")),
            _fmt_order(r.get("direct_freekicks_order")),
            _fmt_order(r.get("corners_and_indirect_freekicks_order")),
            f"{float(r.get('setpiece_moneyball_score', r.get('moneyball_score', 0.0))):.2f}",
            squad_badge
        )

    console.print(league_table)

    # 3. Top Value Budget Set-Piece Gems (Under £8.0m on Penalties or FKs)
    if not club and role in ["all", "penalties"]:
        gems = players_df[(players_df["status"] == "a") & (players_df["now_cost"] <= 8.0) & (players_df["penalties_order"] == 1)].sort_values(by="moneyball_efficiency", ascending=False)
        if not gems.empty:
            gem_table = Table(title="[bold green]💰 Top Value Primary Penalty Takers Under £8.0m (Budget Arbitrage Targets)[/bold green]", border_style="green")
            gem_table.add_column("Player", width=16)
            gem_table.add_column("Club", width=14)
            gem_table.add_column("Pos", width=5)
            gem_table.add_column("Price", justify="right", width=7)
            gem_table.add_column("Pts", justify="right", width=5)
            gem_table.add_column("Form", justify="right", width=6)
            gem_table.add_column("Set Pieces", width=22)
            gem_table.add_column("SetPiece Score", justify="right", width=14)

            for _, g in gems.head(8).iterrows():
                gem_table.add_row(
                    g["web_name"],
                    g["club_name"],
                    g["position_name"],
                    f"£{g['now_cost']:.1f}m",
                    str(int(g["total_points"])),
                    f"{float(g.get('form', 0.0)):.1f}",
                    str(g.get("set_piece_badges", "None")),
                    f"{float(g.get('setpiece_moneyball_score', 0.0)):.2f}"
                )
            console.print(gem_table)

    # 4. Moneyball Set-Piece Transfer Protocol Box
    console.print(Panel(
        "[bold gold1]Moneyball Set-Piece Insights & Arbitrage Rules:[/bold gold1]\n"
        "• [bold green]The 0.79 xG Edge:[/bold green] Penalties convert at roughly 79%. A primary penalty taker generates 3–6 unassisted goals per season.\n"
        "• [bold cyan]Dead-Ball Delivery Floor:[/bold cyan] Corner deliverers (like Rayan Cherki and Pedro Porro) accumulate steady baseline Bonus Points System (BPS) and high $xA$.\n"
        "• [bold yellow]Price Tag Arbitrage:[/bold yellow] Mid-priced penalty takers (like Solanke £5.9m or Mateta £6.5m) offer expected goal involvement comparable to £8.5m+ open-play forwards.",
        border_style="yellow"
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Set-Piece & Penalty Hierarchy Matrix")
    parser.add_argument("--club", type=str, default=None, help="Filter by club name (e.g. Arsenal, Spurs, Man City)")
    parser.add_argument("--role", choices=["all", "penalties", "freekicks", "corners"], default="all", help="Filter by duty")
    parser.add_argument("--refresh", action="store_true", help="Force refresh live FPL API cache")
    args = parser.parse_args()
    run_setpiece_tracker(club=args.club, role=args.role, force_refresh=args.refresh)
