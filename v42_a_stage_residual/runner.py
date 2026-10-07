"""One residual-directed experiment; at most two diversified batches."""
from pathlib import Path
from fractions import Fraction
from time import perf_counter
from concurrent.futures import ProcessPoolExecutor
import gzip,pickle,traceback
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,table
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention,verify_zero,phase_objective
from v42_a_stage_early.progress import capture,inclusion_witness
from .policy import OUT,STATIC,DAY,POLICY
from .budget import Budget
from .native import Native,BudgetStop
from .execution import verify
from .attribution import analyze
from .pricing import targeted
from .activation import activate

def csv(path,rows,fields):table(path,rows,sorted(set().union(*(r.keys() for r in rows))) if rows else fields)

def run():
    verify()
    if (OUT/'RUN_STARTED.json').exists():raise PermissionError('NO_AUTOMATIC_RERUN_OR_BUDGET_RESET')
    initial=read(OUT/'INITIAL_VERIFICATION.json');authority=read(OUT/'ROW_ATTRIBUTION_AUTHORITY.json')
    for r in (initial['state'],initial['historical_included_point'],authority['atlas'],initial['frozen_weights']):
        if record(r['path'])!=r:raise PermissionError('FROZEN_STATIC_BYTES_DRIFT')
    with gzip.open(initial['state']['path'],'rb') as f:state=pickle.load(f)
    base,desc,data,domains,ledger,base_axes,n,base_grows,lrows,owned=state
    weights=np.load(initial['frozen_weights']['path'])['weights'];row_weights={};cursor=0
    for row in base_grows:
        row_weights[row]=Fraction(float(weights[cursor]));cursor+=2 if base.senses[row]=='=' else 1
    original=base;axes=base_axes;grows=base_grows;master=elastic_master(original,grows,weights_by_row=row_weights)
    if master.snapshot.fingerprint()!=initial['phase1_snapshot_sha256']:raise PermissionError('INITIAL_PHASE1_MODEL_DRIFT')
    atlas={k:v for k,v in np.load(authority['atlas']['path']).items()};atlas['domains']=domains
    historical_X=np.load(initial['historical_included_point']['path'])['X']
    historical_prior=capture(original,desc,master,dict(X=historical_X))
    budget=Budget();native=Native(budget);workers=read(OUT/'PARALLEL_PRICING_EQUIVALENCE.json')['selected_workers']
    atomic(OUT/'RUN_STARTED.json',dict(day=DAY,budget=1200,no_resets=True,source_freeze=record(OUT/'SOURCE_FREEZE.json')))
    executor=ProcessPoolExecutor(max_workers=workers) if workers>1 else None
    result=dict(day=DAY,classification=None,scientific_status='INCONCLUSIVE',ACTIVE_DOMAIN_FEASIBLE=False,
        source_commit=read(OUT/'SOURCE_FREEZE.json')['git_head'],master_solves=0,activation_rounds=0,
        selected_workers=workers,negative_STAY=0,negative_migration=0,activated_STAY=0,activated_migration=0,
        no_P1=True,no_other_dates_or_production=True,permanent_candidate_deletions=0,physics_tolerances_weights_changed=False)
    traces=[];activations=[];batches=[];sizes=[];prior=historical_prior;prior_phi=None;pending_batch=None
    try:
        for iteration in range(3):
            budget.remaining();folder=OUT/'M19'/('R'+str(iteration));folder.mkdir(parents=True,exist_ok=True)
            counts=ledger['receipt']
            sizes.append(dict(iteration=iteration,original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz,
                auxiliary_rows=master.snapshot.matrix.shape[0],auxiliary_cols=master.snapshot.matrix.shape[1],auxiliary_nnz=master.snapshot.matrix.nnz,
                active_STAY=counts['active_STAY'],active_migration=counts['active_migration']))
            if master.snapshot.matrix.shape[0]>=4417827/2 or master.snapshot.matrix.shape[1]>=4316192/2 or master.snapshot.matrix.nnz>=49651657/2:
                raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
            rec,raw=native.solve(master.snapshot,folder,'PHASE_I');result['master_solves']+=1
            if rec['status']!=gp.GRB.OPTIMAL or not all(k in raw for k in ('X','Pi','RC')):
                result['classification']='PHASE1_NUMERICAL_INCONCLUSIVE' if rec['status'] not in (9,11) else 'PHASE1_TRACTABILITY_FAIL'
                result['stop_reason']='INITIAL_OR_RESOLVE_NOT_CERTIFIED_OPTIMAL';break
            sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC']);replay=primal_replay(master.snapshot,raw['X']);phi=phase_objective(master,raw['X']);zero=verify_zero(master,raw['X'])
            atomic(folder/'RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],sign=sign,primal=replay,zero=zero,Phi=str(phi),raw_persisted_first=True))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('PHASE1_CERTIFIED_RAW_REPLAY_FAIL')
            witness,mapped=inclusion_witness(prior,original,desc,master,n)
            if not witness['PASS']:raise ValueError('PRIOR_FEASIBLE_POINT_INCLUSION_FAIL')
            point=STATIC/folder.relative_to(OUT)/'PRIOR_POINT_WITNESS.npz';np.savez_compressed(point,X=mapped)
            atomic(folder/'INCLUSION_WITNESS.json',dict(witness=witness,separate_point=record(point),native_raw_Phi_not_replaced=True))
            if (rec['max_factor_nnz'] or 0)>250000000 or (rec['max_factor_memory_GB'] or 0)>2:
                raise BudgetStop('PHASE1_FACTOR_LIMIT')
            reduction=None if prior_phi is None else float((prior_phi-phi)/abs(prior_phi))
            traces.append(dict(iteration=iteration,Phi=float(phi),exact_Phi=str(phi),before_Phi=None if prior_phi is None else float(prior_phi),
                relative_Phi_reduction=reduction,native_seconds=rec['native_seconds'],Work=rec['Work'],elapsed_wall=perf_counter()-budget.started,
                factor_nnz=rec['max_factor_nnz'],factor_memory_GB=rec['max_factor_memory_GB'],prior_inclusion_PASS=True))
            csv(OUT/'PHASE1_ITERATION_TRACE.csv',traces,['iteration','Phi']);print('RESIDUAL_PHASE',iteration,float(phi),reduction,flush=True)
            if iteration==0:result['initial_phi']=float(phi)
            if pending_batch is not None:
                pending_batch.update(Phi_after=float(phi),relative_Phi_reduction=reduction,re_solved=True)
                atomic(OUT/'BATCH_DECISION_TRACE.json',dict(batches=batches))
            if zero['PASS']:
                atomic(folder/'ARTIFICIAL_FREE_ORIGINAL_VERIFICATION.json',zero)
                result.update(classification='PHASE1_RESIDUAL_DIRECTED_SUCCESS',scientific_status='PASS',ACTIVE_DOMAIN_FEASIBLE=True);break
            if iteration and reduction<POLICY['nonmaterial_gate_relative_reduction']:
                result.update(classification='PHASE1_RESIDUAL_DIRECTED_NONMATERIAL',stop_reason='DIVERSIFIED_BATCH_BELOW_ONE_PERCENT_STOP_ARCHITECTURE_DEVELOPMENT');break
            if iteration==2:
                result['classification']='PHASE1_RESIDUAL_DIRECTED_MATERIAL_PROGRESS';break
            budget.remaining()
            attribution,effect,baseline=analyze(master,raw,data,axes,owned,atlas,folder)
            pricefolder=folder/'TARGETED';priced,selected=targeted(native,executor,workers,original,master,raw,data,domains,ledger,axes,lrows,owned,
                attribution['target_classes'],effect,baseline,pricefolder)
            result['negative_STAY']+=priced['negative_STAY'];result['negative_migration']+=priced['negative_migration']
            if not selected:raise BudgetStop('NO_ADMISSIBLE_RESIDUAL_DIRECTED_CONCRETE_BATCH')
            prior=capture(original,desc,master,raw);prior_phi=phi
            pending_batch=dict(iteration=iteration,Phi_before=float(phi),batch_size=len(selected),STAY=priced['selected_STAY'],migration=priced['selected_migration'],
                targeted_migration_completed=True,re_solved=False,Phi_after=None,relative_Phi_reduction=None)
            batches.append(pending_batch);atomic(OUT/'BATCH_DECISION_TRACE.json',dict(batches=batches))
            activate.previous_cols=original.matrix.shape[1]
            currentstate=(base,desc,data,domains,ledger,base_axes,n,base_grows,lrows,owned)
            data,ledger,original,desc,grows,lrows,owned,axes=activate(currentstate,selected,iteration,folder,activations,budget)
            result['activation_rounds']+=1
            master=elastic_master(original,grows,weights_by_row=row_weights)
            csv(OUT/'ACTIVATED_COLUMNS.csv',activations,['iteration','candidate_id'])
            print('RESIDUAL_ACTIVATED',iteration,len(selected),pending_batch['STAY'],pending_batch['migration'],original.matrix.shape,flush=True)
    except BudgetStop as error:
        result['stop_reason']=str(error)
        material=any(r['relative_Phi_reduction'] is not None and r['relative_Phi_reduction']>=.01 for r in traces)
        result['classification']='PHASE1_RESIDUAL_DIRECTED_MATERIAL_PROGRESS' if material else 'PHASE1_TRACTABILITY_FAIL'
    except Exception as error:
        result.update(classification='PHASE1_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc())
    finally:
        if executor:executor.shutdown(wait=True,cancel_futures=True)
        recovered=[read(p) for p in (OUT/'M19').rglob('CONCRETE_RECOVERY.json')]
        query_receipts=[read(p) for p in (OUT/'M19').rglob('EXACT_QUERY.json')]
        result.update(negative_STAY=sum(r['STAY_valid_negative'] for r in recovered),
            negative_migration=sum(r['migration_valid_negative'] for r in recovered),
            recovery_classes_completed=sum(r['PASS'] for r in recovered),
            unique_classes_queried=len({r['class_id'] for r in query_receipts}),
            STAY_queries_completed=sum(r['kind']=='STAY' for r in query_receipts),
            migration_queries_completed=sum(r['kind']=='MIGRATION' for r in query_receipts),
            unmaterialized_negative_blocks=sum(r['unmaterialized_negative_blocks'] for r in recovered))
        result.update(final_certified_phi=None if not traces else traces[-1]['Phi'],Phi_trajectory=[r['Phi'] for r in traces],
            activated_STAY=sum(r['kind']=='STAY' for r in activations),activated_migration=sum(r['kind']=='MIGRATION' for r in activations),
            native_calls=len(native.calls),native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),
            elapsed_wall_seconds=perf_counter()-budget.started,accounted_seconds=budget.accounted(),
            final_original_model=dict(rows=original.matrix.shape[0],cols=original.matrix.shape[1],nnz=original.matrix.nnz),
            maximum_factor_nnz=max((c['max_factor_nnz'] or 0 for c in native.calls),default=0),
            maximum_factor_memory_GB=max((c['max_factor_memory_GB'] or 0 for c in native.calls),default=0))
        if result['classification'] is None:result['classification']='PHASE1_TRACTABILITY_FAIL'
        for name,rows,fields in [('PHASE1_ITERATION_TRACE',traces,['iteration','Phi']),('ACTIVATED_COLUMNS',activations,['iteration','candidate_id']),
            ('MODEL_SIZE_TRACE',sizes,['iteration','original_rows']),('RESOURCE_TELEMETRY',native.resources,['wall_seconds','RSS'])]:csv(OUT/(name+'.csv'),rows,fields)
        atomic(OUT/'NATIVE_CALLS.json',dict(calls=native.calls,native_seconds=native.native_seconds))
        atomic(OUT/'BATCH_DECISION_TRACE.json',dict(batches=batches));atomic(OUT/'PHASE1_RESULT.json',result)
        print('RESIDUAL_RESULT',result,flush=True)
    return result

if __name__=='__main__':run()
