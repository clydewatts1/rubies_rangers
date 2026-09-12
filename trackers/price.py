"""
Rubies Rangers FPL Live Market Velocity & Price Change Tracker
Monitors real-time transfer streams to forecast nightly £0.1m price rises and falls.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import argparse
import pandas as pd
from typing import Dict, List, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn

from clients.fpl_client import FPLClient

DEFAULT_SQUAD = [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]

console = Console()


class PriceTracker:
    def __init__(self, force_refresh: bool = False):
        self.client = FPLClient()
        self.boot_data = self.client.get_bootstrap_data(force_refresh=force_refresh)
        self.teams = {t["id"]: t["name"] for t in self.boot_data["teams"]}
        self.team_shorts = {t["id"]: t["short_name"] for t in self.boot_data["teams"]}
        self.positions = {p["id"]: p["singular_name_short"] for p in self.boot_data["element_types"]}
        self._build_market_df()

    def _build_market_df(self):
        elements = self.boot_data["elements"]
        total_players = len(elements)
        
        rows = []
        for p in elements:
            cost = p["now_cost"] / 10.0
            tin = p.get("transfers_in_event", 0)
            tout = p.get("transfers_out_event", 0)
            net = tin - tout
            selected = p.get("selected", 1)
            selected_pct = float(p.get("selected_by_percent") or 0.0)
            cost_event = p.get("cost_change_event", 0) / 10.0
            status = p.get("status", "a")

            # Dynamic price thresholds
            # High-ownership assets need more transfers to move; baseline minimum is ~75k
            rise_threshold = max(75000, selected * 0.075)
            fall_threshold = max(60000, selected * 0.065)

            # If player already changed price in this gameweek, subsequent threshold is ~50% higher
            if cost_event > 0:
                rise_threshold *= 1.5
            elif cost_event < 0:
                fall_threshold *= 1.5

            if net >= 0:
                direction = "RISE"
                progress_pct = round((net / rise_threshold) * 100.0, 1)
                transfers_needed = max(0, int(rise_threshold - net))
            else:
                direction = "FALL"
                progress_pct = round((abs(net) / fall_threshold) * 100.0, 1)
                transfers_needed = max(0, int(fall_threshold - abs(net)))

            # Status classification
            if progress_pct >= 100.0:
                pred_status = f"{direction} TONIGHT"
                urgency = "HIGH"
            elif progress_pct >= 70.0:
                pred_status = f"{direction} Soon (24-48h)"
                urgency = "MEDIUM"
            elif progress_pct >= 40.0:
                pred_status = f"{direction} Watchlist"
                urgency = "LOW"
            else:
                pred_status = "Stable"
                urgency = "NONE"

            rows.append({
                "id": p["id"],
                "web_name": p["web_name"],
                "first_name": p["first_name"],
                "second_name": p["second_name"],
                "full_name": f"{p['first_name']} {p['second_name']}",
                "club_name": self.teams.get(p["team"], "Unknown"),
                "club_short": self.team_shorts.get(p["team"], "UNK"),
                "position_name": self.positions.get(p["element_type"], "UNK"),
                "now_cost": cost,
                "cost_change_event": cost_event,
                "cost_change_start": p.get("cost_change_start", 0) / 10.0,
                "transfers_in_event": tin,
                "transfers_out_event": tout,
                "net_transfers": net,
                "selected": selected,
                "selected_by_percent": selected_pct,
                "direction": direction,
                "progress_pct": progress_pct,
                "transfers_needed": transfers_needed,
                "pred_status": pred_status,
                "urgency": urgency,
                "status": status,
                "news": p.get("news", "")
            })

        self.df = pd.DataFrame(rows)

    def get_market_df(self) -> pd.DataFrame:
        return self.df.copy()

    def get_squad_price_report(self, squad_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Detailed market momentum and price movement report for a specific squad."""
        names = squad_names or DEFAULT_SQUAD
        df = self.df
        
        matched = []
        for name in names:
            m = df[df["web_name"].str.lower() == name.lower()]
            if m.empty:
                m = df[df["full_name"].str.lower() == name.lower()]
            if m.empty:
                m = df[df["web_name"].str.contains(name, case=False, na=False)]
            if not m.empty:
                matched.append(m.iloc[0].to_dict())

        squad_df = pd.DataFrame(matched)
        
        rises_tonight = squad_df[squad_df["pred_status"] == "RISE TONIGHT"]
        falls_tonight = squad_df[squad_df["pred_status"] == "FALL TONIGHT"]
        rising_soon = squad_df[squad_df["pred_status"] == "RISE Soon (24-48h)"]
        falling_soon = squad_df[squad_df["pred_status"] == "FALL Soon (24-48h)"]

        total_net_transfers = squad_df["net_transfers"].sum()
        projected_value_delta = (len(rises_tonight) * 0.1) - (len(falls_tonight) * 0.1)

        return {
            "squad_df": squad_df,
            "rises_tonight": rises_tonight,
            "falls_tonight": falls_tonight,
            "rising_soon": rising_soon,
            "falling_soon": falling_soon,
            "total_net_transfers": total_net_transfers,
            "projected_value_delta": round(projected_value_delta, 2)
        }

    def get_top_risers(self, limit: int = 15) -> pd.DataFrame:
        """Top players projected to rise in price tonight."""
        df = self.df
        sub = df[(df["direction"] == "RISE") & (df["status"] == "a")].copy()
        return sub.sort_values(by="progress_pct", ascending=False).head(limit)

    def get_top_fallers(self, limit: int = 15) -> pd.DataFrame:
        """Top players projected to drop in price tonight."""
        df = self.df
        sub = df[(df["direction"] == "FALL") & (df["status"] == "a")].copy()
        return sub.sort_values(by="progress_pct", ascending=False).head(limit)


