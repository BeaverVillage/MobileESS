"""Replay historical F&O bounds in the actual unmodified Gurobi MPS."""
import hashlib
import time
import numpy as np
from collections import Counter
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT, OLD, NEW, DAY, A0
from .flex_model import Data, ProbeModel
from .feasible_seed import row_audit


def run():
    d=Data();p=ProbeModel(d)
    try:
        seed_audit=row_audit(p.m,p.seed)
        assert seed_audit['status']=='PASS'
        outputs={}
        for label,root in [('pre_early',OLD),('early',NEW)]:
            stage=root/DAY/'B1/dayahead/A0'
            history=sorted((stage/'bounded_checkpoints').glob('ITERATION_*.json'),key=lambda q:int(q.stem.split('_')[1]))
            counts=Counter();receipts=[];samples=[];visited=set();variables=set()
            for path in history:
                h=read(path);opened=set(h['free_cohorts']);p.reset(opened)
                ids=np.array([i for g in sorted(opened) for i in p.groups[g]],dtype=int)
                vv=[p.vs[i] for i in ids]
                lbs=np.array(p.m.getAttr('LB',vv));ubs=np.array(p.m.getAttr('UB',vv));starts=p.m.getAttr('Start',vv)
                original_ok=np.array_equal(lbs,p.lb[ids]) and np.array_equal(ubs,p.ub[ids])
                assert original_ok and len(ids)==h['free_discrete_variable_count']
                non_singleton=(ubs>lbs)
                visited.update(opened);variables.update(ids.tolist())
                counts['visited_candidate_occurrences']+=h['free_candidate_count']
                counts['bound_open_variable_occurrences']+=int(non_singleton.sum())
                counts['explicitly_fixed_opened_variable_occurrences']+=int((~non_singleton).sum())
                p5=h['objective_stage']=='QUATERNARY_STABLE_TIE'
                if p5:counts['candidate_occurrences_implicitly_fixed_by_P3_P4_zero_locks']+=h['free_candidate_count']
                packed=np.column_stack([ids,lbs,ubs])
                receipt=dict(iteration=h['iteration'],stage=h['objective_stage'],historical_receipt=record(path),
                    original_bounds_restored=original_ok,visited_candidates=h['free_candidate_count'],
                    actual_bound_open_variables=int(non_singleton.sum()),actual_bound_fixed_variables=int((~non_singleton).sum()),
                    bound_replay_SHA256=hashlib.sha256(packed.tobytes()).hexdigest(),
                    upper_objective_locks=h['higher_priority_locks'],
                    implicit_fixing='ALL_NON_B0_CHOICES_EXCLUDED_BY_REQUIRED_P3_P4_ZERO_LOCKS' if p5 else 'REQUIRES_FEASIBLE_ALTERNATIVE_WITNESS; NOT_INFERRED_FROM_BOUNDS')
                receipts.append(receipt)
                if len(samples)<30:
                    for ii,i in enumerate(ids):
                        kind,g,tail=p.varparts[i];uid=d.cohorts[g]['members'][0];r=d.byuid[uid]
                        if kind not in ('choice','placement','migration_route','migration_arrival'):continue
                        if p.seed[i]>0:continue
                        if len(samples)>=30:break
                        if sum(x['kind']==kind for x in samples)>=8:continue
                        samples.append(dict(neighborhood=h['neighborhood_id'],kind=kind,variable=p.names[i],
                            type=p.vs[i].VType,LB=float(lbs[ii]),UB=float(ubs[ii]),Start=float(starts[ii]),
                            incumbent=float(p.seed[i]),explicitly_fixed_by_FO=bool(lbs[ii]==ubs[ii]),
                            implicit_fixed='NOT_YET_CERTIFIED',job=uid,source_IDC=r['AIDC_site'],
                            destination_encoding=tail,incumbent_source='HASHED_HISTORICAL_COMPLETE_CHECKPOINT'))
            total=sum(len(d.opts[d.cohorts[g]['members'][0]])*len(d.cohorts[g]['members']) for g in visited)
            outputs[label]=dict(counts=dict(counts),visited_unique_candidates=total,
                bound_open_unique_variables=len(variables),neighborhoods=receipts,representatives=samples,
                evidence_scope='ACTUAL_MPS_BOUND_REPLAY_USING_HASHED_HISTORICAL_SOURCE_AND_OPENED_GROUPS; NOT_RETROSPECTIVE_LIVE_OBSERVATION')
            print('BOUND_REPLAY_FINISHED',label,len(receipts),total,dict(counts),flush=True)
        result=dict(status='PASS',unfixing_defect_detected=False,original_model_seed_audit=seed_audit,
            production_runs=outputs,actually_free_definition='TWO_ADMISSIBLE_VALUES_REQUIRE_FEASIBLE_WITNESS; NONSINGLETON_BOUNDS_ALONE_ARE_NOT_SUFFICIENT',
            P5_implicit_fixing='Required lexicographic P3=0 and P4=0 constraints, not missing F&O unfixing.',
            full_MPS=record(A0/'PRIMARY_MODEL.mps.gz'),Actual_reads=0)
        write_json(OUT/'B1_VARIABLE_ACTIVATION_AUDIT.json',result)
    finally:p.close();d.close()


if __name__=='__main__':run()
