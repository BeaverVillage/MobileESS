"""All150 full-native original LP class oracles, including fractional directions."""
from pathlib import Path
from fractions import Fraction
from dataclasses import replace
from time import perf_counter
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import read,atomic
from v42_a_stage_phase1.runner import serial,load_cache,projected_global_pi,block_folder
from v42_a_stage_phase1.producer import price_snapshot,support_graph,native_block
from v42_a_stage_phase1.backend import project_local_point
from v42_a_stage_phase1.oracle import corrected_certificate,true_objective,validate_coverage
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,interval_box_bound,phase_objective
from v42_a_stage_early.native import BudgetStop
from .policy import OUT,HISTORY,POLICY

def full_pricing(native,original,master,raw,descriptor,data,domains,ledger,axes,global_variables,global_rows,local_rows,owned,round_folder,*,zero=False):
    before=perf_counter();qualified=read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    required={r['class_id']:r for r in qualified['records']}
    if len({key[:12] for key in required})!=len(required):raise ValueError('BLOCK_PATH_PREFIX_COLLISION')
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
    epsilon=Fraction(POLICY['price_epsilon'])
    for i,(key,want) in enumerate(sorted(required.items())):
        native.remaining()
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
            folder=block_folder(round_folder,key)
            native_result,point_raw=native.solve(priced,folder,'LOCAL_PRICING')
            if native_result['status']==gp.GRB.INFEASIBLE:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_FULL_LOCAL_BLOCK_INFEASIBLE')
            if native_result['status']!=gp.GRB.OPTIMAL or not all(n in point_raw for n in ('X','Pi','RC')):
                raise BudgetStop('FULL_LOCAL_PRICING_NOT_CERTIFIABLY_OPTIMAL')
            sign=verify_sign_convention(priced,point_raw['Pi'],point_raw['RC'],absolute=1e-7,relative=1e-10)
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
            active_raw_point_price=str(active_price),active_reference_scientific_replay_tolerance=1e-6,
            oracle_point_price=str(actual_delta),minimum_is_certified_interval=True,
            min_attaining_exact_rational_point_certified=False,zero_dual_analytical_certificate=zero,
            local_raw_pi=tuple(map(float,local_pi)),global_coupling_pi=tuple(map(float,coupling_pi)),
            full_mixed_fractional_finish_coverage=True,heuristic_path_prefix_used=False)
        certificates.append(receipt);records.append({k:v for k,v in receipt.items() if k!='certificate'})
        folder=block_folder(round_folder,key);folder.mkdir(parents=True,exist_ok=True)
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

