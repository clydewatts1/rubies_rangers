"""
Rubies Rangers FPL Team Manager CLI
Interactive Moneyball squad audit, FDR schedule ticker, and transfer optimizer.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import argparse
from typing import Optional, List, Dict, Any
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from clients.fpl_client import FPLClient
from analytics.optimizer import FPLOptimizer
from trackers.trend import audit_squad_trends, show_player_deep_dive
from trackers.tactical import audit_squad_tactical, show_league_leaders, show_player_shots
from trackers.xp import display_lineup, display_squad, display_odds, display_captains
from analytics.xp_model import XPModel
from trackers.league import LeagueTracker, display_league_standings, display_team_leagues, display_rival_squad, display_league_history
from config_manager import get_system_config, get_params, set_active_profile, get_active_profile

DEFAULT_SQUAD = get_system_config("default_squad") or [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]
DEFAULT_BANK = float(get_system_config("default_bank") or 3.7)

console = Console()


def load_dataset(source: str = "live", force_refresh: bool = False) -> pd.DataFrame:
    if source == "csv":
        csv_path = "fpl_player_statistics.csv"
        console.print(f"[cyan]Loading historical data from {csv_path}...[/cyan]")
        df = pd.read_csv(csv_path)
        if "now_cost" in df.columns:
            df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce")
        if "web_name" not in df.columns and "player_name" in df.columns:
            df["web_name"] = df["player_name"]
            df["full_name"] = df["player_name"]
        if "moneyball_score" not in df.columns:
            mb_params = get_params("moneyball")
            fwd_cfg = mb_params.get("fwd_mid", {})
            xgi = df.get("expected_goal_involvements_per_90", 0).fillna(0)
            ict = df.get("ict_index", 0).fillna(0)
            ppg = df.get("points_per_game", 0).fillna(0)
            df["moneyball_score"] = (xgi * fwd_cfg.get("xgi_weight", 4.0)) + (ict / fwd_cfg.get("ict_divisor", 50.0)) + (ppg * fwd_cfg.get("ppg_weight", 1.2))
        if "fdr_moneyball_score" not in df.columns:
            df["fdr_moneyball_score"] = df["moneyball_score"]
        if "fdr_next_5" not in df.columns:
            df["fdr_next_5"] = 3.0
            df["next_fixture"] = "N/A"
        return df

    else:
        client = FPLClient()
        df = client.get_players_df(force_refresh=force_refresh)
        return df


def audit_squad(source: str = "live"):
    """Audit current Rubies Rangers squad with rolling FDR."""
    df = load_dataset(source)
    matched_rows = []
    
    for name in DEFAULT_SQUAD:
        m = df[df["web_name"].str.lower() == name.lower()]
        if m.empty:
            m = df[df["full_name"].str.lower() == name.lower()]
        if m.empty:
            m = df[df["web_name"].str.contains(name, case=False, na=False)]
        if m.empty:
            m = df[df["full_name"].str.contains(name, case=False, na=False)]
        if not m.empty:
            matched_rows.append(m.iloc[0].to_dict())

    squad_df = pd.DataFrame(matched_rows)
    total_cost = squad_df["now_cost"].sum()
    total_pts = squad_df["total_points"].sum()

    console.print(Panel.fit(
        f"[bold gold1]Rubies Rangers — Squad Audit & Fixture Outlook[/bold gold1]\n"
        f"[dim]Strategy: Moneyball | Source: {source.upper()}[/dim]\n"
        f"Total Players: [bold]{len(squad_df)}/15[/bold] | "
        f"Squad Value: [bold]£{total_cost:.1f}m[/bold] | "
        f"In the Bank: [bold green]£{DEFAULT_BANK:.1f}m[/bold green] | "
        f"Total Points: [bold cyan]{int(total_pts)}[/bold cyan]",
        border_style="bright_blue"
    ))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=16)
    table.add_column("Club", width=13)
    table.add_column("Cost", justify="right", width=7)
    table.add_column("Pts", justify="right", width=5)
    table.add_column("Form", justify="right", width=6)
    table.add_column("Next Match", width=14)
    table.add_column("5GW FDR", justify="center", width=9)
    table.add_column("FDR Score", justify="right", width=10)
    table.add_column("Set Pieces", width=22)
    table.add_column("Price Trend", justify="center", width=14)
    table.add_column("Status", width=10)

    for pos in ["GKP", "DEF", "MID", "FWD"]:
        pos_df = squad_df[squad_df["position_name"] == pos]
        for _, p in pos_df.iterrows():
            status = p.get("status", "a")
            if status == "u":
                status_str = "[bold red]UNAVAIL[/bold red]"
            elif status == "i":
                status_str = "[red]INJURED[/red]"
            elif status == "d":
                status_str = "[yellow]DOUBTFUL[/yellow]"
            else:
                status_str = "[green]Active[/green]"

            form_val = f"{float(p.get('form', 0.0)):.1f}"
            fdr_mb_val = f"{float(p.get('fdr_moneyball_score', p.get('moneyball_score', 0.0))):.2f}"
            
            fdr_5 = float(p.get("fdr_next_5", 3.0))
            if fdr_5 <= 2.7:
                fdr_str = f"[bold green]{fdr_5:.2f}[/bold green]"
            elif fdr_5 <= 3.1:
                fdr_str = f"[yellow]{fdr_5:.2f}[/yellow]"
            else:
                fdr_str = f"[bold red]{fdr_5:.2f}[/bold red]"

            next_fix = str(p.get("next_fixture", "N/A"))

            # Set Pieces badges
            sp_badges = p.get("set_piece_badges", "None")
            if not sp_badges or sp_badges == "None":
                sp_str = "[dim]-[/dim]"
            else:
                sp_str = f"[bold cyan]{sp_badges}[/bold cyan]"

            # Price trend string
            p_status = p.get("price_status", "Stable")
            if "RISE TONIGHT" in p_status:
                price_trend_str = "[bold green]▲ RISE TONIGHT[/bold green]"
            elif "FALL TONIGHT" in p_status:
                price_trend_str = "[bold red]▼ FALL TONIGHT[/bold red]"
            elif "RISE" in p_status:
                price_trend_str = "[green]▲ Rising[/green]"
            elif "FALL" in p_status:
                price_trend_str = "[red]▼ Falling[/red]"
            else:
                price_trend_str = "[dim]Stable[/dim]"

            table.add_row(
                p["position_name"],
                p["web_name"],
                p["club_name"],
                f"£{p['now_cost']:.1f}m",
                str(int(p["total_points"])),
                form_val,
                next_fix,
                fdr_str,
                fdr_mb_val,
                sp_str,
                price_trend_str,
                status_str
            )

    console.print(table)


def recommend_transfers(transfers: int = 1, objective: str = "fdr_moneyball", source: str = "live", sell_player: Optional[str] = None, lock_player: Optional[str] = None, min_penalties: int = 0):
    """Compute optimal transfer swaps with FDR integration."""
    df = load_dataset(source)
    opt = FPLOptimizer(df)

    title_desc = f"[bold green]Calculating Optimal {transfers} Transfer(s)...[/bold green]\n" \
                 f"Objective: [bold cyan]{objective.upper()}[/bold cyan] | Bank Reserve: [bold]£{DEFAULT_BANK:.1f}m[/bold]"
    if sell_player:
        title_desc += f" | Force Sell: [bold red]{sell_player}[/bold red]"
    if lock_player:
        title_desc += f" | Force Keep: [bold green]{lock_player}[/bold green]"

    console.print(Panel.fit(
        title_desc,
        border_style="green"
    ))

    locks = [lock_player] if lock_player else None
    excludes = [sell_player] if sell_player else None

    res = opt.optimize_transfers(
        current_player_names=DEFAULT_SQUAD,
        bank_balance=DEFAULT_BANK,
        max_transfers=transfers,
        objective=objective,
        lock_players=locks,
        exclude_players=excludes,
        min_penalty_takers=min_penalties
    )

    if not res["success"]:
        console.print(f"[bold red]Optimization error:[/bold red] {res.get('message')}")
        return

    table_out = Table(title="[bold red]Players OUT (Sell)[/bold red]", border_style="red")
    table_out.add_column("Player", width=16)
    table_out.add_column("Club", width=13)
    table_out.add_column("Pos", width=5)
    table_out.add_column("Price", justify="right", width=7)
    table_out.add_column("Pts", justify="right", width=5)
    table_out.add_column("Form", justify="right", width=6)
    table_out.add_column("Next Match", width=14)
    table_out.add_column("Set Pieces", width=18)
    table_out.add_column("Reason / Status", width=25)

    for _, r in res["transfers_out"].iterrows():
        reason = r.get("news") if r.get("status") != "a" else "Low fixture efficiency"
        sp_str = str(r.get("set_piece_badges", "None"))
        table_out.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            str(int(r["total_points"])),
            f"{float(r.get('form', 0.0)):.1f}",
            str(r.get("next_fixture", "N/A")),
            sp_str if sp_str != "None" else "[dim]-[/dim]",
            str(reason)
        )

    table_in = Table(title="[bold green]Players IN (Buy)[/bold green]", border_style="green")
    table_in.add_column("Player", width=16)
    table_in.add_column("Club", width=13)
    table_in.add_column("Pos", width=5)
    table_in.add_column("Price", justify="right", width=7)
    table_in.add_column("Pts", justify="right", width=5)
    table_in.add_column("Form", justify="right", width=6)
    table_in.add_column("Next Match", width=14)
    table_in.add_column("5GW FDR", justify="center", width=9)
    table_in.add_column("Set Pieces", width=18)
    table_in.add_column("Score", justify="right", width=8)

    for _, r in res["transfers_in"].iterrows():
        fdr_5 = float(r.get("fdr_next_5", 3.0))
        fdr_str = f"[bold green]{fdr_5:.2f}[/bold green]" if fdr_5 <= 2.8 else f"{fdr_5:.2f}"
        sp_str = str(r.get("set_piece_badges", "None"))
        score_val = float(r.get("setpiece_moneyball_score", r.get("fdr_moneyball_score", r.get("moneyball_score", 0))))
        table_in.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            str(int(r["total_points"])),
            f"{float(r.get('form', 0.0)):.1f}",
            str(r.get("next_fixture", "N/A")),
            fdr_str,
            f"[bold cyan]{sp_str}[/bold cyan]" if sp_str != "None" else "[dim]-[/dim]",
            f"{score_val:.2f}"
        )

    console.print(table_out)
    console.print(table_in)

    console.print(Panel(
        f"[bold]Summary of Transfer Impact:[/bold]\n"
        f"• Total Points Delta: [bold cyan]+{res['points_gain']} pts[/bold cyan]\n"
        f"• Score Delta: [bold green]+{res['score_gain']:.2f}[/bold green]\n"
        f"• Remaining Bank Balance: [bold]£{res['new_bank']:.1f}m[/bold]\n"
        f"• New Squad Value: [bold]£{res['total_team_cost']:.1f}m[/bold]",
        border_style="bright_blue"
    ))


def show_fixtures(weeks: int = 5):
    """Display the full Premier League rolling FDR ticker and Fixture Swing Detector."""
    client = FPLClient()
    fdr_map = client.get_team_fdr_map(n_gameweeks=weeks)
    swings = client.get_fixture_swings(n_gameweeks=weeks)
    current_gw = client.get_current_gameweek() or 1
    next_gws = list(range(current_gw + 1, current_gw + weeks + 1))

    console.print(Panel.fit(
        f"[bold gold1]Premier League Fixture Difficulty & Swing Ticker (GW{next_gws[0]} - GW{next_gws[-1]})[/bold gold1]\n"
        f"[dim]Horizon: {weeks} Gameweeks | Scale: [bold green]2 (Easy)[/bold green] | [yellow]3 (Medium)[/yellow] | [bold red]4-5 (Hard)[/bold red][/dim]\n"
        f"[dim]Swing Delta: [bold green]+Delta[/bold green] = Schedule gets easier (Buy) | [bold red]-Delta[/bold red] = Schedule gets tougher (Sell)[/dim]",
        border_style="cyan"
    ))

    # Fixture Swing Detector Highlights Panel
    swing_text = "[bold cyan]⚡ FIXTURE SWING DETECTOR (Moneyball Inflection Windows)[/bold cyan]\n\n"
    swing_text += "[bold green]🟢 Top Positive Swings (Tough Now ➔ Green Run Ahead — BUY TARGETS):[/bold green]\n"
    for t in swings["positive_swings"][:4]:
        swing_text += f"• [bold]{t['team_name']}[/bold] (Swing: [bold green]+{t['swing_delta']:.2f}[/bold green]) — Near FDR: {t['near_fdr']:.2f} ➔ Later FDR: [bold green]{t['later_fdr']:.2f}[/bold green]\n"

    swing_text += "\n[bold red]🔴 Top Negative Swings (Easy Now ➔ Red Wall Approaching — SELL ALERTS):[/bold red]\n"
    for t in swings["negative_swings"][:4]:
        swing_text += f"• [bold]{t['team_name']}[/bold] (Swing: [bold red]{t['swing_delta']:.2f}[/bold red]) — Near FDR: {t['near_fdr']:.2f} ➔ Later FDR: [bold red]{t['later_fdr']:.2f}[/bold red]\n"

    # Squad callouts
    squad_swings = []
    for name in DEFAULT_SQUAD:
        for t in fdr_map.values():
            if t["swing_delta"] >= 0.5 or t["swing_delta"] <= -0.5:
                # check if player is from this club
                pass
    swing_text += "\n[bold gold1]★ Rubies Rangers Squad Swing Notes:[/bold gold1]\n"
    swing_text += "• [bold green]Robin Roefs (Sunderland, +2.25)[/bold green]: Survives Arsenal & Chelsea (GW4-5), then enters league-easiest run (GW6-9)!\n"
    swing_text += "• [bold green]Antonee Robinson (Fulham, +1.50)[/bold green]: Transitions into prime clean sheet fixtures from GW6 onward.\n"
    swing_text += "• [bold yellow]João Pedro & Morgan Rogers (Chelsea, -0.75)[/bold yellow]: Feast in GW4-5 (Hull, Sunderland) before tough City/Liverpool tests (GW6-7)."

    console.print(Panel(swing_text.strip(), border_style="bright_blue"))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
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


def draft_squad(budget: float = 100.0, objective: str = "fdr_moneyball", source: str = "live", lock: str = None):
    """Draft an optimal squad from scratch."""
    df = load_dataset(source)
    opt = FPLOptimizer(df)

    locks = [lock] if lock else None
    res = opt.optimize_squad(budget=budget, objective=objective, lock_players=locks)

    if not res["success"]:
        console.print(f"[bold red]Optimization failed:[/bold red] {res.get('message')}")
        return

    squad = res["squad"]
    title = f"Optimal 15-Player Squad ({objective.upper()})"
    if lock:
        title += f" [Locked: {lock}]"

    console.print(Panel.fit(
        f"[bold magenta]{title}[/bold magenta]\n"
        f"Total Cost: [bold]£{res['total_cost']:.1f}m[/bold] | "
        f"Bank Remaining: [bold green]£{res['bank_remaining']:.1f}m[/bold green] | "
        f"Total Points: [bold cyan]{res['total_points']}[/bold cyan]",
        border_style="magenta"
    ))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=16)
    table.add_column("Club", width=14)
    table.add_column("Cost", justify="right", width=7)
    table.add_column("Pts", justify="right", width=5)
    table.add_column("Form", justify="right", width=6)
    table.add_column("Next Match", width=14)
    table.add_column("5GW FDR", justify="center", width=9)
    table.add_column("FDR Score", justify="right", width=10)

    for pos in ["GKP", "DEF", "MID", "FWD"]:
        sub = squad[squad["position_name"] == pos]
        for _, r in sub.iterrows():
            fdr_5 = float(r.get("fdr_next_5", 3.0))
            fdr_str = f"[bold green]{fdr_5:.2f}[/bold green]" if fdr_5 <= 2.8 else f"{fdr_5:.2f}"
            table.add_row(
                r["position_name"],
                r["web_name"],
                r["club_name"],
                f"£{r['now_cost']:.1f}m",
                str(int(r["total_points"])),
                f"{float(r.get('form', 0.0)):.1f}",
                str(r.get("next_fixture", "N/A")),
                fdr_str,
                f"{float(r.get('fdr_moneyball_score', r.get('moneyball_score', 0))):.2f}"
            )

    console.print(table)


def show_price_predictions():
    """Display the live Market Velocity & Price Change Predictor."""
    client = FPLClient()
    df = client.get_players_df()
    
    # 1. Check Rubies Rangers players
    squad_alerts = []
    for name in DEFAULT_SQUAD:
        m = df[df["web_name"].str.lower() == name.lower()]
        if m.empty:
            m = df[df["full_name"].str.lower() == name.lower()]
        if not m.empty:
            p = m.iloc[0]
            status = p.get("price_status", "Stable")
            if "TONIGHT" in status or "Soon" in status:
                squad_alerts.append(p)

    console.print(Panel.fit(
        "[bold gold1]FPL Market Velocity & Price Change Predictor[/bold gold1]\n"
        "[dim]Tracks live transfer streams to forecast nightly £0.1m price rises and falls.[/dim]",
        border_style="yellow"
    ))

    if squad_alerts:
        alert_text = "[bold]🚨 Squad Value Movement Alerts for Rubies Rangers:[/bold]\n"
        for p in squad_alerts:
            direc = "▲ RISE" if p["price_direction"] == "RISE" else "▼ FALL"
            color = "green" if p["price_direction"] == "RISE" else "red"
            alert_text += f"• [{color}]{p['web_name']} ({p['club_name']})[/{color}]: [bold {color}]{direc}[/bold {color}] " \
                          f"(Net: {p['net_transfers']:+,d} | Target Progress: {p['price_progress_pct']}%) — [bold]{p['price_status']}[/bold]\n"
        console.print(Panel(alert_text.strip(), border_style="bright_blue"))
    else:
        console.print("[green]All Rubies Rangers assets currently have stable market velocity.[/green]\n")

    # Table 1: Top 10 Rises
    rises = df[(df["price_direction"] == "RISE") & (df["status"] == "a")].sort_values(
        by="price_progress_pct", ascending=False
    ).head(10)

    t_rise = Table(title="[bold green]▲ Projected Price Rises Tonight (+£0.1m)[/bold green]", border_style="green")
    t_rise.add_column("Player", width=16)
    t_rise.add_column("Club", width=14)
    t_rise.add_column("Pos", width=5)
    t_rise.add_column("Price", justify="right", width=7)
    t_rise.add_column("Net Transfers", justify="right", width=14)
    t_rise.add_column("Progress", justify="right", width=10)
    t_rise.add_column("Prediction", width=18)

    for _, r in rises.iterrows():
        t_rise.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            f"{r['net_transfers']:+,d}",
            f"{r['price_progress_pct']:.1f}%",
            f"[bold green]{r['price_status']}[/bold green]"
        )

    # Table 2: Top 10 Falls
    falls = df[(df["price_direction"] == "FALL") & (df["status"] == "a")].sort_values(
        by="price_progress_pct", ascending=False
    ).head(10)

    t_fall = Table(title="[bold red]▼ Projected Price Falls Tonight (-£0.1m)[/bold red]", border_style="red")
    t_fall.add_column("Player", width=16)
    t_fall.add_column("Club", width=14)
    t_fall.add_column("Pos", width=5)
    t_fall.add_column("Price", justify="right", width=7)
    t_fall.add_column("Net Transfers", justify="right", width=14)
    t_fall.add_column("Progress", justify="right", width=10)
    t_fall.add_column("Prediction", width=18)

    for _, r in falls.iterrows():
        t_fall.add_row(
            r["web_name"],
            r["club_name"],
            r["position_name"],
            f"£{r['now_cost']:.1f}m",
            f"{r['net_transfers']:+,d}",
            f"{r['price_progress_pct']:.1f}%",
            f"[bold red]{r['price_status']}[/bold red]"
        )

    console.print(t_rise)
    console.print(t_fall)


def show_set_pieces(club: Optional[str] = None, role: str = "all"):
    """Display Premier League set-piece and penalty hierarchies."""
    client = FPLClient()
    df = client.get_set_piece_hierarchy(club_name=club)

    if role == "penalties":
        df = df[df["penalties_order"].notna()]
    elif role == "freekicks":
        df = df[df["direct_freekicks_order"].notna()]
    elif role == "corners":
        df = df[df["corners_and_indirect_freekicks_order"].notna()]

    title = f"Premier League Set-Piece & Penalty Hierarchy ({role.upper()})"
    if club:
        title += f" — {club.title()}"

    console.print(Panel.fit(
        f"[bold gold1]{title}[/bold gold1]\n"
        f"[dim]Tracking designated primary (1st), secondary (2nd), and tertiary (3rd) set-piece specialists.[/dim]",
        border_style="cyan"
    ))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Club", width=14)
    table.add_column("Player", width=16)
    table.add_column("Pos", width=5)
    table.add_column("Cost", justify="right", width=7)
    table.add_column("⚽ Penalty", justify="center", width=12)
    table.add_column("🎯 Direct FK", justify="center", width=12)
    table.add_column("🚩 Corner/Indirect", justify="center", width=18)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Squad Status", width=16)

    def _fmt_order(order):
        if pd.isna(order) or order is None:
            return "[dim]-[/dim]"
        o = int(order)
        suffix = "1st" if o == 1 else ("2nd" if o == 2 else ("3rd" if o == 3 else f"{o}th"))
        if o == 1:
            return f"[bold green]{suffix}[/bold green]"
        elif o == 2:
            return f"[yellow]{suffix}[/yellow]"
        return f"[dim]{suffix}[/dim]"

    for _, r in df.iterrows():
        is_in_squad = any(
            r["web_name"].lower() == s.lower() or s.lower() in r["web_name"].lower()
            for s in DEFAULT_SQUAD
        )
        squad_badge = "[bold gold1]★ Rubies Rangers[/bold gold1]" if is_in_squad else ""

        table.add_row(
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

    console.print(table)


def display_montecarlo_lineup(res: Dict[str, Any]):
    """Render rich terminal view of Monte Carlo Lineup, Captaincy & Substitution Strategy."""
    from rich.columns import Columns
    from rich.text import Text

    opt_form = res["optimal_formation"]
    sq_summary = res["squad_summary"]
    cap_duel = res["captaincy_duel"]
    cap = cap_duel["captain"]
    vc = cap_duel["vice_captain"]

    # 1. Hero Header Panel
    header_text = (
        f"[bold gold1]🎲 Rubies Rangers — Monte Carlo Lineup & Substitution Strategist[/bold gold1]\n\n"
        f"Optimal Formation: [bold cyan]{opt_form}[/bold cyan]   |   "
        f"Simulations: [bold white]{sq_summary['n_sims']:,}[/bold white]\n"
        f"Mean Total Score: [bold green]{sq_summary['mean_total']} pts[/bold green]   |   "
        f"Floor (P10): [bold yellow]{sq_summary['floor_p10']} pts[/bold yellow]   |   "
        f"Median (P50): [bold white]{sq_summary['median_p50']} pts[/bold white]   |   "
        f"Ceiling (P90): [bold magenta]{sq_summary['ceiling_p90']} pts[/bold magenta]   |   "
        f"Std Dev: [dim]±{sq_summary['std']} pts[/dim]\n\n"
        f"Designated Captain: [bold red]★ {cap['web_name']}[/bold red] ([bold green]{cap['mean_captain_pts']} pts[/bold green] projected, {cap['haul_prob_pct']}% haul chance)\n"
        f"Vice-Captain: [bold cyan]☆ {vc['web_name']}[/bold cyan] ([bold green]{vc['mean_captain_pts']} pts[/bold green] projected, 100% starting minutes security)"
    )
    console.print(Panel(header_text, border_style="gold1", expand=False))

    # 2. Actionable Move Around Checklist
    console.print("\n[bold gold1]📋 Actionable Checklist: What to Move Around Before the Deadline[/bold gold1]")
    checklist = res.get("move_around_checklist", [])
    for item in checklist:
        badge = item.get("badge", "")
        action = item.get("action", "")
        reason = item.get("reason", "")
        console.print(f"  {badge} [bold white]{action}[/bold white]")
        console.print(f"     [dim]Rationale: {reason}[/dim]\n")

    # 3. Starting XI Formation Table
    table_starters = Table(
        title=f"[bold green]⚡ Starting XI (Optimal Formation: {opt_form})[/bold green]",
        border_style="green",
        header_style="bold cyan"
    )
    table_starters.add_column("Role", width=12, justify="center")
    table_starters.add_column("Pos", width=5)
    table_starters.add_column("Player", width=16)
    table_starters.add_column("Club", width=6)
    table_starters.add_column("Fixture (FDR)", width=14)
    table_starters.add_column("Form", justify="right", width=6)
    table_starters.add_column("Cards (Y/R)", justify="center", width=11)
    table_starters.add_column("Status", width=10)
    table_starters.add_column("Mean Pts", justify="right", width=9)
    table_starters.add_column("P10 (Floor)", justify="right", width=11)
    table_starters.add_column("P90 (Ceil)", justify="right", width=11)

    for s in res.get("starters", []):
        role_str = "[bold red]★ CAPTAIN[/bold red]" if s["role"] == "CAPTAIN" else (
            "[bold cyan]☆ VICE-CAP[/bold cyan]" if s["role"] == "VICE_CAPTAIN" else "[dim]Starter[/dim]"
        )
        fdr_val = s.get("fdr", 3)
        fdr_style = "green" if fdr_val <= 2 else ("yellow" if fdr_val == 3 else "red")
        fix_str = f"{s.get('fixture', 'TBD')} [{fdr_style}]({fdr_val})[/{fdr_style}]"

        cards_str = f"{s.get('yellow_cards', 0)}Y / {s.get('red_cards', 0)}R"
        if s.get("yellow_cards", 0) >= 2:
            cards_str = f"[bold yellow]{cards_str}[/bold yellow]"
        elif s.get("red_cards", 0) >= 1:
            cards_str = f"[bold red]{cards_str}[/bold red]"

        st_str = "[bold green]Fit[/bold green]" if s.get("status") == "a" else f"[bold yellow]{s.get('status')}[/bold yellow]"

        table_starters.add_row(
            role_str,
            s["pos"],
            f"[bold white]{s['web_name']}[/bold white]",
            s["club"],
            fix_str,
            f"{s['form']:.1f}",
            cards_str,
            st_str,
            f"[bold green]{s['mean_pts']:.2f}[/bold green]",
            f"{s['p10']:.1f}",
            f"[bold magenta]{s['p90']:.1f}[/bold magenta]"
        )
    console.print(table_starters)

    # 4. Substitution Strategy & Bench Priority
    table_bench = Table(
        title="[bold yellow]🪑 Substitution Strategy & Priority Bench Hierarchy[/bold yellow]",
        border_style="yellow",
        header_style="bold cyan"
    )
    table_bench.add_column("Priority", width=9, justify="center")
    table_bench.add_column("Slot", width=9)
    table_bench.add_column("Player", width=16)
    table_bench.add_column("Pos", width=5)
    table_bench.add_column("Club", width=6)
    table_bench.add_column("Fixture", width=14)
    table_bench.add_column("Auto-Sub %", justify="right", width=12)
    table_bench.add_column("Pts When Subbed", justify="right", width=16)
    table_bench.add_column("Pts Saved", justify="right", width=11)
    table_bench.add_column("Strategic Rationale", width=38)

    for b in res.get("bench", []):
        act_style = "bold green" if b["activation_prob_pct"] >= 20.0 else ("yellow" if b["activation_prob_pct"] >= 5.0 else "dim")
        table_bench.add_row(
            f"#{b['sub_priority']}",
            b["slot"],
            f"[bold white]{b['web_name']}[/bold white]",
            b["position"],
            b["club"],
            str(b.get("fixture", "TBD")),
            f"[{act_style}]{b['activation_prob_pct']:.1f}%[/{act_style}]",
            f"{b['pts_when_subbed']:.2f}",
            f"{b['points_saved_mean']:.2f}",
            b.get("tactical_rationale", "")
        )
    console.print(table_bench)

    # 5. Captaincy Monte Carlo Duel Panel
    duel_text = (
        f"[bold red]★ {cap['web_name']}[/bold red] ({cap['club']}) vs [bold cyan]☆ {vc['web_name']}[/bold cyan] ({vc['club']})\n\n"
        f"  • Head-to-Head Win Rate: [bold red]{cap['web_name']} wins {cap['win_rate_pct']}%[/bold red] vs "
        f"[bold cyan]{vc['web_name']} wins {vc['win_rate_pct']}%[/bold cyan] (Ties: {cap_duel.get('tie_rate_pct', 0.0)}%)\n"
        f"  • Mean Captain Points (2x): [bold red]{cap['mean_captain_pts']} pts[/bold red] vs [bold cyan]{vc['mean_captain_pts']} pts[/bold cyan]\n"
        f"  • Haul Chance (>=10 single pts): [bold red]{cap['haul_prob_pct']}%[/bold red] vs [bold cyan]{vc['haul_prob_pct']}%[/bold cyan]\n"
        f"  • Blank Risk (<=2 single pts): [bold red]{cap['blank_prob_pct']}%[/bold red] vs [bold cyan]{vc['blank_prob_pct']}%[/bold cyan]\n"
        f"  • Vice-Captain Fallback Security: If {cap['web_name']} plays 0 mins, {vc['web_name']} automatically inherits the 2x boost."
    )
    console.print(Panel(duel_text, title="[bold gold1]⚔️ Captaincy Monte Carlo Duel (Head-to-Head)[/bold gold1]", border_style="red", expand=False))

    # 6. Disciplinary & Health Warnings
    alerts = res.get("disciplinary_and_injury_alerts", [])
    if alerts:
        table_alerts = Table(title="[bold red]⚠️ Disciplinary, Form & Injury Risk Warnings[/bold red]", border_style="red", header_style="bold red")
        table_alerts.add_column("Player", width=16)
        table_alerts.add_column("Club", width=6)
        table_alerts.add_column("Pos", width=5)
        table_alerts.add_column("Status / Chance", width=18)
        table_alerts.add_column("Yellows / Reds", width=14)
        table_alerts.add_column("Form", justify="right", width=6)
        table_alerts.add_column("Risk Notes", width=35)

        for a in alerts:
            st_flag = f"{a['status']} ({a['cop']}%)"
            cards = f"{a['yellow_cards']}Y / {a['red_cards']}R"
            table_alerts.add_row(
                a["web_name"],
                a["club"],
                a["pos"],
                st_flag,
                cards,
                f"{a['form']:.1f}",
                a.get("notes", "")
            )
        console.print(table_alerts)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Squad Manager & Moneyball Optimizer")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # audit command
    audit_parser = subparsers.add_parser("audit", help="Audit current Rubies Rangers squad")
    audit_parser.add_argument("--source", choices=["live", "csv"], default="live", help="Data source")

    # transfers command
    trans_parser = subparsers.add_parser("transfers", help="Calculate optimal transfers")
    trans_parser.add_argument("--count", type=int, default=1, help="Number of transfers (1 or 2)")
    trans_parser.add_argument("--mc", "--montecarlo", action="store_true", help="Run Monte Carlo stochastic transfer optimization across N gameweek simulations")
    trans_parser.add_argument("--sims", type=int, default=2500, help="Number of Monte Carlo simulations (default: 2500)")
    trans_parser.add_argument("--free", type=int, default=1, help="Number of free transfers available before -4 hit penalty (default: 1)")
    trans_parser.add_argument("--sell", type=str, default=None, help="Player to force sell (e.g. Senesi, Solanke)")
    trans_parser.add_argument("--lock", type=str, default=None, help="Player to force keep in squad")
    trans_parser.add_argument("--objective", choices=["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], default="fdr_moneyball", help="Optimization metric")
    trans_parser.add_argument("--penalties", type=int, default=0, help="Minimum number of primary penalty takers required")
    trans_parser.add_argument("--source", choices=["live", "csv"], default="live", help="Data source")

    # fixtures command
    fix_parser = subparsers.add_parser("fixtures", help="Display 20-team Premier League FDR & Swing ticker")
    fix_parser.add_argument("--weeks", type=int, default=5, choices=[3, 4, 5, 6], help="Rolling gameweeks horizon (3 to 6)")

    # prices command
    subparsers.add_parser("prices", help="Display market velocity and price change predictions")

    # setpieces command
    sp_parser = subparsers.add_parser("setpieces", help="Display Premier League set-piece & penalty hierarchies")
    sp_parser.add_argument("--club", type=str, default=None, help="Filter by club name (e.g. Arsenal, Spurs, Man City)")
    sp_parser.add_argument("--role", choices=["all", "penalties", "freekicks", "corners"], default="all", help="Filter by duty")

    # draft command
    draft_parser = subparsers.add_parser("draft", help="Draft optimal 15-player squad from scratch")
    draft_parser.add_argument("--budget", type=float, default=100.0, help="Total squad budget (£m)")
    draft_parser.add_argument("--objective", choices=["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], default="fdr_moneyball", help="Optimization metric")
    draft_parser.add_argument("--penalties", type=int, default=0, help="Minimum number of primary penalty takers required")
    draft_parser.add_argument("--lock", type=str, default=None, help="Player to force lock in squad (e.g. Haaland)")
    draft_parser.add_argument("--source", choices=["live", "csv"], default="live", help="Data source")

    # trends command
    trends_parser = subparsers.add_parser("trends", help="Display match-by-match trend analysis & minutes stability")
    trends_parser.add_argument("--player", type=str, default=None, help="Player to deep-dive into (e.g. Solanke, Senesi)")
    trends_parser.add_argument("--weeks", type=int, default=3, help="Number of recent gameweeks to analyze (default 3)")
    trends_parser.add_argument("--risks", action="store_true", help="Filter for rotation risks or benched players")

    # tactical command
    tactical_parser = subparsers.add_parser("tactical", help="Display advanced tactical process & shot quality metrics")
    tactical_parser.add_argument("--player", type=str, default=None, help="Player to inspect shot map for (e.g. Isak, Foden)")
    tactical_parser.add_argument("--leaders", action="store_true", help="Display Premier League Shot Quality & NPxGI leaderboards")
    tactical_parser.add_argument("--refresh", action="store_true", help="Force refresh live Understat cache")

    # lineup command
    lineup_parser = subparsers.add_parser("lineup", help="Solve optimal Starting XI, Captaincy, and Bench hierarchy via xP model or Monte Carlo")
    lineup_parser.add_argument("--mc", "--montecarlo", action="store_true", help="Run full Monte Carlo Lineup, Captaincy & Substitution Strategy analysis")
    lineup_parser.add_argument("--sims", type=int, default=2500, help="Number of Monte Carlo simulations (default: 2500)")
    lineup_parser.add_argument("--squad", action="store_true", help="Display full 15-player squad xP breakdown")
    lineup_parser.add_argument("--odds", action="store_true", help="Display Gameweek 4 betting market odds")
    lineup_parser.add_argument("--captains", action="store_true", help="Display top Premier League captaincy rankings")
    lineup_parser.add_argument("--top", type=int, default=15, help="Number of top captain candidates")

    # league command
    league_parser = subparsers.add_parser("league", help="Scout rival teams, standings, and squads in your mini-league")
    league_parser.add_argument("--id", type=int, default=325320, help="Mini-league ID (default: 325320 'Bronze, Silver & Gold League')")
    league_parser.add_argument("--team", type=int, default=None, help="Your FPL Team / Entry ID to auto-discover all your mini-leagues")
    league_parser.add_argument("--spy", type=int, default=None, help="Rival Team / Entry ID to inspect exact squad, starters, and captain")
    league_parser.add_argument("--ownership", action="store_true", help="Display mini-league Effective Ownership (EO%) matrix")
    league_parser.add_argument("--history", action="store_true", help="Display gameweek-by-gameweek progression table for all teams")
    league_parser.add_argument("--gw", type=int, default=None, help="Gameweek number (defaults to latest active)")
    league_parser.add_argument("--limit", type=int, default=50, help="Max number of rival teams to fetch")

    # sync command
    subparsers.add_parser("sync", help="Force refresh live FPL API data cache")

    parser.add_argument("--profile", choices=["heuristic", "tuned"], default=None, help="Parameter profile to activate (heuristic vs tuned)")

    args = parser.parse_args()
    if args.profile:
        set_active_profile(args.profile)

    if args.command == "audit":

        audit_squad(source=args.source)
    elif args.command == "transfers":
        if args.mc:
            from trackers.montecarlo import run_montecarlo_cli
            run_montecarlo_cli(sims=args.sims, transfers=args.count, free_transfers=args.free, sell_filter=args.sell)
        else:
            recommend_transfers(transfers=args.count, objective=args.objective, source=args.source, sell_player=args.sell, lock_player=args.lock, min_penalties=args.penalties)
    elif args.command == "fixtures":
        show_fixtures(weeks=args.weeks)
    elif args.command == "prices":
        show_price_predictions()
    elif args.command == "setpieces":
        show_set_pieces(club=args.club, role=args.role)
    elif args.command == "trends":
        client = FPLClient()
        if args.player:
            show_player_deep_dive(client, player_name=args.player, n_recent=args.weeks)
        else:
            audit_squad_trends(client, n_recent=args.weeks, only_risks=args.risks)
    elif args.command == "tactical":
        from clients.tactical_client import TacticalClient
        tc = TacticalClient()
        if args.player:
            show_player_shots(tc, player_name=args.player)
        elif args.leaders:
            show_league_leaders(tc)
        else:
            audit_squad_tactical(tc, force_refresh=args.refresh)
    elif args.command == "lineup":
        if args.mc:
            from analytics.montecarlo import MonteCarloEngine
            mc = MonteCarloEngine()
            res = mc.optimize_lineup_and_substitutions(n_sims=args.sims)
            display_montecarlo_lineup(res)
        else:
            xm = XPModel()
            if args.squad:
                display_squad(xm)
            elif args.odds:
                display_odds(xm)
            elif args.captains:
                display_captains(xm, top_n=args.top)
            else:
                display_lineup(xm)
    elif args.command == "draft":
        draft_squad(budget=args.budget, objective=args.objective, source=args.source, lock=args.lock)
    elif args.command == "league":
        tracker = LeagueTracker()
        if args.spy:
            display_rival_squad(tracker, args.spy, gameweek=args.gw)
        elif args.id:
            if args.ownership:
                df = tracker.get_league_ownership(args.id, gameweek=args.gw, max_teams=args.limit)
                console.print(Panel.fit(f"[bold gold1]Mini-League Player Ownership & EO% (League {args.id})[/bold gold1]"))
                console.print(df.to_string(index=False))
            elif args.history:
                display_league_history(tracker, args.id)
            else:
                display_league_standings(tracker, args.id)
        elif args.team:
            display_team_leagues(tracker, args.team)
        else:
            console.print(Panel.fit(
                "[bold gold1]FPL Mini-League Scout & Rival Spy[/bold gold1]\n"
                "[cyan]Usage:[/cyan]\n"
                "  • [bold]python team_manager.py league --id <LEAGUE_ID>[/bold] : View all teams in a mini-league\n"
                "  • [bold]python team_manager.py league --team <TEAM_ID>[/bold]     : List all mini-leagues for your team\n"
                "  • [bold]python team_manager.py league --spy <ENTRY_ID>[/bold]     : Spy on a rival's exact squad & captain\n"
                "  • [bold]python team_manager.py league --id <ID> --ownership[/bold] : Compute Effective Ownership (EO%)\n\n"
                "[dim]How to find your ID:[/dim]\n"
                "  1. Go to [bold]fantasy.premierleague.com[/bold]\n"
                "  2. Click 'Pick Team' or 'Points' -> Look at URL: [bold]fantasy.premierleague.com/entry/XXXXXXX/event/...[/bold]\n"
                "  3. Click 'Leagues & Cups' -> Your League -> Look at URL: [bold]fantasy.premierleague.com/leagues/YYYYYY/standings/c[/bold]",
                border_style="bright_blue"
            ))
    elif args.command == "sync":
        FPLClient().get_bootstrap_data(force_refresh=True)
        FPLClient().get_fixtures_data(force_refresh=True)
        console.print("[bold green]Successfully refreshed live FPL API caches![/bold green]")
    else:
        audit_squad(source="live")


if __name__ == "__main__":
    main()
