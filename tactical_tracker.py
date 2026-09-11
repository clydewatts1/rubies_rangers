"""
Rubies Rangers FPL Advanced Tactical Process Tracker (Understat / Shot Quality)
Monitors Non-Penalty Expected Goals (NPxG/90), Shot Quality (xG/Shot), Box Dominance, and Open-Play Threat.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
import pandas as pd
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from tactical_client import TacticalClient, normalize_name

console = Console()


def audit_squad_tactical(client: TacticalClient, force_refresh: bool = False):
    """Audit current Rubies Rangers squad with advanced tactical process metrics."""
    squad_df = client.get_squad_tactical_df(force_refresh=force_refresh)

    console.print(Panel.fit(
        f"[bold gold1]Rubies Rangers — Tactical Process & Shot Quality Audit[/bold gold1]\n"
        f"[dim]Strategy: Moneyball | Source: Understat Official 2026/27 Live Shot Stream[/dim]\n"
        f"[dim]Evaluates NPxG (Non-Penalty Threat), Shot Quality (xG/Shot), Box Dominance, and Open-Play Creation.[/dim]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Player", width=14)
    table.add_column("Club", width=15)
    table.add_column("Shots", justify="right", width=6)
    table.add_column("Goals", justify="right", width=6)
    table.add_column("NPxG", justify="right", width=7)
    table.add_column("NPxG/90", justify="right", width=8)
    table.add_column("xG/Shot", justify="right", width=8)
    table.add_column("Box %", justify="right", width=7)
    table.add_column("NPxGI/90", justify="right", width=9)
    table.add_column("Tactical Archetype", width=24)

    # Sort by NPxGI/90
    squad_df = squad_df.sort_values(by="NPxGI_90", ascending=False)

    clinical_poachers = []
    dual_threats = []
    speculative_shooters = []

    for _, r in squad_df.iterrows():
        p_name = r["player_name"]
        shots = r["shots"]
        xg_shot = r["xG_per_shot"]
        npxgi = r["NPxGI_90"]
        box_pct = r["box_shot_pct"]
        arch = r["tactical_archetype"]

        # Styling
        if xg_shot >= 0.20 and shots >= 5:
            styled_xg_shot = f"[bold green]{xg_shot:.3f}[/bold green]"
            clinical_poachers.append(f"{p_name} ({xg_shot:.3f} xG/shot)")
        elif xg_shot < 0.08 and shots >= 5:
            styled_xg_shot = f"[bold red]{xg_shot:.3f}[/bold red]"
            speculative_shooters.append(f"{p_name} ({xg_shot:.3f} xG/shot)")
        else:
            styled_xg_shot = f"{xg_shot:.3f}"

        if npxgi >= 0.85:
            styled_npxgi = f"[bold cyan]{npxgi:.2f}[/bold cyan]"
            dual_threats.append(f"{p_name} ({npxgi:.2f})")
        else:
            styled_npxgi = f"{npxgi:.2f}"

        if "ELITE" in arch:
            styled_arch = f"[bold cyan]{arch}[/bold cyan]"
        elif "CLINICAL" in arch:
            styled_arch = f"[bold green]{arch}[/bold green]"
        elif "PERIMETER" in arch:
            styled_arch = f"[yellow]{arch}[/yellow]"
        else:
            styled_arch = f"[dim]{arch}[/dim]"

        table.add_row(
            f"[bold white]{p_name}[/bold white]",
            r["team_title"],
            str(int(shots)),
            str(int(r["goals"])),
            f"{r['NPxG']:.2f}",
            f"{r['NPxG_90']:.2f}",
            styled_xg_shot,
            f"{box_pct:.1f}%",
            styled_npxgi,
            styled_arch
        )

    console.print(table)

    # Tactical Intelligence Panel
    insights = []
    if clinical_poachers:
        insights.append(f"[bold green]🎯 HIGH-PROBABILITY BOX FINISHERS (xG/Shot ≥ 0.20):[/bold green] {', '.join(clinical_poachers)}")
    if dual_threats:
        insights.append(f"[bold cyan]👑 PREMIER LEAGUE OPEN-PLAY TITANS (NPxGI/90 ≥ 0.85):[/bold cyan] {', '.join(dual_threats)}")
    if speculative_shooters:
        insights.append(f"[bold red]🚀 LOW SHOT QUALITY / PERIMETER SHOOTERS (xG/Shot < 0.08):[/bold red] {', '.join(speculative_shooters)}")

    if insights:
        console.print(Panel(
            "\n".join(insights),
            title="[bold yellow]Moneyball Tactical Intelligence & Shot Quality Analysis[/bold yellow]",
            border_style="yellow"
        ))


def show_league_leaders(client: TacticalClient, top_n: int = 15):
    """Display Premier League leaderboards for Shot Quality and Open-Play Threat."""
    df = client.get_league_tactical_df()

    console.print(Panel.fit(
        f"[bold gold1]Premier League Advanced Tactical Process Leaderboard[/bold gold1]\n"
        f"[dim]Top performers in Shot Quality (xG/Shot) and Non-Penalty Expected Goal Involvements (NPxGI/90).[/dim]",
        border_style="green"
    ))

    # Leaderboard 1: Shot Quality
    table_qual = Table(title="[bold green]Top Attackers by Shot Quality (xG per Shot, Min 6 Shots)[/bold green]", border_style="green")
    table_qual.add_column("Rank", justify="center", width=5)
    table_qual.add_column("Player", width=20)
    table_qual.add_column("Club", width=18)
    table_qual.add_column("Shots", justify="right", width=6)
    table_qual.add_column("Goals", justify="right", width=6)
    table_qual.add_column("xG", justify="right", width=6)
    table_qual.add_column("xG/Shot", justify="right", width=9)
    table_qual.add_column("NPxG/90", justify="right", width=8)

    qual_df = df[df["shots"] >= 6].sort_values(by="xG_per_shot", ascending=False).head(top_n)
    for idx, (_, r) in enumerate(qual_df.iterrows(), 1):
        table_qual.add_row(
            str(idx),
            f"[bold white]{r['player_name']}[/bold white]",
            r["team_title"],
            str(int(r["shots"])),
            str(int(r["goals"])),
            f"{r['xG']:.2f}",
            f"[bold green]{r['xG_per_shot']:.3f}[/bold green]",
            f"{r['NPxG_90']:.2f}"
        )

    console.print(table_qual)

    # Leaderboard 2: Open Play Threat (NPxGI/90)
    table_threat = Table(title="[bold cyan]Top Players by Open-Play Threat (NPxGI/90, Min 180 Mins)[/bold cyan]", border_style="cyan")
    table_threat.add_column("Rank", justify="center", width=5)
    table_threat.add_column("Player", width=20)
    table_threat.add_column("Club", width=18)
    table_threat.add_column("Mins", justify="right", width=6)
    table_threat.add_column("NPxG/90", justify="right", width=8)
    table_threat.add_column("xA/90", justify="right", width=7)
    table_threat.add_column("NPxGI/90", justify="right", width=9)
    table_threat.add_column("xG/Shot", justify="right", width=8)

    threat_df = df[df["minutes"] >= 180].sort_values(by="NPxGI_90", ascending=False).head(top_n)
    for idx, (_, r) in enumerate(threat_df.iterrows(), 1):
        table_threat.add_row(
            str(idx),
            f"[bold white]{r['player_name']}[/bold white]",
            r["team_title"],
            str(int(r["minutes"])),
            f"{r['NPxG_90']:.2f}",
            f"{r['xA_90']:.2f}",
            f"[bold cyan]{r['NPxGI_90']:.2f}[/bold cyan]",
            f"{r['xG_per_shot']:.3f}"
        )

    console.print(table_threat)


def show_player_shots(client: TacticalClient, player_name: str):
    """Display individual shot map and location breakdown for a player."""
    df = client.get_league_tactical_df()
    norm = normalize_name(player_name)
    m = df[df["norm_name"].str.contains(norm, case=False, na=False)]
    if m.empty:
        parts = norm.split()
        if len(parts) > 1:
            m = df[df["norm_name"].str.contains(parts[-1], case=False, na=False)]

    if m.empty:
        console.print(f"[bold red]Player '{player_name}' not found in Understat dataset.[/bold red]")
        return

    p_row = m.iloc[0]
    u_id = p_row["understat_id"]
    sb = client.get_player_shot_breakdown(u_id)

    console.print(Panel.fit(
        f"[bold gold1]{p_row['player_name']} ({p_row['team_title']}) — Shot Map & Box Breakdown[/bold gold1]\n"
        f"Total Shots: [bold]{sb['total_shots']}[/bold] | Total xG: [bold]{sb['total_xG']:.2f}[/bold] | "
        f"Avg Shot Quality: [bold green]{sb['avg_shot_quality']:.3f} xG/shot[/bold green]\n"
        f"Box Dominance: [bold]{sb['box_shot_pct']:.1f}% in Box[/bold] "
        f"([cyan]{sb['six_yard_shots']} in 6-Yard Box[/cyan], [blue]{sb['penalty_box_shots']} in 18-Yard Box[/blue], [red]{sb['outside_box_shots']} Outside[/red])",
        border_style="cyan"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Min", justify="center", width=5)
    table.add_column("Result", width=14)
    table.add_column("Situation", width=12)
    table.add_column("Shot Type", width=12)
    table.add_column("Location", width=14)
    table.add_column("Pitch X", justify="right", width=8)
    table.add_column("Pitch Y", justify="right", width=8)
    table.add_column("xG", justify="right", width=7)

    for s in sb["shot_log"]:
        res_str = f"[bold green]{s['result']}[/bold green]" if s["result"] == "Goal" else s["result"]
        loc = s["location"]
        loc_str = f"[bold cyan]{loc}[/bold cyan]" if loc == "6-Yard Box" else (f"[blue]{loc}[/blue]" if loc == "Penalty Box" else f"[dim red]{loc}[/dim red]")

        table.add_row(
            str(s["minute"]),
            res_str,
            s["situation"],
            s["shot_type"],
            loc_str,
            f"{s['X']:.2f}",
            f"{s['Y']:.2f}",
            f"{s['xG']:.3f}"
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Tactical Process & Shot Quality Tracker")
    parser.add_argument("--squad", action="store_true", help="Audit Rubies Rangers squad tactical process (default)")
    parser.add_argument("--leaders", action="store_true", help="Show Premier League Shot Quality and NPxGI leaderboards")
    parser.add_argument("--shots", type=str, default=None, help="Display shot map and location log for a player (e.g. Isak)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh live Understat cache")

    args = parser.parse_args()

    client = TacticalClient()
    if args.refresh:
        client.get_league_players_raw(force_refresh=True)

    if args.shots:
        show_player_shots(client, player_name=args.shots)
    elif args.leaders:
        show_league_leaders(client)
    else:
        audit_squad_tactical(client, force_refresh=args.refresh)


if __name__ == "__main__":
    main()
