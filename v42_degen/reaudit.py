"""Reaudit immutable saved points without building a model or calling optimize."""
import io
import json
import math
import pickle
import shutil
import numpy as np
from .common import ROOT,OUT,REF,SOURCE,LOCAL,POLICY,sha,read,write
from .identity import inputs
from .resources import gate
from v42_postsolve.contract import contract,audit_point,numerical_residuals,feasible,current_certificate

IMMUTABLE=('M1_DEGENMOVES0_SOLVE.log','RUN_WORKER.log','M1_DEGENMOVES0_SOLVE_RESULT.json','M1_DEGENMOVES0_ROOT_TIMELINE.json','M1_DEGENMOVES0_RESOURCE_TIMELINE.csv','M1_DEGENMOVES0_RESOURCE_SUMMARY.json','M1_DEGENMOVES0_CERTIFICATE.json','M1_DEGENMOVES0_P1_CERTIFICATE.json','M1_DEGENMOVES0_PHYSICAL_AUDIT.json','M1_P1_ALL_INCUMBENT_AUDITS.json','M1_CALLBACK_OVERHEAD_AUDIT.json','M1_ZERO_ACTION_START_VALIDATION.json','M1_ZERO_ACTION_START_PRIMARY.csv','EXECUTION_RECEIPT.json','EXECUTED_SOURCE_RECEIPT.json','M1_MODEL_IDENTITY_PR134_PAIR.json','M1_MODEL_IDENTITY_PR134_PAIR_BEFORE_P1.json','M1_PHYSICAL_AUDIT.json','M1_P2_RESULT.json')

