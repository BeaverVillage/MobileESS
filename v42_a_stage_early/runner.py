from fractions import Fraction
from pathlib import Path
from time import perf_counter
from concurrent.futures import ProcessPoolExecutor
import gzip,pickle,traceback
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,table
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention,verify_zero,phase_objective,interval_box_bound
from v42_a_stage_phase1.backend import assemble_original,update_graph
from v42_a_stage_phase1.runner import serial
from v42_a_stage_phase1.producer import native_block
from .policy import OUT,STATIC,DAY,POLICY,stagnated
from .budget import Budget
from .native import Native,BudgetStop
from .execution import verify
from .candidate import expanded_graph,point_for_option,exact_coupling
from .pricing import partial
from .progress import capture,inclusion_witness

def csv(path,rows,defaults):
    table(path,rows,sorted(set().union(*(r.keys() for r in rows))) if rows else defaults)

def activate(state,negative,iteration,folder,activations):
    base,descriptor,data,domains,ledger,base_axes,n,grows,local_rows,owned=state
    proposed=data;newledger=ledger;selected=sorted(negative,key=lambda c:(c['price'],c['identity']))[:16]
    for c in selected:
        uid=data[7]['classes'][c['class_id']][0]
        graph=expanded_graph(proposed[5][uid],c['option'],data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
        block,B,constant,units=native_block(proposed,c['class_id'],graph,tuple(base_axes),averaged=False)
        target=dict(snapshot=block,B=B,graph=graph,units=units)
        concrete=point_for_option(target,data[1][uid],data[3],c['option'],c['cardinality'])
        replay=primal_replay(block,concrete)
        if not replay['PASS'] or exact_coupling(B,concrete)!={r:Fraction(v) for r,v in c['coupling']}:
            raise ValueError('TARGET_ORIGINAL_NATIVE_CANDIDATE_REPLAY_FAIL')
        proposed,newledger=update_graph(proposed,domains,c['class_id'],graph)
    counts=newledger['receipt']
    if counts['active_STAY'] > .5*counts['physical_STAY'] or counts['active_migration']>2000000:
        atomic(folder/'EXPANSION_STOP.json',dict(counts=counts,committed=False))
        raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
    new,desc,global_rows,lrows,owners,axes=assemble_original(base,grows,n,base_axes,proposed)
    if new.matrix.shape[1]>200000 or new.matrix.shape[1]-activate.previous_cols>10000:
        atomic(folder/'EXPANSION_STOP.json',dict(rows=new.matrix.shape[0],cols=new.matrix.shape[1],nnz=new.matrix.nnz,committed=False))
        raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
    for c in selected:
        activations.append(dict(iteration=iteration,class_id=c['class_id'],candidate_id=c['candidate_id'],kind=c['kind'],
            option=repr(c['option']),exact_reduced_cost=str(c['price']),coefficient_sha256=c['coefficient_sha256'],cardinality=c['cardinality'],
            native_local_PASS=True,physical_membership_PASS=True,exact_coupling_PASS=True,independent_rc_PASS=True))
    return proposed,newledger,new,desc,global_rows,lrows,owners,axes

def closure(original,raw,grows,axes,n,pricing):
    pi=np.asarray(raw['Pi']).copy();pi[(original.senses=='<')&(pi>0)]=0;pi[(original.senses=='>')&(pi<0)]=0
    c=np.zeros(n)
    for j,v in original.objective('rho').coefficients().items():
        if j<n:c[j]=float(v)
    lower=interval_box_bound(original.matrix[list(grows),:n],c,pi[list(grows)],original.lower[:n],original.upper[:n],original.rhs[list(grows)])
    if lower is not None:lower+=sum((Fraction(r['certificate']['exact_lower_bound']) for r in pricing['receipts']),Fraction(0))
    upper=sum((v*Fraction(float(raw['X'][j])) for j,v in original.objective('rho').coefficients().items()),Fraction(original.objective('rho').constant))
    gap=None if lower is None else upper-lower
    eps=Fraction(POLICY['epsilon_price'])
    return dict(PASS=pricing['full_150_coverage'] and all(Fraction(r['minimum_rc_lower_bound'])>=-eps for r in pricing['receipts']) and gap is not None and 0<=gap<=eps,
        full_150_coverage=pricing['full_150_coverage'],all_STAY_migration_mixed_fractional=True,
        exact_lower_bound=None if lower is None else str(lower),active_upper=str(upper),gap=None if gap is None else str(gap),INTEGER_DOMAIN_CLOSURE_PROVEN=False)

def run():
    verify()
    if (OUT/'RUN_STARTED.json').exists():raise PermissionError('EARLY_NO_AUTOMATIC_RERUN_OR_RESET')
    if record(STATIC/'INITIAL_STATE.pkl.gz')!=read(OUT/'INITIAL_VERIFICATION.json')['state']:
        raise PermissionError('INITIAL_STATIC_STATE_BYTE_DRIFT')
    with gzip.open(STATIC/'INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
    base,descriptor,data,domains,ledger,base_axes,n,grows,local_rows,owned=state
    original=base;axes=base_axes;global_rows=grows
    master=elastic_master(base,grows)
    frozen={r:w for r,w in zip(master.artificial_rows,master.weights)}
    old=read(OUT/'INITIAL_VERIFICATION.json')
    if master.snapshot.fingerprint()!=old['phase1_snapshot_sha256']:raise PermissionError('INITIAL_PHASE1_IDENTITY_DRIFT')
    budget=Budget();native=Native(budget)
    atomic(OUT/'RUN_STARTED.json',dict(day=DAY,source_freeze=record(OUT/'SOURCE_FREEZE.json'),budget=900,no_resets=True))
    workers=read(OUT/'PARALLEL_PRICING_EQUIVALENCE.json')['selected_workers']
    executor=ProcessPoolExecutor(max_workers=workers) if workers>1 else None
    traces=[];activations=[];batches=[];sizes=[];relative=[];cursor=0;prior=None
    result=dict(day=DAY,classification=None,ACTIVE_DOMAIN_FEASIBLE=False,LP_PRICING_CLOSED=False,
        INTEGER_DOMAIN_CLOSURE_PROVEN=False,PRODUCTION_ACCEPTED=False,initial_phi=None,phase1_master_solves=0,
        time_to_zero=None,permanent_scientific_candidate_deletions=0,physics_or_tolerance_changed=False,
        forbidden_dates_or_pipeline_run=False,source_commit=read(OUT/'SOURCE_FREEZE.json')['git_head'])
    p1result=dict(status='NOT_AUTHORIZED_THIS_TASK_STOP_AT_ZERO',PASS=False)
    finalclosure=dict(PASS=False,status='NOT_AUTHORIZED_THIS_TASK',full_150_coverage=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False)
    try:
        for iteration in range(12):
            folder=OUT/'M19'/('R'+str(iteration));folder.mkdir(parents=True,exist_ok=True)
            budget.remaining();counts=ledger['receipt']
            sizes.append(dict(iteration=iteration,stage='PHASE_I',original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz,
                auxiliary_rows=master.snapshot.matrix.shape[0],auxiliary_cols=master.snapshot.matrix.shape[1],auxiliary_nnz=master.snapshot.matrix.nnz,
                active_STAY=counts['active_STAY'],active_migration=counts['active_migration']))
            if (master.snapshot.matrix.shape[0]>=4417827/2 or master.snapshot.matrix.shape[1]>=4316192/2 or master.snapshot.matrix.nnz>=49651657/2):
                raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
            rec,raw=native.solve(master.snapshot,folder,'PHASE_I');result['phase1_master_solves']+=1
            if rec['status']!=gp.GRB.OPTIMAL or not all(k in raw for k in ('X','Pi','RC')):raise BudgetStop('PHASE1_MASTER_NOT_OPTIMAL')
            sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC']);replay=primal_replay(master.snapshot,raw['X'])
            phi=float(phase_objective(master,raw['X']));zero=verify_zero(master,raw['X'])
            atomic(folder/'RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],sign=sign,primal=replay,zero=zero,Phi=str(phase_objective(master,raw['X'])),raw_persisted_first=True))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('PHASE1_RAW_REPLAY_FAIL')
            previous=traces[-1]['Phi'] if traces else None
            decrease=None if previous is None else previous-phi
            rel=None if previous is None else decrease/max(abs(previous),1e-30)
            if rel is not None:relative.append(rel)
            traces.append(dict(iteration=iteration,Phi=phi,exact_Phi=str(phase_objective(master,raw['X'])),delta_Phi=decrease,
                relative_decrease=rel,monotone=previous is None or phi<=previous+1e-8,native_seconds=rec['native_seconds'],
                elapsed_wall=perf_counter()-budget.started,factor_nnz=rec['max_factor_nnz'],factor_memory_GB=rec['max_factor_memory_GB'],RSS=rec['peak_RSS_bytes']))
            if result['initial_phi'] is None:result['initial_phi']=phi
            csv(OUT/'PHASE1_ITERATION_TRACE.csv',traces,['iteration','Phi'])
            print('EARLY_PHASE',iteration,phi,flush=True)
            if previous is not None and phi>previous+1e-8:
                budget.remaining()
                witness,mapped=inclusion_witness(prior,original,descriptor,master,n)
                point_path=STATIC/folder.relative_to(OUT)/'PRIOR_POINT_WITNESS.npz'
                np.savez_compressed(point_path,X=mapped)
                atomic(folder/'MONOTONICITY_INVESTIGATION.json',dict(previous=previous,current=phi,replay=replay,
                    witness=witness,separate_point=record(point_path),stop=not witness['PASS'],
                    native_raw_Phi_not_replaced=True,numerical_degeneracy_investigated=True))
                if not witness['PASS']:raise BudgetStop('MATERIAL_PHI_INCREASE_INVESTIGATION')
            if (rec['max_factor_nnz'] or 0)>250000000 or (rec['max_factor_memory_GB'] or 0)>2:
                raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
            if zero['PASS']:
                result['ACTIVE_DOMAIN_FEASIBLE']=True;result['time_to_zero']=perf_counter()-budget.started
                result['classification']='PHASE1_EARLY_ACTIVATION_ACCEPTED'
                # Original artificial-free replay is included in verify_zero;
                # no full sweep is performed during Phase I.
                atomic(folder/'ARTIFICIAL_FREE_ORIGINAL_VERIFICATION.json',zero)
                break
            scanned_classes=set();negative=[];price_folder=folder
            while not negative and len(scanned_classes)<150:
                priced,negative=partial(native,executor,workers,original,master,raw,data,domains,ledger,axes,local_rows,owned,price_folder,cursor,max_classes=150-len(scanned_classes))
                batches.append(dict(stage='PHASE_I',iteration=iteration,**{k:v for k,v in priced.items() if k not in ('receipts','class_ids')}))
                cursor=priced['next_index'];scanned_classes.update(priced['class_ids'])
                price_folder=folder/('Q'+str(len(batches)))
            if stagnated(relative,len(negative)):
                result['classification']='PHASE1_ACTIVATION_STAGNATION';break
            if not negative:raise BudgetStop('BOUNDED_PRICING_NO_CONCRETE_COLUMN_RECOVERED')
            if iteration==11:raise BudgetStop('TWELVE_PHASE1_MASTERS_LIMIT')
            activate.previous_cols=original.matrix.shape[1]
            prior=capture(original,descriptor,master,raw)
            currentstate=(base,descriptor,data,domains,ledger,base_axes,n,grows,local_rows,owned)
            data,ledger,original,descriptor,global_rows,local_rows,owned,axes=activate(currentstate,negative,iteration,folder,activations)
            master=elastic_master(original,global_rows,weights_by_row={i:frozen[r] for i,r in enumerate(grows)})
            csv(OUT/'ACTIVATED_COLUMNS.csv',activations,['iteration','candidate_id'])
            print('EARLY_ACTIVATED',iteration,len(negative),original.matrix.shape,original.matrix.nnz,flush=True)
    except BudgetStop as error:
        result['stop_reason']=str(error)
        if 'DOMAIN_EXPANSION_TOO_LARGE' in str(error):result['classification']='PHASE1_DOMAIN_EXPANSION_TOO_LARGE'
        elif not result['ACTIVE_DOMAIN_FEASIBLE']:
            reduction=0 if not traces or not result['initial_phi'] else (result['initial_phi']-traces[-1]['Phi'])/result['initial_phi']
            result['classification']='PHASE1_EARLY_ACTIVATION_PARTIAL_SUCCESS' if reduction>=.01 else 'PHASE1_TRACTABILITY_FAIL'
    except Exception as error:
        result['classification']='PHASE1_TRACTABILITY_FAIL';result['stop_reason']=repr(error);result['traceback']=traceback.format_exc()
    finally:
        if executor:executor.shutdown(wait=True,cancel_futures=True)
        result.update(final_phi=None if not traces else traces[-1]['Phi'],phase1_trajectory=[r['Phi'] for r in traces],
            valid_negative_columns=sum(r['valid_negative_columns'] for r in batches),activated_columns=len(activations),
            activated_STAY=sum(r['kind']=='STAY' for r in activations),activated_migration=sum(r['kind']=='MIGRATION' for r in activations),
            activation_rounds=len(set(r['iteration'] for r in activations)),stagnation=result['classification']=='PHASE1_ACTIVATION_STAGNATION',
            scientific_status='PASS' if result['ACTIVE_DOMAIN_FEASIBLE'] else 'INCONCLUSIVE',
            partial_pricing_batches=len(batches),native_calls=len(native.calls),native_seconds=native.native_seconds,
            elapsed_wall_seconds=perf_counter()-budget.started,accounted_seconds=budget.accounted(),selected_workers=workers,
            final_original_model=dict(rows=original.matrix.shape[0],cols=original.matrix.shape[1],nnz=original.matrix.nnz),
            final_active_STAY=ledger['receipt']['active_STAY'],final_active_migration=ledger['receipt']['active_migration'],
            maximum_factor_nnz=max((c['max_factor_nnz'] or 0 for c in native.calls),default=0),
            maximum_factor_memory_GB=max((c['max_factor_memory_GB'] or 0 for c in native.calls),default=0))
        if result['classification'] is None:result['classification']='PHASE1_TRACTABILITY_FAIL'
        for name,rows,fields in [('PHASE1_ITERATION_TRACE',traces,['iteration','Phi']),('ACTIVATED_COLUMNS',activations,['iteration','candidate_id']),
            ('PRICING_BATCH_TRACE',batches,['iteration','fully_priced_classes']),('MODEL_SIZE_TRACE',sizes,['iteration','original_rows']),
            ('RESOURCE_TELEMETRY',native.resources,['wall_seconds','RSS'])]:csv(OUT/(name+'.csv'),rows,fields)
        atomic(OUT/'NATIVE_CALLS.json',dict(calls=native.calls,native_seconds=native.native_seconds))
        atomic(OUT/'PHASE1_RESULT.json',result);atomic(OUT/'ORIGINAL_P1_RESULT.json',p1result);atomic(OUT/'FINAL_PRICING_CLOSURE.json',finalclosure)
        print('EARLY_RESULT',result,flush=True)
    return result

if __name__=='__main__':run()
