"""Explicit smoke only. Full Actual campaign authorization is deliberately absent."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, write_parquet, write_npz, canonical, digest, reference
from .contracts import ReplayError, ZERO_COUNTERS, write_contracts
from .inputs import capacity, frozen_jobs, observations
from .job_replay import replay_jobs, validate_jobs
from .rack_dispatch import Rack
from .power_replay import power_from_execution
from .exogenous import load as load_exogenous
from .mobility_inputs import actual_mobility
from .grid_replay import replay as grid_replay
from .preflight import verify_protected
from .capacity_audit import write_runtime_audits, require_current_capacity
from .physical_audit import c1_recalculation


def smoke(repo, day="2025-05-01", cases=("B0","B1","B2","B3")):
    repo = Path(repo)
    audit = repo/"dayahead/artifacts/v40d_actual_realized_replay"
    root = audit/"smoke"/day
    write_json(root/"SMOKE_STATUS.json",{"status":"RUNNING","full_campaign_authorized":False})
    bindings = read(audit/"V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    selected = [b for b in bindings if b["day"]==day and b["case"] in cases]
    if len(selected)!=len(cases):
        raise ReplayError("SMOKE_CERTIFIED_CASE_SET")
    guard = verify_protected(repo,audit)
    if guard["status"]!="PASS":
        raise ReplayError("SMOKE_PROTECTED_INPUT_DRIFT")
    # Check decisions before reading any realized inputs.
    jobs = [(b,*frozen_jobs(repo,b)) for b in selected]
    obs = observations(audit)
    a,_,*_=capacity(repo)
    sites = a["frozen_V39C_site_capacity"]
    require_current_capacity(sites)
    racks = [Rack(r["aidc_id"],r["rack_pool_id"],int(r["compatibility_GPU_limit"])) for r in a["logical_Rack_pools"]]
    for b,j,issue in jobs:
        failures=validate_jobs(j,obs,sites,issue)
        if failures:
            raise ReplayError("SMOKE_BLOCKED_CASE:"+b["case"]+":"+str(failures[:3]))
    write_contracts(repo,root/"contracts")
    import gurobipy as gp
    old = gp.Model.optimize
    optimizer_calls = 0
    def forbidden(*args,**kwargs):
        nonlocal optimizer_calls
        optimizer_calls+=1
        raise ReplayError("ACTUAL_OPTIMIZATION_FORBIDDEN")
    gp.Model.optimize=forbidden
    context=None
    outcomes=[]
    try:
        from dayahead.v40a.context import load_planning_context
        context=load_planning_context(repo,day)
        exo=load_exogenous(repo,day)
        write_npz(root/"actual_exogenous.npz", demand_mw=exo["demand_mw"],pv_mw=exo["pv_mw"],
                  t_wb_c=exo["weather"].t_wb_c.to_numpy(),rh_pct=exo["weather"].rh_pct.to_numpy())
        write_json(root/"actual_exogenous_authority.json",exo["authority"])
        for b,j,issue in jobs:
            case=b["case"]; out=root/case
            run_id=str(uuid4());run_started=datetime.now(timezone.utc).isoformat()
            print("Actual smoke "+day+" "+case+" computing",flush=True)
            executed=replay_jobs(j,obs,issue_time=issue,site_capacity=sites,racks=racks)
            repeated=replay_jobs(j,obs,issue_time=issue,site_capacity=sites,racks=racks)
            if canonical(executed)!=canonical(repeated):
                raise ReplayError("NONDETERMINISTIC_ACTUAL_COMPUTING")
            power=power_from_execution(repo,executed,sites,exo["weather"])
            c1_audit=c1_recalculation(repo,power,exo["weather"])
            write_json(out/"V40D_ACTUAL_C1_PCC_RECALCULATION.json",c1_audit)
            capacity_results=write_runtime_audits(out,day,case,j,executed,sites,racks,power)
            mess=actual_mobility(repo,b)
            write_json(out/"V40D_ACTUAL_MESS_D00_STATE_AUDIT.json",mess["initial_states"])
            write_json(out/"V40D_ACTUAL_MESS_INVARIANT_SOC_AUDIT.json",mess["audit"])
            write_json(out/"MESS_FROZEN_COMMANDS.json",mess["frozen_commands"])
            replay_identity=digest({"frozen_accepted_decision":b["final_executed_joint_sha"],
                "jobs":executed["job_ledger"],"MESS_commands":mess["frozen_commands_SHA"]})
            for name, data in (("job_ledger",executed["job_ledger"]),("rack_ledger",executed["rack_ledger"]),
                               ("rack_waits",executed["rack_waits"]),("job_GPU_contributions",power["job_slot_contributions"])):
                frame=pd.DataFrame(data)
                # Mixed integer/string priority keys are JSON strings, preserving their exact ordering semantics.
                for column in ("stable_priority_key", "WAN_state", "accepted_A0_assignment_and_WAN", "checks"):
                    if column in frame:
                        frame[column]=frame[column].map(lambda v:canonical(v).decode().strip() if isinstance(v,(dict,list,str)) else None)
                write_parquet(out/(name+".parquet"),frame)
            write_parquet(out/"aidc_site_timeseries.parquet",power["frame"])
            write_parquet(out/"MESS_executed_trajectory.parquet",mess["frame"])
            write_json(out/"MESS_actual_moves.json",mess["moves"])
            write_json(out/"V40D_AIDC_ACTUAL_OCCUPANCY_CONSERVATION.json",power["occupancy_audit"])
            write_json(out/"V40D_AIDC_ACTUAL_POWER_CONSERVATION.json",power["power_audit"])
            print("Actual smoke "+case+" OpenDSS",flush=True)
            first,binding_audit=grid_replay(repo,day,case,context,power,exo,mess,replay_identity,out/"actual_grid")
            from dayahead.paper_analysis.live import capture
            with capture(out/"rich_capture"):
                second,_=grid_replay(repo,day,case,context,power,exo,mess,replay_identity,out/"repeat_grid")
            fields=("voltage_pu","phase_current_a","phase_current_loading_pu","transformer_total_kva_loading_pu",
                    "losses_kw_kvar","regulator_taps","capacitor_states","convergence")
            exact=all(np.array_equal(getattr(first,k),getattr(second,k),equal_nan=True) for k in fields)
            if not exact:
                raise ReplayError("NONDETERMINISTIC_OR_OBSERVER_MUTATED_ACTUAL_GRID")
            write_json(out/"V40D_AIDC_ACTUAL_PCC_BINDING_AUDIT.json",binding_audit)
            runtime_summary={"status":"PASS","day":day,"case":case,"Actual_AC_rho":first.summary["rho_max_AC"],
                "Actual_OpenDSS_run_id":run_id,"Actual_run_started_UTC":run_started,
                "Actual_run_finished_UTC":datetime.now(timezone.utc).isoformat(),
                "Actual_summary":first.summary,"computing_repeat_byte_equal":True,"grid_observer_repeat_bit_equal":exact,
                "counters":executed["counters"],"actual_optimizer_calls":optimizer_calls,"full_campaign_authorized":False,
                "decision_binding":b,"normative_AIDC_stage":"CURRENT_A1" if case=="B3" else "FINAL_CASE_FREEZE",
                "normative_MESS_stage":"FINAL_AC_ACCEPTED_FIXED_ROUTE_ELECTRICAL_STATE",
                "aliases":{"CURRENT_A0":"PAPER_A1","CURRENT_M1":"PAPER_M1","CURRENT_A1":"PAPER_A2","CURRENT_MF":"PAPER_M2"}}
            write_json(out/"SMOKE_RESULT.json",runtime_summary)
            outcomes.append(runtime_summary)
            print("Actual smoke "+case+" PASS",flush=True)
    finally:
        gp.Model.optimize=old
        if context is not None:
            context.electrical.voltage.close();context.electrical.current.close()
        write_json(root/"SMOKE_STATUS.json",{"status":"PASS" if len(outcomes)==len(cases) else "FAIL_CLOSED",
            "case_count":len(outcomes),"optimizer_calls":optimizer_calls,"full_campaign_authorized":False})
    final_guard=verify_protected(repo,audit)
    write_json(root/"PROTECTED_REFERENCE_AFTER_SMOKE.json",final_guard)
    if final_guard["status"]!="PASS":
        raise ReplayError("SMOKE_PROTECTED_FILE_MODIFICATION")
    return outcomes
