"""Pre-solve May01 job-window evidence; no Actual or voltage calibration."""
from collections import defaultdict
from pathlib import Path
import json
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.persistence import table
from dayahead.v41.data import SOURCE_REPO
from .terminal import attach, start_bounds, authorized_options, accounting


def run():
    previous = ROOT.parent / 'MobileESS_v41_final_ml_interface_may_campaign/frozen_artifacts/v41_may_campaign'
    source = previous / 'inputs/2025-05-01/common/COMMON_B0_REFERENCE_JOBS.json'
    old_diag = previous / 'diagnostics/may01_primary_gain_explanation/PRIMARY_GAIN_EXPLANATION.json'
    old = read(old_diag)
    assert old['minimum_total_peak_GPU'] == 576 and old['post_H_frozen_PENDING_jobs_starting_exactly_at_peak'] == 156
    assert old['policies']['B0']['peak_GPU'] == 583 and old['policies']['B1']['peak_GPU'] == 576
    jobs = attach(read(source))
    from dayahead.v39d.evaluate import _load_capacity
    capacity = _load_capacity(SOURCE_REPO)[0]
    rows = []
    for row in jobs:
        if row['state_at_issue'] != 'PENDING' or not row['terminal_reference_selected']:
            continue
        opts = authorized_options(row, capacity); lo, hi = start_bounds(row)
        rows.append(dict(job_id=row['job_uid'],GPU=row['requested_GPU'],reference_start=row['start_slot']-24,
            duration_slots=row['safe_duration_slots'],reference_site=row['AIDC_site'],
            reference_terminal_slots=row['terminal_reference_remaining_slots'],
            earliest_start=lo-24,latest_start=hi-24,site_count=len({s for s,t in opts}),
            can_time_shift=lo!=hi,can_change_site=len({s for s,t in opts})>1,
            old_156_peak_cohort=row['start_slot']==96 and row['end_slot']>120,
            mandatory_at_18=hi<=96<lo+row['safe_duration_slots'],
            binding_start_slots=[t-24 for t in range(lo,hi+1)
                if accounting(t-24,row['safe_duration_slots'])[2]==row['terminal_reference_remaining_slots']]))
    frame=pd.DataFrame(rows)
    frame['binding_start_slots']=frame.binding_start_slots.map(json.dumps)
    source_table=table(OUT/'diagnostic/PENDING_START_DOMAIN.parquet',frame)
    selected=frame[frame.old_156_peak_cohort]
    assert len(selected)==156
    pending_min=int(frame.loc[frame.mandatory_at_18,'GPU'].sum())
    # RUNNING rules are unchanged. Verify the old complete membership witness
    # before using its first-checkpoint/latest-ready proof at this timestamp.
    membership=pd.read_parquet(old['membership']['path'])
    assert record(old['membership']['path'])==old['membership']
    running=membership[(membership.state=='RUNNING')&membership.mandatory_at_peak]
    running_min=int(running.GPU_request.sum()); assert running_min==290
    # Separately solve the 96-slot temporal job-window relaxation, keeping
    # RUNNING intervals fixed. This is not the full site/rack/grid optimum.
    model=gp.Model('R1_JOB_WINDOW_PEAK_DIAGNOSTIC');model.Params.OutputFlag=0
    model.Params.Threads=4;model.Params.Seed=20260905;model.Params.MIPGap=0
    model.Params.FeasibilityTol=1e-9;model.Params.IntFeasTol=1e-9
    loads=[gp.LinExpr() for _ in range(96)];groups=defaultdict(list)
    for row in jobs:
        if row['AIDC_site']=='UNASSIGNED':continue
        if row['state_at_issue']=='PENDING':lo,hi=start_bounds(row)
        else:lo=hi=row['start_slot']
        groups[(row['requested_GPU'],row['safe_duration_slots'],lo,hi)].append(row['job_uid'])
    for i,((gpu,d,lo,hi),ids) in enumerate(sorted(groups.items())):
        choices=[]
        for start in range(lo,hi+1):
            value=len(ids) if lo==hi else model.addVar(vtype=GRB.INTEGER,lb=0,ub=len(ids),name=f'window_choice[{i},{start-24}]')
            choices.append(value)
            for t in range(max(24,start),min(120,start+d)):loads[t-24]+=gpu*value
        model.addConstr(gp.quicksum(choices)==len(ids))
    peak=model.addVar(lb=0,name='peak_GPU')
    for load in loads:model.addConstr(load<=peak)
    model.setObjective(peak,GRB.MINIMIZE);model.optimize()
    assert model.Status==GRB.OPTIMAL
    profile=[float(load.getValue()) for load in loads]
    result=dict(status='PASS',Actual_reads=0,OpenDSS_calls=0,voltage_margin_calibration=False,
        old_evidence=record(old_diag),old_classification='VALID_UNDER_SUPERSEDED_POST_H_FREEZE_SEMANTICS',
        new_classification='PER_JOB_TERMINAL_RESIDUAL_SEMANTICS',common_reference_source=record(source),
        old_18h_B0_GPU=583,old_18h_B1_GPU=576,old_18h_lower_bound=576,
        reference_cross_midnight_PENDING=int((frame.reference_terminal_slots>0).sum()),
        old_peak_cohort=156,newly_time_movable_in_156=int(selected.can_time_shift.sum()),
        newly_site_movable_in_156=int(selected.can_change_site.sum()),
        newly_time_movable_cross_midnight=int(((frame.reference_terminal_slots>0)&frame.can_time_shift).sum()),
        mandatory_18h_PENDING_GPU=pending_min,mandatory_18h_RUNNING_GPU=running_min,
        new_18h_theoretical_minimum_GPU=pending_min+running_min,
        all_156_still_overlap_18h_for_every_authorized_start=bool(selected.mandatory_at_18.all()),
        H=96,whole_day_job_window_relaxation_peak=float(peak.X),whole_day_job_window_relaxation_bound=float(model.ObjBound),
        whole_day_job_window_relaxation_GPU=profile,
        relaxation_scope='Minimum maximum total GPU over 96 slots with exact per-job start windows and terminal caps; RUNNING reference intervals fixed, site/rack/WAN/grid coupling omitted',
        no_full_grid_optimality_claim=True,domain_table=source_table,
        pre_day_issue_PENDING_fixed_count=int((frame.reference_start<0).sum()))
    model.dispose();write_json(OUT/'V41R1_MAY01_PREOPTIMIZATION_FLEXIBILITY_DIAGNOSTIC.json',result)
    print({k:v for k,v in result.items() if k.endswith('_GPU') or 'movable' in k or k=='all_156_still_overlap_18h_for_every_authorized_start'},flush=True)


if __name__=='__main__':run()
