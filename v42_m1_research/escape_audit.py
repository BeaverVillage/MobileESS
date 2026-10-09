"""Read-only optimize=0 cut escape and objective-projection diagnostics.

No model builder, optimizer, parameter, callback or experiment plan is imported
or changed. Historical completed-M blobs are read in memory. Only this module's
two new reports are written; unfinished native outputs are never examined.
"""
from fractions import Fraction as Q
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
from time import perf_counter
from types import SimpleNamespace
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'docs/v42_m1_joint_gap_research'
M_HEAD='4b19e85089171729a3225529a40cb00bf31f43d5'
HIST='docs/v42_m1_gap_rootcause_20261007/'


def _blob(path):
    raw=subprocess.check_output(['git','show',M_HEAD+':'+path],cwd=ROOT)
    return raw,dict(head=M_HEAD,path=path,sha256=sha256(raw).hexdigest(),read_mode='COMPLETED_GIT_BLOB_IN_MEMORY')


def _json_blob(path):
    raw,receipt=_blob(path)
    return json.loads(raw),receipt


def _npz_blob(path):
    raw,receipt=_blob(path)
    with np.load(BytesIO(raw),allow_pickle=False) as z:data={k:z[k].copy() for k in z.files}
    return data,receipt


def _file_sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _load_case_read_only():
    identity=json.loads((REPORTS/'SCIENTIFIC_MODEL_IDENTITY.json').read_text(encoding='utf-8'))
    out=ROOT/'docs/v42_m1_ultracompact_exact_20261006'
    parent=ROOT/'docs/v42_m1_supercompact_exact_20261006'
    source=ROOT/'artifacts/v42_unified/sources/C/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL'
    paths=[(out/'C3A_A.npz','C3A_matrix_sha256'),(out/'C3A_DATA.npz','C3A_data_sha256'),
        (source/'FULL_A.npz','original_matrix_sha256'),(source/'FULL_DATA.npz','original_data_sha256'),
        (parent/'C2_RETAINED_AXES.npz','retained_columns_sha256'),
        (parent/'C2_ELIMINATION_CERTIFICATES.json','alias_sha256')]
    for path,key in paths:
        if _file_sha(path)!=identity[key]:raise ValueError('READ_ONLY_ESCAPE_CASE_IDENTITY_DRIFT:'+key)
    with np.load(out/'C3A_DATA.npz') as z:d={k:z[k].copy() for k in z.files}
    with np.load(source/'FULL_DATA.npz') as z:original_d={k:z[k].copy() for k in z.files}
    with np.load(parent/'C2_RETAINED_AXES.npz') as z:columns=z['columns'].copy()
    aliases=json.loads((parent/'C2_ELIMINATION_CERTIFICATES.json').read_text(encoding='utf-8'))
    def lift(point):
        x=np.zeros(identity['C1_columns'])
        known=np.zeros(len(x),dtype=bool)
        x[columns]=point;known[columns]=True
        for record in reversed(aliases):
            j=int(record['column'])
            if known[j]:raise ValueError('ESCAPE_ALIAS_DUPLICATE')
            value=float(record['constant'])
            for key,weight in record['terms'].items():
                k=int(key)
                if not known[k] or weight!=1.:raise ValueError('ESCAPE_ALIAS_TRANSPORT_NOT_CERTIFIED')
                value+=x[k]
            x[j]=value;known[j]=True
        if not known.all():raise ValueError('ESCAPE_ALIAS_TRANSPORT_INCOMPLETE')
        return x[:len(original_d['names'])].copy()
    return SimpleNamespace(A=sparse.load_npz(out/'C3A_A.npz'),d=d,
        original_A=sparse.load_npz(source/'FULL_A.npz'),original_d=original_d,
        lift=lift,case_sha=identity['case_sha'],identity=identity)


