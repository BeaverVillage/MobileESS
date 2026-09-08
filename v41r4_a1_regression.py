"""Read-only real-day A1 model/seed regression; never optimizes a campaign day."""
from fast_prepare import *
from v41r4_runtime import MAY_RUN,MAY_OUT
from pathlib import Path
import time,sys
import numpy as np
from dataclasses import replace
from dayahead.paper_analysis.storage import write_json

def main():
    import v41r4_b3_equivalent as a
    from dayahead.v40g import optimizer
    from dayahead.v41r1 import feasible_seed
    from dayahead.v41r1.bounded_solver import PolicyBudget
    from dayahead.v41 import physics_ranking as ranking,frozen_candidates as fc
    from dayahead.v41.common import build
    from dayahead.v41.snapshot import create
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v41.temporal_restore import activate
    from v41r4_electrical import configure as physics
    day='2025-05-04';out=MAY_OUT/'A1_regression';out.mkdir(parents=True,exist_ok=True)
    solve=a.make_solver(optimizer.solve);seed=a.make_seed(feasible_seed.complete_start)
    a.configure(day,'B3')
    ctx=physics(day).load(day)
    try:
        path,seal=create(day);bind(ctx,path,seal['snapshot']['sha256'])
        rows,_=build(day,path,ctx.capacity);power=planning_power(import_frozen(rows),ctx)
        ctx.v41_bounded_compute=dict(total_seconds=1800,fix_and_optimize=True)
        ctx.v41_policy_budget=PolicyBudget(1800);ctx.v41_policy='B3'
        neutral=feasible_seed.neutral_mess()
        probe=tuple(replace(s,q_kvar=-1.) if s.mess_id==neutral.slots[0].mess_id else s for s in neutral.slots)
        ctx.v41_fixed_mess=probe
        fc.OUT=ranking.OUT=out/'ranking'
        for name in ('V41R3_B0_ACCEPTANCE.json','V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'):
            copy(MAY_OUT/day/name,ranking.OUT/name)
        with activate():
            rank=ranking.prepare(ctx,rows,power)
            assert rank['candidate_set_SHA']==read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')['candidate_set_SHA']
            print('A1_REAL_RANKING_PASS',flush=True)
            deadline=time.time()+600
            while not (MAY_RUN/day/'B1/dayahead/DAYAHEAD_RECEIPT.json').exists():
                assert time.time()<deadline,'B1_SEED_NOT_READY'
                time.sleep(2)
            b1=read(MAY_RUN/day/'B1/dayahead/A0/ACCEPTED_AIDC.json')
            ctx.v41_a1_seed_jobs=import_frozen(b1['jobs'])
            ctx.v41_a1_seed_pcc=planning_power(ctx.v41_a1_seed_jobs,ctx)['pcc']
            feasible_seed.complete_start=seed
            # Both passes construct all 4,889,827 choices. No solver optimize.
            results={}
            for label,mess in (('zero_MESS',tuple(neutral.slots)),('fixed_nonzero_Q',probe)):
                ctx.v41_fixed_mess=mess
                started=time.perf_counter();folder=out/label
                result=solve(rows,power['pcc'],ctx,folder,build_only=True)
                structural=a.same_structure(ctx,folder)
                witness=read(folder/'POLICY_FEASIBLE_SEED_AUDIT.json')
                assert witness['status']=='PASS' and witness['model']['all_hard_model_rows_substituted']
                assert np.allclose(witness['seed_objective_vector'][1:],b1['OBJECTIVE_VECTOR'][1:],rtol=0,atol=1e-9)
                if label=='zero_MESS':assert np.allclose(witness['seed_objective_vector'],b1['OBJECTIVE_VECTOR'],rtol=0,atol=1e-9)
                results[label]=dict(status='PASS',structure=structural,seed=record(folder/'POLICY_FEASIBLE_SEED_AUDIT.json'),
                    OBJECTIVE_VECTOR=witness['seed_objective_vector'],seconds=time.perf_counter()-started,
                    optimization_calls=0)
                print('A1_FULL_MODEL_SEED_PASS',label,flush=True)
            assert results['zero_MESS']['OBJECTIVE_VECTOR'][0]!=results['fixed_nonzero_Q']['OBJECTIVE_VECTOR'][0], 'FIXED_MESS_NOT_IN_ELECTRICAL_EVALUATION'
            audit=dict(status='PASS',day=day,diagnostic_only=True,alpha_BG=1.15,alpha_tests=0,
                candidate_count=4889827,passes=results,A1_own_budget_seconds=1800,
                full_variable_axis_equal_B1=True,NEW_VARIABLES=0,NEW_CONSTRAINTS=0,
                original_B1_P2_P3_P4_P5_seed_exact=True,nonzero_fixed_MESS_changes_P1=True,
                optimizer_calls=0,Actual_reads=0,
                production_compound_consumption='Required fail-closed from every A1 actual ordering receipt',
                source=[record(ROOT/p) for p in a.HELPERS],regression_source=record(__file__),patches=a.PATCHES)
            write_json(out/'V41R4_A1_FOCUSED_REGRESSION.json',audit)
            print('A1_FOCUSED_REGRESSION_PASS',flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':main()