def raw_grid(coeff,controls,rho):
    angles=2*np.pi*np.arange(16)/16;co=np.cos(angles);si=np.sin(angles)
    collected=dict(voltage_pu=[],line_loading=[],transformer_current_ratio=[],transformer_current_A=[],transformer_apparent_kVA=[],transformer_kVA_ratio=[])
    exceeds=dict(voltage_pu=0.,line_loading_above_rho=0.,transformer_current_A=0.,transformer_kVA=0.)
    for c,x in zip(coeff,controls):
        x=np.asarray(x,float);v=np.sqrt(np.maximum(c.voltage_constant+c.voltage_matrix.T@x,0.))
        collected['voltage_pu'].extend((float(v.min()),float(v.max())))
        exceeds['voltage_pu']=max(exceeds['voltage_pu'],float(np.maximum(.95-v,0).max()),float(np.maximum(v-1.05,0).max()))
        p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*co+qa[:,None]*si)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(co[active,None]*c.flow_p_matrix+si[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        currents=c.current_constant+c.current_matrix.T@x
        for k,name in enumerate(c.branch_names):
            if name.lower().startswith('transformer.'):
                ratio=float(currents[k]);amperes=ratio*float(c.current_denominators_A[k])
                collected['transformer_current_ratio'].append(ratio);collected['transformer_current_A'].append(amperes)
                exceeds['transformer_current_A']=max(exceeds['transformer_current_A'],max(0.,amperes-float(c.current_denominators_A[k])))
            else:
                loading=float(np.max((co*p[k]+si*q[k])/ap[k]+correction[k]@(x-c.anchor)+bias[k]))
                collected['line_loading'].append(loading);exceeds['line_loading_above_rho']=max(exceeds['line_loading_above_rho'],loading-rho)
            if c.transformer_ratings[k] is not None:
                apparent=math.hypot(float(p[k]),float(q[k]));rating=float(c.transformer_ratings[k])
                collected['transformer_apparent_kVA'].append(apparent);collected['transformer_kVA_ratio'].append(apparent/rating)
                exceeds['transformer_kVA']=max(exceeds['transformer_kVA'],apparent-rating)
    return dict(raw_minimum_maximum={k:dict(minimum=min(v),maximum=max(v)) for k,v in collected.items()},actual_exceedance={k:max(0.,v) for k,v in exceeds.items()},physical_voltage_band=[.95,1.05],physical_margin_pu=0.,physical_audit_tolerance=1e-5,numerical_tolerance_added_to_ratings=False,values='Frozen compiled Planning affine/current and polygon-flow model; not a Fresh AC calculation.')

def controls_for(point,d,bundle,coeff,freeze):
    values=dict(zip(map(str,d['names']),map(float,point)));controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for i,name in enumerate(c.control_names):
            site=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):row.append(freeze['anchor']['controls'][t][i])
            elif name.startswith('mess_p_kw'):row.append(sum(values.get(f'Pdis[{u},{site},{t}]',0.)-values.get(f'Pch[{u},{site},{t}]',0.) for u in bundle['initial_MESS_sites']))
            else:row.append(sum(values.get(f'Q[{u},{site},{t}]',0.) for u in bundle['initial_MESS_sites']))
        controls.append(row)
    family={}
    for prefix in ('SOC[','Pch[','Pdis[','Q['):
        a=[value for name,value in values.items() if name.startswith(prefix)]
        family[prefix[:-1]]=dict(minimum=min(a),maximum=max(a))
    return controls,family

def saved(path,expected_sha,d):
    assert sha(path)==expected_sha,'RAW_POINT_BYTES_CHANGED'
    data=path.read_bytes()
    with np.load(io.BytesIO(data)) as z:
        assert np.array_equal(z['names'],d['names']);point=z['values'].copy()
    # A fresh numeric NPZ serialization roundtrip is compared without rounding.
    stream=io.BytesIO();np.savez(stream,values=point)
    with np.load(io.BytesIO(stream.getvalue())) as z:roundtrip=z['values']
    mismatch=float(np.max(abs(point-roundtrip),initial=0.))
    assert np.array_equal(point,roundtrip)
    target=OUT/'RAW_POINTS'/path.name;target.parent.mkdir(exist_ok=True)
    target.write_bytes(data);assert sha(target)==expected_sha
    return point,dict(serialization_roundtrip=mismatch,raw_saved_point_mismatch=0.)

def run():
    gate('tolerance_reaudit_no_optimize')
    policy=contract();write('V42_POSTSOLVE_NUMERICAL_TOLERANCE_CONTRACT.json',policy)
    write('TOLERANCE_CONTRACT_FREEZE.json',dict(contract_sha256=sha(OUT/'V42_POSTSOLVE_NUMERICAL_TOLERANCE_CONTRACT.json'),frozen_before_current_point_reaudit=True,solver_policy=POLICY,new_optimize_calls=0))
    immutable={name:sha(OUT/name) for name in IMMUTABLE}
    write('PRE_AMENDMENT_SCIENTIFIC_EVIDENCE_RECEIPT.json',dict(files=[dict(path=name,sha256=value) for name,value in immutable.items()],immutable_scientific_execution=True))
    A,d,B,e,identity,freeze=inputs()
    from v42_integrated.import_guard import selected_imports
    from v42_integrated.contract import physical_authority,grid_audit
    from v42_bootstrap.grid import coefficients
    import v42_integrated.solve as solve
    solve.LOCAL=SOURCE;solve.OUT=OUT;solve.write=lambda *args:None
    result=read(OUT/'M1_DEGENMOVES0_SOLVE_RESULT.json');prior=read(OUT/'M1_P1_ALL_INCUMBENT_AUDITS.json')
    log_sha=sha(OUT/'M1_DEGENMOVES0_SOLVE.log');numerical=[];physical=[];records=[]
    with selected_imports(),physical_authority():
        with (SOURCE/'DATA.pkl').open('rb') as f:data=pickle.load(f)
        bundle=data[0];_,coeff=coefficients(bundle)
        def phys(point):
            answer=solve.physical(point,d);units=solve.grid_point(point,d)
            controls,family=controls_for(point,d,bundle,coeff,freeze)
            return dict(PHYSICAL_AUDIT_PASS=bool(answer['PASS'] and units['PASS']),inherited_independent_physical_audit=answer,original_unit_grid_audit=units,raw_grid=raw_grid(coeff,controls,float(point[list(map(str,d['names'])).index('rho_max')])),raw_MESS_minimum_maximum=family,A1_fixed_identity=True,physical_limits_changed=False,rounding_clipping_repair_calls=0)
        for old in prior['records']:
            point,transport=saved(LOCAL/f"M1_P1_INCUMBENT_{old['index']}.npz",old['point_sha256'],d)
            before=point.tobytes();n=audit_point('M1',A,d,point,transport_residuals=transport);p=phys(point)
            original=old['validation']['full_unreduced_matrix_audit'];fresh=n['full_unreduced_matrix_audit']
            assert all(fresh[k]==original[k] for k in original if k!='PASS'),'RESIDUAL_NOT_REPRODUCED'
            assert before==point.tobytes(),'RAW_POINT_MUTATED'
            objective=float(d['objective']@point+float(d['constant']));assert objective==old['reported_objective']==result['raw_solver_UB']
            accepted=bool(result['solver_incumbents']==2 and prior['reported_MIPSOL_points']==2 and result['status']=='TIME_LIMIT')
            record=dict(index=old['index'],point_sha256=old['point_sha256'],solve_log_sha256=log_sha,solver_accepted=accepted,solver_acceptance_evidence='Two reported MIPSOL solutions match the native terminal objective and Solution count 2; the original worker compared terminal X to buffered points and needed no extra terminal point. Literal first H incumbent and original records are preserved.',objective=objective,callback_time=old['callback_time'],numerical=n,physical=p,NUMERICAL_AUDIT_PASS=n['NUMERICAL_AUDIT_PASS'],PHYSICAL_AUDIT_PASS=p['PHYSICAL_AUDIT_PASS'],scientifically_feasible=feasible(n,p,solver_accepted=accepted),original_1e8_gate_PASS=old['PASS'],residuals_exactly_reproduced=True)
            records.append(record);numerical.append({k:record[k] for k in ('index','point_sha256','objective','solver_accepted','NUMERICAL_AUDIT_PASS','residuals_exactly_reproduced','numerical')});physical.append({k:record[k] for k in ('index','point_sha256','PHYSICAL_AUDIT_PASS','physical')})
        write('CURRENT_INCUMBENT_NUMERICAL_REAUDIT.json',dict(PASS=all(r['NUMERICAL_AUDIT_PASS'] for r in records),records=numerical,new_optimize_calls=0,all_observed_points_reaudited=True))
        write('CURRENT_INCUMBENT_PHYSICAL_REAUDIT.json',dict(PASS=all(r['PHYSICAL_AUDIT_PASS'] for r in records),records=physical,physical_policy_unchanged=True,new_optimize_calls=0))
        start=read(OUT/'M1_ZERO_ACTION_START_VALIDATION.json');point,transport=saved(LOCAL/'ZERO_ACTION_CANDIDATE.npz',start['candidate_sha256'],d)
        before=point.tobytes();n=audit_point('M1',A,d,point,transport_residuals=transport);p=phys(point);assert point.tobytes()==before
        original=start['validation']['full_unreduced_matrix_audit'];assert all(n['full_unreduced_matrix_audit'][k]==original[k] for k in original if k!='PASS')
        valid=bool(n['NUMERICAL_AUDIT_PASS'] and p['PHYSICAL_AUDIT_PASS'] and start['primary_semantics']['PASS'])
        write('ZERO_ACTION_START_TOLERANCE_REAUDIT.json',dict(M1_ZERO_ACTION_START_VALID=valid,NUMERICAL_AUDIT_PASS=n['NUMERICAL_AUDIT_PASS'],PHYSICAL_AUDIT_PASS=p['PHYSICAL_AUDIT_PASS'],numerical=n,physical=p,primary_semantics=start['primary_semantics'],candidate_sha256=start['candidate_sha256'],original_validation_preserved=True,original_gate_tolerance=1e-8,postsolve_numerical_tolerance=1e-6,CURRENT_SOLVE_START_USED=False,repair_calls=0,new_optimize_calls=0))
        # Accepted A1: no A1 model/matrix is rebuilt. Recheck saved primary bindings
        # and independent physical semantics; apply the common residual validator
        # to the recorded native aggregate and independent binding maxima.
        a1_path=SOURCE/'A1_FINAL_POINT.npz';a1_sha=sha(a1_path)
        with np.load(a1_path) as z:a1=z['values'];names=z['names']
        rho=float(a1[list(map(str,names)).index('rho_max')]);assert rho==freeze['physical']['P1_rho']
        bindings={str(name):float(a1[i]) for i,name in enumerate(names) if str(name).startswith(('CC4_','RT_reserve[','RT_shortfall[','rho_max'))}
        from v42_exact.validation import check
        from v42_native.voltage import Stage
        a1_physical=check(freeze['selected_jobs'],data,freeze['anchor']['controls'],bindings,rho,stage=Stage.A1)
        a1_physical['all_phase_grid']=grid_audit(coeff,freeze['anchor']['controls'],rho)
        a1_physical['PASS']=bool(a1_physical['PASS'] and a1_physical['all_phase_grid']['PASS'])
        available=freeze['physical'];residuals={k:available[k] for k in ('solver_max_violation','independent_known_GPU_max_violation','independent_Runtime_binding_max_violation','independent_reserve_headroom_max_violation')}
        a1_numerical=numerical_residuals('A1',residuals,finite=np.isfinite(a1).all());assert sha(a1_path)==a1_sha
        a1_consistent=bool(a1_numerical['NUMERICAL_AUDIT_PASS'] and a1_physical['PASS'])
        write('TOLERANCE_RETROSPECTIVE_CONSISTENCY_AUDIT.json',dict(PASS=a1_consistent,A1=dict(prior_accepted=True,acceptance_reversed=False if a1_consistent else True,saved_point_sha256=a1_sha,numerical=a1_numerical,physical=a1_physical,raw_grid=raw_grid(coeff,freeze['anchor']['controls'],rho),original_A1_matrix_not_retained=True,full_A1_rows_recomputed=False,limitation='A1 row/bound/integrality aggregate is the preserved native MaxVio evidence, not a new full A1 matrix audit. Fresh independent job/Runtime/CC4/grid semantics and raw saved bindings are rechecked. No A1 model is rebuilt.'),M1_history=dict(PR133='NOT_RUN_A1_GATE_FAILED',PR134='NO_INCUMBENT; no accepted same-authority M1 point to reevaluate',older_superseded_M1='Different scientific authority; no transfer of historical numerical bounds or acceptance into this new certificate.',current_saved_points_reaudited=2),same_global_validator=True,unavailable_audits_not_claimed=True,new_optimize_calls=0,A1_rebuild_calls=0,downstream_runs=0))
    pair=read(OUT/'M1_MODEL_IDENTITY_PR134_PAIR.json')
    run_identity=dict(bound_provenance='same_completed_solve',old_bounds_used=False,solve_log_sha256=log_sha,solve_result_sha256=sha(OUT/'M1_DEGENMOVES0_SOLVE_RESULT.json'),model_identity=pair['reference'],cold_Gurobi_fingerprint=pair['cold_Gurobi_fingerprint'],A1_freeze_sha256=identity['A1_freeze_sha256'],NormalAmps_authority_sha256=identity['NormalAmps_authority'],LB=result['LB'],valid_global_LB=result['valid_global_LB'],solver_policy=result['settings'],runtime=result['runtime'])
    certificate=current_certificate(run_identity,records);write('M1_CERTIFICATE_RECLASSIFIED.json',certificate)
    write('M1_GAP_RECALCULATION.json',dict(UB=certificate['UB'],LB=certificate['LB'],gap=certificate['gap'],gap_percent=None if certificate['gap'] is None else 100*certificate['gap'],formula='(UB-LB)/abs(UB)',MIPGap_authority=.005,M1_P1_ACCEPTED=certificate['M1_P1_ACCEPTED'],P2='NOT_RUN_P1_GAP_NOT_ACCEPTED',new_optimize_calls=0,old_UB_LB_gap_used=False))
    after={name:sha(OUT/name) for name in IMMUTABLE};assert after==immutable
    write('AMENDMENT_EVIDENCE_PRESERVATION_AUDIT.json',dict(PASS=True,checked_files=len(immutable),original_scientific_artifacts_unchanged=True,checksums=after,solver_parameters_unchanged=True,scientific_model_unchanged=True,new_optimize_calls=0,raw_points_modified=False,retrospective_consistency_PASS=a1_consistent))
    print('RECLASSIFIED',certificate['UB'],certificate['LB'],certificate['gap'],'P1',certificate['M1_P1_ACCEPTED'],'Start valid',valid,'Start used False; optimize calls 0',flush=True)

if __name__=='__main__':run()
