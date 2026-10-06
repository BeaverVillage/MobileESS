"""Close out rejected RMP dual without new optimization or invented intervals."""
from v42_m_stage.common import *
from v42_dw_root.partition import axes
from v42_degen.identity import inputs
from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
from v42_dw_runtime.validation import OriginalBlockValidator
from v42_m_stage.guard import Guard
from fractions import Fraction as F
import numpy as np
import time
import re
from concurrent.futures import ThreadPoolExecutor

def union(intervals):
    merged=[]
    for a,b in sorted(intervals):
        assert a<=b
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    return sum(b-a for a,b in merged)

def run():
    assert not (OUT/'ROOT_RECOVERY_STARTED.json').exists(),'One read-only closeout'
    cp=read(OUT/'DW_CHECKPOINT_LATEST.json');journal=read(OUT/'DW_BUDGET_JOURNAL.json')
    assert cp['type']=='DISCOVERY_ADDED' and journal['round']==cp['RMP']['round']+1
    assert cp['RMP']['status']==2 and cp['RMP']['point_file']
    guard=Guard('ROOT_CLOSEOUT',[]);guard.gate();start=time.perf_counter();guard.start(float('inf'))
    write('ROOT_RECOVERY_STARTED.json',dict(native_calls=0,reason='RMP43 exact dual sign rejected; finalize could not select prior valid point',
        retained_pool=cp['total_retained_columns'],durable_debit=journal['elapsed_budget']))
    write('PRE_RECOVERY_CHECKPOINT.json',cp)
    try:
        known=union(cp['optimize_intervals']);assert abs(known-cp['elapsed_budget'])<1e-8
        debit=journal['elapsed_budget']-known;assert debit>0 and journal['elapsed_budget']<=1800
        runtime_log=(OUT/f"logs/RMP_{journal['round']:04d}.log").read_text(encoding='utf8')
        assert 'Optimal objective' in runtime_log
        native_rounded=float(re.search(r'Solved in .* iterations and ([\d.]+) seconds',runtime_log).group(1))
        assert abs(debit-native_rounded)<1
        budget=dict(PASS=True,total=journal['elapsed_budget'],known_interval_union=known,
            durable_unpersisted_RMP_debit=debit,native_log_runtime_rounded=native_rounded,
            debit_source='Durable DW_BUDGET_JOURNAL measured union after optimize returned',
            incomplete_interval_evidence=True,missing_RMP_start_end_not_invented=True,
            original_intervals=cp['optimize_intervals'],budget=1800,automatic_extension=False,native_calls_replayed=0)
        write('ROOT_BUDGET_RECOVERY_AUDIT.json',budget)
        A,d,B,e,*_=inputs();owner,row_owner=axes()
        from v42_dw_continuation.common import OLD
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names'].copy()
        blocks=prototypes(B,e,owner,row_owner,native);validators={}
        rr=[[] for _ in range(4)]
        for i in range(A.shape[0]):
            deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
            if len(deps)==1 and -1 not in deps:rr[next(iter(deps))].append(i)
        for m,b in enumerate(blocks):
            rows=np.asarray(rr[m]);cols=b.columns;matrix=A[rows][:,cols]
            attrs=dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],lower=d['lower'][cols],upper=d['upper'][cols],
                types=d['types'][cols],objective=d['objective'][cols],constant=np.array(0.))
            validators[m]=OriginalBlockValidator(m,b,matrix,attrs,pure_binary_equalities(matrix,attrs))
        point_file=OUT/cp['RMP']['point_file'];assert sha(point_file)==cp['RMP']['point_SHA']
        with np.load(point_file) as z:point=z['point'].copy();pi=z['pi'].copy();alpha=z['alpha'].copy();weights=z['lambda_values'].copy()
        key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();assert key==cp['RMP']['dual_SHA']
        assert len(weights)<len(cp['pool']);weights=np.pad(weights,(0,len(cp['pool'])-len(weights)))
        from v42_dw_root.run import exact_rc
        def audit(job):
            h,w=job;m=int(h['MESS'][-2:])-1;b=blocks[m];p=ROOT/h['file'];assert sha(p)==h['file_SHA']
            with np.load(p) as z:
                modern='x' in z;x=(z['x'] if modern else z['local_values']).copy()
                axis=z['axis'] if modern else z['original_columns'];stored=z['a'] if modern else z['master_coefficients']
                c=float(z['c'] if modern else z['objective'])
                assert np.array_equal(axis,b.columns)
                a,c2,column=b.column(x);assert column==h['column_SHA'] and c2==c and np.array_equal(a,stored)
            physical=validators[m].audit(x);assert physical['local_PASS'] and physical['physical_PASS'] and physical['integral']
            assert not guard.cancel.is_set()
            rc=float(exact_rc(b,x,pi,alpha[m]))
            return dict(SHA=column,MESS=h['MESS'],true_RC=rc,PASS=True,original_rows=physical['full_original_local'],
                max_residual=physical['max_residual'],zero_extension_weight=float(w)),m,x*float(w)
        reconstructed=np.zeros_like(point);reconstructed[owner<0]=point[owner<0];audited=[]
        with ThreadPoolExecutor(max_workers=4) as executor:
            for record,m,part in executor.map(audit,zip(cp['pool'],weights)):
                audited.append(record);reconstructed[blocks[m].columns]+=part
        assert np.max(abs(reconstructed-point),initial=0)<=1e-6
        raw=corrected_rows(A,d,reconstructed,False,pure_binary_equalities(A,d));assert raw['PASS']
        upper=float(d['objective']@reconstructed+d['constant']);assert abs(upper-cp['RMP']['objective'])<=1e-6
        full=dict(PASS=True,columns=len(audited),all_columns_freshly_audited=True,records=audited,
            true_dual_origin_RMP=cp['RMP']['round'],true_dual_SHA=key,full_original_primal=raw,
            primal_upper=upper,zero_extension_new_column_lambdas=True,latest_RMP_dual_accepted=False,
            original_matrix_unchanged=True,no_column_deletion=True,native_optimize_calls=0,
            wall_seconds=time.perf_counter()-start)
        write('DW_CONTINUATION_FULL_POOL_AUDIT.json',full);write('DW_FULL_POOL_FINAL_AUDIT.json',full)
        state=cp['restart_state'];state['accepted']=list(state['accepted'])
        pending=len(state['rounds'])<len(state['accepted'])
        if pending:
            state['rounds'].append(dict(discovery_round=len(state['accepted']),pricing_round=cp['RMP']['round'],
                post_RMP_round=journal['round'],columns_added=state['accepted'][-1],U_before=cp['best_interval'][1],
                U_after=None,RMP_native_status=2,RMP_dual_accepted=False,stop_reason='EXACT_RMP_DUAL_SIGN_REJECTED'))
        failed=dict(round=journal['round'],type='POST_DISCOVERY_TRUE_RMP',status=2,objective=None,
            dual_SHA=None,point_file=None,scientific_authority_accepted=False,
            native_seconds_measured_by_journal=debit,native_runtime_log_rounded=native_rounded,
            interval=None,reason='EXACT_RMP_DUAL_SIGN_REJECTED')
        state['rmps'].append(failed);write(f"RMP_RECEIPT_{journal['round']:04d}.json",failed)
        historical=read(OUT/'ROOT1604_RESUME_AUTHORITY.json')['historical_total_native']
        total_model=sum(b-a for a,b in cp['optimize_intervals'])+debit
        result=dict(status='M1_ROOT_NOT_CONVERGED',stop_reason='EXACT_RMP_DUAL_SIGN_REJECTED',
            retained_columns=cp['total_retained_columns'],initial_retained_columns=1604,
            new_RMP_solves=len(state['rmps']),audited_RMP_points=len(state['rmps'])-1,
            new_pricing_calls=len(state['prices']),discovery_rounds=len(state['accepted']),
            certification_rounds=len(state['certs']),smallest_RMP_upper=cp['best_interval'][1],
            best_certified_LB=cp['best_interval'][0],DW_ROOT_OPTIMAL_CERTIFIED=False,
            materiality='PROVEN_NONMATERIAL',new_authorized_optimize=1800,
            total_optimize_wall_union=journal['elapsed_budget'],sum_native_optimize_wall=total_model,
            cumulative_optimize=historical+journal['elapsed_budget'],
            build_seconds=read(OUT/'DW_INITIAL_POOL_AUDIT.json')['wall'],
            build_measurement='initial pool/audit restore wall; original constructor build-only timer not durably persisted',
            elapsed_including_build_audit=journal['elapsed_wall']+time.perf_counter()-start,
            elapsed_measurement='Durable pre-failure elapsed plus read-only closeout; gap between processes excluded',
            budget_exhausted=False,remaining_grant_unused=1800-journal['elapsed_budget'],
            automatic_extension=False,failed_native_point_not_used=True,pricing_backend_changed=False)
        write('DW_CONTINUATION_FINAL_RESULT.json',result)
        last=state['certs'][-1]
        write('DW_CONTINUATION_FINAL_CERTIFICATION.json',dict(status='COMPLETED',certificate=last,
            true_dual_origin_RMP=last['true_dual_origin_RMP'],latest_rejected_RMP_not_certified=True))
        cp.update(type='TERMINAL',elapsed_budget=journal['elapsed_budget'],elapsed_wall=result['elapsed_including_build_audit'],
            restart_state=state,budget_recovery=budget,stop_reason=result['stop_reason'],certificate=last,
            cumulative_optimize=result['cumulative_optimize'],source_algorithm_unchanged=True)
        write('DW_CHECKPOINT_LATEST.json',cp);write('DW_CONTINUATION_LATEST_CHECKPOINT.json',cp)
        (OUT/'DW_INFLIGHT.json').unlink(missing_ok=True)
        write('ROOT_RECOVERY_RECEIPT.json',dict(PASS=True,algorithm_changed=False,new_optimize_calls=0,
            completed_calls_replayed=False,new_grant_created=False,source_SHA=sha(ROOT/'recover_m_stage.py'),
            stop='EXACT_RMP_DUAL_SIGN_REJECTED',accepted_RMP=cp['RMP']['round'],rejected_RMP=journal['round']))
        print('ROOT_RECOVERY_PASS',cp['total_retained_columns'],journal['elapsed_budget'],flush=True)
    finally:guard.close()

if __name__=='__main__':run()
