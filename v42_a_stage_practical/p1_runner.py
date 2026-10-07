"""Artificial-free P1: row closure and complete full-native column pricing."""
import gzip,pickle,traceback
from fractions import Fraction
from time import perf_counter
import numpy as np
from v42_pr134_b1.common import read,record,atomic,table
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_phase1.backend import update_graph
from v42_a_stage_early.progress import capture,inclusion_witness
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.rowgen import restricted,certified_separate
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_compact_rowgen.assembly import build,partition,compact_inverse
from .policy import ROOT,OUT,STATIC,HISTORY
from .native import Native
from .execution import verify
from .full_pricing import full_pricing

def objective(s,x):
    o=s.objective('rho');return o.constant+sum((c*Fraction(float(x[j])) for j,c in o.coefficients().items()),Fraction(0))

def run():
    verify();budget=Budget();budget.remaining();native=Native(budget)
    if (OUT/'P1_STARTED.json').exists():raise PermissionError('P1_ALREADY_STARTED_USE_CHECKPOINT_NO_RESET')
    z=read(OUT/'FROZEN64_RESULT.json')
    if not z.get('certified_zero'):z=read(OUT/'ADAPTIVE_PHASE1_RESULT.json')
    if not z.get('certified_zero'):raise PermissionError('CERTIFIED_ZERO_REQUIRED')
    source=read(OUT/'BUILD_VERIFICATION.json')['state'] if z.get('stage')=='A2_FROZEN64' else z['state']
    if record(source['path'])!=source:raise PermissionError('P1_STATE_BYTE_DRIFT')
    with gzip.open(source['path'],'rb') as f:state=pickle.load(f)
    original_initial=read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/INITIAL_VERIFICATION.json')
    with gzip.open(original_initial['state']['path'],'rb') as f:oldstate=pickle.load(f)
    base=oldstate[0];grows=state['grows'];n=state['n'];axes=state['axes'];included=set(z['included_rows'])
    candidate_list=[c for m in state['metas'].values() for c in m['candidates']]
    result=dict(stage='A4_ORIGINAL_P1_LP',P1_LP_closure=False,integer_domain_closure=False,valid_LB=None,valid_UB=None,certified_gap=None,
        integer_BNP_nodes=0,pricing_rounds=0,row_generation_solves=0,P2=None,canaries=None)
    traces=[];last_bound=None;activation_round=0
    atomic(OUT/'P1_STARTED.json',dict(PASS=True,zero_gate=z['closure_certificate'],source_freeze=record(OUT/'PRACTICAL_SOURCE_FREEZE.json'),deadline=budget.record))
    try:
        for iteration in range(1000000):
            budget.remaining();s=state['compact'];rows=tuple(sorted(included));r=restricted(s,rows)
            folder=OUT/'M19/P1'/('S'+str(iteration));folder.mkdir(parents=True,exist_ok=True)
            rec,raw=native.solve(r,folder,'ORIGINAL_P1');result['row_generation_solves']+=1
            if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise RuntimeError('ORIGINAL_P1_NATIVE_NOT_OPTIMAL:'+str(rec['status']))
            sign=verify_sign_convention(r,raw['Pi'],raw['RC']);replay=primal_replay(r,raw['X'])
            atomic(folder/'RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],sign=sign,primal=replay,original_objective=str(objective(s,raw['X'])),artificials=0))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('P1_RAW_REPLAY_FAIL')
            start=perf_counter();sep=certified_separate(s,raw['X'],included);sep['seconds']=perf_counter()-start;atomic(folder/'ROW_SEPARATION.json',sep)
            value=objective(s,raw['X'])
            trace=dict(solve=iteration,P1=float(value),exact_P1=str(value),row_closed=sep['PASS'],added_rows=len(sep['violated_rows']),
                rows=r.matrix.shape[0],cols=r.matrix.shape[1],nnz=r.matrix.nnz,Runtime=rec['native_seconds'],Work=rec['Work'],
                factor_nnz=rec['max_factor_nnz'],factor_memory_GB=rec['max_factor_memory_GB'],pricing_seconds=None,valid_LB=last_bound,integer_UB=None,global_gap=None)
            traces.append(trace);table(OUT/'P1_ITERATION_TRACE.csv',traces,list(traces[0]))
            print('P1_ROWGEN',iteration,float(value),len(sep['violated_rows']),flush=True)
            if (rec['max_factor_nnz'] or 0)>250000000 or (rec['max_factor_memory_GB'] or 0)>2:raise RuntimeError('MEASURED_P1_FACTOR_TRACTABILITY_LIMIT')
            if not sep['PASS']:included.update(sep['violated_rows']);continue
            expanded=expanded_point(state,raw['X']);replay_full=primal_replay(state['reference'],expanded)
            if not replay_full['PASS'] or objective(state['reference'],expanded)!=value:raise ValueError('ARTIFICIAL_FREE_FULL_ORIGINAL_P1_REPLAY_FAIL:'+str(replay_full))
            atomic(folder/'ORIGINAL_REPLAY.json',dict(PASS=True,original_replay=replay_full,exact_objective=str(value),artificials=0,integer_closure=False))
            pi=np.zeros(s.matrix.shape[0]);pi[list(rows)]=raw['Pi'];fullraw=dict(X=raw['X'],Pi=pi)
            local,owned=partition(s,state['metas'],grows)
            start=perf_counter();priced,negative=full_pricing(native,s,None,fullraw,None,state['data'],state['domains'],state['ledger'],axes,n,grows,local,owned,folder/'PRICE')
            trace['pricing_seconds']=perf_counter()-start;result['pricing_rounds']+=1
            if priced['full_domain_phase1_lower_bound'] is not None:
                b=Fraction(priced['full_domain_phase1_lower_bound']);last_bound=float(b);trace['valid_LB']=float(b)
                result['valid_LB']=float(b);result['exact_valid_LB']=str(b)
            table(OUT/'P1_ITERATION_TRACE.csv',traces,list(traces[0]))
            if priced['no_negative_omitted_block_certified']:
                point=STATIC/'P1_LP_CLOSED_POINT.npz';np.savez_compressed(point,X=raw['X'],expanded_X=expanded,Pi=pi)
                with gzip.open(STATIC/'P1_LP_CLOSED_STATE.pkl.gz','wb') as f:pickle.dump(state,f,protocol=5)
                result.update(P1_LP_closure=True,classification='A_ROWCOL_PHASE1_SUCCESS_BNP_PENDING',P1_LP_value=float(value),exact_P1_LP_value=str(value),
                    closed_point=record(point),state=record(STATIC/'P1_LP_CLOSED_STATE.pkl.gz'),closure_receipt=record(folder/'PRICE/FULL_PRICING_RESULT.json'),
                    included_rows=list(rows),activation_rounds=activation_round)
                break
            if not negative:raise ValueError('EXACT_PRICING_INTERVAL_UNRESOLVED_WITHOUT_VERIFIED_NEGATIVE_SUPPORT')
            selected=sorted(negative,key=lambda c:(c['price'],c['class_id'],c['support_sha256']))[:64]
            if all(c['graph'].sha==state['data'][5][state['data'][7]['classes'][c['class_id']][0]].sha for c in selected):raise ValueError('NEGATIVE_ORACLE_SUPPORT_ALREADY_ACTIVE_NUMERICAL_OBSTRUCTION')
            data=state['data'];ledger=state['ledger']
            for c in selected:data,ledger=update_graph(data,state['domains'],c['class_id'],c['graph'])
            previous_master=elastic_master(state['reference'],grows,weights_by_row=state['row_weights'])
            prior=capture(state['reference'],state['reference_descriptor'],previous_master,dict(X=np.r_[expanded,np.zeros(len(previous_master.artificial_rows))]))
            nextstate=build(base,grows,n,axes,data,state['domains'],ledger,candidate_list);nextstate['row_weights']=state['row_weights']
            nextmaster=elastic_master(nextstate['reference'],grows,weights_by_row=state['row_weights'])
            witness,mapped=inclusion_witness(prior,nextstate['reference'],nextstate['reference_descriptor'],nextmaster,n)
            if not witness['PASS']:raise ValueError('P1_PREVIOUS_FEASIBLE_POINT_INCLUSION_FAIL')
            inverse=compact_inverse(nextstate,mapped[:nextstate['reference'].matrix.shape[1]])
            if not primal_replay(nextstate['compact'],inverse)['PASS']:raise ValueError('P1_COMPACT_INVERSE_REPLAY_FAIL')
            atomic(folder/'ACTIVATION.json',dict(PASS=True,selected=[dict(class_id=c['class_id'],price=str(c['price']),support_sha256=c['support_sha256']) for c in selected],
                previous_point_inclusion=witness,LP_native_fractional_support=True,physical_integer_column_claim=False,candidate_deletions=0))
            retained_global={i for i in included if i<len(grows)};included=retained_global|set(range(len(grows),nextstate['compact'].matrix.shape[0]))
            state=nextstate;activation_round+=1
            with gzip.open(STATIC/'P1_CHECKPOINT_STATE.pkl.gz','wb') as f:pickle.dump(state,f,protocol=5)
            atomic(OUT/'P1_CHECKPOINT.json',dict(PASS=True,state=record(STATIC/'P1_CHECKPOINT_STATE.pkl.gz'),included_rows=sorted(included),deadline=budget.record,
                activation_rounds=activation_round,source_freeze=record(OUT/'PRACTICAL_SOURCE_FREEZE.json')))
    except Exception as error:result.update(classification='A_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc())
    finally:
        result.update(native_calls=len(native.calls),native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),elapsed_wall_seconds=budget.accounted(),
            peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'P1_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'P1_RESULT.json',result)
        print('P1_RESULT',result.get('classification'),result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
