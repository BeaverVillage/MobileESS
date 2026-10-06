"""Saved-evidence forensic only: no model construction or optimize calls."""
from pathlib import Path
import json,csv,hashlib,time,collections
from fractions import Fraction as F
import numpy as np
import psutil
from v42_degen.identity import inputs,digest
from v42_dw_root.partition import axes
from v42_disjunctive.certificate import down

ROOT=Path(__file__).resolve().parent
OLD=ROOT/'docs/v42_m_stage_exact_completion'
OUT=ROOT/'docs/v42_m1_dual_authority_early_bap'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
def table(n,rows,fields):
    with (OUT/n).open('w',encoding='utf8',newline='') as s:w=csv.DictWriter(s,fields);w.writeheader();w.writerows(rows)
def run():
    OUT.mkdir(exist_ok=True);begin=time.perf_counter();p=psutil.Process()
    start_RSS=p.memory_info().rss
    original_files=[f for f in OLD.rglob('*') if f.is_file()]
    preserved={str(f.relative_to(ROOT)):sha(f) for f in original_files}
    write('PR155_BYTE_PRESERVATION.json',dict(base_HEAD='0b557f6318b8192e08ee99102046576e68dd27d4',files=preserved,original_files=len(preserved)))
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json');r42=read(OLD/'RMP_RECEIPT_0042.json');r43=read(OLD/'RMP_RECEIPT_0043.json')
    assert cp['RMP']['round']==42 and len(cp['pool'])==1841
    pointfile=OLD/r42['point_file'];assert sha(pointfile)==r42['point_SHA']
    with np.load(pointfile) as z:point=z['point'];pi=z['pi'];alpha=z['alpha'];weights=z['lambda_values']
    key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();assert key==r42['dual_SHA']
    A,d,B,e,*_=inputs();owner,row_owner=axes();rr=np.flatnonzero(row_owner<0);cc=np.flatnonzero(owner<0)
    matrix=B[rr][:,cc];sense=e['sense'][rr];row_names=e['row_names'][rr]
    assert digest(rr)==cp['dual_axis_SHA'] and digest(row_names)==cp['row_axis_SHA']
    families={}
    for family in sorted(set(str(n).split('[',1)[0] for n in row_names)):
        mask=np.array([str(n).split('[',1)[0]==family for n in row_names]);s=sense[mask];du=pi[mask]
        families[family]=dict(rows=int(mask.sum()),original_senses=dict(zip(*[a.tolist() for a in np.unique(s,return_counts=True)])),
            original_constraint='Original CSR row: A_i,z*z + sum_j a_i,j*lambda_j [original sense] RHS_i',
            original_to_code_negation=False,normalization_multiplier=1.,actual_Gurobi_senses=dict(zip(*[a.tolist() for a in np.unique(s,return_counts=True)])),
            raw_Pi_source=str(pointfile.relative_to(ROOT)),raw_Pi_row_indices_SHA=digest(np.flatnonzero(mask)),
            raw_Pi_min=float(du.min()),raw_Pi_max=float(du.max()),canonical_dual='Pi (identity multiplier 1)',pricing_dual='same raw Pi, not smoothed dual',
            strict_sign_PASS=bool(np.all(du[s=='<']<=0) and np.all(du[s=='>']>=0)),raw_Pi_nonzero_rows=int(np.count_nonzero(du)))
    families['DW_convexity']=dict(rows=4,original_constraint='sum valid trajectory lambda for each MESS = 1',original_senses={'=':4},original_to_code_negation=False,normalization_multiplier=1.,actual_Gurobi_senses={'=':4},raw_Pi=alpha.tolist(),canonical_dual=alpha.tolist(),pricing_dual='alpha[unit], subtracted once from column reduced cost',strict_sign_PASS=True)
    local_senses={}
    for n,s in zip(e['row_names'][row_owner>=0],e['sense'][row_owner>=0]):local_senses.setdefault(str(n).split('[',1)[0],collections.Counter())[str(s)]+=1
    convention=dict(RMP42_same_axis_SHA_PASS=True,original_rows=679955,convexity_rows=4,row_axis_SHA=cp['row_axis_SHA'],dual_axis_SHA=cp['dual_axis_SHA'],
        transformation_SHA=hashlib.sha256(b'identity row transformation; multiplier +1; no normalization').hexdigest(),
        row_families=families,local_pricing_row_families={k:dict(v) for k,v in local_senses.items()},
        fleet_location_route_movement_rows='Original local block constraints; not separate RMP Pi families. Their domain is enforced by original full-domain pricing.',
        branch_rows=dict(rows=0,status='NOT_RUN'),generated_master_rows='Only the four explicit convexity equalities; no early-B&P branch/master row added.',
        Method=2,Crossover=1,terminal_dual='Pi paired with terminal X/RC after crossover; BarPi paired with barrier BarX is not interchangeable',
        RMP43_first_bad_family=None,RMP43_actual_Pi=None,scientific_authority_unresolved=True)
    write('RMP_DUAL_CANONICAL_CONVENTION.json',convention)
    zpoint=point[cc];cost=e['objective'][cc];global_rc=cost-matrix.T@pi
    perunit=[np.flatnonzero(owner==m) for m in range(4)]
    localcost=[e['objective'][cols]-B[rr][:,cols].T@pi for cols in perunit]
    rc_rows=[];column_obj=0.;lambda_bound_min=0.;max_dot_error=0.
    for j,h in enumerate(cp['pool']):
        path=ROOT/h['file'];assert sha(path)==h['file_SHA'];m=int(h['MESS'][-2:])-1
        with np.load(path) as s:
            modern='x' in s;x=s['x'] if modern else s['local_values'];a=s['a'] if modern else s['master_coefficients'];c=float(s['c'] if modern else s['objective'])
        raw=c-float(pi@a)-alpha[m];independent=float(localcost[m]@x)-alpha[m]
        err=abs(raw-independent);max_dot_error=max(max_dot_error,err)
        historical=j<len(weights)
        rc_rows.append(dict(column=j,MESS=h['MESS'],column_SHA=h['column_SHA'],in_RMP42=historical,
            lambda42=float(weights[j]) if historical else 0.,canonical_RC=float(raw),independent_original_domain_RC=float(independent),
            transport_RC_error=err,saved_solver_RC='',solver_RC_semantics_available=False,
            historical_all_native_RC_error_bound=r42['manual_RC_error'] if historical else '',
            PASS_transport=err<=1e-8,terminal_native_RC_identity_PASS='UNRESOLVED_MISSING_NATIVE_RC_VECTOR'))
        if historical:column_obj+=c*weights[j];lambda_bound_min=min(lambda_bound_min,raw)
    table('EXISTING_COLUMN_RC_IDENTITY.csv',rc_rows,list(rc_rows[0]))
    primal=float(cost@zpoint+column_obj+e['constant']);rhs=float(pi@e['rhs'][rr]+alpha.sum()+e['constant'])
    choose=np.where(global_rc>=0,e['lower'][cc],e['upper'][cc]);mask=global_rc!=0
    finite_support=bool(np.all(abs(choose[mask])<1e90) and lambda_bound_min>=0)
    dual=rhs+float(global_rc[mask]@choose[mask]) if finite_support else None
    free=np.flatnonzero((abs(e['lower'][cc])>=1e90)|(abs(e['upper'][cc])>=1e90))
    sd=dict(status='UNRESOLVED_SAVED_BOUND_DUAL_AND_REJECTED_POINT_MISSING',EXACT_DUAL_AUTHORITY_PASS=False,
        primal_RMP42=primal,native_RMP42_objective=r42['objective'],primal_difference=abs(primal-r42['objective']),
        complete_original_bound_support_available_from_manual_residual=finite_support,
        dual_objective_if_available=dual,manual_global_RC_nonzero=int(np.count_nonzero(global_rc)),free_coordinate_max_stationarity_residual=float(np.max(abs(global_rc[free]),initial=0)),
        native_RC_vector_saved=False,native_bound_duals_saved=False,all_1841_native_RC_identity_PASS=False,
        historical_RMP42_native_RC_audit_scalar=r42['manual_RC_error'],RMP42_active_columns=len(weights),retained_pool_columns=len(cp['pool']),
        extra_after_RMP42_columns=len(cp['pool'])-len(weights),manual_two_path_max_RC_error=max_dot_error,
        bTpi_without_bound_terms_used_for_acceptance=False,manual_numerical_identity_not_substituted_for_native_RC=True,
        RMP43_point_saved=False,RMP43_dual_saved=False,fullscale_native_calls=0)
    write('DUAL_STRONG_DUALITY_AUDIT.json',sd)
    diff=dict(last_valid_round=42,rejected_round=43,last_valid_dual_SHA=key,last_valid_point_SHA=r42['point_SHA'],
        rejected_receipt=r43,rejected_log_SHA=sha(OLD/'logs/RMP_0043.log'),
        first_bad_family=None,raw_rejected_Pi_available=False,comparison='UNRESOLVED: rejected X/Pi/RC/matrix-axis snapshot not persisted',
        root_cause_classification='EXACT_SIGN_FAILURE_CAUSE_UNRESOLVED',proven_secondary_defect='Capture-after-assert loses terminal rejected-point evidence',
        no_evidence_for_sign_conversion_negation_bug=True,barrier_numeric_to_optimal_log_observed=True,
        numeric_log_not_proof_of_Pi_sign_error=True,no_replay_or_fullscale_solve=True)
    write('RMP42_RMP_REJECTED_DUAL_DIFF.json',diff)
    # Reconstruct the existing approved corrected formula, not materiality.
    cert=read(OLD/'DW_CONTINUATION_FINAL_CERTIFICATION.json')['certificate']
    recorded=read(OLD/'ROOT_INDEPENDENT_BOUND_CHECK.json')
    value=F(int(recorded['exact_global_numerator']),int(recorded['exact_global_denominator']))
    safe=[F(down(F(float(v))-F(1e-8))) for v in cert['beta_raw']]
    delta=[min(F(0),v) for v in safe]
    with np.load(OLD/'RMP_POINT_0036.npz') as s:alpha36=s['alpha'];pi36=s['pi']
    key36=hashlib.sha256(pi36.tobytes()+alpha36.tobytes()).hexdigest()
    corrected=value+sum((F(float(a))+v for a,v in zip(alpha36,delta)),F(0))
    corrected_ok=key36==cert['dual_SHA'] and down(corrected)==cert['L_corr'] and corrected==F(int(cert['exact_numerator']),int(cert['exact_denominator']))
    write('CORRECTED_BOUND_RECONSTRUCTION.json',dict(PASS=corrected_ok,scope='Saved exact rational global term and same-RMP36 alpha/full-domain pricing bounds; independently recomputed safe/delta arithmetic. Matrix-global term is existing separately audited authority, not re-proven here.',source_SHA=sha(OLD/'ROOT_INDEPENDENT_BOUND_CHECK.json'),dual_SHA=key36,corrected_LB=down(corrected),aggregate_certified_root_LB=.5687115725336208,restricted_LP_not_integer_UB=True,materiality_NOT_RECOMPUTED=True))
    write('FORENSIC_COMPLETION.json',dict(status='STOP_DUAL_AUTHORITY_UNRESOLVED',EXACT_DUAL_AUTHORITY_PASS=False,pricing_calls=0,fullscale_native_calls=0,native_models_built=0,forensic_wall_seconds=time.perf_counter()-begin,RSS_start_bytes=start_RSS,RSS_end_bytes=p.memory_info().rss,RSS_os_high_water_bytes=getattr(p.memory_info(),'peak_wset',None),columns=len(rc_rows),corrected_bound_reconstruction_PASS=corrected_ok))
    print(json.dumps(dict(status='STOP_DUAL_AUTHORITY_UNRESOLVED',rows=len(rr),columns=len(rc_rows),active_RMP42=len(weights),transport_RC_max_error=max_dot_error,corrected_bound=corrected_ok,wall=time.perf_counter()-begin)))
if __name__=='__main__':run()