def lp_replay(A,d,point,tolerance,*,label):
    """Original continuous-row replay; integrality is reported, never required.

    Close threshold comparisons use exact dyadic sparse products. Raw residual
    and tolerance have separate fields, so a tolerant PASS is not exact zero.
    """
    start=perf_counter();x=np.asarray(point,dtype=float);A=A.tocsr()
    if x.shape!=(A.shape[1],) or not np.isfinite(x).all():
        return dict(PASS=False,label=label,reason='WRONG_AXIS_OR_NONFINITE')
    tol=np.full(A.shape[0],float(tolerance)) if np.ndim(tolerance)==0 else np.asarray(tolerance,dtype=float)
    residual=A@x-d['rhs'];senses=d['sense']
    violation=np.where(senses=='=',abs(residual),np.where(senses=='<',residual,-residual))
    count=np.diff(A.indptr);eps=np.finfo(float).eps
    gamma=(2*count+4)*eps/(1-(2*count+4)*eps)
    error=np.nextafter(gamma*((abs(A)@abs(x))/(1-gamma)+abs(d['rhs'])),np.inf)
    uncertain=np.flatnonzero((violation+error>tol)&(violation-error<=tol))
    failures=set(map(int,np.flatnonzero(violation-error>tol)))
    for i in uncertain:
        a,b=A.indptr[i:i+2]
        exact=sum((Q(float(w))*Q(float(x[j])) for j,w in zip(A.indices[a:b],A.data[a:b])),Q(0))-Q(float(d['rhs'][i]))
        exact=abs(exact) if senses[i]=='=' else exact if senses[i]=='<' else -exact
        if exact>Q(float(tol[i])):failures.add(int(i))
    bounds=max(0.,float(np.max(d['lower']-x)),float(np.max(x-d['upper'])))
    discrete=np.flatnonzero(d['types']!='C')
    integer=float(np.max(abs(x[discrete]-np.rint(x[discrete])),initial=0.))
    worst=np.argsort(violation)[-8:][::-1]
    values,counts=np.unique(tol,return_counts=True)
    return dict(PASS=not failures and bounds<=1e-8,label=label,rows=A.shape[0],columns=A.shape[1],
        raw_maximum_row_violation=max(0.,float(violation.max(initial=0.))),
        row_tolerances=[dict(tolerance=float(v),row_count=int(c)) for v,c in zip(values,counts)],
        bound_tolerance=1e-8,raw_maximum_bound_violation=bounds,
        fractional_integrality_residual=integer,integrality_required=False,
        failing_row_count=len(failures),failing_rows=sorted(failures)[:20],
        exact_dyadic_threshold_checks=len(uncertain),
        worst_rows=[dict(row=int(i),name=str(d['row_names'][i]),raw_violation=float(violation[i]),tolerance=float(tol[i])) for i in worst],
        objective=float(d['objective']@x+float(d['constant'])),
        native_optimize_calls=0,replay_wall_seconds=perf_counter()-start)


def _mode_interval(A,d,x,column):
    lo,hi=Q(float(d['lower'][column])),Q(float(d['upper'][column]));csc=A.tocsc()
    rows=csc.indices[csc.indptr[column]:csc.indptr[column+1]]
    for i in rows:
        a,b=A.indptr[i:i+2];terms=list(zip(A.indices[a:b],A.data[a:b]))
        coefficient=next(Q(float(w)) for j,w in terms if int(j)==column)
        other=sum((Q(float(w))*Q(float(x[j])) for j,w in terms if int(j)!=column),Q(0))
        bound=(Q(float(d['rhs'][i]))-other)/coefficient
        sense=str(d['sense'][i])
        if sense=='=':lo=max(lo,bound);hi=min(hi,bound)
        elif (sense=='<' and coefficient>0) or (sense=='>' and coefficient<0):hi=min(hi,bound)
        else:lo=max(lo,bound)
    return dict(row_count=len(rows),minimum_exact=str(lo),maximum_exact=str(hi),
        minimum=float(lo),maximum=float(hi),interval_nonempty=lo<=hi),lo,hi