def print_cli_report(force_refresh: bool = False):
    """Render rich visual CLI price tracker report."""
    tracker = PriceTracker(force_refresh=force_refresh)
    report = tracker.get_squad_price_report()

    console.print(Panel.fit(
        "[bold gold1]FPL Live Market Velocity & Price Change Tracker[/bold gold1]\n"
        "[dim]Price changes trigger nightly between 01:30 and 02:30 UTC / GMT.[/dim]\n"
        f"Squad Net Market Volume: [bold cyan]{report['total_net_transfers']:+,d} transfers[/bold cyan] | "
        f"Projected Squad Value Delta: [bold green]{report['projected_value_delta']:+.1f}m[/bold green]",
        border_style="bright_blue"
    ))

    # Squad Report Table
    squad_table = Table(title="[bold gold1]Rubies Rangers — Squad Price Movement & Velocity[/bold gold1]", border_style="dim")
    squad_table.add_column("Pos", width=5)
    squad_table.add_column("Player", width=16)
    squad_table.add_column("Club", width=13)
    squad_table.add_column("Price", justify="right", width=7)
    squad_table.add_column("Net Transfers", justify="right", width=14)
    squad_table.add_column("Progress", justify="right", width=10)
    squad_table.add_column("Needed", justify="right", width=10)
    squad_table.add_column("Nightly Forecast", width=22)

    for _, r in report["squad_df"].iterrows():
        p_status = r["pred_status"]
        if "RISE TONIGHT" in p_status:
            stat_str = "[bold green]▲ RISE TONIGHT (+£0.1m)[/bold green]"
        elif "FALL TONIGHT" in p_status:
            stat_str = "[bold red]▼ FALL TONIGHT (-£0.1m)[/bold red]"
        elif "Soon" in p_status:
            if r["direction"] == "RISE":
                stat_str = "[green]▲ Rising Soon[/green]"
            else:
                stat_str = "[red]▼ Falling Soon[/red]"
        else:
            stat_str = "[dim]Stable[/dim]"

        squad_table.add_row(
            r["position_name"],
            r["web_name"],
            r["club_name"],
            f"£{r['now_cost']:.1f}m",
            f"{r['net_transfers']:+,d}",
            f"{r['progress_pct']:.1f}%",
            f"{r['transfers_needed']:,d}",
            stat_str
        )

    console.print(squad_table)

    # Top Risers Table
    risers = tracker.get_top_risers(limit=10)
    r_table = Table(title="[bold green]▲ Premier League — Top Projected Price Rises Tonight (+£0.1m)[/bold green]", border_style="green")
    r_table.add_column("Player", width=16)
    r_table.add_column("Club", width=14)
    r_table.add_column("Pos", width=5)
    r_table.add_column("Price", justify="right", width=7)
    r_table.add_column("In / Out", justify="right", width=18)
    r_table.add_column("Net Transfers", justify="right", width=14)
    r_table.add_column("Progress", justify="right", width=10)
    r_table.add_column("Status", width=18)

    for _, r in risers.iterrows():
        r_table.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            f"{r['transfers_in_event']:,d} / {r['transfers_out_event']:,d}",
            f"{r['net_transfers']:+,d}",
            f"{r['progress_pct']:.1f}%",
            "[bold green]RISE TONIGHT[/bold green]" if r["progress_pct"] >= 100 else "[green]Rising Soon[/green]"
        )

    console.print(r_table)

    # Top Fallers Table
    fallers = tracker.get_top_fallers(limit=10)
    f_table = Table(title="[bold red]▼ Premier League — Top Projected Price Drops Tonight (-£0.1m)[/bold red]", border_style="red")
    f_table.add_column("Player", width=16)
    f_table.add_column("Club", width=14)
    f_table.add_column("Pos", width=5)
    f_table.add_column("Price", justify="right", width=7)
    f_table.add_column("In / Out", justify="right", width=18)
    f_table.add_column("Net Transfers", justify="right", width=14)
    f_table.add_column("Progress", justify="right", width=10)
    f_table.add_column("Status", width=18)

    for _, r in fallers.iterrows():
        f_table.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            f"{r['transfers_in_event']:,d} / {r['transfers_out_event']:,d}",
            f"{r['net_transfers']:+,d}",
            f"{r['progress_pct']:.1f}%",
            "[bold red]FALL TONIGHT[/bold red]" if r["progress_pct"] >= 100 else "[red]Falling Soon[/red]"
        )

    console.print(f_table)

    # Moneyball Actionable Advice
    console.print(Panel(
        "[bold cyan]Moneyball Transfer Timing Protocol:[/bold cyan]\n"
        "• [bold green]Buying an Asset:[/bold green] Execute your transfer [bold]before 01:30 UTC[/bold] on the night a player rises to lock in the lower price.\n"
        "• [bold red]Selling an Underperformer:[/bold red] Sell [bold]before 01:30 UTC[/bold] on the night they drop to preserve your bank capital and team value.\n"
        "• [bold yellow]Profit Realization:[/bold yellow] In FPL, you receive £0.1m profit for every £0.2m a player rises while in your squad.",
        border_style="yellow"
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FPL Live Market Velocity & Price Change Tracker")
    parser.add_argument("--refresh", action="store_true", help="Force refresh live FPL data")
    args = parser.parse_args()
    print_cli_report(force_refresh=args.refresh)
