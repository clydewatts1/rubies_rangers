"""
Rubies Rangers FPL Granular Match-by-Match Trend Analysis
Monitors minutes stability, rotation risks, rolling 3-GW xGI vs seasonal baselines, and defensive actions.
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

from fpl_client import FPLClient

DEFAULT_SQUAD = [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]

console = Console()


def audit_squad_trends(client: FPLClient, n_recent: int = 3, only_risks: bool = False):
    """Audit current Rubies Rangers squad for minutes security, rotation risks, and trend momentum."""
    squad_df = client.get_squad_trends(DEFAULT_SQUAD, n_recent=n_recent)

    title = f"Rubies Rangers — Match-by-Match Trend & Minutes Security Audit (Last {n_recent} GWs)"
    if only_risks:
        title += " [ROTATION RISKS ONLY]"
        squad_df = squad_df[squad_df["minutes_status"].isin(["BENCHED_OR_DROPPED", "ROTATION_RISK"])]

    console.print(Panel.fit(
        f"[bold gold1]{title}[/bold gold1]\n"
        f"[dim]Strategy: Moneyball | Source: Official FPL /api/element-summary/ Stream[/dim]\n"
        f"[dim]Evaluates starts vs cameos, rolling xGI momentum, and granular defensive work rate.[/dim]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=14)
    table.add_column("Club", width=6)
    table.add_column("Cost", justify="right", width=6)
    table.add_column(f"Last {n_recent} Mins", justify="center", width=14)
    table.add_column("Starts", justify="center", width=8)
    table.add_column("Minutes Security", width=20)
    table.add_column("Roll xGI", justify="right", width=9)
    table.add_column("Season xGI", justify="right", width=10)
    table.add_column("Attacking Trend", width=18)
    table.add_column("Def Act", justify="right", width=8)
    table.add_column("Pts/M", justify="right", width=6)

    pos_order = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
    squad_df["pos_rank"] = squad_df["position_name"].map(pos_order).fillna(5)
    squad_df = squad_df.sort_values(by=["pos_rank", "now_cost"], ascending=[True, False])

    benched_players = []
    rotation_risks = []
    surging_attackers = []
    defensive_anchors = []

    for _, r in squad_df.iterrows():
        pos = r["position_name"]
        color = "yellow" if pos == "GKP" else ("blue" if pos == "DEF" else ("green" if pos == "MID" else "red"))

        status_raw = r["status_badge"]
        if "BENCHED" in status_raw or "DROPPED" in status_raw:
            styled_status = f"[bold red]{status_raw}[/bold red]"
            benched_players.append(f"{r['web_name']} ({r['recent_minutes_str']} mins)")
        elif "ROTATION" in status_raw:
            styled_status = f"[bold yellow]{status_raw}[/bold yellow]"
            rotation_risks.append(f"{r['web_name']} ({r['recent_minutes_str']} mins)")
        else:
            styled_status = f"[green]{status_raw}[/green]"

        trend_raw = r["xgi_trend_label"]
        if "SURGING" in trend_raw:
            styled_trend = f"[bold red]{trend_raw}[/bold red]"
            surging_attackers.append(f"{r['web_name']} (+{r['xgi_trend_delta']} xGI)")
        elif "COOLING" in trend_raw:
            styled_trend = f"[dim cyan]{trend_raw}[/dim cyan]"
        else:
            styled_trend = f"[dim]{trend_raw}[/dim]"

        if r["avg_recent_def_contrib"] >= 5.0 and pos == "DEF":
            defensive_anchors.append(f"{r['web_name']} ({r['avg_recent_def_contrib']:.1f}/match)")

        table.add_row(
            f"[{color}]{pos}[/{color}]",
            f"[bold white]{r['web_name']}[/bold white]",
            r["club_short"],
            f"£{r['now_cost']:.1f}m",
            f"[bold]{r['recent_minutes_str']}[/bold]",
            r["recent_starts"],
            styled_status,
            f"{r['avg_recent_xgi']:.2f}",
            f"{r['season_xgi_per_match']:.2f}",
            styled_trend,
            f"{r['avg_recent_def_contrib']:.1f}",
            f"{r['avg_recent_pts']:.1f}"
        )

    console.print(table)

    insights = []
    if benched_players:
        insights.append(f"[bold red]🚨 CRITICAL MINUTES LOSS (Benched / Out of Favor):[/bold red] {', '.join(benched_players)}")
    if rotation_risks:
        insights.append(f"[bold yellow]⚠️ ROTATION / MINUTES ALERT:[/bold yellow] {', '.join(rotation_risks)}")
    if defensive_anchors:
        insights.append(f"[bold blue]🛡️ ELITE DEFENSIVE WORKHORSE FLOORS (≥5 Def Actions/m):[/bold blue] {', '.join(defensive_anchors)}")
    if surging_attackers:
        insights.append(f"[bold green]🔥 SURGING ATTACKING FORM SPIKES:[/bold green] {', '.join(surging_attackers)}")

    if insights:
        console.print(Panel(
            "\n".join(insights),
            title="[bold yellow]Moneyball Tactical Intelligence & Transfer Triggers[/bold yellow]",
            border_style="yellow"
        ))


def show_player_deep_dive(client: FPLClient, player_name: str, n_recent: int = 3):
    """Display comprehensive match-by-match log and role analysis for a specific player."""
    players_df = client.get_players_df()
    m = players_df[players_df["web_name"].str.lower() == player_name.lower()]
    if m.empty:
        m = players_df[players_df["full_name"].str.lower() == player_name.lower()]
    if m.empty:
        m = players_df[players_df["web_name"].str.contains(player_name, case=False, na=False)]
    if m.empty:
        m = players_df[players_df["full_name"].str.contains(player_name, case=False, na=False)]

    if m.empty:
        console.print(f"[bold red]Player '{player_name}' not found in live dataset.[/bold red]")
        return

    player_row = m.iloc[0]
    p_id = int(player_row["id"])
    tr = client.get_player_trends(p_id, n_recent=n_recent)

    console.print(Panel.fit(
        f"[bold gold1]{player_row['full_name']} ({player_row['club_name']}) — Granular Match Log[/bold gold1]\n"
        f"Position: [bold]{player_row['position_name']}[/bold] | Cost: [bold]£{player_row['now_cost']:.1f}m[/bold] | "
        f"Status: {tr['status_badge']}\n"
        f"Recent Minutes: [bold]{tr['recent_minutes_str']}[/bold] (Starts: {tr['recent_starts']}) | "
        f"Rolling xGI: [bold]{tr['avg_recent_xgi']:.2f}[/bold] (Season Avg: {tr['season_xgi_per_match']:.2f}) | "
        f"Trend: {tr['xgi_trend_label']}",
        border_style="cyan"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("GW", justify="center", width=5)
    table.add_column("Opponent", width=12)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Mins", justify="right", width=6)
    table.add_column("Start?", justify="center", width=7)
    table.add_column("xG", justify="right", width=6)
    table.add_column("xA", justify="right", width=6)
    table.add_column("xGI", justify="right", width=6)
    table.add_column("Tackles", justify="right", width=8)
    table.add_column("CBI", justify="right", width=6)
    table.add_column("Recov", justify="right", width=6)
    table.add_column("DefCont", justify="right", width=8)
    table.add_column("BPS", justify="right", width=5)
    table.add_column("Pts", justify="right", width=5)

    for m_log in tr["match_log"]:
        is_start = "Yes" if m_log["starts"] == 1 else "[dim]No (Sub)[/dim]"
        mins_val = m_log["minutes"]
        mins_str = f"[bold green]{mins_val}[/bold green]" if mins_val >= 75 else (f"[yellow]{mins_val}[/yellow]" if mins_val > 0 else "[bold red]0[/bold red]")
        pts_val = m_log["total_points"]
        pts_str = f"[bold cyan]{pts_val}[/bold cyan]" if pts_val >= 6 else str(pts_val)

        table.add_row(
            f"GW{m_log['round']}",
            m_log["fixture"],
            m_log["score"],
            mins_str,
            is_start,
            f"{m_log['expected_goals']:.2f}",
            f"{m_log['expected_assists']:.2f}",
            f"[bold]{m_log['expected_goal_involvements']:.2f}[/bold]",
            str(m_log["tackles"]),
            str(m_log["cbi"]),
            str(m_log["recoveries"]),
            f"[bold]{m_log['defensive_contribution']}[/bold]",
            str(m_log["bps"]),
            pts_str
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Match-by-Match Trend & Minutes Tracker")
    parser.add_argument("--squad", action="store_true", help="Audit Rubies Rangers squad match trends (default)")
    parser.add_argument("--player", type=str, default=None, help="Deep-dive into a specific player's match history")
    parser.add_argument("--risks", action="store_true", help="Filter for rotation risks or benched players")
    parser.add_argument("--weeks", type=int, default=3, help="Rolling recent matches window (default 3)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh live API cache")

    args = parser.parse_args()

    client = FPLClient()
    if args.refresh:
        client.get_bootstrap_data(force_refresh=True)

    if args.player:
        show_player_deep_dive(client, player_name=args.player, n_recent=args.weeks)
    else:
        audit_squad_trends(client, n_recent=args.weeks, only_risks=args.risks)


if __name__ == "__main__":
    main()