def historical_mode_escape(case):
    control,rc=_json_blob(HIST+'MODE_COORDINATE_CAUSAL_CONTROL.json')
    separator,rs=_json_blob(HIST+'MESS04_69_72_COMMON_MODE_SEPARATION.json')
    before,rb=_npz_blob('docs/v42_m1_root_gap_attribution_20261007/PURE_LP_POINT.npz')
    after,ra=_npz_blob(HIST+'MODE_RELABELED_PROXY_POINT.npz')
    x,y=before['x'],after['x']
    if x.shape!=(case.A.shape[1],) or y.shape!=x.shape:raise ValueError('PR169_POINT_AXIS_DRIFT')
    mask=np.char.startswith(case.d['names'],'charge_mode[')
    bit_identical=x[~mask].tobytes()==y[~mask].tobytes()
    objective_before=float(case.d['objective']@x+float(case.d['constant']))
    objective_after=float(case.d['objective']@y+float(case.d['constant']))
    original_x,original_y=case.lift(x),case.lift(y)
    original_mask=np.char.startswith(case.original_d['names'],'charge_mode[')
    original_bit_identical=original_x[~original_mask].tobytes()==original_y[~original_mask].tobytes()
    lookup={str(n):j for j,n in enumerate(case.original_d['names'])}
    cut=next(r for r in separator['results'] if r['slot']==71)
    def evaluate(point):
        return sum((Q(weight)*Q(float(point[lookup[name]])) for name,weight in cut['physical_terms'].items()),Q(0))-Q(cut['rhs'])
    pre,post=evaluate(original_x),evaluate(original_y)
    j=int(np.flatnonzero(case.d['names']=='charge_mode[MESS04,71]')[0])
    interval,lo,hi=_mode_interval(case.A,case.d,x,j)
    native_interval_contains_proxy=lo<=Q(float(y[j]))<=hi
    replays={}
    full_families=np.asarray([str(n).split('[',1)[0] for n in case.original_d['row_names']])
    mixed=np.where(np.isin(full_families,['flow','terminal_location','voltage_lower','voltage_upper','NormalAmps','line_thermal_face','transformer_kVA']),1e-8,1e-6)
    for name,point,original in [('before',x,original_x),('after',y,original_y)]:
        replays[name]=dict(C3A_strict=lp_replay(case.A,case.d,point,1e-8,label='C3A_M_SCIENTIFIC_1e-8'),
            original_full_strict=lp_replay(case.original_A,case.original_d,original,1e-8,label='ORIGINAL_ALL_ROWS_1e-8'),
            original_full_preserved_mixed=lp_replay(case.original_A,case.original_d,original,mixed,label='ORIGINAL_PRESERVED_ROW_TOLERANCES'),
            original_full_1e6_diagnostic=lp_replay(case.original_A,case.original_d,original,1e-6,label='LOOSER_ALL_ROWS_DIAGNOSTIC_NOT_ADOPTED'))
    full_pass=all(replays[q]['C3A_strict']['PASS'] and replays[q]['original_full_preserved_mixed']['PASS'] for q in ('before','after'))
    escape=bit_identical and original_bit_identical and objective_before==objective_after and pre>0 and post<=0 and native_interval_contains_proxy and full_pass
    return dict(history='PR169_COMPLETED_EVIDENCE_NOT_NEW_SOLVE',case_sha=case.case_sha,
        performed=True,native_optimize_calls=0,Native_Runtime_added_seconds=0,
        status='AUXILIARY_ESCAPE_FOUND' if escape else 'NUMERICAL_FAIL_SEPARATOR_REMOVED_ONLY',
        AUXILIARY_ESCAPE_FOUND=escape,source_receipts=[rc,rs,rb,ra],
        physical_PQ_route_SOC_grid_rho_bit_identical=bit_identical,
        original_full_non_mode_coordinates_bit_identical=original_bit_identical,
        old_mode=float(x[j]),new_mode=float(y[j]),objective_before=objective_before,objective_after=objective_after,
        exact_cut_violation_before=str(pre),exact_cut_violation_after=str(post),
        cut_violation_before=float(pre),cut_violation_after=float(post),
        native_mode_interval_with_all_other_coordinates_fixed=interval,
        proxy_mode_in_native_mode_interval=native_interval_contains_proxy,
        full_original_LP_replays=replays,original_LP_strict_numerical_failure_separately_preserved=not full_pass,
        integer_feasibility_claimed=False,full_four_slot_hull_membership_claimed=False,
        new_UB_or_LB_claimed=False,stored_producer_values_are_not_the_current_verification=control['strict_C3A_raw_after'],
        interpretation='The selected separator is removed by one objective-zero mode coordinate, but strict global LP feasibility is independently required before accepting an auxiliary escape witness.')


