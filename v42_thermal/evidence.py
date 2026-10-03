"""All-phase source audit, independent raw reclassification and supersession."""
import numpy as np
from .common import *
from .authority import current_authority,arm_contract,denominators,require_certificate
from .security import classify,require_security_receipt

def month(label,source,count):
    rows=[];files=[];worst=None;old_count=0;old_days=0;oldmax=0.;ledger=[]
    for d in range(1,count+1):
        day=f'2025-{4 if label=="APRIL" else 5:02d}-{d:02d}';path=source/'BUNDLE'/day_folder(day)/'V_ACTUAL_AC.npz'
        before=record(path)
        with np.load(path) as z:raw={k:z[k].copy() for k in z.files}
        result,ratios=classify(raw);names=tuple(map(str,raw['branch_names']))
        mask=np.array([n.startswith('transformer.') for n in names]);oldlimits=denominators(names,old=True)
        # Both old and new classifications are rebuilt from raw amperes.
        oldratios=raw['current_A']/oldlimits;oldbad=oldratios[:,mask]>1
        old_count+=int(oldbad.sum());old_days+=bool(oldbad.any());oldmax=max(oldmax,float(oldratios[:,mask].max()))
        if not np.array_equal(oldratios,raw['current_pu']):raise ValueError('OLD_RAW_CURRENT_DENOMINATOR_DRIFT:'+day)
        if not np.array_equal(ratios[:,~mask],raw['current_pu'][:,~mask]):raise ValueError('LINE_CURRENT_CLASSIFICATION_DRIFT')
        if record(path)!=before:raise ValueError('RAW_ARRAY_BYTES_CHANGED')
        files.append(before)
        row=dict(day=day,slots=raw['current_A'].shape[0],converged=result['converged'],
            old_transformer_current_cells=int(oldbad.sum()),new_transformer_current_cells=result['cells']['transformer_current'],
            voltage_cells=result['cells']['voltage'],line_current_cells=result['cells']['line_current'],
            transformer_kVA_cells=result['cells']['transformer_kVA'],max_transformer_current_pu=result['max_transformer_current_pu'],
            FULL_AC_SECURITY_PASS=result['FULL_AC_SECURITY_PASS']);rows.append(row)
        k=int(np.argmax(ratios[:,mask]));t,j=np.unravel_index(k,ratios[:,mask].shape);ix=np.flatnonzero(mask)[j]
        peak=dict(day=day,slot=int(t),branch_phase=names[ix],current_A=float(raw['current_A'][t,ix]),NormalAmps=float(denominators(names)[ix]),current_pu=float(ratios[t,ix]))
        if worst is None or peak['current_pu']>worst['current_pu']:worst=peak
        for t,ix in zip(*np.where(oldratios>1)):
            if not mask[ix]:continue
            ledger.append(dict(day=day,slot=int(t),branch_phase=names[ix],current_A=float(raw['current_A'][t,ix]),old_limit_A=float(oldlimits[ix]),
                new_limit_A=float(denominators(names)[ix]),old_current_pu=float(oldratios[t,ix]),new_current_pu=float(ratios[t,ix]),new_violation=bool(ratios[t,ix]>1)))
        dest=OUT/'RECLASSIFICATION'/day_folder(day);dest.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(dest/'CURRENT_NORMALAMPS.npz',branch_names=np.array(names),current_pu_NormalAmps=ratios,
            current_denominators_A=denominators(names),transformer_current_authority_sha256=np.array(result['transformer_current_authority_sha256']))
    csv(label+'_DAILY_SECURITY_RECLASSIFICATION.csv',rows)
    if ledger:csv(label+'_OLD_EXCEEDANCE_RECLASSIFICATION_LEDGER.csv',ledger)
    receipt=dict(**arm_contract('B0'),month=label,days=count,slots=sum(r['slots'] for r in rows),
        raw_current_A_used=True,inherited_current_pu_not_used_to_classify=True,new_AC_solves=0,original_arrays_byte_unchanged=True,
        old_transformer_current_violation_cells=old_count,old_transformer_current_violation_days=old_days,old_max_transformer_current_pu=oldmax,
        new_transformer_current_violation_cells=sum(r['new_transformer_current_cells'] for r in rows),
        new_transformer_current_violation_days=sum(r['new_transformer_current_cells']>0 for r in rows),
        max_transformer_current_pu=worst['current_pu'],peak=worst,
        cells={k:sum(r[v] for r in rows) for k,v in dict(voltage='voltage_cells',line_current='line_current_cells',transformer_current='new_transformer_current_cells',transformer_kVA='transformer_kVA_cells').items()},
        days_with_violation={k:sum(r[v]>0 for r in rows) for k,v in dict(voltage='voltage_cells',line_current='line_current_cells',transformer_current='new_transformer_current_cells',transformer_kVA='transformer_kVA_cells').items()},
        converged=all(r['converged'] for r in rows),FULL_AC_SECURITY_PASS=all(r['FULL_AC_SECURITY_PASS'] for r in rows),
        source_files=files,daily=rows,PQ_repair=0,tuning=0)
    if receipt['FULL_AC_SECURITY_PASS']:require_security_receipt(receipt)
    write(OUT,label+'_B0_CURRENT_RECLASSIFICATION.json',receipt)
    return receipt

