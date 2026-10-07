from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace, asdict
from fractions import Fraction
from pathlib import Path
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic, read
from v42_a_stage_phase1.runner import load_cache, serial, projected_global_pi
from v42_a_stage_phase1.producer import price_snapshot
from v42_a_stage_phase1.oracle import corrected_certificate, true_objective
from v42_a_stage_phase1.core import primal_replay, verify_sign_convention
from .policy import OUT, HISTORY, POLICY, trigger
from .budget import Budget
from .native import Native, BudgetStop
from .candidate import recover

def worker_price(task):
    want,pi,folder,started,limit=task
    budget=Budget(started=started,native_limit=limit);native=Native(budget)
    cache=load_cache(want);full,B=cache['snapshot'],cache['B']
    if full.matrix.shape[1]==0:
        raw=dict(X=np.zeros(0),Pi=np.zeros(full.matrix.shape[0]))
        rec=None
    else:
        priced=price_snapshot(full,B,pi)
        rec,raw=native.solve(priced,folder,'LOCAL_PRICING')
        if rec['status']!=gp.GRB.OPTIMAL or not all(n in raw for n in ('X','Pi','RC')):
            return dict(PASS=False,error='LOCAL_PRICING_NOT_OPTIMAL',calls=native.calls,resources=native.resources)
        replay=primal_replay(priced,raw['X']);sign=verify_sign_convention(priced,raw['Pi'],raw['RC'])
        atomic(Path(folder)/'REPLAY.json',dict(PASS=replay['PASS'] and sign['PASS'],primal=replay,dual_sign=sign,raw_persisted_first=True))
        if not replay['PASS'] or not sign['PASS']:raise ValueError('LOCAL_RAW_REPLAY_FAIL')
    certificate=corrected_certificate(full,B,pi,raw['Pi'])
    return dict(PASS=certificate['PASS'],certificate=certificate,point=raw['X'],local_pi=raw['Pi'],
        calls=native.calls,resources=native.resources)

def partial(native,executor,workers,original,master,raw,data,domains,ledger,axes,local_rows,owned,folder,start_index=0,full_sweep=False):
    required={r['class_id']:r for r in read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    roster=sorted(required);order=roster if full_sweep else roster[start_index:]+roster[:start_index]
    pi=projected_global_pi(master,raw['Pi']) if master else np.asarray(raw['Pi']).copy()
    if not master:
        pi[(original.senses=='<') & (pi>0)]=0;pi[(original.senses=='>') & (pi<0)]=0
    coupling_pi=np.asarray([pi[row] for row in axes.values()]);epsilon=Fraction(POLICY['epsilon_price'])
    columns={key:[] for key in required}
    for j,key in owned.items():columns[key].append(j)
    for key in columns:columns[key].sort()
    receipts=[];negative=[];lookahead=0
    for wave_first in range(0,len(order),workers):
        native.remaining()
        if not full_sweep and trigger(len(negative),len(receipts)):break
        room=len(order)-wave_first if full_sweep else POLICY['fully_priced_class_trigger']-len(receipts)
        keys=order[wave_first:wave_first+min(workers,room)]
        if not keys:break
        limit=native.budget.reservation(len(keys))
        tasks=[(required[key],coupling_pi,str(Path(folder)/'B'/key[:12]),native.budget.started,limit) for key in keys]
        results=list(executor.map(worker_price,tasks)) if executor else [worker_price(t) for t in tasks]
        # Consume in class order, independently of completion order. Every
        # actually launched solve (including unused lookahead) is charged.
        for response in results:
            for call in response['calls']:
                native.calls.append(call);native.native_seconds+=call['native_seconds'] or 0
                native.budget.charge(call['native_seconds'] or 0)
            native.resources.extend(response['resources'])
        for key,response in zip(keys,results):
            if not full_sweep and trigger(len(negative),len(receipts)):
                lookahead+=1;continue
            if not response['PASS']:raise BudgetStop(response.get('error','LOCAL_EXACT_CERTIFICATE_FAIL'))
            cache=load_cache(required[key]);cache['coupling_axes']=tuple(axes)
            cols=columns[key];rows=list(local_rows.get(key,()))
            active=replace(original,matrix=original.matrix[rows][:,cols].tocsr(),lower=original.lower[cols],upper=original.upper[cols],
                senses=original.senses[rows],rhs=original.rhs[rows],vtypes=np.full(len(cols),'C'),objectives=cache['snapshot'].objectives)
            AB=original.matrix[list(axes.values())][:,cols].tocsr()
            current=corrected_certificate(active,AB,coupling_pi,pi[rows])
            if not current['PASS']:raise ValueError('ACTIVE_LOCAL_DUAL_FAIL')
            cert=corrected_certificate(cache['snapshot'],cache['B'],coupling_pi,response['local_pi'])
            if cert!=response['certificate']:raise ValueError('INDEPENDENT_BLOCK_CERTIFICATE_MISMATCH')
            active_price=true_objective(AB,coupling_pi,raw['X'][cols])
            delta=Fraction(cert['exact_lower_bound'])-active_price
            point_delta=true_objective(cache['B'],coupling_pi,response['point'])-Fraction(current['exact_lower_bound'])
            candidate=recover(cache,data,domains,ledger,key,coupling_pi,current['exact_lower_bound'],response['point'],epsilon,native.budget)
            if candidate:
                if not candidate['price'] < -epsilon:raise ValueError('NONNEGATIVE_COLUMN_ACTIVATION')
                negative.append(candidate)
            receipt=dict(class_id=key,complete_STAY=required[key]['full_physical_STAY'],complete_migration=required[key]['full_physical_migration'],
                minimum_rc_lower_bound=str(delta),block_point_rc=str(point_delta),certificate=cert,
                active_local_lower_bound=current['exact_lower_bound'],global_coupling_pi=tuple(map(float,coupling_pi)),
                local_raw_pi=tuple(map(float,response['local_pi'])),
                status='VALID_NEGATIVE_CONCRETE_COLUMN' if candidate else 'NEGATIVE_BLOCK_UNMATERIALIZED' if point_delta < -epsilon else 'NO_CONCRETE_NEGATIVE_RECOVERED',
                candidate=None if candidate is None else dict(candidate,option=asdict(candidate['option']),price=str(candidate['price'])))
            receipts.append(receipt)
            atomic(Path(folder)/'B'/key[:12]/'EXACT_PRICING.json',serial(receipt))
            atomic(Path(folder)/'BATCH_PROGRESS.json',dict(fully_priced_classes=len(receipts),valid_negative_columns=len(negative),lookahead_priced=lookahead))
            print('EARLY_PRICED',len(receipts),len(negative),key[:12],receipt['status'],flush=True)
    next_index=(roster.index(receipts[-1]['class_id'])+1)%len(roster) if receipts else start_index
    result=dict(fully_priced_classes=len(receipts),valid_negative_columns=len(negative),lookahead_priced=lookahead,
        trigger='16_VALID_NEGATIVES' if len(negative)>=16 else '24_FULLY_PRICED_CLASSES' if len(receipts)>=24 and not full_sweep else 'END_OF_ROSTER',
        next_index=next_index,partial=not full_sweep,full_150_coverage=len(receipts)==150,
        negative_blocks_unmaterialized=sum(r['status']=='NEGATIVE_BLOCK_UNMATERIALIZED' for r in receipts),
        class_ids=[r['class_id'] for r in receipts],receipts=receipts)
    atomic(Path(folder)/'PRICING_RESULT.json',serial(result))
    return result,negative