def count_route_fixed_audit(case,run_path):
    """Equality proof: fixed complete route_flow fixes counted node_activity."""
    root,receipt=_npz_blob('docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz')
    snapshot=run_path/'JOINT_DISJUNCTION_RESULT.json'
    completed=json.loads(snapshot.read_text(encoding='utf-8')) if snapshot.exists() else None
    proof=completed['cover'] if completed else None
    if proof is None:
        names=[f'node_activity[MESS0{u},IDC09,{t}]' for t in (70,86) for u in range(1,5)]
        index={str(n):j for j,n in enumerate(case.d['names'])}
        columns=[index[n] for n in names]
        source='PRE_REGISTERED_COUNT_SELECTION_FROM_SAVED_ROOT; LEAF_RESULTS_PENDING'
    else:
        columns=proof['original_binary_columns'];names=[str(case.d['names'][j]) for j in columns]
        source='COMPLETED_COUNT_COVER_RECEIPT'
    definitions=[];rows=case.A.tocsc()
    for j in columns:
        if case.d['types'][j]!='B':raise ValueError('COUNT_ESCAPE_NOT_ORIGINAL_BINARY')
        candidates=[]
        for i in rows.indices[rows.indptr[j]:rows.indptr[j+1]]:
            if str(case.d['row_names'][i]).split('[',1)[0]!='node_activity_link' or case.d['sense'][i]!='=':continue
            a,b=case.A.indptr[i:i+2];terms=list(zip(case.A.indices[a:b],case.A.data[a:b]))
            coefficient=next(Q(float(w)) for k,w in terms if int(k)==int(j))
            if coefficient==0 or any(not str(case.d['names'][k]).startswith('route_flow[') for k,w in terms if int(k)!=int(j)):
                continue
            candidates.append(dict(row=int(i),node_column=int(j),node_name=str(case.d['names'][j]),
                exact_node_coefficient=str(coefficient),original_rhs_exact=str(Q(float(case.d['rhs'][i]))),
                route_columns=[int(k) for k,w in terms if int(k)!=int(j)],
                exact_route_coefficients=[str(Q(float(w))) for k,w in terms if int(k)!=int(j)]))
        if len(candidates)!=1:raise ValueError('COUNT_ROUTE_FIXED_DEFINITION_NOT_UNIQUE')
        definitions.append(candidates[0])
    value=sum((Q(float(root['x'][j])) for j in columns),Q(0))
    split=int(np.floor(float(value)))
    return dict(performed=True,verification_level='EXACT_ORIGINAL_NODE_ACTIVITY_EQUALITY_STRUCTURE',
        native_optimize_calls=0,Native_Runtime_added_seconds=0,case_sha=case.case_sha,
        status='NO_AUXILIARY_ESCAPE_WITH_COMPLETE_ROUTE_FLOW_FIXED_PROVED',
        source=source,root_source_receipt=receipt,columns=columns,names=names,
        root_count_exact=str(value),root_count=float(value),leaf_senses=['<','>'],leaf_rhs=[split,split+1],
        node_equalities=definitions,all_other_auxiliary_variables_may_vary=True,
        mode_only_change_cannot_change_count=True,
        theorem='Each counted node has a nonzero-coefficient native equality containing only itself and route_flow. Holding every route_flow fixed determines that node exactly. Changing charge_mode or grid auxiliaries cannot move its count into either integer halfspace.',
        original_rows_retained_96_slot=True,
        counterfactual_fixed_physical_LP_solve=dict(status='NOT_RUN',reason='Exact equality structure resolves route-fixed count invariance without optimization; no new solver call authorized by this audit'),
        allowing_route_reallocation_with_fixed_injections=dict(status='NOT_RUN',proof='NOT_PROVEN'),
        completed_result=completed)


