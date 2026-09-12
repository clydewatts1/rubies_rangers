"""
Rubies Rangers FPL Monte Carlo Transfer Tracker CLI
Displays stochastic transfer evaluations, hit penalties, and the 3 Best Transfer Archetypes.
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
from rich.text import Text

from analytics.montecarlo import MonteCarloEngine

console = Console()


def run_montecarlo_cli(sims: int = 2500,
                       transfers: int = 1,
                       free_transfers: int = 1,
                       bank: float = 3.7,
                       pos_filter: str = "ALL",
                       sell_filter: str = None,
                       show_all: bool = False):
    """Run Monte Carlo simulation and display results in terminal."""
    hit_penalty = max(0, transfers - free_transfers) * 4

    console.print(Panel.fit(
        f"[bold gold1]🎲 Rubies Rangers — Monte Carlo Transfer Optimizer[/bold gold1]\n"
        f"[dim]Simulations: {sims:,} trials | Transfers: {transfers} | Free: {free_transfers} | Hit Cost: -{hit_penalty} pts | Bank: £{bank:.1f}m[/dim]\n"
        f"[dim]Hygiene: Strictly purged injured, suspended, and transferred-out non-starters.[/dim]",
        border_style="bright_blue"
    ))

    with console.status(f"[bold cyan]Simulating {sims:,} gameweek scenarios across candidate transfers...[/bold cyan]"):
        mc = MonteCarloEngine()
        res = mc.evaluate_transfers(
            bank=bank,
            num_transfers=transfers,
            free_transfers=free_transfers,
            n_sims=sims,
            position_filter=None if pos_filter == "ALL" else pos_filter,
            sell_player_filter=sell_filter
        )

    if not res.get("success"):
        console.print(f"[bold red]❌ {res.get('message', 'No valid transfers found.')}[/bold red]")
        return

    base = res["baseline"]
    console.print(Panel(
        f"[bold white]Baseline Squad (Current 15):[/bold white] "
        f"Mean: [bold cyan]{base['mean']} pts[/bold cyan] | "
        f"Floor (P10): [bold green]{base['p10']} pts[/bold green] | "
        f"Median (P50): [bold]{base['p50']} pts[/bold] | "
        f"Ceiling (P90): [bold magenta]{base['p90']} pts[/bold magenta] | "
        f"Std Dev: ±{base['std']}",
        border_style="dim"
    ))

    top_3 = res["top_3"]
    console.print("\n[bold gold1]✨ The 3 Best Strategic Transfer Options (Monte Carlo Modeled):[/bold gold1]\n")

    for i, opt in enumerate(top_3):
        color = opt.get("badge_color", "cyan")
        border = "gold1" if i == 0 else ("green" if i == 1 else "magenta")
        title = f"OPTION {i+1}: {opt['archetype']}"

        hit_txt = f" [bold red](-{opt['hit_penalty']} pts hit)[/bold red]" if opt['hit_penalty'] > 0 else " [bold green](Free)[/bold green]"

        content = (
            f"[bold red]SELL OUT:[/bold red] {opt['out_player']} [dim]({opt['out_club']} | £{opt['out_cost']}m | avg {opt['out_mean']} pts)[/dim]\n"
            f"[bold green]BUY IN:  [/bold green] {opt['in_player']} [dim]({opt['in_club']} | £{opt['in_cost']}m | avg {opt['in_mean']} pts)[/dim]\n"
            f"────────────────────────────────────────────────────────────────────────\n"
            f"• [bold white]Net Expected Gain:[/bold white] [bold gold1]{opt['net_mean_gain']:+.2f} pts/GW[/bold gold1]{hit_txt}\n"
            f"• [bold white]Win Probability (Beats Current Squad):[/bold white] [bold cyan]{opt['win_prob']}%[/bold cyan]\n"
            f"• [bold white]Floor (P10 Safety):[/bold white] {opt['floor_p10']} pts | "
            f"[bold white]Ceiling (P90 Haul):[/bold white] {opt['ceiling_p90']} pts | "
            f"[bold white]Sharpe Ratio:[/bold white] {opt['sharpe']}\n"
            f"• [bold white]Bank Remaining:[/bold white] £{opt['bank_remaining']:.1f}m (Cost Delta: {opt['cost_diff']:+.1f}m)\n"
            f"• [dim italic]{opt['rationale']}[/dim italic]"
        )

        console.print(Panel(content, title=f"[bold {border}]{title}[/bold {border}]", border_style=border))

    # All candidate table
    df_all = res["all_results_df"]
    console.print(f"\n[bold cyan]📋 Evaluated Transfer Candidates (Top {min(15, len(df_all))} of {len(df_all)}):[/bold cyan]")
    
    tbl = Table(show_header=True, header_style="bold magenta", border_style="dim")
    tbl.add_column("Rank", width=5, justify="center")
    tbl.add_column("Sell Out", width=14)
    tbl.add_column("Buy In", width=14)
    tbl.add_column("Club", width=8, justify="center")
    tbl.add_column("Cost Δ", width=8, justify="right")
    tbl.add_column("Net Gain", width=10, justify="right")
    tbl.add_column("Win %", width=8, justify="right")
    tbl.add_column("P10 Floor", width=10, justify="right")
    tbl.add_column("P50 Med", width=9, justify="right")
    tbl.add_column("P90 Ceil", width=10, justify="right")
    tbl.add_column("Bank Left", width=10, justify="right")

    for rank, (_, row) in enumerate(df_all.head(15).iterrows(), start=1):
        gain_str = f"[bold green]+{row['net_mean_gain']:.2f}[/bold green]" if row['net_mean_gain'] > 0 else f"[red]{row['net_mean_gain']:.2f}[/red]"
        win_str = f"[cyan]{row['win_prob']:.1f}%[/cyan]"
        tbl.add_row(
            str(rank),
            str(row["out_player"]),
            f"[bold]{row['in_player']}[/bold]",
            str(row["in_club"]),
            f"{row['cost_diff']:+.1f}m",
            gain_str,
            win_str,
            str(row["floor_p10"]),
            str(row["median_p50"]),
            str(row["ceiling_p90"]),
            f"£{row['bank_remaining']:.1f}m"
        )

    console.print(tbl)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Monte Carlo Transfer Optimizer")
    parser.add_argument("--sims", type=int, default=2500, help="Number of Monte Carlo simulations (default: 2500)")
    parser.add_argument("--transfers", type=int, default=1, choices=[1, 2], help="Number of transfers to evaluate (1 or 2)")
    parser.add_argument("--free", type=int, default=1, help="Number of free transfers available (default: 1)")
    parser.add_argument("--bank", type=float, default=3.7, help="Current bank balance in £m (default: 3.7)")
    parser.add_argument("--pos", type=str, default="ALL", choices=["ALL", "GKP", "DEF", "MID", "FWD"], help="Position filter")
    parser.add_argument("--sell", type=str, default=None, help="Filter transfers to sell a specific player (e.g. Senesi)")
    parser.add_argument("--all", action="store_true", help="Display full table of all evaluated candidates")

    args = parser.parse_args()
    run_montecarlo_cli(
        sims=args.sims,
        transfers=args.transfers,
        free_transfers=args.free,
        bank=args.bank,
        pos_filter=args.pos,
        sell_filter=args.sell,
        show_all=args.all
    )


if __name__ == "__main__":
    main()
