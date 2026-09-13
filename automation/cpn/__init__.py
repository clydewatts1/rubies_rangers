"""
automation/cpn/__init__.py
Kurt Jensen Timed Coloured Petri Net (TCPN) Autonomous Execution Pipeline.
Exports public tokens, places, guards, transitions, engine, and diagnostics.
"""
from automation.cpn.tokens import (
    K3Status,
    Color_Deadline,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
    Color_OptimizedPlan,
    Color_GuardToken,
    Color_Receipt,
    Color_Alert,
)
from automation.cpn.places import (
    CPNPlace,
    CPNStatePlace,
    CPNMarkingRegistry,
)
from automation.cpn.guards import (
    GuardEvaluationResult,
    evaluate_budget_guard,
    evaluate_club_cap_guard,
    evaluate_formation_guard,
    evaluate_hit_utility_guard,
    evaluate_fitness_guard,
    evaluate_chip_safety_guard,
    evaluate_preflight_session_guard,
    evaluate_time_window_guard,
    evaluate_joint_guards,
)
from automation.cpn.transitions import (
    t_preflight_and_ingest,
    t_session_keepalive,
    t_simulate_and_solve,
    t_evaluate_guards,
    t_abort_and_alert,
    t_degrade_plan,
    t_scatter_indeterminate,
    t_early_leak_resolve,
    t_force_disambiguate,
    t_gather_and_reevaluate,
    t_dispatch_transfers,
    t_reconcile_transfers,
    t_dispatch_lineup,
    t_reconcile_lineup,
)
from automation.cpn.engine import CPNEngine
from automation.cpn.diagnostics import CPNDiagnosticJournal
from automation.cpn.daemon import CPNDaemon, get_cpn_daemon

__all__ = [
    "K3Status",
    "Color_Deadline",
    "Color_Session",
    "Color_MarketData",
    "Color_SquadState",
    "Color_OptimizedPlan",
    "Color_GuardToken",
    "Color_Receipt",
    "Color_Alert",
    "CPNPlace",
    "CPNStatePlace",
    "CPNMarkingRegistry",
    "GuardEvaluationResult",
    "evaluate_budget_guard",
    "evaluate_club_cap_guard",
    "evaluate_formation_guard",
    "evaluate_hit_utility_guard",
    "evaluate_fitness_guard",
    "evaluate_chip_safety_guard",
    "evaluate_preflight_session_guard",
    "evaluate_time_window_guard",
    "evaluate_joint_guards",
    "t_preflight_and_ingest",
    "t_session_keepalive",
    "t_simulate_and_solve",
    "t_evaluate_guards",
    "t_abort_and_alert",
    "t_degrade_plan",
    "t_scatter_indeterminate",
    "t_early_leak_resolve",
    "t_force_disambiguate",
    "t_gather_and_reevaluate",
    "t_dispatch_transfers",
    "t_reconcile_transfers",
    "t_dispatch_lineup",
    "t_reconcile_lineup",
    "CPNEngine",
    "CPNDiagnosticJournal",
    "CPNDaemon",
    "get_cpn_daemon",
]
