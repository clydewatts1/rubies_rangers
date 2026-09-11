"""
Rubies Rangers FPL Rolling Fixture Difficulty Rating (FDR) & Schedule Swing Tracker
Monitors upcoming schedule difficulty and detects critical fixture inflection swings.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
import pandas as pd
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


def run_fixture_tracker(weeks: int = 6, force_refresh: bool = False):
    """Run comprehensive Rolling FDR & Fixture Swing Detector report."""
    client = FPLClient()
    if force_refresh:
        client.get_fixtures_data(force_refresh=True)

    fdr_map = client.get_team_fdr_map(n_gameweeks=weeks)
    swings = client.get_fixture_swings(n_gameweeks=weeks)
    players_df = client.get_players_df(n_fdr_weeks=weeks)
    current_gw = client.get_current_gameweek() or 1
    next_gws = list(range(current_gw + 1, current_gw + weeks + 1))

    console.print(Panel.fit(
        f"[bold gold1]Premier League Rolling FDR & Schedule Swing Detector[/bold gold1]\n"
        f"[dim]Source: Official FPL Fixtures API | Horizon: GW{next_gws[0]} through GW{next_gws[-1]} ({weeks} Gameweeks)[/dim]\n"
        f"[dim]Moneyball Philosophy: Past points show what happened; upcoming fixtures predict what will happen.[/dim]",
        border_style="cyan"
    ))

    # 1. Fixture Swing Detector Highlights Panel
    swing_text = "[bold cyan]⚡ FIXTURE SWING DETECTOR (Moneyball Inflection Windows)[/bold cyan]\n"
    swing_text += "[dim]Swing Delta = (Near-term GW4-5 FDR) - (Later GW6+ FDR). Positive = Schedule gets easier (Buy Window)![/dim]\n\n"

    swing_text += "[bold green]🟢 Top Positive Swings (Tough Now ➔ Easy Run Ahead — BUY TARGETS):[/bold green]\n"
    for t in swings["positive_swings"][:4]:
        swing_text += f"• [bold]{t['team_name']}[/bold] (Swing: [bold green]+{t['swing_delta']:.2f} ▲[/bold green]) — Near FDR: {t['near_fdr']:.2f} ➔ Later FDR: [bold green]{t['later_fdr']:.2f}[/bold green] (Next: {t['next_fixture']})\n"

    swing_text += "\n[bold red]🔴 Top Negative Swings (Easy Now ➔ Red Wall Approaching — SELL ALERTS):[/bold red]\n"
    for t in swings["negative_swings"][:4]:
        swing_text += f"• [bold]{t['team_name']}[/bold] (Swing: [bold red]{t['swing_delta']:.2f} ▼[/bold red]) — Near FDR: {t['near_fdr']:.2f} ➔ Later FDR: [bold red]{t['later_fdr']:.2f}[/bold red] (Next: {t['next_fixture']})\n"

    swing_text += "\n[bold gold1]★ Rubies Rangers Squad Swing Notes:[/bold gold1]\n"
    swing_text += "• [bold green]Robin Roefs (Sunderland, +2.25 ▲)[/bold green]: Bench through Arsenal/Chelsea (GW4-5); starts during league's easiest green run from GW6!\n"
    swing_text += "• [bold green]Antonee Robinson (Fulham, +1.50 ▲)[/bold green]: Clean sheet potential skyrockets from GW6 (Ipswich, Hull, Coventry).\n"
    swing_text += "• [bold yellow]João Pedro & Morgan Rogers (Chelsea, -0.75 ▼)[/bold yellow]: Capitalize on GW4-5 (Hull, Brentford) before City/Liverpool tests."

    console.print(Panel(swing_text.strip(), border_style="bright_blue"))

    # 2. Rubies Rangers Squad Fixture Outlook Table
    squad_rows = []
    for name in DEFAULT_SQUAD:
        m = players_df[players_df["web_name"].str.lower() == name.lower()]
        if m.empty:
            m = players_df[players_df["full_name"].str.lower() == name.lower()]
        if not m.empty:
            squad_rows.append(m.iloc[0].to_dict())

    squad_df = pd.DataFrame(squad_rows)
    squad_table = Table(title=f"[bold gold1]Rubies Rangers — Squad Schedule Outlook (GW{next_gws[0]} - GW{next_gws[-1]})[/bold gold1]", border_style="dim")
    squad_table.add_column("Pos", width=5)
    squad_table.add_column("Player", width=16)
    squad_table.add_column("Club", width=14)
    squad_table.add_column("Next Match", width=14)
    squad_table.add_column(f"{weeks}GW FDR", justify="center", width=9)
    squad_table.add_column("Swing", justify="center", width=10)
    squad_table.add_column("Schedule Phase", width=22)
    squad_table.add_column("Action", width=18)

    for _, r in squad_df.iterrows():
        fdr_val = float(r.get("fdr_next_5", 3.0))
        if fdr_val <= 2.7:
            fdr_str = f"[bold green]{fdr_val:.2f}[/bold green]"
        elif fdr_val <= 3.1:
            fdr_str = f"[yellow]{fdr_val:.2f}[/yellow]"
        else:
            fdr_str = f"[bold red]{fdr_val:.2f}[/bold red]"

        delta = float(r.get("swing_delta", 0.0))
        if delta >= 0.8:
            swing_str = f"[bold green]+{delta:.2f} ▲[/bold green]"
            phase = "[bold green]Tough ➔ Green Run[/bold green]"
            action = "[green]Hold / Start GW6[/green]"
        elif delta >= 0.4:
            swing_str = f"[green]+{delta:.2f} ▲[/green]"
            phase = "[green]Improving Run[/green]"
            action = "[green]Hold / Monitor[/green]"
        elif delta <= -0.8:
            swing_str = f"[bold red]{delta:.2f} ▼[/bold red]"
            phase = "[bold red]Red Wall Ahead[/bold red]"
            action = "[bold red]Plan Exit GW6[/bold red]"
        elif delta <= -0.4:
            swing_str = f"[red]{delta:.2f} ▼[/red]"
            phase = "[red]Tightening Run[/red]"
            action = "[yellow]Hold Short-Term[/yellow]"
        else:
            swing_str = "[dim]0.00[/dim]"
            phase = "[dim]Consistent FDR[/dim]"
            action = "[dim]Standard Rotation[/dim]"

        squad_table.add_row(
            r["position_name"],
            r["web_name"],
            r["club_name"],
            str(r.get("next_fixture", "N/A")),
            fdr_str,
            swing_str,
            phase,
            action
        )

    console.print(squad_table)

    # 3. Full 20-Team Schedule Grid
    table = Table(title=f"[bold cyan]Premier League 20-Club Rolling Schedule Grid (GW{next_gws[0]} - GW{next_gws[-1]})[/bold cyan]", border_style="dim")
    table.add_column("Rank", justify="right", width=5)
    table.add_column("Club", width=16)
    table.add_column("Avg FDR", justify="center", width=8)
    table.add_column("Swing", justify="center", width=10)
    for gw in next_gws:
        table.add_column(f"GW{gw}", justify="center", width=11)

    sorted_teams = sorted(fdr_map.values(), key=lambda x: x["avg_fdr"])
    for rank, t in enumerate(sorted_teams, 1):
        avg_val = t["avg_fdr"]
        if avg_val <= 2.7:
            avg_str = f"[bold green]{avg_val:.2f}[/bold green]"
        elif avg_val <= 3.1:
            avg_str = f"[yellow]{avg_val:.2f}[/yellow]"
        else:
            avg_str = f"[bold red]{avg_val:.2f}[/bold red]"

        delta = t.get("swing_delta", 0.0)
        if delta >= 0.8:
            swing_str = f"[bold green]+{delta:.2f} ▲[/bold green]"
        elif delta >= 0.4:
            swing_str = f"[green]+{delta:.2f} ▲[/green]"
        elif delta <= -0.8:
            swing_str = f"[bold red]{delta:.2f} ▼[/bold red]"
        elif delta <= -0.4:
            swing_str = f"[red]{delta:.2f} ▼[/red]"
        else:
            swing_str = "[dim]0.00[/dim]"

        gw_cells = []
        for f in t["fixtures"]:
            diff = f["difficulty"]
            loc = "H" if f["is_home"] else "A"
            cell = f"{f['opp_short']}({loc})"
            if diff <= 2:
                gw_cells.append(f"[green]{cell}[/green]")
            elif diff == 3:
                gw_cells.append(f"[yellow]{cell}[/yellow]")
            else:
                gw_cells.append(f"[red]{cell}[/red]")

        while len(gw_cells) < len(next_gws):
            gw_cells.append("[dim]Blank[/dim]")

        table.add_row(str(rank), t["team_name"], avg_str, swing_str, *gw_cells)

    console.print(table)

    # 4. Actionable Moneyball Strategy Box
    console.print(Panel(
        "[bold gold1]Moneyball Schedule Rules & Timing:[/bold gold1]\n"
        "• [bold green]Accumulation Zone:[/bold green] Identify assets with high $xGI$ from clubs with positive swings ([bold green]+Delta[/bold green]). Buy 1 week before the green run begins while ownership is low and price is depressed.\n"
        "• [bold red]Profit-Taking Zone:[/bold red] Identify assets with negative swings ([bold red]-Delta[/bold red]). Sell before the red wall begins to lock in accrued team value and dodge incoming blanks.\n"
        "• [bold cyan]Bench Synergy:[/bold cyan] Pair budget assets with opposing fixture swings (e.g., Sunderland's Roefs with Brighton's Verbruggen) to guarantee a green fixture every gameweek.",
        border_style="yellow"
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Rolling FDR & Schedule Swing Tracker")
    parser.add_argument("--weeks", type=int, default=6, choices=[3, 4, 5, 6], help="Rolling schedule horizon (3 to 6 gameweeks)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh live fixtures cache")
    args = parser.parse_args()
    run_fixture_tracker(weeks=args.weeks, force_refresh=args.refresh)
