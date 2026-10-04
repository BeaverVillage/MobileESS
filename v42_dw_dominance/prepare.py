"""Stages 0-9: independently inspect every original axis and retained column."""
from .common import *
import numpy as np
from fractions import Fraction as F

def diagnosis(directory,certificates,output_prefix=''):
    rows=[];rounds=[]
    for certificate in certificates:
        cert=read(certificate);group=[]
        for i,file in enumerate(cert['pricing_receipts']):
            p=read(directory/file);beta=p['ObjBound'] if p['valid_bound'] else None;inc=p['rc_inc'] if p['valid_point'] else None
            raw_gap=None if beta is None or inc is None else inc-beta
            if raw_gap is not None:assert raw_gap>=-EPS
            gap=None if raw_gap is None else max(0,raw_gap)
            room=None if gap is None else max(0,min(0,inc)-min(0,beta))
            log=directory/'logs'/f"PRICE_{p['call']:04d}_{p['MESS']}.log";raw=log.read_text(encoding='utf8',errors='replace')
            import re
            root=re.findall(r'Root relaxation: objective ([+-]?[\d.eE+-]+).*?([\d.]+) seconds',raw)
            row=dict(round=cert['iteration'],MESS=p['MESS'],call=p['call'],dual_SHA=p['dual_SHA'],beta_m=beta,rc_inc_m=inc,rc_opt_m=inc if p['native_status']==2 and p['valid_point'] else None,proof_gap_m=gap,delta_m=None if beta is None else min(0,beta),hypothetical_delta_using_inc=None if inc is None else min(0,inc),proof_weakness_room_m=room,root_relaxation_bound=float(root[-1][0]) if root else p.get('root_relaxation_bound'),root_completion_time=float(root[-1][1]) if root else p.get('root_completion_time'),root_time_semantics='Native root-relaxation log elapsed seconds; not a pricing optimum',terminal_BestBd=beta,terminal_incumbent_RC=inc,native_gap=p['MIPGap'],node_count=p['nodes'],first_incumbent_time=p.get('first_incumbent_time'),native_status=p['native_status'],receipt_SHA=sha(directory/file),incumbent_used_for_LB=False)
            row.update(proof_gap_raw_m=raw_gap,diagnostic_negative_roundoff_clamped_to_zero=bool(raw_gap is not None and raw_gap<0),pricing_root_terminal_bound_gap=None if not root or beta is None else beta-float(root[-1][0]),pricing_terminal_proof_gap=gap)
            rows.append(row);group.append(row)
        sufficient=cert['certified'] and len(group)==4 and all(x['proof_gap_m'] is not None for x in group)
        room=sum(x['proof_weakness_room_m'] for x in group) if sufficient else 0
        negative=-sum(min(0,x['rc_inc_m']) for x in group) if sufficient else 0
        deficit=T_MATERIAL-cert['L_corr'] if cert['certified'] else None
        rounds.append(dict(round=cert['iteration'],L_corr=cert['L_corr'],U_RMP=cert['U_RMP'],sum_proof_weakness_room=room,sum_negative_incumbent_magnitude=negative,material_threshold_L_corr_deficit=deficit,classification=classify(room,negative,deficit or 0,sufficient),exact_residual_correction=cert.get('exact_RMP_dual_minus_native_ObjVal'),native_beta_safety=EPS,outward_rounding=True,incumbent_hypothesis_diagnostic_only=True))
    table(output_prefix+'DW_PRICING_BOUND_WEAKNESS.csv',rows)
    value=dict(PASS=True,classification=rounds[-1]['classification'] if rounds else 'INCONCLUSIVE',rounds=rounds,per_MESS=rows,classification_policy=read(OUT/'DW_THRESHOLD_PREREGISTRATION.json')['classification_policy'],causal_uniqueness_claimed=False,incumbent_used_as_LB=False,unobservable_times=None)
    write(output_prefix+'DW_PRICING_BOUND_DIAGNOSIS.json',value);return value