def planning_evidence():
    # No optimization or new sensitivity solve: reconstruct physical ampere
    # affine coefficients and change only their transformer denominator.
    from v42_may01.prepare import native_coefficients
    from v42_thermal.planning import require_coefficient
    path=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r4_may/e/20250501/V41_ELECTRICAL_CERTIFICATE.json')
    certificate=read(path);before=[record(resolve(r)) for r in certificate['outputs'].values()]
    coeff=native_coefficients(certificate)
    with np.load(resolve(certificate['outputs']['planning_coefficients'])) as z:old={k:z[k].copy() for k in z.files}
    with np.load(resolve(certificate['outputs']['current'])) as z:old_limits=z['rating_a'].copy()
    mask=np.array([str(n).startswith('transformer.') for n in old['branch_names']]);newc=[];newm=[]
    untouched=('voltage_constant','voltage_matrix','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits')
    for t,c in enumerate(coeff):
        require_coefficient(c)
        for field in untouched:
            if not np.array_equal(getattr(c,field),old[field][t]):raise ValueError('NON_CURRENT_PLANNING_FIELD_DRIFT:'+field)
        for field in ('current_constant','current_matrix'):
            new=getattr(c,field);prior=old[field][t]
            if not np.array_equal(new[...,~mask],prior[...,~mask]):raise ValueError('LINE_AFFINE_RESPONSE_DRIFT')
            factor=old_limits/denominators(c.branch_names)
            if not np.array_equal(new[...,mask],prior[...,mask]*factor[mask]):raise ValueError('EXACT_NORMALAMPS_RESPONSE_RESCALE_DRIFT')
        newc.append(c.current_constant);newm.append(c.current_matrix)
    a=current_authority()
    np.savez_compressed(OUT/'PLANNING_CURRENT_RESPONSE_NORMALAMPS.npz',branch_names=old['branch_names'],current_constant=np.array(newc),
        current_matrix=np.array(newm),old_denominators_A=old_limits,current_denominators_A=denominators(old['branch_names']),
        transformer_current_authority_sha256=np.array(a['transformer_current_authority_sha256']))
    write(OUT,'PLANNING_CURRENT_RESPONSE_RESCALE_RECEIPT.json',dict(PASS=True,slots=96,
        source_certificate=record(path),source_outputs=before,source_arrays_unchanged=True,
        transformed_response=record(OUT/'PLANNING_CURRENT_RESPONSE_NORMALAMPS.npz'),
        formula='I_affine_A = old_current_pu * old_rating_A; new_current_pu = I_affine_A / compiled NormalAmps',
        line_current_affine_bit_identical=True,voltage_flow_line_polygon_transformer_kVA_bit_identical=True,
        transformer_kVA_ratings_unchanged=True,current_coefficient_SHA_changed=True,
        optimization_calls=0,new_sensitivity_solves=0,**arm_contract('B0')))

