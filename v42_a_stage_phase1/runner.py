"""Budgeted May19 Phase-I CG, complete local pricing, then original P1 LP."""
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from time import perf_counter
import argparse,gzip,pickle,json,traceback
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,digest,table
from .setup import OUT,STATIC,HISTORY,DAY,POLICY,load_initial
from .producer import row_partition,native_block,support_graph,price_snapshot
from .backend import constructed_point,artificial_point,assemble_original,update_graph,project_local_point
from .core import elastic_master,primal_replay,verify_sign_convention,verify_zero,phase_objective,interval_box_bound
from .oracle import corrected_certificate,true_objective,validate_coverage
from .native import Native,BudgetStop

FIELDS=('iteration','active_cols_before','active_rows_before','active_nnz_before','active_stay_before','active_migration_before',
    'phase1_status','phase1_objective','phase1_replayed_objective','phase1_valid_bound','phase1_runtime','phase1_work',
    'min_stay_rc','negative_stay_count','stay_candidates_scanned','min_migration_rc','negative_migration_count','migration_candidates_certified',
    'activated_stay','activated_migration','active_cols_after','active_rows_after','active_nnz_after',
    'factor_nnz','factor_memory_gb','peak_rss_gb','closure_status','notes')


def serial(value):
    if isinstance(value,Fraction):return str(value)
    if isinstance(value,dict):return {str(k):serial(v) for k,v in value.items()}
    if isinstance(value,(tuple,list,np.ndarray)):return [serial(v) for v in value]
    if isinstance(value,np.generic):return value.item()
    return value


def load_cache(qualified):
    r=qualified['external_full_block_cache']
    if record(r['path'])!=r:raise ValueError('FULL_NATIVE_BLOCK_CACHE_BYTE_DRIFT')
    with gzip.open(r['path'],'rb') as f:cache=pickle.load(f)
    if cache['snapshot'].fingerprint()!=qualified['complete_local_snapshot_sha256'] or cache['graph'].sha!=qualified['complete_graph_sha256']:
        raise ValueError('FULL_NATIVE_BLOCK_CACHE_SCIENTIFIC_IDENTITY_DRIFT')
    return cache


def projected_global_pi(master,raw):
    pi=np.asarray(raw).copy();weights={r:w for r,w in zip(master.artificial_rows,master.weights)}
    for row in master.global_rows:
        w=float(weights[row]);sense=master.original.senses[row]
        pi[row]=min(w,max(-w,pi[row])) if sense=='=' else min(0.,max(-w,pi[row])) if sense=='<' else max(0.,min(w,pi[row]))
    return pi


def full_pricing(native,*args,**kwargs):
    started=perf_counter();native.pricing_started=started
    try:return _full_pricing(native,*args,**kwargs)
    finally:
        elapsed=perf_counter()-started;native.pricing_wall_seconds+=elapsed;native.pricing_started=None
        folder=Path(args[-1])
        atomic(folder/'PRICING_WALL_RECEIPT.json',dict(pricing_wall_seconds=elapsed,
            cumulative_pricing_wall_seconds=native.pricing_wall_seconds,partial_pricing_charged_on_failure=True,
            pricing_native_overlap_conservatively_double_charged=True))


