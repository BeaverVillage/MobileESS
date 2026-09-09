"""Reconnect inherited V17/V37 Fresh cuts using the current alpha=1.15 coefficients."""
from dataclasses import asdict,replace
from pathlib import Path
import time
import numpy as np
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_budget import adapted
from dayahead.v17_ac_restoration_contract import RHO
# User-confirmed operating cap: solve within ten correction rounds, stop on PASS.
K_MAX=10
from dayahead.v37r3.restoration import extract_ac_violations,local_fresh_ac_restoration_cuts,_discrete_signature,control_matrix
from dayahead.v34.integrated_mess import _add_restoration_cuts,_add_restoration_recourse_trust_region
from dayahead.v40h.recourse import solve_fixed_route,validate_physics
from dayahead.v40a.grid import add_grid,controls_from_trajectory,evaluate_grid
from dayahead.v40a.invariants import digest
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v40e.mapping import corrected_mapping
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
from dayahead.v41.execution import command_arrays
from dayahead.mess_physics import P_LIMIT_KW,PCS_KVA

MARGINS_PATH=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4/audit/mission/AC_CUT_MARGIN_AUTHORITY.json'

def make_frozen(day,policy,jobs,power,mess):
    commands=[asdict(r) for r in mess.slots]
    sha=digest(dict(day=day,policy=policy,AIDC_decision=jobs,MESS_trajectory=commands))
    p,q,ids,locations=command_arrays(commands)
    return FrozenTrajectory(day,'DAYAHEAD',policy,power['pcc'],power['qcc'],p,q,tuple(ids),locations,sha)

def restore(day,policy,jobs,power,trajectory,context,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    margins=read(MARGINS_PATH);assert margins['status']=='PASS_FROZEN_BEFORE_APR12_REPLAY'
    started=time.perf_counter();initial=digest(trajectory);discrete=_discrete_signature(trajectory);aidc=digest(jobs)
    accumulated=[];rounds=[];current=trajectory
    for k in range(K_MAX+1):
        folder=output/f'round_{k:02d}';folder.mkdir(parents=True,exist_ok=True)
        frozen=make_frozen(day,policy,jobs,power,current)
        write_json(folder/'FROZEN_INPUT.json',dict(AIDC_SHA=aidc,MESS_slots=[asdict(r) for r in current.slots],decision_SHA=frozen.source_schedule_sha256))
        write_json(output/'LIVE.json',dict(status='RUNNING',round=k,stage='FRESH',updated_at=time.time()))
        with corrected_mapping():
            fresh=run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=context.electrical,
                voltage=context.electrical.voltage,trajectory=frozen,output=folder/'fresh')
        assert _discrete_signature(current)==discrete and digest(jobs)==aidc
        if not fresh.summary['physical_violation']:
            result=dict(status='PASS',initial_trajectory_SHA=initial,final_trajectory_SHA=digest(current),
                restoration_rounds=k,rounds=rounds,Fresh=fresh.summary,route_search_calls=0,AIDC_optimization_calls=0,
                Actual_reads=0,discrete_unchanged=True,final_slots=[asdict(r) for r in current.slots],
                margin_authority=record(MARGINS_PATH),K_MAX=K_MAX,RHO=RHO,coefficients=context.v41_electrical_certificate,
                elapsed_seconds=time.perf_counter()-started)
            write_json(output/'RESULT.json',result);write_json(output/'LIVE.json',dict(status='PASS',round=k,stage='COMPLETE',updated_at=time.time()))
            return current,result
        if k==K_MAX:raise RuntimeError('INHERITED_AC_RESTORATION_FAILED_CLOSED')
        violations=extract_ac_violations(fresh)
        write_json(output/'LIVE.json',dict(status='RUNNING',round=k+1,stage='GENERATE_CUTS',updated_at=time.time()))
        with corrected_mapping():
            generated,derivative=local_fresh_ac_restoration_cuts(source_repo=SOURCE_DATA_REPOSITORY,
                electrical=context.electrical,voltage=context.electrical.voltage,frozen=frozen,fresh=fresh,
                violations=violations,iteration_index=k+1,margins=margins['margins'])
        assert generated;accumulated.extend(generated)
        anchor=control_matrix(context.electrical.voltage,frozen)
        write_json(folder/'CUTS.json',dict(cuts=[c.payload() for c in accumulated],derivative=derivative))
        cut_stats={}
        def grid_with_cuts(model,coefficients,controls,cap):
            rho,counts=add_grid(model,coefficients,controls,cap)
            rows,trust=_add_restoration_cuts(model,coefficients[0].control_names,controls,accumulated)
            whole=_add_restoration_recourse_trust_region(model,coefficients[0].control_names,controls,anchor,
                p_radius_kw=RHO*P_LIMIT_KW,q_radius_kvar=RHO*PCS_KVA)
            assert len(rows)==len(accumulated)
            counts.update(restoration_cuts=len(rows),cut_trust_rows=trust,full_horizon_trust_rows=whole)
            cut_stats.update(counts);return rho,counts
        solver=adapted(solve_fixed_route,[('min(1,before[\'rho_max\']+tolerance)','1.0')],dict(add_grid=grid_with_cuts))
        budget=getattr(context,'v41_policy_budget',None)
        if hasattr(context,'v41_policy_budget'):del context.v41_policy_budget
        write_json(output/'LIVE.json',dict(status='RUNNING',round=k+1,stage='SOLVE_CUT_MODEL',updated_at=time.time()))
        try:solved=solver(power['pcc'],current,context)
        finally:
            if budget is not None:context.v41_policy_budget=budget
        assert solved['status']=='PASS',('CUT_RECOURSE_FAILURE',solved.get('solver'))
        candidate=solved['trajectory'];assert _discrete_signature(candidate)==discrete
        assert validate_physics(candidate)['status']=='PASS'
        values=controls_from_trajectory(context.coefficients,power['pcc'],candidate.slots)
        arithmetic=[]
        for c in accumulated:
            value=c.actual_value+np.dot(c.coefficients,values[c.slot]-np.array(c.anchor_controls))
            slack=c.hard_limit-c.margin-value if c.relation=='<=' else value-c.hard_limit-c.margin
            assert slack>=-2e-6,('RESTORATION_CUT_NOT_ENFORCED',c.slot,slack)
            arithmetic.append(dict(slot=c.slot,violation=c.violation_type.value,value=float(value),slack=float(slack)))
        report=dict(round=k+1,new_cut_count=len(generated),total_cut_count=len(accumulated),
            inserted_rows=cut_stats,arithmetic=arithmetic,solver=solved['solver'],Fresh_before=fresh.summary)
        write_json(folder/'RECOURSE.json',report);rounds.append(report);current=candidate
        print('CUT_ROUND_SOLVED',day,policy,k+1,'cuts',len(accumulated),flush=True)

def standalone(day,policy):
    from v41r4_electrical import configure
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    run=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4';da=run/day/policy/'dayahead'
    d=read(da/'FROZEN_JOINT_DECISION.json')['decision']
    with np.load(da/'FROZEN_AIDC_POWER.npz') as z:power={k:z[k].copy() for k in z.files}
    ctx=configure(day).load(day)
    try:restore(day,policy,d['AIDC_decision'],power,MessTrajectory(tuple(_restore_slots(d['MESS_trajectory']))),ctx,run/'audit/mission/CUT_REPAIR'/day/policy)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':
    import sys
    standalone(sys.argv[1],sys.argv[2])
