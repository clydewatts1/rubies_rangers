"""
Rubies Rangers FPL Mini-League Scout & Rival Spy
Extracts and analyzes all other teams, manager standings, squad compositions,
captaincy picks, and effective player ownership within an FPL mini-league.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import json
import urllib.request
import argparse
from typing import Dict, List, Any, Optional
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from fpl_client import FPLClient
from config_manager import get_system_config

console = Console()

LEAGUE_STANDINGS_URL = "https://fantasy.premierleague.com/api/leagues-classic/{}/standings/?page_new_entries=1&page_standings={}"
ENTRY_URL = "https://fantasy.premierleague.com/api/entry/{}/"
ENTRY_PICKS_URL = "https://fantasy.premierleague.com/api/entry/{}/event/{}/picks/"

# Default Mini-League & Team from config
DEFAULT_LEAGUE_ID = get_system_config("default_league_id") or 325320  # Bronze, Silver & Gold League
DEFAULT_ENTRY_ID = get_system_config("default_entry_id") or 6173410   # Rubies Rangers (Clyde Watts)



class LeagueTracker:
    def __init__(self):
        self.fpl_client = FPLClient()
        self._players_map = None

    def _fetch_url(self, url: str) -> Any:
        return self.fpl_client._fetch_url(url)

    def _get_player_info_map(self) -> Dict[int, Dict[str, Any]]:
        if self._players_map is None:
            boot = self.fpl_client.get_bootstrap_data()
            teams = {t["id"]: t["short_name"] for t in boot["teams"]}
            pos = {p["id"]: p["singular_name_short"] for p in boot["element_types"]}
            self._players_map = {}
            for el in boot["elements"]:
                self._players_map[el["id"]] = {
                    "web_name": el["web_name"],
                    "club": teams.get(el["team"], "UNK"),
                    "pos": pos.get(el["element_type"], "UNK"),
                    "cost": el["now_cost"] / 10.0
                }
        return self._players_map

    def get_team_leagues(self, entry_id: int) -> Dict[str, Any]:
        """Fetch details of an FPL manager team and list all the classic leagues it competes in."""
        data = self._fetch_url(ENTRY_URL.format(entry_id))
        team_name = data.get("name", "Unknown")
        manager_name = f"{data.get('player_first_name', '')} {data.get('player_last_name', '')}".strip()
        overall_pts = data.get("summary_overall_points", 0)
        overall_rank = data.get("summary_overall_rank", 0)

        classic_leagues = []
        for l in data.get("leagues", {}).get("classic", []):
            classic_leagues.append({
                "id": l["id"],
                "name": l["name"],
                "rank": l.get("entry_rank", 0),
                "last_rank": l.get("entry_last_rank", 0)
            })

        return {
            "entry_id": entry_id,
            "team_name": team_name,
            "manager_name": manager_name,
            "overall_points": overall_pts,
            "overall_rank": overall_rank,
            "leagues": classic_leagues
        }

    def get_league_standings(self, league_id: int, max_teams: int = 50) -> Dict[str, Any]:
        """Fetch all teams and manager standings in a classic mini-league."""
        url = LEAGUE_STANDINGS_URL.format(league_id, 1)
        data = self._fetch_url(url)
        league_info = data.get("league", {})
        results = data.get("standings", {}).get("results", [])

        # If more teams on page 2
        if len(results) < max_teams and data.get("standings", {}).get("has_next"):
            try:
                p2 = self._fetch_url(LEAGUE_STANDINGS_URL.format(league_id, 2))
                results.extend(p2.get("standings", {}).get("results", []))
            except Exception:
                pass

        teams = []
        for r in results[:max_teams]:
            teams.append({
                "rank": r.get("rank"),
                "entry_id": r.get("entry"),
                "team_name": r.get("entry_name"),
                "manager_name": r.get("player_name"),
                "gw_points": r.get("event_total"),
                "total_points": r.get("total"),
                "last_rank": r.get("last_rank", r.get("rank"))
            })

        return {
            "league_id": league_id,
            "league_name": league_info.get("name", "FPL Mini-League"),
            "created": league_info.get("created"),
            "teams": teams
        }

    def get_team_picks(self, entry_id: int, gameweek: Optional[int] = None) -> Dict[str, Any]:
        """Fetch exact 15-player squad, starters, captain, and bench for a team in a given gameweek."""
        if gameweek is None:
            gameweek = self.fpl_client.get_current_gameweek() or 3

        url = ENTRY_PICKS_URL.format(entry_id, gameweek)
        data = self._fetch_url(url)
        pmap = self._get_player_info_map()

        starters = []
        bench = []
        captain = None
        vice_captain = None

        for p in data.get("picks", []):
            el_id = p["element"]
            multiplier = p.get("multiplier", 1)
            is_cap = p.get("is_captain", False)
            is_vc = p.get("is_vice_captain", False)
            pos_num = p.get("position", 1)  # 1-11 starters, 12-15 bench

            info = pmap.get(el_id, {"web_name": f"Player {el_id}", "club": "UNK", "pos": "MID", "cost": 5.0})
            player_obj = {
                "id": el_id,
                "web_name": info["web_name"],
                "club": info["club"],
                "pos": info["pos"],
                "cost": info["cost"],
                "multiplier": multiplier,
                "is_captain": is_cap,
                "is_vice_captain": is_vc,
                "slot": pos_num
            }

            if is_cap:
                captain = player_obj
            if is_vc:
                vice_captain = player_obj

            if pos_num <= 11:
                starters.append(player_obj)
            else:
                bench.append(player_obj)

        history = data.get("entry_history", {})
        active_chip = data.get("active_chip")

        return {
            "entry_id": entry_id,
            "gameweek": gameweek,
            "active_chip": active_chip,
            "gw_points": history.get("points"),
            "total_points": history.get("total_points"),
            "transfers": history.get("event_transfers"),
            "transfer_cost": history.get("event_transfers_cost"),
            "captain": captain,
            "vice_captain": vice_captain,
            "starters": starters,
            "bench": bench
        }

    def get_league_ownership(self, league_id: int, gameweek: Optional[int] = None, max_teams: int = 20) -> pd.DataFrame:
        """
        Compute player ownership and captaincy percentage across rival teams in the mini-league.
        Reveals mini-league Effective Ownership (EO%) to inform Moneyball differential picks!
        """
        if gameweek is None:
            gameweek = self.fpl_client.get_current_gameweek() or 3

        standings = self.get_league_standings(league_id, max_teams=max_teams)
        teams = standings.get("teams", [])
        total_rivals = len(teams)

        if total_rivals == 0:
            return pd.DataFrame()

        ownership_counts: Dict[str, Dict[str, Any]] = {}

        for t in teams:
            e_id = t["entry_id"]
            try:
                picks_data = self.get_team_picks(e_id, gameweek=gameweek)
                for p in picks_data["starters"] + picks_data["bench"]:
                    name = p["web_name"]
                    if name not in ownership_counts:
                        ownership_counts[name] = {
                            "Player": name,
                            "Club": p["club"],
                            "Pos": p["pos"],
                            "Cost": f"£{p['cost']:.1f}m",
                            "Owned": 0,
                            "Started": 0,
                            "Captained": 0
                        }
                    ownership_counts[name]["Owned"] += 1
                    if p["slot"] <= 11:
                        ownership_counts[name]["Started"] += 1
                    if p["is_captain"]:
                        ownership_counts[name]["Captained"] += 1
            except Exception:
                continue

        records = []
        for name, stats in ownership_counts.items():
            own_pct = round((stats["Owned"] / total_rivals) * 100, 1)
            start_pct = round((stats["Started"] / total_rivals) * 100, 1)
            cap_pct = round((stats["Captained"] / total_rivals) * 100, 1)
            eo_pct = round(start_pct + cap_pct, 1)

            records.append({
                "Player": stats["Player"],
                "Club": stats["Club"],
                "Pos": stats["Pos"],
                "Cost": stats["Cost"],
                "Teams Owning": f"{stats['Owned']}/{total_rivals}",
                "Ownership %": f"{own_pct}%",
                "Started %": f"{start_pct}%",
                "Captained %": f"{cap_pct}%",
                "Effective Ownership (EO)": f"{eo_pct}%",
                "raw_eo": eo_pct
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values(by="raw_eo", ascending=False).drop(columns=["raw_eo"]).reset_index(drop=True)
        return df

    def get_league_performance_history(self, league_id: int, max_teams: int = 20) -> Dict[str, Any]:
        """
        Fetch gameweek-by-gameweek historical points, cumulative score progression,
        and chip usage for all rival teams in a mini-league.
        """
        standings = self.get_league_standings(league_id, max_teams=max_teams)
        teams = standings.get("teams", [])
        
        history_records = []
        team_chips = {}
        
        for t in teams:
            entry_id = t["entry_id"]
            team_name = t["team_name"]
            manager = t["manager_name"]
            
            try:
                url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
                h_data = self._fetch_url(url)
                
                # Chips
                chips = h_data.get("chips", [])
                team_chips[team_name] = chips
                
                # Gameweek progression
                for gw in h_data.get("current", []):
                    event = gw["event"]
                    pts = gw["points"]
                    tot = gw["total_points"]
                    bench_pts = gw.get("points_on_bench", 0)
                    transfers = gw.get("event_transfers", 0)
                    cost = gw.get("event_transfers_cost", 0)
                    
                    history_records.append({
                        "entry_id": entry_id,
                        "team_name": team_name,
                        "manager_name": manager,
                        "gameweek": f"GW{event}",
                        "gw_num": event,
                        "gw_points": pts,
                        "cumulative_points": tot,
                        "bench_points": bench_pts,
                        "transfers": transfers,
                        "transfer_cost": cost
                    })
            except Exception:
                continue

        df = pd.DataFrame(history_records)
        
        # Calculate mini-league rank at each gameweek
        if not df.empty:
            df["league_rank"] = df.groupby("gw_num")["cumulative_points"].rank(ascending=False, method="min").astype(int)

        return {
            "league_id": league_id,
            "league_name": standings.get("league_name", "Mini-League"),
            "df": df,
            "chips": team_chips,
            "teams": teams
        }


def display_league_standings(tracker: LeagueTracker, league_id: int):
    """Render Rich CLI table of all teams in the mini-league."""
    res = tracker.get_league_standings(league_id)
    league_name = res["league_name"]
    teams = res["teams"]

    console.print(Panel.fit(
        f"[bold gold1]FPL Mini-League Standings — {league_name}[/bold gold1]\n"
        f"[dim]League ID: {league_id} | Total Teams: {len(teams)}[/dim]",
        border_style="bright_blue"
    ))

    table = Table(header_style="bold magenta", border_style="dim")
    table.add_column("Rank", justify="center", width=6)
    table.add_column("Team Name", width=24)
    table.add_column("Manager", width=20)
    table.add_column("Entry ID", justify="center", width=12)
    table.add_column("GW Pts", justify="right", width=8, style="cyan")
    table.add_column("Total Pts", justify="right", width=10, style="bold yellow")
    table.add_column("Movement", justify="center", width=10)

    for t in teams:
        rank = t["rank"]
        last = t["last_rank"]
        if rank < last:
            move = f"[green]▲ {last - rank}[/green]"
        elif rank > last:
            move = f"[red]▼ {rank - last}[/red]"
        else:
            move = "[dim]=[/dim]"

        table.add_row(
            str(rank),
            t["team_name"],
            t["manager_name"],
            str(t["entry_id"]),
            str(t["gw_points"]),
            str(t["total_points"]),
            move
        )

    console.print(table)


def display_team_leagues(tracker: LeagueTracker, entry_id: int):
    """Render Rich CLI table of all leagues for a manager entry."""
    res = tracker.get_team_leagues(entry_id)
    
    console.print(Panel.fit(
        f"[bold gold1]FPL Manager Profile — {res['team_name']}[/bold gold1]\n"
        f"Manager: [bold white]{res['manager_name']}[/bold white] | Overall Points: [bold yellow]{res['overall_points']}[/bold yellow] | Overall Rank: [bold cyan]{res['overall_rank']:,}[/bold cyan]",
        border_style="bright_blue"
    ))

    table = Table(title="[bold green]Competitions & Mini-Leagues[/bold green]", header_style="bold magenta", border_style="dim")
    table.add_column("League ID", width=12, justify="center")
    table.add_column("League Name", width=30)
    table.add_column("Current Rank", justify="right", width=14, style="bold yellow")
    table.add_column("Previous Rank", justify="right", width=14)

    for l in res["leagues"]:
        table.add_row(
            str(l["id"]),
            l["name"],
            f"#{l['rank']:,}",
            f"#{l['last_rank']:,}" if l['last_rank'] else "-"
        )

    console.print(table)


def display_rival_squad(tracker: LeagueTracker, entry_id: int, gameweek: Optional[int] = None):
    """Render detailed 15-player squad of a rival team."""
    res = tracker.get_team_picks(entry_id, gameweek=gameweek)
    gw = res["gameweek"]
    cap = res["captain"]
    vc = res["vice_captain"]

    console.print(Panel.fit(
        f"[bold gold1]Rival Team Squad Spy — Gameweek {gw}[/bold gold1]\n"
        f"Entry ID: [bold white]{entry_id}[/bold white] | GW Points: [bold cyan]{res['gw_points']}[/bold cyan] | Total: [bold yellow]{res['total_points']}[/bold yellow]\n"
        f"Active Chip: [bold magenta]{res['active_chip'] or 'None'}[/bold magenta] | Transfers: [bold]{res['transfers']} (-{res['transfer_cost']} pts)[/bold]\n"
        f"★ Captain: [bold red]{cap['web_name']} ({cap['club']})[/bold red] | ☆ Vice: [bold blue]{vc['web_name']} ({vc['club']})[/bold blue]",
        border_style="bright_blue"
    ))

    table = Table(title="[bold green]Starting XI (1-11)[/bold green]", header_style="bold magenta", border_style="dim")
    table.add_column("Slot", width=5, justify="center")
    table.add_column("Pos", width=5)
    table.add_column("Player", width=16)
    table.add_column("Club", width=6)
    table.add_column("Cost", justify="right", width=7)
    table.add_column("Role", width=8, justify="center")

    for p in res["starters"]:
        role = ""
        if p["is_captain"]:
            role = "[bold red](C)[/bold red]"
        elif p["is_vice_captain"]:
            role = "[bold blue](VC)[/bold blue]"

        table.add_row(
            str(p["slot"]),
            p["pos"],
            p["web_name"],
            p["club"],
            f"£{p['cost']:.1f}m",
            role
        )

    console.print(table)

    b_table = Table(title="[bold yellow]Substitutes Bench (12-15)[/bold yellow]", header_style="bold yellow", border_style="dim")
    b_table.add_column("Slot", width=5, justify="center")
    b_table.add_column("Pos", width=5)
    b_table.add_column("Player", width=16)
    b_table.add_column("Club", width=6)
    b_table.add_column("Cost", justify="right", width=7)

    for p in res["bench"]:
        b_table.add_row(
            str(p["slot"]),
            p["pos"],
            p["web_name"],
            p["club"],
            f"£{p['cost']:.1f}m"
        )

    console.print(b_table)


def display_league_history(tracker: LeagueTracker, league_id: int):
    """Render Rich CLI table showing gameweek-by-gameweek cumulative points and ranks."""
    res = tracker.get_league_performance_history(league_id)
    df = res["df"]
    chips = res["chips"]
    league_name = res["league_name"]

    console.print(Panel.fit(
        f"[bold gold1]Mini-League Performance Trajectory — {league_name}[/bold gold1]\n"
        f"[dim]League ID: {league_id}[/dim]",
        border_style="bright_blue"
    ))

    # Pivot table of cumulative points
    piv = df.pivot(index="team_name", columns="gameweek", values="cumulative_points")
    table = Table(title="[bold green]Championship Race — Cumulative Points Progression[/bold green]", border_style="dim")
    table.add_column("Team Name", width=24)
    for col in piv.columns:
        table.add_column(str(col), justify="right", width=10)

    for team, row in piv.iterrows():
        is_rr = (team == "Rubies Rangers")
        t_style = "[bold gold1]" if is_rr else ""
        t_end = "[/bold gold1]" if is_rr else ""
        
        vals = [f"{t_style}{int(v) if pd.notnull(v) else '-'}{t_end}" for v in row]
        table.add_row(f"{t_style}{team}{t_end}", *vals)

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers FPL Mini-League Scout & Rival Spy")
    parser.add_argument("--league", type=int, default=DEFAULT_LEAGUE_ID, help=f"Mini-League ID (default: {DEFAULT_LEAGUE_ID} 'Bronze, Silver & Gold League')")
    parser.add_argument("--team", type=int, default=None, help="Team / Entry ID (e.g. 987654)")
    parser.add_argument("--spy", type=int, default=None, help="Rival Entry ID to inspect squad for")
    parser.add_argument("--ownership", action="store_true", help="Calculate mini-league player ownership matrix (EO%)")
    parser.add_argument("--history", action="store_true", help="Display gameweek-by-gameweek progression table for all teams")
    parser.add_argument("--gw", type=int, default=None, help="Gameweek number (default latest active)")
    parser.add_argument("--top", type=int, default=50, help="Max number of teams to inspect")

    args = parser.parse_args()
    tracker = LeagueTracker()

    if args.spy:
        display_rival_squad(tracker, args.spy, gameweek=args.gw)
    elif args.team:
        display_team_leagues(tracker, args.team)
    elif args.ownership:
        df = tracker.get_league_ownership(args.league, gameweek=args.gw, max_teams=args.top)
        console.print(Panel.fit(f"[bold gold1]Mini-League Player Ownership & EO% (League {args.league})[/bold gold1]"))
        console.print(df.to_string(index=False))
    elif args.history:
        display_league_history(tracker, args.league)
    else:
        display_league_standings(tracker, args.league)


if __name__ == "__main__":
    main()