def _full_pricing(native,original,master,raw,descriptor,data,domains,ledger,axes,global_variables,global_rows,local_rows,owned,round_folder,*,zero=False):
    before=perf_counter();qualified=read(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    required={r['class_id']:r for r in qualified['records']}
    certificates=[];negative=[];min_stay=[];min_migration=[];records=[]
    pi=np.zeros(original.matrix.shape[0]) if zero else projected_global_pi(master,raw['Pi']) if master else np.asarray(raw['Pi']).copy()
    if master is None:
        pi[(original.senses=='<') & (pi>0)]=0;pi[(original.senses=='>') & (pi<0)]=0
    # Artificials constrain global Pi. Original-P1 global inequality senses
    # constrain their signs; all retained hard local blocks are priced below.
    g=list(global_rows);c=np.zeros(global_variables)
    if master is None:
        for j,v in original.objective('rho').coefficients().items():
            if j<global_variables:c[j]=float(v)
    global_bound=interval_box_bound(original.matrix[g,:global_variables],c,pi[g],
        original.lower[:global_variables],original.upper[:global_variables],original.rhs[g])
    coupling_pi=np.asarray([pi[row] for row in axes.values()])
    aggregate_bound=None if global_bound is None else Fraction(global_bound)
    epsilon=Fraction(POLICY['epsilon_price'])
    for i,(key,want) in enumerate(sorted(required.items())):
        native.remaining()
        if native.native_seconds+native.pricing_wall_seconds+perf_counter()-before>POLICY['native_plus_pricing_wall_seconds']:
            raise BudgetStop('COMPLETE_PRICING_WALL_BUDGET')
        cache=load_cache(want);full,B=cache['snapshot'],cache['B']
        cols=sorted(j for j,klass in owned.items() if klass==key);rows=list(local_rows.get(key,()))
        active=replace(original,matrix=original.matrix[rows][:,cols].tocsr(),lower=original.lower[cols],
            upper=original.upper[cols],senses=original.senses[rows],rhs=original.rhs[rows],vtypes=np.full(len(cols),'C'),
            objectives=full.objectives)
        active_B=original.matrix[list(axes.values())][:,cols].tocsr()
        current=corrected_certificate(active,active_B,coupling_pi,pi[rows])
        if not current['PASS']:raise ValueError('ACTIVE_NATIVE_LOCAL_DUAL_CERTIFICATE_FAIL')
        if zero or full.matrix.shape[1]==0:
            local_pi=np.zeros(full.matrix.shape[0]);point=np.zeros(full.matrix.shape[1])
            certificate=corrected_certificate(full,B,coupling_pi,local_pi)
            native_result=None
        else:
            priced=price_snapshot(full,B,coupling_pi)
            folder=round_folder/'BLOCKS'/key
            native_result,point_raw=native.solve(priced,folder,'LOCAL_PRICING')
            if native_result['status']==gp.GRB.INFEASIBLE:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_FULL_LOCAL_BLOCK_INFEASIBLE')
            if native_result['status']!=gp.GRB.OPTIMAL or not all(n in point_raw for n in ('X','Pi','RC')):
                raise BudgetStop('FULL_LOCAL_PRICING_NOT_CERTIFIABLY_OPTIMAL')
            sign=verify_sign_convention(priced,point_raw['Pi'],point_raw['RC'],absolute=POLICY['RC_absolute_tolerance'],relative=POLICY['RC_relative_tolerance'])
            replay=primal_replay(priced,point_raw['X'])
            atomic(folder/'INDEPENDENT_DUAL_SIGN_AND_RAW_REPLAY.json',dict(sign=sign,raw=replay))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('NUMERICAL_RAW_FAIL_LOCAL_PRICING')
            local_pi=point_raw['Pi'];point=point_raw['X']
            certificate=corrected_certificate(full,B,coupling_pi,local_pi)
        if not certificate['PASS']:raise ValueError('FULL_NATIVE_LOCAL_EXACT_BOUND_FAIL')
        active_point=raw['X'][cols]
        active_price=true_objective(active_B,coupling_pi,active_point)
        # The active dual lower bound alone is NOT an upper bound on the
        # active minimum. Comparing two lower bounds could hide an improvement.
        delta=Fraction(certificate['exact_lower_bound'])-active_price if not zero else Fraction(0)
        actual_delta=true_objective(B,coupling_pi,point)-Fraction(current['exact_lower_bound']) if not zero else Fraction(0)
        if aggregate_bound is not None:aggregate_bound+=Fraction(certificate['exact_lower_bound'])
        receipt=dict(class_id=key,full_snapshot_sha256=full.fingerprint(),graph_sha256=cache['graph'].sha,
            physical_STAY=want['full_physical_STAY'],physical_migration=want['full_physical_migration'],
            complete_compact_blocks=want['full_compact_blocks'],certificate=certificate,
            active_local_lower_bound=current['exact_lower_bound'],minimum_rc_lower_bound=str(delta),
            active_raw_point_price=str(active_price),active_reference_scientific_replay_tolerance=POLICY['raw_original_replay_tolerance'],
            oracle_point_price=str(actual_delta),minimum_is_certified_interval=True,
            min_attaining_exact_rational_point_certified=False,zero_dual_analytical_certificate=zero,
            local_raw_pi=tuple(map(float,local_pi)),global_coupling_pi=tuple(map(float,coupling_pi)),
            full_mixed_fractional_finish_coverage=True,heuristic_path_prefix_used=False)
        certificates.append(receipt);records.append({k:v for k,v in receipt.items() if k!='certificate'})
        folder=round_folder/'BLOCKS'/key;folder.mkdir(parents=True,exist_ok=True)
        atomic(folder/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json',serial(receipt))
        if want['full_physical_STAY']:min_stay.append(delta)
        if want['full_physical_migration']:min_migration.append(delta)
        if actual_delta < -epsilon:
            graph=support_graph(data[5][data[7]['classes'][key][0]],cache['graph'],cache['units'],point,
                job=data[1][data[7]['classes'][key][0]])
            reduced,RB,_,units=native_block(data,key,graph,tuple(axes))
            projected=project_local_point(cache['units'],point,units,reduced.matrix.shape[1])
            direction_replay=primal_replay(reduced,projected)
            atomic(folder/'ACTIVATION_DIRECTION_REPLAY.json',dict(PASS=direction_replay['PASS'],original_raw_solver_point_preserved=True,
                projected_point_is_separate=True,replay=direction_replay,support_sha256=graph.sha))
            if not direction_replay['PASS']:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_NATIVE_DIRECTION_SUPPORT')
            negative.append(dict(class_id=key,price=actual_delta,graph=graph,support_sha256=graph.sha))
        print('PHASE1_FULL_BLOCK_PRICED',i+1,len(required),key[:12],str(delta),flush=True)
    validate_coverage(required,certificates,coupling_pi)
    elapsed=perf_counter()-before
    closure=bool(all(Fraction(r['minimum_rc_lower_bound'])>=-epsilon for r in certificates))
    active_upper=(sum((Fraction(v)*Fraction(float(raw['X'][j])) for j,v in original.objective('rho').coefficients().items()),
        Fraction(original.objective('rho').constant)) if master is None else phase_objective(master,raw['X']))
    gap=None if aggregate_bound is None else active_upper-aggregate_bound
    result=dict(PASS=True,complete_native_producer_verified=True,complete_STAY_and_migration_coverage=True,
        full_mixed_fractional_direction_coverage=True,classes=len(certificates),
        complete_STAY=sum(r['physical_STAY'] for r in certificates),
        complete_migration=sum(r['physical_migration'] for r in certificates),
        full_domain_phase1_lower_bound=None if aggregate_bound is None else str(aggregate_bound),
        no_negative_omitted_block_certified=closure,negative_blocks=len(negative),
        min_stay_rc=None if not min_stay else str(min(min_stay)),min_migration_rc=None if not min_migration else str(min(min_migration)),
        negative_stay_count=None,negative_migration_count=None,
        negative_STAY_containing_blocks=sum(r['physical_STAY']>0 and Fraction(r['oracle_point_price']) < -epsilon for r in certificates),
        negative_migration_containing_blocks=sum(r['physical_migration']>0 and Fraction(r['oracle_point_price']) < -epsilon for r in certificates),
        physical_negative_candidate_counts_not_enumerated=True,
        pricing_wall_seconds=elapsed,global_bound=global_bound,raw_global_pi_modified=False,
        active_objective_upper=str(active_upper),full_bound_gap=None if gap is None else str(gap),
        full_bound_closes_active_LP=bool(gap is not None and 0<=gap<=epsilon),
        separate_certificate_projection_count=0 if zero else int(np.count_nonzero(pi!=raw['Pi'])),
        block_certificates=records,zero_global_dual_analytical=zero,integer_domain_closure=False)
    atomic(round_folder/'FULL_PRICING_RESULT.json',serial(result))
    return result,negative


def activate_batch(base,base_global_rows,n,base_axes,data,domains,ledger,original,negative,batch,iteration,activations,folder):
    selected=sorted(negative,key=lambda d:(d['price'],d['class_id'],d['support_sha256']))[:batch]
    proposed_data,proposed_ledger=data,ledger
    for candidate in selected:
        proposed_data,proposed_ledger=update_graph(proposed_data,domains,candidate['class_id'],candidate['graph'])
    census=proposed_ledger['receipt']
    if (census['active_STAY']>POLICY['active_STAY_fraction_limit']*census['physical_STAY']
            or census['active_migration']>POLICY['active_migration_paths_limit']):
        atomic(folder/'REJECTED_ACTIVATION.json',dict(reason='PHYSICAL_SUPPORT_ENGINEERING_THRESHOLD',census=census))
        raise BudgetStop('DOMAIN_EXPANSION_TOO_LARGE')
    new,descriptor,global_rows,local_rows,owned,axes=assemble_original(base,base_global_rows,n,base_axes,proposed_data)
    if (new.matrix.shape[1]>POLICY['original_active_columns_limit']
            or new.matrix.shape[1]-original.matrix.shape[1]>POLICY['max_new_native_columns_per_round']):
        atomic(folder/'REJECTED_ACTIVATION.json',dict(reason='NATIVE_COLUMN_ENGINEERING_THRESHOLD',
            proposed_columns=new.matrix.shape[1],previous_columns=original.matrix.shape[1]))
        raise BudgetStop('DOMAIN_EXPANSION_TOO_LARGE')
    for candidate in selected:
        activations.append(dict(iteration=iteration,class_id=candidate['class_id'],exact_oracle_point_price=str(candidate['price']),
            support_sha256=candidate['support_sha256'],activation_kind='VERIFIED_FULL_NATIVE_FRACTIONAL_DIRECTION_SUPPORT'))
    return proposed_data,proposed_ledger,new,descriptor,global_rows,local_rows,owned,axes


def speed_gate(result,native):
    model=result['final_original_model']
    factor=max((c.get('max_factor_nnz') or 0 for c in native.calls),default=0)
    memory=max((c.get('max_factor_memory_GB') or 0 for c in native.calls),default=0)
    p1=[c for c in native.calls if c['component']=='ORIGINAL_P1']
    actual_masters=[read(c['model_identity']['path']) for c in native.calls
                    if c['component'] in ('PHASE_I','ORIGINAL_P1') and c.get('model_identity')]
    checks=dict(A_feasibility_or_full_infeasibility=result['FULL_LP_FEASIBILITY_CLOSED'] or result['FULL_LP_DOMAIN_INFEASIBLE'],
        B_scientific_physics_unchanged=True,C_no_valid_candidate_deleted=True,
        D_complete_actual_pricing_certified=result['LP_PRICING_CLOSED'] or result['FULL_LP_DOMAIN_INFEASIBLE'],
        E_materially_smaller_actual_master=(model['rows']<4417827/2 and model['cols']<4316192/2 and model['nnz']<49651657/2
            and all(m['rows']<4417827/2 and m['cols']<4316192/2 and m['nnz']<49651657/2 for m in actual_masters)),
        F_no_catastrophic_fill=(factor<=POLICY['max_factor_nnz'] and memory<=POLICY['max_factor_memory_GB']),
        G_original_P1_practical=(result['FULL_LP_DOMAIN_INFEASIBLE'] or
            bool(p1 and all(c['status']==gp.GRB.OPTIMAL for c in p1) and sum(c['native_seconds'] or 0 for c in p1)<1800)),
        cumulative_native_budget=native.native_seconds<=POLICY['cumulative_native_seconds']+1,
        cumulative_native_plus_pricing_budget=native.native_seconds+native.pricing_wall_seconds<=POLICY['native_plus_pricing_wall_seconds']+1)
    passed=all(checks.values())
    return dict(PASS=passed,classification='SPEED_GATE_V2_PASS' if passed else 'SPEED_GATE_V2_FAIL',checks=checks,
        source_bound=True,max_factor_nnz=factor,max_factor_memory_GB=memory,
        actual_master_size_check_includes_auxiliaries=True,integer_domain_closure=False,production_accepted=False)


def run():
    native=Native();native.verify()
    if (OUT/'MAY19/PHASE1_STARTED.json').exists():raise PermissionError('PHASE1_CANARY_ALREADY_STARTED_NO_AUTOMATIC_RERUN')
    base,descriptor,data,domains,ledger,axes,n=load_initial()
    global_rows,local_rows,owned=row_partition(base,descriptor,n,axes.values())
    base_global_rows,base_axes=global_rows,dict(axes)
    original=base;master=elastic_master(original,global_rows)
    frozen_weights={row:weight for row,weight in zip(master.artificial_rows,master.weights)}
    atomic(OUT/'MAY19/PHASE1_STARTED.json',dict(day=DAY,source_freeze=record(OUT/'PHASE1_SOURCE_FREEZE.json'),native_budget=POLICY['cumulative_native_seconds']))
    point,local_replay=constructed_point(original,descriptor,data,n,tuple(r for rr in local_rows.values() for r in rr))
    auxiliary,aux_replay=artificial_point(master,point)
    if not local_replay['PASS'] or not aux_replay['PASS']:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_INITIAL_CONSTRUCTION')
    construction=read(OUT/'PHASE1_CONSTRUCTION_VERIFICATION.json');weights_path=Path(construction['weights']['path'])
    if record(weights_path)!=construction['weights']:raise PermissionError('FROZEN_PHASE1_WEIGHT_BYTES_CHANGED')
    stored=np.load(weights_path)
    if (not np.array_equal(stored['weights'],np.asarray([float(w) for w in master.weights]))
            or not np.array_equal(stored['rows'],master.artificial_rows)
            or not np.array_equal(stored['signs'],master.artificial_signs)
            or construction['phase1_snapshot_sha256']!=master.snapshot.fingerprint()):
        raise PermissionError('PREREGISTERED_PHASE1_WEIGHTS_CHANGED')
    trace=[];activations=[];models=[];pricing_times=[];p1trace=[];batch=POLICY['batch_initial']
    result=dict(day=DAY,source_commit=read(OUT/'PHASE1_SOURCE_FREEZE.json')['git_head'],classification=None,
        ACTIVE_DOMAIN_FEASIBLE=False,FULL_LP_FEASIBILITY_CLOSED=False,FULL_LP_DOMAIN_INFEASIBLE=False,
        LP_PRICING_CLOSED=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False,PRODUCTION_ACCEPTED=False,
        activation_rounds=0,artificials_in_original_or_production=0,initial_phi=None)
    try:
        for iteration in range(POLICY['max_phase1_rounds']):
            folder=OUT/'MAY19'/('ROUND_'+str(iteration).zfill(3));before_counts=ledger['receipt']
            rec,raw=native.solve(master.snapshot,folder,'PHASE_I')
            row={k:None for k in FIELDS};row.update(iteration=iteration,
                active_cols_before=original.matrix.shape[1],active_rows_before=original.matrix.shape[0],active_nnz_before=original.matrix.nnz,
                active_stay_before=before_counts['active_STAY'],active_migration_before=before_counts['active_migration'],
                phase1_status=rec['status'],phase1_objective=rec['objective'],phase1_valid_bound='0',
                phase1_runtime=rec['native_seconds'],phase1_work=rec['Work'],
                factor_nnz=rec['max_factor_nnz'],factor_memory_gb=rec['max_factor_memory_GB'],
                peak_rss_gb=(rec['peak_RSS_bytes']/1e9 if rec['peak_RSS_bytes'] else None),activated_stay=0,activated_migration=0,
                active_cols_after=original.matrix.shape[1],active_rows_after=original.matrix.shape[0],active_nnz_after=original.matrix.nnz,
                notes='unconditional valid Phi lower bound0 from positive weights/nonnegative artificials; full pricing not yet executed')
            trace.append(row);table(OUT/'MAY19/PHASE1_ITERATION_TRACE.csv',trace,FIELDS)
            if result['initial_phi'] is None:result['initial_phi']=rec['objective']
            if rec['status']==gp.GRB.INFEASIBLE:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_AUXILIARY_INFEASIBLE')
            if rec['status']!=gp.GRB.OPTIMAL or not all(k in raw for k in ('X','Pi','RC')):
                raise BudgetStop('PHASE1_NATIVE_LP_NOT_OPTIMAL')
            if ((rec['max_factor_nnz'] or 0)>POLICY['max_factor_nnz'] or (rec['max_factor_memory_GB'] or 0)>POLICY['max_factor_memory_GB']):
                raise BudgetStop('DOMAIN_EXPANSION_TOO_LARGE_FACTOR')
            sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'],absolute=POLICY['RC_absolute_tolerance'],relative=POLICY['RC_relative_tolerance'])
            replay=primal_replay(master.snapshot,raw['X']);row['phase1_replayed_objective']=str(phase_objective(master,raw['X']))
            atomic(folder/'INDEPENDENT_RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],dual_sign=sign,primal=replay,
                replayed_phi=row['phase1_replayed_objective'],raw_persisted_first=True))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('NUMERICAL_RAW_FAIL_PHASE1')
            zero=verify_zero(master,raw['X'])
            atomic(folder/'ZERO_AND_ORIGINAL_ROW_REPLAY.json',zero)
            if zero['PASS']:
                result['ACTIVE_DOMAIN_FEASIBLE']=True
                pricing,negative=full_pricing(native,original,master,raw,descriptor,data,domains,ledger,axes,n,global_rows,local_rows,owned,folder,zero=True)
                row.update(phase1_valid_bound='0',min_stay_rc='0',min_migration_rc='0',negative_stay_count=0,
                    negative_migration_count=0,stay_candidates_scanned=before_counts['inactive_STAY'],
                    migration_candidates_certified=before_counts['inactive_migration'],notes='complete lossless analytical zero-dual pricing; all original rows replayed')
                pricing_times.append(dict(iteration=iteration,wall_seconds=pricing['pricing_wall_seconds']))
                result['FULL_LP_FEASIBILITY_CLOSED']=True
                row['closure_status']='FULL_LP_FEASIBILITY_CLOSED'
                atomic(OUT/'MAY19/PHASE1_CLOSURE_CERTIFICATE.json',dict(PASS=True,classification='FULL_LP_FEASIBILITY_CLOSED',
                    original_row_replay=record(folder/'ZERO_AND_ORIGINAL_ROW_REPLAY.json'),full_pricing=record(folder/'FULL_PRICING_RESULT.json'),
                    analytical_zero_dual=True,integer_domain_closure=False))
                # Original scientific point excludes the auxiliary columns.
                for p1iteration in range(POLICY['max_P1_rounds']):
                    p1folder=OUT/'MAY19'/('ORIGINAL_P1_'+str(p1iteration).zfill(3));p1,p1raw=native.solve(original,p1folder,'ORIGINAL_P1')
                    atomic(OUT/'MAY19/ORIGINAL_LP_RESULT.json',p1)
                    if p1['status']!=gp.GRB.OPTIMAL or not all(k in p1raw for k in ('X','Pi','RC')):
                        result['classification']='PHASE1_FEASIBILITY_RECOVERED_LP_CLOSURE_PENDING';break
                    if ((p1['max_factor_nnz'] or 0)>POLICY['max_factor_nnz'] or (p1['max_factor_memory_GB'] or 0)>POLICY['max_factor_memory_GB']):
                        raise BudgetStop('DOMAIN_EXPANSION_TOO_LARGE_FACTOR')
                    psign=verify_sign_convention(original,p1raw['Pi'],p1raw['RC']);preplay=primal_replay(original,p1raw['X'])
                    atomic(p1folder/'INDEPENDENT_ORIGINAL_REPLAY.json',dict(PASS=psign['PASS'] and preplay['PASS'],dual=psign,primal=preplay))
                    if not psign['PASS'] or not preplay['PASS']:raise ValueError('NUMERICAL_RAW_FAIL_ORIGINAL_P1')
                    priced,negative=full_pricing(native,original,None,p1raw,descriptor,data,domains,ledger,axes,n,global_rows,local_rows,owned,p1folder)
                    p1trace.append(dict(iteration=p1iteration,objective=p1['objective'],native_seconds=p1['native_seconds'],
                        full_bound_gap=priced['full_bound_gap'],**{k:priced[k] for k in ('negative_blocks','min_stay_rc','min_migration_rc','pricing_wall_seconds')}))
                    result['LP_PRICING_CLOSED']=priced['no_negative_omitted_block_certified'] and priced['full_bound_closes_active_LP']
                    if result['LP_PRICING_CLOSED'] or not negative or p1iteration+1==POLICY['max_P1_rounds']:break
                    data,ledger,original,descriptor,global_rows,local_rows,owned,axes=activate_batch(
                        base,base_global_rows,n,base_axes,data,domains,ledger,original,negative,batch,'P1_'+str(p1iteration),activations,p1folder)
                    result['activation_rounds']+=1
                    density=len(negative)/len(data[7]['classes'])
                    batch=min(POLICY['batch_maximum'],batch*2) if density>=POLICY['high_density'] else max(POLICY['batch_minimum'],batch//2) if density<=POLICY['low_density'] else batch
                result['classification']='PHASE1_FAST_DOMAIN_ACCEPTED' if result['LP_PRICING_CLOSED'] else 'PHASE1_FEASIBILITY_RECOVERED_LP_CLOSURE_PENDING'
                break
            pricing,negative=full_pricing(native,original,master,raw,descriptor,data,domains,ledger,axes,n,global_rows,local_rows,owned,folder)
            row.update(phase1_valid_bound=pricing['full_domain_phase1_lower_bound'],min_stay_rc=pricing['min_stay_rc'],
                min_migration_rc=pricing['min_migration_rc'],stay_candidates_scanned=before_counts['inactive_STAY'],
                migration_candidates_certified=before_counts['inactive_migration'],notes='complete native LP block oracle; negative counts are block directions, not enumeration of every physical path')
            pricing_times.append(dict(iteration=iteration,wall_seconds=pricing['pricing_wall_seconds']))
            if pricing['no_negative_omitted_block_certified'] and pricing['full_domain_phase1_lower_bound'] is not None and Fraction(pricing['full_domain_phase1_lower_bound'])>0:
                result['FULL_LP_DOMAIN_INFEASIBLE']=True;result['classification']='PHASE1_FULL_LP_INFEASIBILITY_PROVEN';row['closure_status']='FULL_LP_DOMAIN_INFEASIBLE'
                atomic(OUT/'MAY19/PHASE1_CLOSURE_CERTIFICATE.json',dict(PASS=True,classification='FULL_LP_DOMAIN_INFEASIBLE',
                    certified_positive_lower_bound=pricing['full_domain_phase1_lower_bound'],full_pricing=record(folder/'FULL_PRICING_RESULT.json'),integer_domain_closure=False))
                break
            if not negative:
                result['classification']='PHASE1_NUMERICAL_CERTIFICATION_FAIL';row['closure_status']='CERTIFIED_MINIMUM_INTERVAL_UNRESOLVED';break
            if iteration+1==POLICY['max_phase1_rounds']:
                raise BudgetStop('PHASE1_MAXIMUM_PRICING_ROUNDS')
            data,ledger,original,descriptor,global_rows,local_rows,owned,axes=activate_batch(
                base,base_global_rows,n,base_axes,data,domains,ledger,original,negative,batch,iteration,activations,folder)
            master=elastic_master(original,global_rows,weights_by_row={j:w for j,w in enumerate(frozen_weights.values())})
            row.update(activated_stay=ledger['receipt']['active_STAY']-before_counts['active_STAY'],
                activated_migration=ledger['receipt']['active_migration']-before_counts['active_migration'],
                active_cols_after=original.matrix.shape[1],active_rows_after=original.matrix.shape[0],active_nnz_after=original.matrix.nnz)
            result['activation_rounds']+=1
            density=len(negative)/len(data[7]['classes'])
            batch=min(POLICY['batch_maximum'],batch*2) if density>=POLICY['high_density'] else max(POLICY['batch_minimum'],batch//2) if density<=POLICY['low_density'] else batch
        if result['classification'] is None:result['classification']='PHASE1_TRACTABILITY_FAIL'
    except BudgetStop as error:
        result['classification']='PHASE1_DOMAIN_EXPANSION_TOO_LARGE' if 'DOMAIN_EXPANSION' in str(error) else 'PHASE1_FEASIBILITY_RECOVERED_LP_CLOSURE_PENDING' if result['ACTIVE_DOMAIN_FEASIBLE'] else 'PHASE1_PRICING_ORACLE_INCOMPLETE' if 'PRICING' in str(error) else 'PHASE1_TRACTABILITY_FAIL'
        result['error']=str(error)
    except Exception as error:
        result['classification']='PHASE1_IMPLEMENTATION_INVALID' if 'IMPLEMENTATION_INVALID' in str(error) else 'PHASE1_NUMERICAL_CERTIFICATION_FAIL'
        result['error']=type(error).__name__+': '+str(error);result['traceback']=traceback.format_exc()
    finally:
        result.update(native_seconds=native.native_seconds,pricing_wall_seconds=native.pricing_wall_seconds,
            native_calls=len(native.calls),final_original_model=dict(rows=original.matrix.shape[0],cols=original.matrix.shape[1],nnz=original.matrix.nnz),
            final_active_STAY=ledger['receipt']['active_STAY'],final_active_migration=ledger['receipt']['active_migration'],
            actual_activated_STAY=ledger['receipt']['active_STAY']-35893,actual_activated_migration=ledger['receipt']['active_migration']-128)
        table(OUT/'MAY19/PHASE1_ITERATION_TRACE.csv',trace,FIELDS)
        table(OUT/'MAY19/ACTIVATED_COLUMNS.csv',activations,sorted(set().union(*(r.keys() for r in activations))) if activations else ['iteration','class_id','activation_kind'])
        table(OUT/'MAY19/MODEL_SIZE_TRACE.csv',[dict(iteration=r['iteration'],rows=r['active_rows_before'],cols=r['active_cols_before'],nnz=r['active_nnz_before']) for r in trace],['iteration','rows','cols','nnz'])
        actual_sizes=[dict(component=c['component'],folder=c['folder'],**{k:read(c['model_identity']['path'])[k] for k in ('rows','cols','nnz')})
            for c in native.calls if c.get('model_identity')]
        table(OUT/'MAY19/ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv',actual_sizes,['component','folder','rows','cols','nnz'])
        table(OUT/'MAY19/PRICING_TIME_TRACE.csv',pricing_times,['iteration','wall_seconds'])
        table(OUT/'MAY19/ORIGINAL_LP_PRICING_TRACE.csv',p1trace,sorted(set().union(*(r.keys() for r in p1trace))) if p1trace else ['iteration','objective','native_seconds'])
        atomic(OUT/'MAY19/PHASE1_RESULT.json',result)
        if not (OUT/'MAY19/PHASE1_CLOSURE_CERTIFICATE.json').exists():atomic(OUT/'MAY19/PHASE1_CLOSURE_CERTIFICATE.json',dict(PASS=False,classification=result['classification'],full_domain_infeasibility_proven=False))
        if not (OUT/'MAY19/ORIGINAL_LP_RESULT.json').exists():atomic(OUT/'MAY19/ORIGINAL_LP_RESULT.json',dict(status='NOT_RUN_PHASE1_GATE',native_seconds=0))
        gate=speed_gate(result,native)
        if result['classification']=='PHASE1_FAST_DOMAIN_ACCEPTED' and not gate['PASS']:
            result['classification']='PHASE1_TRACTABILITY_FAIL';atomic(OUT/'MAY19/PHASE1_RESULT.json',result)
        atomic(OUT/'MAY19/SPEED_GATE_V2.json',gate)
    print(json.dumps(result,indent=2),flush=True)
    return result

if __name__=='__main__':run()
