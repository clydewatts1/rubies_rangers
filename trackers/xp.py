"""
Expected Points (xP) & Bookmaker Implied Probabilities CLI Tracker
Solves the optimal Starting XI, Captaincy pick, Bench hierarchy, and audits Gameweek 4 betting odds.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from analytics.xp_model import XPModel

console = Console()


def display_lineup(model: XPModel):
    """Display the optimal Starting XI, Captain, Vice-Captain, and Bench order."""
    res = model.optimize_lineup()

    console.print(Panel.fit(
        f"[bold gold1]Rubies Rangers — Gameweek 4 Optimal Starting XI & Lineup Solution[/bold gold1]\n"
        f"[dim]Strategy: Moneyball Implied Probability Modeling | Engine: Poisson & Bookmaker Match Odds[/dim]\n"
        f"[bold cyan]Optimal Formation: {res['formation']}[/bold cyan] | "
        f"[bold green]Starting XI Base xP: {res['base_starting_xp']:.2f}[/bold green] | "
        f"[bold yellow]Effective Total (with C): {res['effective_total_xp']:.2f}[/bold yellow]\n"
        f"[bold red]★ CAPTAIN (C): {res['captain']['web_name']} ({res['captain']['xP']} xP)[/bold red] | "
        f"[bold blue]☆ VICE-CAPTAIN (VC): {res['vice_captain']['web_name']} ({res['vice_captain']['xP']} xP)[/bold blue]",
        border_style="bright_blue"
    ))

    # Starters Table
    table = Table(title="[bold green]Starting XI (Ranked by Expected Points)[/bold green]", header_style="bold magenta", border_style="dim")
    table.add_column("Role", width=6, justify="center")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=14)
    table.add_column("Club", width=6)
    table.add_column("Fixture", width=10)
    table.add_column("Exp Mins", justify="right", width=9)
    table.add_column("Team xG", justify="right", width=8)
    table.add_column("P(CS)", justify="right", width=8)
    table.add_column("P(Goal)", justify="right", width=8)
    table.add_column("P(Assist)", justify="right", width=9)
    table.add_column("xBonus", justify="right", width=7)
    table.add_column("xP", justify="right", width=7, style="bold yellow")

    starters = res["starting_xi"]
    cap_id = res["captain"]["id"]
    vc_id = res["vice_captain"]["id"]

    for _, row in starters.iterrows():
        role = ""
        p_name = row["web_name"]
        if row["id"] == cap_id:
            role = "[bold red]C[/bold red]"
            p_name = f"[bold red]{p_name} (C)[/bold red]"
        elif row["id"] == vc_id:
            role = "[bold blue]VC[/bold blue]"
            p_name = f"[bold blue]{p_name} (VC)[/bold blue]"

        table.add_row(
            role,
            row["position_name"],
            p_name,
            row["club_short"],
            row["fixture"],
            f"{row['exp_mins']:.0f}'",
            f"{row['team_xg']:.2f}",
            f"{row['cs_prob']:.1f}%",
            f"{row['p_goal']:.1f}%",
            f"{row['p_assist']:.1f}%",
            f"{row['x_bonus']:.2f}",
            f"{row['xP']:.2f}"
        )

    console.print(table)

    # Bench Table
    b_table = Table(title="[bold red]Ordered Substitutes (Automatic Sub Priority)[/bold red]", header_style="bold yellow", border_style="dim")
    b_table.add_column("Sub #", width=6, justify="center")
    b_table.add_column("Pos", width=5)
    b_table.add_column("Player", width=14)
    b_table.add_column("Club", width=6)
    b_table.add_column("Fixture", width=10)
    b_table.add_column("Status", width=18)
    b_table.add_column("Exp Mins", justify="right", width=9)
    b_table.add_column("P(CS)", justify="right", width=8)
    b_table.add_column("xP", justify="right", width=7, style="bold")

    bench = res["bench"]
    for idx, (_, row) in enumerate(bench.iterrows(), start=1):
        sub_label = f"Sub {idx}" if row["position_name"] != "GKP" else "GKP Sub"
        b_table.add_row(
            sub_label,
            row["position_name"],
            row["web_name"],
            row["club_short"],
            row["fixture"],
            row["mins_status"],
            f"{row['exp_mins']:.0f}'",
            f"{row['cs_prob']:.1f}%",
            f"{row['xP']:.2f}"
        )

    console.print(b_table)


def display_squad(model: XPModel):
    """Display full squad expected points and bookmaker odds."""
    df = model.evaluate_squad_xp()

    console.print(Panel.fit(
        "[bold gold1]Rubies Rangers — 15-Player Squad Expected Points & Betting Market Odds[/bold gold1]\n"
        "[dim]Combines Understat NPxG/xA, FPL Set-Piece Hierarchy, and Bookmaker Implied Clean Sheet Probabilities[/dim]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=14)
    table.add_column("Club", width=6)
    table.add_column("Cost", justify="right", width=6)
    table.add_column("Fixture", width=10)
    table.add_column("Exp Mins", justify="right", width=9)
    table.add_column("Team xG", justify="right", width=8)
    table.add_column("P(CS)", justify="right", width=8)
    table.add_column("Goal Odds", justify="right", width=10)
    table.add_column("Assist Odds", justify="right", width=11)
    table.add_column("xBonus", justify="right", width=7)
    table.add_column("xP", justify="right", width=7, style="bold yellow")

    for _, row in df.sort_values(by="xP", ascending=False).iterrows():
        table.add_row(
            row["position_name"],
            row["web_name"],
            row["club_short"],
            f"£{row['now_cost']:.1f}m",
            row["fixture"],
            f"{row['exp_mins']:.0f}'",
            f"{row['team_xg']:.2f}",
            f"{row['cs_prob']:.1f}%",
            f"{row['goal_odds']:.2f} ({row['p_goal']:.0f}%)",
            f"{row['assist_odds']:.2f} ({row['p_assist']:.0f}%)",
            f"{row['x_bonus']:.2f}",
            f"{row['xP']:.2f}"
        )

    console.print(table)


def display_odds(model: XPModel):
    """Display Gameweek 4 bookmaker consensus implied team goals and clean sheet odds."""
    df = model.get_gw4_odds_table()

    console.print(Panel.fit(
        "[bold gold1]Gameweek 4 — Premier League Betting Market Implied Goals & Clean Sheet Odds[/bold gold1]\n"
        "[dim]Sharp Bookmaker Consensus Odds | Poisson P(CS) = e^(-Opponent xG)[/dim]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Rank", justify="center", width=5)
    table.add_column("Club", width=8)
    table.add_column("GW4 Matchup", width=14)
    table.add_column("Team xG", justify="right", width=9)
    table.add_column("Opp xG (xGC)", justify="right", width=12)
    table.add_column("P(Clean Sheet)", justify="right", width=14, style="bold green")
    table.add_column("CS Dec Odds", justify="right", width=12)

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        table.add_row(
            str(idx),
            row["Club"],
            row["GW4 Fixture"],
            f"{row['Team xG']:.2f}",
            f"{row['Opponent xG (xGC)']:.2f}",
            row["Clean Sheet Prob"],
            row["Clean Sheet Odds"]
        )

    console.print(table)


def display_captains(model: XPModel, top_n: int = 15):
    """Display Gameweek 4 top Premier League captaincy rankings."""
    df = model.get_top_captains(top_n=top_n)

    console.print(Panel.fit(
        f"[bold gold1]Gameweek 4 — Premier League Top {top_n} Captaincy & Anytime Goal Rankings[/bold gold1]\n"
        f"[dim]Ranked by Projected xP from Bookmaker Implied Team Goals and Player Threat[/dim]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Rank", justify="center", width=5)
    table.add_column("Player", width=14)
    table.add_column("Club", width=6)
    table.add_column("Pos", width=5)
    table.add_column("Cost", justify="right", width=7)
    table.add_column("GW4 Fixture", width=12)
    table.add_column("Team xG", justify="right", width=8)
    table.add_column("Match xG", justify="right", width=9)
    table.add_column("P(Goal)", justify="right", width=9)
    table.add_column("Goal Odds", justify="right", width=10)
    table.add_column("Projected xP", justify="right", width=12, style="bold yellow")
    table.add_column("Captain xP (2x)", justify="right", width=15, style="bold red")

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        table.add_row(
            str(idx),
            row["Player"],
            row["Club"],
            row["Pos"],
            row["Cost"],
            row["GW4 Fixture"],
            f"{row['Team xG']:.2f}",
            f"{row['Match xG']:.2f}",
            row["P(Goal)"],
            row["Goal Odds"],
            f"{row['Projected xP']:.2f}",
            f"{row['Captain xP (2x)']:.2f}"
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers Expected Points & Bookmaker Probabilities Tracker")
    parser.add_argument("--lineup", action="store_true", help="Solve and display optimal Starting XI, Captaincy, and Bench order")
    parser.add_argument("--squad", action="store_true", help="Display full 15-player squad xP breakdown")
    parser.add_argument("--odds", action="store_true", help="Display Gameweek 4 betting market implied goals and clean sheet odds")
    parser.add_argument("--captains", action="store_true", help="Display Premier League top captaincy rankings")
    parser.add_argument("--top", type=int, default=15, help="Number of top captain candidates to display")

    args = parser.parse_args()
    model = XPModel()

    if args.lineup:
        display_lineup(model)
    elif args.squad:
        display_squad(model)
    elif args.odds:
        display_odds(model)
    elif args.captains:
        display_captains(model, top_n=args.top)
    else:
        # Default: display Lineup followed by Squad summary
        display_lineup(model)
        console.print("\n")
        display_squad(model)


if __name__ == "__main__":
    main()
