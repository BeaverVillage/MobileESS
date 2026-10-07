"""Residual-directed physical-column rounds, each with original row closure."""
import gzip,pickle,traceback
from fractions import Fraction
from time import perf_counter
from dataclasses import asdict
import numpy as np
from v42_pr134_b1.common import read,record,atomic,table
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention,verify_zero,phase_objective
from v42_a_stage_phase1.backend import update_graph
from v42_a_stage_early.candidate import expanded_graph
from v42_a_stage_early.progress import capture,inclusion_witness
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.rowgen import restricted,certified_separate
from v42_a_stage_compact_rowgen.lift import expanded_point,full_artificial_point
from v42_a_stage_compact_rowgen.assembly import build,partition,compact_inverse
from v42_a_stage_compact_rowgen.resources import sample
from .policy import ROOT,OUT,STATIC
from .execution import verify
from .native import Native
from .targeted_pricing import targeted
from .attribution import analyze

def run():
    verify();budget=Budget();budget.remaining();native=Native(budget)
    if (OUT/'ADAPTIVE_STARTED.json').exists():raise PermissionError('ADAPTIVE_ALREADY_STARTED_NO_RESET')
    initial=read(OUT/'FROZEN64_RESULT.json')
    if not initial['row_closed'] or initial['certified_zero']:raise PermissionError('ADAPTIVE_REQUIRES_POSITIVE_ROW_CLOSED_FROZEN64')
    source=read(OUT/'BUILD_VERIFICATION.json')['state']
    with gzip.open(source['path'],'rb') as f:state=pickle.load(f)
    with gzip.open(read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/INITIAL_VERIFICATION.json')['state']['path'],'rb') as f:base=pickle.load(f)[0]
    closed=np.load(STATIC/'FROZEN64_CLOSED_POINT.npz');point=closed['X'].copy();rx=closed['expanded_X'].copy()
    rows=tuple(initial['included_rows']);rawrec=read(Path(initial['closed_master_folder'])/'NATIVE_RESULT.json')['raw_attributes']
    with np.load(rawrec['path']) as z:pi=np.zeros(state['compact'].matrix.shape[0]);pi[list(rows)]=z['Pi']
    current_phi=Fraction(initial['exact_Phi_after']);stagnation=1 if initial['reduction']<.01 else 0
    traces=[];candidates=[c for m in state['metas'].values() for c in m['candidates']];round_number=0;global_rows=set(i for i in rows if i<len(state['grows']))
    atomic(OUT/'ADAPTIVE_STARTED.json',dict(PASS=True,deadline=budget.record,first_frozen64_certificate=initial['closure_certificate'],budget_resets=0))
    result=dict(stage='A3_ADAPTIVE_PHASE1',certified_zero=False,classification=None,stagnation_consecutive_rounds=stagnation,activation_rounds=1,
        activated_STAY=32,activated_migration=32,pricing_rounds=0,master_solves=0)
    try:
        while stagnation<3:
            budget.remaining();folder=OUT/'M19/ADAPTIVE'/('R'+str(round_number));folder.mkdir(parents=True,exist_ok=True)
            s=state['compact'];full=elastic_master(s,state['grows'],weights_by_row=state['row_weights']);local,owned=partition(s,state['metas'],state['grows'])
            atlas=dict(state['atlas'],domains=state['domains']);attr,effect,baseline=analyze(full,dict(X=point),state['data'],state['axes'],owned,atlas,folder)
            memory=sample();atomic(folder/'WORKER_RESOURCE_DECISION.json',dict(PASS=not memory['unsafe'],system=memory,workers=1,maximum=4,M_lane_untouched=True))
            if memory['unsafe']:raise RuntimeError('MEASURED_SYSTEM_MEMORY_UNSAFE_AT_MINIMUM_ONE_WORKER')
            priced,selected=targeted(native,None,1,s,full,dict(X=point,Pi=pi),state['data'],state['domains'],state['ledger'],state['axes'],local,owned,
                attr['target_classes'],effect,baseline,folder/'PRICE')
            result['pricing_rounds']+=1
            if not selected:
                remaining=[r['class_id'] for r in attr['classes_ranked'] if r['inactive_candidates_available'] and r['class_id'] not in attr['target_classes']]
                if remaining:
                    priced,selected=targeted(native,None,1,s,full,dict(X=point,Pi=pi),state['data'],state['domains'],state['ledger'],state['axes'],local,owned,
                        remaining,effect,baseline,folder/'REMAINING_PRICE')
                    result['pricing_rounds']+=1
                if not selected:raise RuntimeError('FULL_PHYSICAL_QUERY_RECOVERY_EXHAUSTED_WITHOUT_ADMISSIBLE_NEGATIVE_CONCRETE_COLUMN')
            data=state['data'];ledger=state['ledger']
            for c in selected:
                uid=data[7]['classes'][c['class_id']][0];graph=expanded_graph(data[5][uid],c['option'],data[1][uid],state['domains'][uid],uid in data[7]['preserve_singleton_mixed_flow'])
                data,ledger=update_graph(data,state['domains'],c['class_id'],graph)
                candidates.append(dict(c,option=asdict(c['option']),price=str(c['price'])))
            oldmaster=elastic_master(state['reference'],state['grows'],weights_by_row=state['row_weights'])
            prior=capture(state['reference'],state['reference_descriptor'],oldmaster,dict(X=rx))
            nxt=build(base,state['grows'],state['n'],state['axes'],data,state['domains'],ledger,candidates)
            nxt.update(row_weights=state['row_weights'],atlas=state['atlas'])
            refmaster=elastic_master(nxt['reference'],nxt['grows'],weights_by_row=nxt['row_weights'])
            witness,mapped=inclusion_witness(prior,nxt['reference'],nxt['reference_descriptor'],refmaster,nxt['n'])
            if not witness['PASS']:raise ValueError('PREVIOUS_FEASIBLE_PHASE1_POINT_INCLUSION_FAIL')
            inverse=compact_inverse(nxt,mapped[:nxt['reference'].matrix.shape[1]])
            nextfull=elastic_master(nxt['compact'],nxt['grows'],weights_by_row=nxt['row_weights']);oldpoint=np.r_[inverse,mapped[nxt['reference'].matrix.shape[1]:]]
            if not primal_replay(nextfull.snapshot,oldpoint)['PASS'] or phase_objective(nextfull,oldpoint)!=current_phi:raise ValueError('PREVIOUS_SAME_PHI_COMPACT_INCLUSION_FAIL')
            atomic(folder/'INCLUSION_WITNESS.json',dict(PASS=True,original=witness,exact_preserved_Phi=str(current_phi),raw_increase_not_real_worsening=True))
            included=global_rows|set(range(len(nxt['grows']),nxt['compact'].matrix.shape[0]))
            for separation_round in range(1000000):
                budget.remaining();rows=tuple(sorted(included));r=restricted(nxt['compact'],rows)
                master=elastic_master(r,tuple(j for j,i in enumerate(rows) if i<len(nxt['grows'])),
                    weights_by_row={j:nxt['row_weights'][i] for j,i in enumerate(rows) if i<len(nxt['grows'])})
                solvefolder=folder/('S'+str(separation_round));rec,raw=native.solve(master.snapshot,solvefolder,'PHASE_I');result['master_solves']+=1
                if rec['status']!=2:raise RuntimeError('ADAPTIVE_MASTER_NOT_OPTIMAL:'+str(rec['status']))
                sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC']);replay=primal_replay(master.snapshot,raw['X'])
                if not sign['PASS'] or not replay['PASS']:raise ValueError('ADAPTIVE_RAW_REPLAY_FAIL')
                phi=phase_objective(master,raw['X']);sep=certified_separate(nxt['compact'],raw['X'][:nxt['compact'].matrix.shape[1]],included)
                atomic(solvefolder/'RAW_REPLAY.json',dict(PASS=True,Phi=str(phi),primal=replay,sign=sign));atomic(solvefolder/'ROW_SEPARATION.json',sep)
                traces.append(dict(round=round_number,solve=separation_round,Phi=float(phi),exact_Phi=str(phi),row_closed=sep['PASS'],rows=master.snapshot.matrix.shape[0],
                    cols=master.snapshot.matrix.shape[1],nnz=master.snapshot.matrix.nnz,Runtime=rec['native_seconds'],Work=rec['Work'],added_rows=len(sep['violated_rows'])))
                table(OUT/'ADAPTIVE_PHASE1_TRACE.csv',traces,list(traces[0]));print('ADAPTIVE_ROWGEN',round_number,separation_round,float(phi),len(sep['violated_rows']),flush=True)
                if not sep['PASS']:included.update(sep['violated_rows']);continue
                point=full_artificial_point(nextfull,master,rows,raw['X'],nxt['compact'].matrix.shape[1]);expanded=expanded_point(nxt,point)
                rx=np.r_[expanded,point[nxt['compact'].matrix.shape[1]:]];replay_orig=primal_replay(refmaster.snapshot,rx)
                if not replay_orig['PASS'] or phase_objective(refmaster,rx)!=phi:raise ValueError('ADAPTIVE_ORIGINAL_FULL_ROW_REPLAY_FAIL')
                reduction=float((current_phi-phi)/abs(current_phi));stagnation=stagnation+1 if reduction<.01 else 0
                cert=dict(PASS=True,Phi=str(phi),row_closed=True,original_replay=replay_orig,zero=verify_zero(refmaster,rx),reduction=reduction)
                atomic(solvefolder/'ROW_CLOSED_CERTIFICATE.json',cert)
                pi=np.zeros(nxt['compact'].matrix.shape[0]);pi[list(rows)]=raw['Pi'];state=nxt;global_rows={i for i in rows if i<len(state['grows'])};current_phi=phi
                result.update(activation_rounds=result['activation_rounds']+1,activated_STAY=result['activated_STAY']+priced['selected_STAY'],
                    activated_migration=result['activated_migration']+priced['selected_migration'],stagnation_consecutive_rounds=stagnation,
                    certified_zero=cert['zero']['PASS'],exact_Phi_after=str(phi),certified_Phi_after=float(phi),closure_certificate=record(solvefolder/'ROW_CLOSED_CERTIFICATE.json'),included_rows=list(rows))
                break
            round_number+=1
            with gzip.open(STATIC/'ADAPTIVE_CHECKPOINT_STATE.pkl.gz','wb') as f:pickle.dump(state,f,protocol=5)
            np.savez_compressed(STATIC/'ADAPTIVE_CHECKPOINT_POINT.npz',X=point,expanded_X=rx,Pi=pi)
            result['state']=record(STATIC/'ADAPTIVE_CHECKPOINT_STATE.pkl.gz');atomic(OUT/'ADAPTIVE_PHASE1_RESULT.json',result)
            if result['certified_zero']:result['classification']='A3_ZERO_READY_A4';break
        if stagnation>=3:result['classification']='A_PHASE1_STAGNATION'
    except Exception as error:result.update(classification='A_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc())
    finally:
        result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),elapsed_wall_seconds=budget.accounted())
        atomic(OUT/'ADAPTIVE_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'ADAPTIVE_PHASE1_RESULT.json',result)
        print('ADAPTIVE_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
from pathlib import Path
if __name__=='__main__':run()