def prepare():
    from v42_degen.identity import inputs,signature,digest
    from v42_dw_root.partition import axes
    from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
    from v42_dw_root.models import hash_column
    from v42_integrated.matrix import payload
    from .fixtures import run as fixture_run
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert head==BASE_HEAD
    remote=json.loads(subprocess.check_output(['gh','pr','view','142','--repo','BeaverVillage/MobileESS','--json','headRefOid,isDraft'],text=True));assert remote['headRefOid']==head and remote['isDraft']
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    write('PR142_BYTE_FREEZE.json',dict(head=head,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked if p]))
    for f in ('logs','pricing_points','pricing_receipts','columns','bound_certificates'):(OUT/f).mkdir(exist_ok=True)
    prereg=dict(base_head=head,checkpoint_columns=1158,optimize_budget_seconds=900,budget_authority='Union of native optimize intervals, including any fixture solves; fixtures here use exact Fraction enumeration and make zero native optimize calls. No automatic extension.',maximum_discovery_rounds=8,discovery_cap=20,certification_cap=90,final_certification_rounds_at_most=1,early_triggers=['two consecutive zero accepted rounds','total U decrease over last three completed rounds < 0.001','U - T <= 0.002'],immediate_stop='Audited U <= T immediately after every RMP; no pricing certification needed',fixed_workers=4,Threads=1,RAM_floor_GiB=1,warm_RMP_selected=False,warm_RMP_tests=False,adaptive_smoothing='PR142 fixed adaptive update rule, initial next alpha 0.125; restore center only exact pool/dual/row axis identity',true_RC_threshold=DISCOVERY_RC,no_negative_BestBd=-EPS,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,postsolve_affine=POST,maximum_columns_per_MESS=4,maximum_columns_per_round=16,full_original_domain=True,column_deletion=False,speed_tuning=False,classification_policy=dict(min_material_component=.001,weakness_supported='sum room >= max(0.001, T - L_corr)',true_negative='sum -min(0,inc) >= 0.001',close_bound='sum room <= max(1e-6, 0.05*negative magnitude)',mixed='Both supported weakness and true negative material components',inconclusive='Receipts insufficient or no registered predicate applies'),certificate_authority='True dual plus native full-domain global BestBd only; unchanged exact Fraction residual correction and fixed 1e-8 beta safety; incumbents diagnostic only',material_threshold=T_MATERIAL,Arc_floor_candidate=BASE_LB,May_production=[0,0,0],Branch_and_Price=False)
    write('DW_THRESHOLD_PREREGISTRATION.json',prereg)
    A,d,B,e,identity,freeze=inputs();owner,row_owner=axes()
    assert signature(B,e)==read(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json')['reference_signature']
    with np.load(SOURCE/'REDUCTION_AXES.npz') as z:keep=z['keep']
    mapping=ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_DUPLICATE_MAP.csv'
    with mapping.open(encoding='utf8',newline='') as f:pairs=list(csv.DictReader(f))
    retained=set(map(int,keep));removed=set(range(A.shape[0]))-retained
    assert removed=={int(x['removed_row']) for x in pairs}
    for x in pairs:
        i=int(x['removed_row']);j=int(x['retained_representative']);assert j in retained
        assert payload(A,d['rhs'],d['sense'],i)==payload(A,d['rhs'],d['sense'],j)
    assert np.array_equal(B.indptr,A[keep].indptr) and np.array_equal(B.indices,A[keep].indices) and np.array_equal(B.data,A[keep].data)
    for key in ('lower','upper','types','objective','names','constant'):assert np.array_equal(d[key],e[key])
    assert set(map(int,owner))=={-1,0,1,2,3} and np.all(e['types'][owner==-1]=='C')
    assert np.all(np.abs(e['lower'][owner>=0])<1e90) and np.all(np.abs(e['upper'][owner>=0])<1e90)
    actual=np.full(B.shape[0],-1,dtype=np.int8)
    original_local=[[] for _ in UNITS]
    for i in range(A.shape[0]):
        deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(deps)==1 and -1 not in deps:original_local[next(iter(deps))].append(i)
    for i in range(B.shape[0]):
        deps=set(map(int,owner[B.indices[B.indptr[i]:B.indptr[i+1]]]))
        if len(deps)==1 and -1 not in deps:actual[i]=next(iter(deps))
    assert np.array_equal(actual,row_owner)
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);full={}
    for m,b in enumerate(blocks):
        rr=np.array(original_local[m]);cc=b.columns;matrix=A[rr][:,cc];attrs=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.));full[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs))
    checks=[];seen=[set() for _ in UNITS]
    for k,(directory,h) in enumerate(old_columns()):
        p=directory/h['file'];assert sha(p)==h['file_SHA'];m=UNITS.index(h['MESS']);b=blocks[m]
        with np.load(p) as z:
            new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c'] if new else z['objective'])
            assert hash_column(x,a,c)==h['SHA256'] and h['SHA256'] not in seen[m];seen[m].add(h['SHA256'])
            matrix,attrs,mask=full[m];local=corrected_rows(matrix,attrs,x,True,mask);physical=b.validate(x,True)
            assert local['PASS'] and physical['PASS'];assert np.array_equal(b.B@x,a) and float(b.d['objective']@x)==c
        checks.append(dict(MESS=h['MESS'],file=p.relative_to(ROOT).as_posix(),file_SHA=h['file_SHA'],column_SHA=h['SHA256'],PASS=True,full_original_local=local))
        if k%200==0:print('DOMINANCE_COLUMN_AUDIT',k,flush=True)
    checkpoint=read(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json');assert len(checks)==len(checkpoint['pool'])==checkpoint['total_retained_columns']==1158
    source_files=[p for folder in ('v42_dw_root','v42_dw_resume','v42_dw_bound','v42_dw_policy','v42_dw_throughput') for p in (ROOT/folder).glob('*.py')]
    source_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in source_files}
    axis=dict(pool_SHA=hashlib.sha256(json.dumps([(x['MESS'],x['column_SHA']) for x in checks],separators=(',',':')).encode()).hexdigest(),dual_axis_SHA=digest(np.flatnonzero(row_owner<0)),row_axis_SHA=digest(e['row_names'][row_owner<0]),column_owner_SHA=digest(owner),row_owner_SHA=digest(row_owner))
    audit=dict(PASS=True,base_SHA=head,remote=remote,retained_columns=1158,checks=checks,matrix_signature=signature(B,e),original_identity=identity,A1_freeze_SHA=sha(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'),checkpoint_SHA=sha(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json'),source_hashes=source_hashes,numerical_contract=prereg,axes=axis,optimize_calls=0,failed_old_points_promoted=False)
    write('DW_DOMINANCE_BASE_AUDIT.json',audit)
    coupling=dict(PASS=True,full_original_rows=A.shape[0],retained_rows=B.shape[0],exact_duplicate_rows=len(pairs),duplicate_map_SHA=sha(mapping),duplicate_elimination_is_exact_equivalence=True,no_constraint_removed_or_weakened_semantically=True,literal_duplicate_copies_removed=True,global_rows=int((row_owner<0).sum()),local_rows=int((row_owner>=0).sum()),original_variable_axis_size=A.shape[1],disjoint_exhaustive_axes=True,global_G='B[global_rows,global_columns]',local_B_m='B[global_rows,local_columns_m]',projection='For every original global row i, coefficients B[i,j] are retained verbatim. Column a[m,p] = B_m v[m,p], not an approximation. Removed FULL row i has byte-identical retained representative j, same sense/RHS; hence it remains implied for every convex combination.',bounds_objective_constant_identical=True,global_variables_continuous_unchanged=True,rho_no_extra_freedom=True,all_checkpoint_coefficients_exact_projection=True,matrix_signature=signature(B,e),axes=axis)
    write('DW_COUPLING_IDENTITY_AUDIT.json',coupling)
    theorem=dict(PASS=True,definitions=dict(X_m_I='Original local affine rows, original continuous bounds and original binary route/mode variables; no route restrictions.',P_m_arc='Same original rows and bounds, replacing each binary integrality constraint with its original [0,1] bounds.',DW='All of conv(X_m_I); unchanged shared grid coordinates z, bounds, objective, and coupling rows.'),proof_steps=['Each x in X_m_I satisfies every defining affine row and bound of P_m_arc, so X_m_I is a subset of P_m_arc.', 'P_m_arc is convex: linear equality/inequality rows and intervals are preserved by nonnegative weights summing to one. Thus conv(X_m_I) is a subset of P_m_arc, including every unseen legal trajectory.', 'Define x_m = sum_p lambda[m,p] v[m,p], lambda >= 0, sum_p lambda = 1. All original local rows/bounds hold by linearity; original integer coordinates lie in [0,1].', 'Exact a[m,p]=B_m v[m,p] gives Gz + sum_m B_m x_m = Gz + sum_m sum_p lambda[m,p] a[m,p]. Same sense/RHS and identical shared bounds mean every original global row holds.', 'Duplicate elimination has exact byte-identical representatives, so all FULL rows hold as well. Original variable-axis reconstruction adds no global or rho freedom.', 'Objective c_z*z + sum_m c_m*x_m + c0 equals the DW objective. Therefore projected DW feasible set is a subset of FULL arc LP, and z_arc_LP <= z_DW_root for minimization.'],unbounded_rays='Every local variable has finite original bounds; integer faces bounded. Shared unbounded grid variables remain unchanged globally, not replaced by columns.',finite_pool_not_full_hull=True,full_domain_proof_is_symbolic_affine_inclusion=True,retained_columns_audited=1158,numerical_column_receipts='Feasible under frozen affine 1e-6 and raw integral/bounds 1e-8 audits; mathematical inclusion concerns exact feasible sets, solver certificates use the stated numerical contract.',coupling_audit_SHA=sha(OUT/'DW_COUPLING_IDENTITY_AUDIT.json'))
    write('DW_FULL_SCALE_DOMINANCE_PROOF.json',theorem)
    fixtures=fixture_run();write('DW_DOMINANCE_ENUMERATION_FIXTURES.json',fixtures)
    arc_receipt=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_SOLVE_RESULT.json')
    arc_cert=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_CERTIFICATE.json')
    assert arc_cert['model_identity']==identity and arc_cert['valid_global_LB'] and arc_cert['LB']==BASE_LB
    lp=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json');assert lp['PASS'] and abs(lp['full']['objective']-BASE_LB)<=EPS
    # STOP unless the native root bound provenance is demonstrably the LP root,
    # not a later MIP cut or branch bound. The full LP equivalence receipt alone
    # only provides audited primal objectives and cannot prove a lower bound.
    source_log=ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_P1.log'
    candidates=list((ROOT/'docs/v42_single_worker_single_thread_a1_m1').glob('*.log'))
    write('ARC_FLOOR_PROVENANCE_INSPECTION.json',dict(candidate_floor=BASE_LB,source_certificate_SHA=sha(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_CERTIFICATE.json'),source_type='Interrupted root MIP global ObjBound, not an exact rational original arc-LP dual certificate',root_objective_rounded=arc_receipt['root_objective'],node_count=arc_receipt['node_count'],LP_receipts_are_primal_objectives=True,logs=[p.name for p in candidates]))
    finish_gate(audit,checkpoint,lp,arc_receipt)

def finish_gate(audit,checkpoint,lp,arc_receipt):
    axis=audit['axes'];checks=audit['checks']
    provenance=read(OUT/'ARC_FLOOR_PROVENANCE_INSPECTION.json')
    live=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_LIVE_TIMELINE.json')
    historical=ROOT/'docs/v42_single_worker_single_thread_a1_m1'
    with np.load(SOURCE/'LP_full_POINT.npz') as z:full_keys=z.files
    with np.load(SOURCE/'LP_reduced_POINT.npz') as z:reduced_keys=z.files
    provenance.update(PASS=False,original_arc_LP_lower_bound_certified=False,reason='The exact requested scalar is terminal global ObjBound from an interrupted integer MIP. Native root-relaxation message has only 7 significant digits, exact root BestBd was not exposed, original LP receipts store audited primal objectives and points only, and no original-axis LP dual/rational certificate exists in this lineage. Numerical agreement does not establish the necessary lower-bound scope.',root_processing_complete=live['timestamps']['root_processing_complete'],native_root_relaxation_complete=live['timestamps']['root_relaxation_complete'],exact_root_BestBd_observed=False,full_LP_point_keys=full_keys,reduced_LP_point_keys=reduced_keys,source_LP_objective=lp['full']['objective'],source_reduced_LP_objective=lp['reduced']['objective'],MIP_certificate_remains_valid_for_integer_problem=True,requested_value_disproved=False,source_files={name:sha(historical/name) for name in ('M1_SINGLE_THREAD_CERTIFICATE.json','M1_SINGLE_THREAD_SOLVE_RESULT.json','M1_SINGLE_THREAD_CHECKPOINT_AUDIT.json','M1_LIVE_TIMELINE.json','M1_SOLVE.log','ROOT_LP_full.json','ROOT_LP_reduced.json')})
    write('ARC_FLOOR_PROVENANCE_INSPECTION.json',provenance)
    aggregation=dict(PASS=False,dominance_theorem_PASS=True,full_scale_matrix_PASS=True,enumeration_PASS=True,requested_floor=BASE_LB,adopted_floor=None,stop_stage=4,status='STOP_ARC_LP_LOWER_CERTIFICATE_SCOPE_UNVERIFIED',mathematical_rule='If L_arc <= z_arc_LP and z_arc_LP <= z_DW*, and L_corr <= z_DW*, then max(L_arc,L_corr) <= z_DW*. The first premise is not supplied by a global integer-MIP lower bound alone.',counterexample=dict(local_blocks='X1=X2={0,1}',unchanged_global_coupling='x1+x2 >= 1/2',objective='min x1+x2',z_original_integer='1',valid_MIP_lower_bound='1',z_arc_LP='1/2',z_DW_root='1/2',why='A global MIP lower bound can exceed the full DW root. Local convexification does not preserve arbitrary global integer cuts.'),primal_objective_not_used_as_LB=True,empirical_LP_agreement_not_used_as_proof=True,pricing_incumbent_not_used_as_LB=True,source_provenance_SHA=sha(OUT/'ARC_FLOOR_PROVENANCE_INSPECTION.json'))
    write('DW_BOUND_AGGREGATION_PROOF.json',aggregation)
    old=read(PR142/'DW_THROUGHPUT_FINAL.json');L=old['best_corrected_LB'];U=old['smallest_RMP_upper']
    write('DW_PR142_REAGGREGATED_INTERVAL.json',dict(PASS=True,optimized=False,optimize_calls=0,dominance_theorem_PASS=True,independent_floor_adopted=False,floor=None,L_corr_best=L,U_RMP_best=U,certified_interval=[L,U],conditional_interval_if_arc_floor_certified=[max(BASE_LB,L),U],conditional_interval_is_certified=False,reason='Independent scalar floor authority missing; conditional numerical calculation is diagnostic only.',source_SHA=sha(PR142/'DW_THROUGHPUT_FINAL.json')))
    diagnosis(PR142,sorted((PR142/'bound_certificates').glob('ROUND_*.json')))
    audit['preopt_gate_PASS']=False;audit['stop_stage']=4;audit['floor_source_gate']='NOT_PROVEN';write('DW_DOMINANCE_BASE_AUDIT.json',audit)
    write('DW_THRESHOLD_FINAL_CERTIFICATION.json',dict(status='NOT_RUN_PREOPT_GATE_STOP',native_optimize_calls=0,true_dual=None,pricing_receipts=[],L_corr=None,aggregate_lower=None,reason=aggregation['status']))
    write('DW_THRESHOLD_FINAL_RESULT.json',dict(status='STOP_ARC_LP_LOWER_CERTIFICATE_SCOPE_UNVERIFIED',materiality='INCONCLUSIVE',experiment_status='NOT_RUN',stop_stage=4,dominance_proven=True,independent_floor_adopted=False,initial_retained_columns=1158,retained_columns=1158,new_discovery_columns=0,new_RMP_solves=0,new_pricing_calls=0,discovery_rounds=0,certification_rounds=0,columns_per_min=None,discovery_median=None,best_corrected_LB=L,best_certified_LB=L,smallest_RMP_upper=U,final_interval=[L,U],material_threshold=T_MATERIAL,D_U=U-T_MATERIAL,D_L=T_MATERIAL-L,total_optimize_wall_union=0,total_elapsed=None,DW_ROOT_OPTIMAL_CERTIFIED=False,classification=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json')['classification'],diagnosis_scope='PR142 certification receipts only; no new final certification',next_single_blocker='A certified lower bound for the original arc LP on the frozen original axes. Recover an original LP dual certificate before adopting the requested floor.',after_floor_gate_recommendation='Continue fixed four-way smoothed discovery within the registered threshold policy; PR142 exact negative RC dominates proof gap.',May_production=[0,0,0],Branch_and_Price=False))
    write('DW_CHECKPOINT_LATEST.json',dict(status='BASE_CHECKPOINT_RETAINED_NO_OPTIMIZE',pool=checkpoint['pool'],total_retained_columns=1158,column_pool_SHA=axis['pool_SHA'],dual_axis_SHA=axis['dual_axis_SHA'],row_axis_SHA=axis['row_axis_SHA'],source_checkpoint_SHA=sha(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json'),source_checkpoint=str((PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json').relative_to(ROOT)),smoothing=dict(resumed=False,reason='No new RMP; preopt floor gate stopped',next_alpha=checkpoint['restart_state']['smooth_weight'],source_center_file=checkpoint['restart_state']['smooth_file']),best_interval=[L,U],elapsed_budget=0,optimize_intervals=[],pricing_replayed=False,new_columns=[]))
    table('DW_THRESHOLD_DISCOVERY_LEDGER.csv',[])
    table('DW_THRESHOLD_DISTANCE.csv',[dict(point='PR142_RETAINED_CERTIFIED_POINT',U_RMP=U,L_DW_cert=L,D_U=U-T_MATERIAL,D_L=T_MATERIAL-L,material_threshold=T_MATERIAL,lower_floor_adopted=False,new_optimize=False)])
    write('CAMPAIGN_WORKER_POLICY.json',dict(B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,days_per_arm=31,Threads=1,B2_INNER_PRICING_WORKERS=1,B3_INNER_PRICING_WORKERS=4,main=['B0','B1','B2','B3(L1)'],after_main=['B3(L2)','B3(L3)','B3(L4)'],Actual_to_Planning=False,previous_Planning_only=True))
    write('CAMPAIGN_ORCHESTRATOR_PRESERVATION.json',dict(PASS=True,source_old_bytes_unchanged=True,sequence=['A1','M1','A2','M2'],Planning_feedback='Previous Planning only',Actual_to_next_Planning_forbidden=True,new_production_execution=False))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(PASS=True,MAY_PRODUCTION_CALLS=0,Actual_calls=0,Fresh_AC_calls=0,PRODUCTION_M1_RUN=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,BRANCH_AND_PRICE_RUN=False,experiment_optimize_calls=0,enumeration_native_optimize_calls=0,tests_separate=True))
    write('FINAL_FLAGS.json',dict(M1_MODEL_PRESERVED=True,DW_DOMINANCE_PROVEN=True,ARC_ROOT_LB=BASE_LB,ARC_ROOT_LB_SCOPE_VERIFIED=False,DW_PR142_CORRECTED_LB=L,DW_PR142_RMP_UPPER=U,DW_AGGREGATED_LOWER_FLOOR=None,DW_MATERIAL_THRESHOLD=T_MATERIAL,PRICING_BOUND_CLASSIFICATION=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json')['classification'],FOUR_WAY_PRICING=True,FOUR_WAY_PRICING_EXECUTED_THIS_TASK=False,PRICING_THREADS=1,RAM_FLOOR_GIB=1,ADAPTIVE_DUAL_SMOOTHING=True,ADAPTIVE_DUAL_SMOOTHING_EXECUTED_THIS_TASK=False,WARM_RMP_SELECTED=False,DW_NEW_COLUMNS=0,DW_NEW_RMP_ROUNDS=0,DW_NEW_PRICING_CALLS=0,DW_BEST_CERTIFIED_LB=L,DW_BEST_RMP_UPPER=U,DW_FINAL_INTERVAL_LOWER=L,DW_FINAL_INTERVAL_UPPER=U,DW_MATERIALITY='INCONCLUSIVE',BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,B2_INNER_PRICING_WORKERS=1,B3_INNER_PRICING_WORKERS=4,MAY_PRODUCTION_CALLS=0,PROBLEM13_FINAL_VALIDATED=False))
    print('DOMINANCE_GEOMETRY_PASS',len(checks),'FLOOR_GATE_STOP_WITHOUT_OPTIMIZE',flush=True)

def source_freeze():
    names=['DW_THRESHOLD_PREREGISTRATION.json','DW_DOMINANCE_BASE_AUDIT.json','DW_FULL_SCALE_DOMINANCE_PROOF.json','DW_COUPLING_IDENTITY_AUDIT.json','DW_DOMINANCE_ENUMERATION_FIXTURES.json','DW_BOUND_AGGREGATION_PROOF.json','ARC_FLOOR_PROVENANCE_INSPECTION.json']
    sources=sorted((ROOT/'v42_dw_dominance').glob('*.py'))+sorted((ROOT/'tests/v42_dw_dominance').glob('*.py'))
    write('EXECUTION_FREEZE.json',dict(sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],preregistrations={n:sha(OUT/n) for n in names},native_experiment_optimize_forbidden=True,reason='Arc LP lower-floor authority unverified'))

if __name__=='__main__':
    import sys
    if '--freeze-only' in sys.argv:source_freeze()
    elif '--finish-only' in sys.argv:finish_gate(read(OUT/'DW_DOMINANCE_BASE_AUDIT.json'),read(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json'),read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json'),read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_SINGLE_THREAD_SOLVE_RESULT.json'))
    else:prepare()
