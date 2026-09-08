"""Preserved historical state replay before first-improvement production edits."""
import json, shutil, time
from pathlib import Path
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from .flex_diagnostic import OUT as DIAG,WORK,OLD,NEW,DAY
from .flex_model import Data,ProbeModel
from .feasible_seed import row_audit

OUT=ROOT/'dayahead/artifacts/v41r1_first_improvement'

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    shutil.copyfile('C:/Users/kjw39/.codex/attachments/b0ee734a-a9ac-41ed-8b6e-f205168ca774/pasted-text.txt',OUT/'USER_REQUEST.txt')
    from dayahead.v41.execution import science,commit
    files=[]
    for ref in science()['files']:
        target=OUT/'before_source'/ref['relative_path'];target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(ref['path'],target)
        assert record(target)['sha256']==ref['sha256'];files.append(dict(original=ref,preserved=record(target)))
    write_json(OUT/'PRESERVATION.json',dict(source=science(),commit=commit(),files=files,diagnostic=record(DIAG/'PRESERVATION.json')))
    d=Data();p=ProbeModel(d)
    try:
        known=read(DIAG/'FORCED_CHANGE_PROBE_SINGLE_BEST_ORIGINAL_MODEL_WITNESS.json')
        propagation=read(DIAG/'FORCED_CHANGE_PROBE_SINGLE_BEST.json')
        u=next(iter(known['choices']));k=known['choices'][u];g=d.uidgroup[u]
        oracle=dict(status='PASS',job=u,option_index=k,group=g,original_decision=d.byuid[u],
            changed_decision=next(r for r in read(known['jobs']['path']) if r['job_uid']==u),
            source_IDC=d.byuid[u]['AIDC_site'],initial_IDC=d.option(u,k).initial_site,destination_IDC=d.option(u,k).site,
            before=d.base,after=known['vector'],constraint_audit=known,propagation=propagation,
            evidence=[record(DIAG/'FORCED_CHANGE_PROBE_SINGLE_BEST_ORIGINAL_MODEL_WITNESS.json'),record(DIAG/'FORCED_CHANGE_PROBE_SINGLE_BEST.json')])
        write_json(OUT/'KNOWN_B1_P2_IMPROVING_COUNTEREXAMPLE.json',oracle)
        singles=read(WORK/'FEASIBLE_SINGLE_MOVES.json');out={}
        for label,root in [('pre_early',OLD),('early',NEW)]:
            a0=root/DAY/'B1/dayahead/A0'
            hist=[(f,read(f)) for f in sorted((a0/'bounded_checkpoints').glob('ITERATION_*.json'),key=lambda x:int(x.stem.split('_')[1]))]
            p2=[(f,h) for f,h in hist if h['objective_stage']=='V41_SECONDARY_MIN_MEAN_H4_SHORTFALL']
            containing=[(f,h) for f,h in p2 if g in h['free_cohorts']]
            eligible=[]
            for f,h in p2:
                witnesses=[s for s in singles if d.uidgroup[s['uid']] in h['free_cohorts'] and s['delta_P2']< -1e-9]
                if witnesses:eligible.append((f,h,min(witnesses,key=lambda s:tuple(s['vector']))))
            assert not containing, 'Unexpected history requires exact known-neighborhood replay'
            f,h,w=eligible[0];p.reset(h['free_cohorts'])
            for lock in h['higher_priority_locks']:
                assert lock['name']=='PRIMARY_EXACT_VALUE_LOCK'
                p.temporary.append(p.m.addConstr(1000*p.rho<=lock['rhs'],name=lock['name']))
            p.m.setObjective(gp.quicksum(p.xi)/81);p.m.update()
            with np.load(h['artifact']['path']) as z:seed=z['values']
            assert np.array_equal(seed,p.seed)
            x,q=p.set_assignment({w['uid']:w['option_index']});audit=row_audit(p.m,x);assert audit['status']=='PASS'
            p.m.Params.MIPGap=.03;p.m.Params.MIPGapAbs=0;p.m.Params.SolutionLimit=GRB.MAXINT
            # These selected historical calls used the normal 60-second slice.
            p.m.Params.TimeLimit=60;p.m.setAttr('Start',p.vs,seed.tolist());p.m.Params.LogFile=str(OUT/(label+'_P2_REPLAY.log'))
            t=time.perf_counter();p.m.optimize();elapsed=time.perf_counter()-t
            raw=np.array(p.m.getAttr('X',p.vs));audit_raw=row_audit(p.m,raw);choices=p.decode(raw)
            known_x,_=p.set_assignment(known['choices'])
            chosen_vector=d.quick(choices)[0]['vector']
            out[label]=dict(known_job_group=g,known_job_in_any_historical_P2=False,known_exact_destination_in_any_P2=False,
                exact_known_P2_replay='NOT_APPLICABLE_NO_SUCH_HISTORICAL_NEIGHBORHOOD_EXISTS',
                P2_neighborhood_count=len(p2),all_P2_receipts=[record(f) for f,h in p2],
                alternate_valid_improvement=w,alternate_witness_audit=audit,actual_replayed_neighborhood=record(f),
                opened_groups=h['free_cohorts'],historical_locks=h['higher_priority_locks'],
                MIPGap=.03,TimeLimit=60,SolutionLimit=GRB.MAXINT,solver_status=int(p.m.Status),
                returned_P2=float(p.m.ObjVal),best_bound=float(p.m.ObjBound),gap=float(p.m.MIPGap),runtime=elapsed,
                independently_recomputed_vector=chosen_vector,raw_row_audit=audit_raw,
                historical_acceptance=h['accepted'],replay_lex_improved=tuple(chosen_vector)<tuple(d.base),
                known_decision_variables=[dict(name=p.names[i],LB=p.vs[i].LB,UB=p.vs[i].UB,Start=p.vs[i].Start,X=raw[i]) for i in p.groups[g] if p.seed[i] or known_x[i]],
                historical_time_limit_evidence='Original _solve min(60,stage available); selected first P2 normal block',
                limits='Exact algebra/bounds/seed and controls replay; solver internal presolve cache of historical long-lived model cannot be restored.')
            print('HISTORICAL_P2_REPLAY',label,out[label]['solver_status'],out[label]['returned_P2'],out[label]['gap'],flush=True)
        write_json(OUT/'OLD_FO_MISSED_IMPROVEMENT_REPLAY.json',dict(status='PASS',runs=out,
            known_counterexample_cause='NEIGHBORHOOD_COMPOSITION: JOB_NOT_OPENED_DURING_P2',
            conclusion='See replayed other-witness subproblems for independently observed gap termination; no fabricated known P2 neighborhood.',Actual_reads=0))
    finally:p.close();d.close()

if __name__=='__main__':run()