def finalize(case=None,run_path=None):
    """Finite snapshot; rerun after completed leaves without polling or solves."""
    started=perf_counter();case=_load_case_read_only() if case is None else case
    run_path=Path(run_path or ROOT/'runtime/v42_m1_joint_gap_research/joint_gap_20261008').resolve()
    if not run_path.is_relative_to(ROOT.resolve()):raise ValueError('D_V42_AUDIT_RUN_REQUIRED')
    history=historical_mode_escape(case)
    count=count_route_fixed_audit(case,run_path)
    completed=count.pop('completed_result')
    cut_audit=dict(schema='V42_READ_ONLY_CUT_ESCAPE_AUDIT_V1',case_sha=case.case_sha,
        Native_optimize_added_calls=0,Native_Runtime_added_seconds=0,performed=True,
        historical_PR169=history,new_four_fleet_two_time_count=count,
        current_solver_or_run_files_modified=False,mode_escape_counterfactual_solve='NOT_RUN',
        new_leaf_results='COMPLETED_SNAPSHOT_READ' if completed else 'PENDING_NO_WAIT',
        no_new_fractional_point_is_an_integer_UB_claim=True)
    projection=dict(schema='V42_READ_ONLY_OBJECTIVE_PROJECTION_AUDIT_V1',case_sha=case.case_sha,
        Native_optimize_added_calls=0,Native_Runtime_added_seconds=0,performed=True,
        historical_mode_cut=dict(mode_objective_coefficient=0.,selected_cut_mode_coefficient='1',
            auxiliary_coordinate_relabel_removes_selected_violation=history['cut_violation_after']<=0,
            same_physical_injection_and_rho=history['physical_PQ_route_SOC_grid_rho_bit_identical'],
            strict_original_LP_validity=not history['original_LP_strict_numerical_failure_separately_preserved'],
            physical_projection_necessary_condition='support(Pch,Pdis,Q,stay) + minimum_native_compatible_mode <= 1',
            minimum_native_compatible_mode=history['native_mode_interval_with_all_other_coordinates_fixed']['minimum_exact'],
            projection_status='LOCAL_FIXED_PHYSICAL_POINT_INTERVAL_ANALYSIS_GLOBAL_RHO_FORM_NOT_PROVEN',
            projected_inequality_added=False,new_rho_direct_inequality_validity='NOT_PROVEN'),
        new_count_cut=dict(exact_route_projection='sum of counted node_activity equals sum of the native arrival route_flow expressions recorded in CUT_ESCAPE_AUDIT',
            exact_fixed_route_escape_impossibility_proved=True,charge_mode_in_cut=False,
            direct_PQ_or_rho_coefficient_in_count_row=False,
            route_reallocation_can_preserve_grid_injections='NOT_PROVEN',
            objective_projection_counterfactual_solve='NOT_RUN',new_stronger_physical_rho_inequality='NOT_PROVEN'),
        bound_effect=dict(status='PENDING_NO_WAIT' if completed is None else 'COMPLETED_PRODUCER_CERTIFICATES_READ_FINAL_INDEPENDENT_CHECK_REQUIRED',
            actual_new_optimization_by_this_audit=False,
            stronger_native_LP_objective_is_not_an_independent_global_bound=True),
        current_solver_or_run_files_modified=False)
    projected_file=REPORTS/'GRID_ROW_PQ_PROJECTION_PROOF.json'
    if projected_file.exists():
        projected=json.loads(projected_file.read_text(encoding='utf-8'))
        if projected['case_sha']!=case.case_sha:raise ValueError('PQ_PROJECTION_AUDIT_SCIENTIFIC_CASE_DRIFT')
        projection['original_grid_PQ_projection']=dict(performed=True,
            status=projected['status'],evidence_path=str(projected_file),evidence_sha256=_file_sha(projected_file),
            exact_original_rows=projected['fixed_scientific_rows'],
            independent_exact_coefficient_RHS_recombination_PASS=projected['independent_recombination_checker']['PASS'],
            physical_rho_requirement_diagnostics=projected['point_diagnostics'],
            native_optimize_added_calls=0,equivalent_original_row_only=True,
            stronger_LB_or_new_cut_claimed=False,model_addition=False)
    if completed:
        projection['bound_effect'].update(
            source_path=str(run_path/'JOINT_DISJUNCTION_RESULT.json'),source_sha256=_file_sha(run_path/'JOINT_DISJUNCTION_RESULT.json'),
            producer_reported_original_certified_LB=completed.get('baseline_independently_certified_global_LB'),
            producer_reported_complete_cover_global_LB=completed.get('independently_certified_global_LB'),
            producer_reported_material_gain=completed.get('material_global_gain_over_best_certified_original_ROOT'),
            leaf_values=[dict(leaf=r['leaf'],native_LP_objective=r['native'].get('objective'),
                native_diagnostic_bound=r['native'].get('native_solver_bound_diagnostic'),
                independent_certificate_value_as_reported=r['independently_certified_leaf_LB'],
                selected_kind=r['selected_certificate_kind']) for r in completed.get('leaves',[])])
    cut_audit['audit_wall_seconds']=perf_counter()-started
    from v42_unified.audit import write
    write(REPORTS/'CUT_ESCAPE_AUDIT.json',cut_audit)
    write(REPORTS/'OBJECTIVE_PROJECTION_AUDIT.json',projection)
    return dict(CUT_ESCAPE_AUDIT=cut_audit,OBJECTIVE_PROJECTION_AUDIT=projection)


if __name__=='__main__':
    result=finalize()
    print('CUT_ESCAPE_AUDIT',result['CUT_ESCAPE_AUDIT']['historical_PR169']['status'],
        result['CUT_ESCAPE_AUDIT']['new_leaf_results'],'NATIVE_ADDED=0')
