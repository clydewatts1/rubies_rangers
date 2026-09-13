def test():
    counts = {'P_Session': 1, 'P_Market': 1, 'P_Squad': 1, 'P_Committed': 1}
    def p_style(name: str, default_label: str) -> str:
        tokens = counts.get(name, 0)
        if name == "P_Committed" and tokens > 0:
            return f'{name} [label="{default_label}\\n[Tokens: {tokens}]", shape=doublecircle, style="filled,bold", fillcolor="#064e3b", fontcolor="#4ade80", color="#10b981"];'
        elif name == "P_DeadLetter" and tokens > 0:
            return f'{name} [label="{default_label}\\n[Tokens: {tokens}]", shape=doublecircle, style="filled,bold", fillcolor="#450a0a", fontcolor="#f87171", color="#ef4444"];'
        elif tokens > 0:
            return f'{name} [label="{default_label}\\n[Tokens: {tokens}]", shape=circle, style="filled,bold", fillcolor="#0c4a6e", fontcolor="#38bdf8", color="#0284c7"];'
        else:
            return f'{name} [label="{default_label}", shape=circle, style="filled", fillcolor="#18181b", fontcolor="#71717a", color="#27272a"];'

    dot = f"""digraph JensenCPN {{
        rankdir=LR;
        bgcolor="transparent";
        fontname="Helvetica";
        node [fontname="Helvetica", fontsize=9];
        edge [color="#64748b", fontname="Helvetica", fontsize=8, arrowsize=0.7];

        node [shape=box, style="filled,rounded", fillcolor="#1e293b", fontcolor="#f8fafc", color="#475569"];
        T_Preflight [label="T_PreflightAndIngest"];
        T_Solve [label="T_SimulateAndSolve"];
        T_Guards [label="T_EvaluateGuards\\n(Kleene K3)"];
        T_Degrade [label="T_DegradePlan"];
        T_DispatchT [label="T_DispatchTransfers\\n(Stage 1)"];
        T_ReconcileT [label="T_ReconcileTransfers\\n(Gate 1 Audit)", color="#f59e0b", style="filled,bold"];
        T_DispatchL [label="T_DispatchLineup\\n(Stage 2)"];
        T_ReconcileL [label="T_ReconcileLineup\\n(Gate 2 Audit)", color="#10b981", style="filled,bold"];

        {p_style("P_Session", "P_Session\\n(Read-Arc)")}
        {p_style("P_Market", "P_Market\\n(Read-Arc)")}
        {p_style("P_Squad", "P_Squad\\n(Read-Arc)")}
        {p_style("P_Plan", "P_Plan")}
        {p_style("P_PendingPlan", "P_PendingPlan")}
        {p_style("P_Contingency", "P_Contingency")}
        {p_style("P_ResolvedGuard", "P_ResolvedGuard")}
        {p_style("P_PlanDegrade", "P_PlanDegrade")}
        {p_style("P_TransfersAwaitingValidation", "P_TransfersWait")}
        {p_style("P_TransfersExecuted", "P_TransfersDone")}
        {p_style("P_LineupAwaitingValidation", "P_LineupWait")}
        {p_style("P_Committed", "P_Committed\\n(Reconciled)")}
        {p_style("P_DeadLetter", "P_DeadLetter\\n(Alerts)")}

        T_Preflight -> P_Session;
        T_Preflight -> P_Market;
        T_Preflight -> P_Squad;
        P_Squad -> T_Solve;
        P_Market -> T_Solve;
        T_Solve -> P_Plan;
        T_Solve -> P_PendingPlan;
        T_Solve -> P_Contingency;
        P_Contingency -> P_ResolvedGuard [label="Scatter-Gather / D-8m"];
        P_ResolvedGuard -> T_Guards;
        P_PendingPlan -> T_Guards;
        T_Guards -> T_DispatchT [label="Guards=T"];
        T_Guards -> P_PlanDegrade [label="Guards=F"];
        P_PlanDegrade -> T_Degrade;
        T_Degrade -> T_DispatchT;
        T_DispatchT -> P_TransfersAwaitingValidation;
        P_TransfersAwaitingValidation -> T_ReconcileT;
        T_ReconcileT -> P_TransfersExecuted;
        P_TransfersExecuted -> T_DispatchL;
        T_DispatchL -> P_LineupAwaitingValidation;
        P_LineupAwaitingValidation -> T_ReconcileL;
        T_ReconcileL -> P_Committed [label="Audit Verified"];
        T_ReconcileT -> P_DeadLetter [label="Audit Mismatch", style=dashed, color="#ef4444"];
        T_ReconcileL -> P_DeadLetter [label="Audit Mismatch", style=dashed, color="#ef4444"];
    }}"""
    print("Generated DOT length:", len(dot))

if __name__ == "__main__":
    test()