def main():
    if (OUT/'PREREGISTRATION.json').exists():raise ValueError('PREREGISTRATION_ALREADY_SEALED')
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT,'PREREGISTRATION.json',dict(exact_base=BASE,schema=SCHEMA,
        explicit_user_contract='attachment 53d84771-cfc3-4b7c-ae5a-f7b396182599, transformer NormalAmps successor',
        all_transformer_phases=True,invalid_NormalAmps_response='STOP; never synthesize',
        transformer_kVA_line_voltage_control_workload_PQ_unchanged=True,AC_reruns=0,M1_full_solve='NOT_RUN',tuning=0))
    a=current_authority();csv('TRANSFORMER_CURRENT_AUTHORITY_AUDIT.csv',a['rows'])
    csv('LINE_CURRENT_AUTHORITY_UNCHANGED.csv',a['lines'])
    write(OUT,'SOURCE_COMPILED_NORMALAMPS_AUTHORITY.json',a)
    write(OUT,'PLANNING_ACTUAL_CURRENT_AUTHORITY_IDENTITY.json',dict(PASS=True,
        transformer_count=len({r['transformer'] for r in a['rows']}),transformer_phase_count=len(a['rows']),
        Planning_transformer_current_authority_sha256=a['transformer_current_authority_sha256'],
        Actual_transformer_current_authority_sha256=a['transformer_current_authority_sha256'],
        compiled_NormalAmps_authority_sha256=a['transformer_current_authority_sha256'],
        exact_values_equal=True,Planning=a['Planning'],Actual=a['Actual'],arms={arm:arm_contract(arm) for arm in ('B0','B1','B2','B3')}))
    planning_evidence();may=month('MAY',MAY,31);april=month('APRIL',APRIL,30)
    write(OUT,'OLD_NAMEPLATE_LIMIT_SUPERSESSION.json',dict(status='SUPERSEDED',scope='physical transformer phase current hard limit only',
        old='kVA/(sqrt(3)*kV) or single-phase kVA/kV',new=SCHEMA,
        transformer_kVA_still_hard=True,line_ratings_not_superseded=True,
        archived_PR128_PR129_PR130_evidence_preserved=True,existing_receipts_rewritten=False))
    try:require_certificate(dict(UB=.5912812634331275,LB=.5722125039436496))
    except ValueError as e:old_rejected=str(e)
    else:raise ValueError('OLD_M1_CERTIFICATE_REUSE_NOT_REJECTED')
    write(OUT,'M1_AUTHORITY_IMPACT.json',dict(old_M1_current_authority='SUPERSEDED',scientific_model_changed=True,
        old_UB=.5912812634331275,old_LB=.5722125039436496,old_UB_LB_gap_valid_for_new_model=False,
        old_certificate_authority_gate='REJECTED',gate_reason=old_rejected,
        new_model_authority_sha256=a['transformer_current_authority_sha256'],separate_followup_M1_solve_required=True,
        new_M1_UB=None,new_M1_LB=None,new_M1_gap=None,M1_full_solve='NOT_RUN',
        PR126_diagnostic_evidence='HISTORICAL_PRESERVED',old_routes_as_future_seed='only after independent new-model feasibility validation; no inherited bound certificate transfer'))
    write(OUT,'FINAL_FLAGS.json',dict(NORMALAMPS_AUTHORITY_PASS=True,
        MAY_B0_FULL_AC_SECURITY_PASS=may['FULL_AC_SECURITY_PASS'],APRIL_B0_FULL_AC_SECURITY_PASS=april['FULL_AC_SECURITY_PASS'],
        Planning_Actual_authority_identical=True,OLD_M1_CERTIFICATE_SUPERSEDED=True,M1_RECALCULATION_REQUIRED=True,
        B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',
        PQ_repair=0,tuning=0,AC_reruns=0,FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    (OUT/'TRANSFORMER_CURRENT_CONTRACT.md').write_text('''# V42 common physical security successor

All B0/B1/B2/B3 use four independent physical constraints:
- Actual voltage: 0.95–1.05 pu (Planning stage-specific voltage bands are unchanged).
- Line phase current: existing source-backed Line NormAmps; existing thermal polygons unchanged.
- Transformer phase current: parent-terminal abs(I_A) <= compiled OpenDSS NormAmps.
- Transformer apparent power: unchanged source-backed winding kVA rating.

Current uses first-winding NormAmps only because every oriented transformer parent is terminal 1; otherwise STOP. Missing/nonfinite/nonpositive NormalAmps means STOP. CTPrim, taps, RegControl settings and synthetic line-rating files never supply a transformer-current denominator. Compiled defaults are source-backed by exact DSS graph and engine version, not generated replacement limits.

Planning affine constants and gradients are denormalized using the exact archived rating_a then renormalized by NormalAmps. Only transformer-current columns change. Native and compressed transformer_current <= 1 rows consume these bound coefficients. Line current columns, all voltage/flow/branch-limit arrays and transformer-kVA rows remain unchanged. Coefficient/current-authority hashes change; mismatching or unbound real IEEE123 rows fail the current-authority gate. Small synthetic row-geometry fixtures do not claim a compiled physical authority.

Actual source().branch_measurement routes to v42_thermal.measurement and uses the same authority SHA; the old external measurement is retained under legacy_branch_measurement for explicit historical auditing only. New Fresh AC receipts and May Planning freezes carry the current contract/SHA. Reclassification validates all four constraints from immutable raw arrays, not prior current_pu labels. Old evidence is preserved and is not relabeled in place.

Old M1 UB/LB/gap certificates are historical and SUPERSEDED for this changed scientific model. require_certificate rejects missing or unequal current authority/schema. A separate successor M1 solve is required; no full M1 solve is run here. P1/P2, voltage margins, line limits, transformer kVA, controllers, capacitors, P/Q, workloads, Runtime/CC4 and capacity queue are unchanged.
''',encoding='utf8',newline='\n')
    (OUT/'FINAL_REVIEW_KO.md').write_text(f'''# Transformer NormalAmps contract 변경

PR130 exact BASE `{BASE}`. transformer {len({r['transformer'] for r in a['rows']})}개 / phase {len(a['rows'])}개 모두 source-backed NormalAmps 유효. Planning/Actual compiled 값 및 SHA `{a['transformer_current_authority_sha256']}` 동일.

reg1a current 한계는 693.930612006762 A(5000/(√3×4.16) nameplate 역산)에서 763.323673207438 A(compiled NormAmps)로 변경. CTPrim=700 및 taps는 thermal 분모가 아니다. transformer kVA와 line ratings는 그대로다.

May {may['days']}일/{may['slots']} slots: transformer current old {may['old_transformer_current_violation_cells']} cells/{may['old_transformer_current_violation_days']} days → new {may['new_transformer_current_violation_cells']} cells/{may['new_transformer_current_violation_days']} days. new max current pu={may['max_transformer_current_pu']}. voltage/line/kVA cells={may['cells']['voltage']}/{may['cells']['line_current']}/{may['cells']['transformer_kVA']}. MAY_B0_FULL_AC_SECURITY_PASS={may['FULL_AC_SECURITY_PASS']}.

April {april['days']}일/{april['slots']} slots: transformer current {april['new_transformer_current_violation_cells']} cells/{april['new_transformer_current_violation_days']} days, new max current pu={april['max_transformer_current_pu']}. voltage/line/kVA cells={april['cells']['voltage']}/{april['cells']['line_current']}/{april['cells']['transformer_kVA']}.

기존 raw OpenDSS current/voltage/kVA/PQ/Planning evidence를 보존하고 raw current_A에서 old/new 분류를 독립 계산했다. 새 AC solve나 repair/tuning은 없다. Planning current-response만 정확한 분모 변환을 수행했고 비-current 및 line current 계수는 bit 동일하다.

기존 M1 current authority/certificate는 **SUPERSEDED**. UB=0.5912812634331275, LB=0.5722125039436496 및 gap을 새 모델에 재사용하지 않는다. 새 SHA identity gate에서 거부한다. 후속 M1 재계산 필요; M1 full solve NOT_RUN. B1/B2/B3/A2/M2 NOT_RUN. FINAL_MARGIN_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false.

full pytest, exact BASE evidence 보존 및 git/index 검증은 TEST_RECEIPT.json/VERIFICATION.json/SHA256_MANIFEST.json에 기록한다.
''',encoding='utf8',newline='\n')
    print('NormalAmps source audit PASS; May',may['cells'],'April',april['cells'],flush=True)

if __name__=='__main__':main()
