"""
CLI Entry Point for Rubies Rangers Auto-Tuner & Backtest Subsystem
Usage:
    python -m tuner.cli fetch-data
    python -m tuner.cli run --trials 50 --n-jobs 4
    python -m tuner.cli dashboard --port 8502
    python -m tuner.cli evaluate --profile tuned --season 2023-24
"""

from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backtest.data_loader import HistoricalDataLoader
from backtest.simulator import WalkForwardSimulator
from .engine import HyperparameterTuner, DEFAULT_DB_PATH
from config_manager import get_params

console = Console()


def cmd_fetch_data(args: argparse.Namespace) -> None:
    """Pre-downloads and caches historical seasons."""
    console.print("[bold cyan]Fetching Historical Premier League Datasets from Vaastav FPL Repo...[/bold cyan]")
    loader = HistoricalDataLoader()
    seasons = args.seasons or loader.AVAILABLE_SEASONS

    for s in seasons:
        try:
            df = loader.fetch_season_raw(s)
            console.print(f"  [green][OK][/green] Season [bold green]{s}[/bold green]: Cached {len(df):,} gameweek records.")
        except Exception as e:
            console.print(f"  [red][FAIL][/red] Season [bold red]{s}[/bold red]: Failed ({e})")


def cmd_run(args: argparse.Namespace) -> None:
    """Runs Optuna hyperparameter optimization."""
    console.print("[bold cyan]====================================================================[/bold cyan]")
    console.print("[bold cyan]   Rubies Rangers -- Multi-Season Hyperparameter Auto-Tuner        [/bold cyan]")
    console.print("[bold cyan]====================================================================[/bold cyan]")
    console.print(f"Study Name:    [yellow]{args.study_name}[/yellow]")
    console.print(f"Database:      [yellow]{DEFAULT_DB_PATH}[/yellow]")
    console.print(f"Train Seasons: [green]{', '.join(args.train_seasons)}[/green]")
    console.print(f"Test Season:   [magenta]{args.test_season}[/magenta] (Strict Out-of-Sample)")
    console.print(f"Trials:        [bold white]{args.trials}[/bold white]")
    console.print(f"Worker Cores:  [bold white]{args.n_jobs}[/bold white]")
    console.print("[cyan]--------------------------------------------------------------------[/cyan]")

    tuner = HyperparameterTuner(
        study_name=args.study_name,
        train_seasons=args.train_seasons,
        test_season=args.test_season,
        auto_update_config=not args.no_auto_update
    )

    study = tuner.optimize(n_trials=args.trials, n_jobs=args.n_jobs)
    best = study.best_trial

    console.print("\n[bold green][OK] Auto-Tuning Run Finished Successfully![/bold green]")
    console.print(f"Best Trial ID:        [bold white]#{best.number}[/bold white]")
    console.print(f"Best Combined Score:  [bold green]{best.value:.3f}[/bold green]")
    console.print(f"Test Season Points:   [bold cyan]{best.user_attrs.get('test_net_points')}[/bold cyan]")
    if not args.no_auto_update:
        console.print("[italic green]config.yaml has been automatically updated with the tuned profile.[/italic green]")


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Launches the interactive Optuna Dashboard on specified port."""
    storage = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    console.print(f"[bold cyan]Launching Optuna Dashboard on http://127.0.0.1:{args.port} ...[/bold cyan]")
    console.print(f"Storage: [yellow]{storage}[/yellow]")

    import optuna_dashboard
    try:
        optuna_dashboard.run_server(storage, host="127.0.0.1", port=args.port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Evaluates a single season walk-forward using specified profile."""
    console.print(f"[bold cyan]Evaluating Season {args.season} using profile: [yellow]{args.profile}[/yellow]...[/bold cyan]")
    loader = HistoricalDataLoader()
    sim = WalkForwardSimulator(loader)

    from config_manager import set_active_profile
    set_active_profile(args.profile)

    params = {
        "moneyball": get_params("moneyball"),
        "optimizer": get_params("optimizer"),
        "xp_model": get_params("xp_model"),
        "montecarlo": get_params("montecarlo"),
    }

    result = sim.run_season(args.season, params=params, start_gw=args.start_gw, end_gw=args.end_gw)

    table = Table(title=f"Walk-Forward Audit: {args.season} ({args.profile.upper()})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Season", result.season)
    table.add_row("Gameweeks Simulated", str(len(result.gameweeks)))
    table.add_row("Total Net Points", f"{result.total_net_points:.1f}")
    table.add_row("Mean Points / GW", f"{result.mean_gw_points:.2f}")
    table.add_row("Points Std Dev", f"{result.std_gw_points:.2f}")
    table.add_row("Sharpe Ratio", f"{result.sharpe_ratio:.3f}")
    table.add_row("Risk-Adjusted Score", f"{result.risk_adjusted_score:.2f}")
    table.add_row("Total Transfers Made", str(result.total_transfers))
    table.add_row("Total Hits Taken", str(result.total_hits))

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Rubies Rangers Backtesting & Auto-Tuning CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch-data
    p_fetch = subparsers.add_parser("fetch-data", help="Download and cache historical FPL seasons")
    p_fetch.add_argument("--seasons", nargs="+", help="Seasons to fetch (e.g. 2021-22 2022-23 2023-24)")
    p_fetch.set_defaults(func=cmd_fetch_data)

    # run
    p_run = subparsers.add_parser("run", help="Run Optuna multi-season hyperparameter optimization")
    p_run.add_argument("--trials", "--n-trials", type=int, default=50, help="Total trials to run")
    p_run.add_argument("--n-jobs", type=int, default=4, help="Concurrent worker threads")
    p_run.add_argument("--study-name", type=str, default="rubies_rangers_moneyball", help="Optuna study name")
    p_run.add_argument("--train-seasons", nargs="+", default=["2021-22", "2022-23"], help="Training seasons")
    p_run.add_argument("--test-season", type=str, default="2023-24", help="Out-of-sample test season")
    p_run.add_argument("--no-auto-update", action="store_true", help="Do not overwrite config.yaml with best parameters")
    p_run.set_defaults(func=cmd_run)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start the Optuna Web Dashboard")
    p_dash.add_argument("--port", type=int, default=8502, help="Port to serve the dashboard on")
    p_dash.set_defaults(func=cmd_dashboard)

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Audit walk-forward season with a profile")
    p_eval.add_argument("--profile", choices=["heuristic", "tuned"], default="heuristic", help="Configuration profile")
    p_eval.add_argument("--season", type=str, default="2023-24", help="Season to evaluate")
    p_eval.add_argument("--start-gw", type=int, default=1, help="Start gameweek")
    p_eval.add_argument("--end-gw", type=int, default=38, help="End gameweek")
    p_eval.set_defaults(func=cmd_evaluate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
