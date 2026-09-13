"""Issue a numerical preflight gate only after every saved audit passes."""
from electrical_engine import *
from datetime import datetime,timezone

def main():
    frozen_check()
    required=['B0_REPLAY/SUMMARY.json','SIGNED_PERTURBATION_VALIDATION.json','FULL_MODEL_SEED_COMPLETE.json','FULL_LOGICAL_B1_SEED_AUDIT.json','NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json','ALL_60_CONTROL_COLUMN_BINDING_AUDIT.json','MESS_24_SERVICE_PCC_COLUMN_BINDING.json','P1_EXACT_B0_WITNESS_BINDING.json','IMMUTABLE_AUTHORITIES_VERIFIED.json','full_model/core/POLICY_FEASIBLE_SEED_AUDIT.json']
    required.extend(['FULL_PRECISION_ELECTRICAL_ROW_AUDIT.json','export_recovery/SHARED_MODEL_SEED_IDENTITY.json','export_recovery/core/MODEL_PERSISTENCE.json'])
    audits={p:read(H/p) for p in required}
    assert all(v['status']=='PASS' for v in audits.values())
    assert audits['FULL_MODEL_SEED_COMPLETE.json']['Gurobi_optimization_calls']==0
    for name in ['GENERATION_CODE_FREEZE.json','VALIDATION_CODE_FREEZE.json','FULL_MODEL_CODE_FREEZE_V2.json','EXPORT_RECOVERY_CODE_FREEZE.json']:
        for r in read(H/name)['files']:assert sha(r['path'])==r['sha256'],r['path']
    model=audits['FULL_LOGICAL_B1_SEED_AUDIT.json'];identity=audits['NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json']
    assert model['electrical_blocks']==96 and model['electrical_linear_rows']==31945536
    blocks=[read(H/f'full_model/electrical_blocks/slot_{t:02}/BLOCK_AUDIT.json') for t in range(96)]
    assert all(b['status']=='PASS' and b['linear_rows']==332766 for b in blocks)
    for b in blocks:
        for key in ('matrix','data'):assert sha(b[key]['path'])==b[key]['sha256']
    original=read(BIND/'IEEE8500_B1/STRUCTURE.json')
    assert model['core_linear_rows']==original['linear_constraints'] and model['core_general_rows']==original['general_constraints']
    assert model['original_core_audit']['matrix_nonzeros']==original['matrix_nonzeros']
    assert identity['variable_count']==original['variable_count']
    residual={k:max([model['original_core_audit']['residual_extrema'][k]]+[b['seed_audit']['residual_extrema'][k] for b in blocks]) for k in ('linear','bounds','integrality','general')}
    precision=audits['FULL_PRECISION_ELECTRICAL_ROW_AUDIT.json']
    residual['linear']=max(residual['linear'],precision['maximum_full_precision_linear_residual'])
    assert max(residual.values())<=1e-9
    corefiles=[record(p) for p in sorted((H/'full_model/core').glob('*')) if p.is_file()]
    corefiles.extend(record(p) for p in sorted((H/'export_recovery/core').glob('*')) if p.is_file())
    save(H/'FULL_JOINT_MODEL_COMPONENT_MANIFEST.json',dict(status='PASS',model='One logical original V41R4 B1 with complete IEEE8500 electrical rows',core_files=corefiles,core_variables=model['global_core_variables'],core_linear_rows=model['core_linear_rows'],core_general_rows=model['core_general_rows'],electrical_rows=model['electrical_linear_rows'],total_logical_linear_rows=model['total_logical_linear_rows'],shared_variable_rule='Each electrical block column binds by exact original global PCC[slot,AIDCxx] variable name, and the same single rho_max. MESS controls are fixed to zero for this B1 seed. No separate per-slot decisions or optimization.',row_retention='Every physical axis and 16 polygon faces per current/kVA axis; both voltage bounds; no coefficient sparsification',monolithic_resident=False,seed_validation='Original row_audit on core and all actual Gurobi block models with one shared global seed; exact affine auxiliary elimination',max_seed_residuals=residual,blocks=model['blocks']))
    generation=read(H/'COEFFICIENT_GENERATION.json');validation=audits['SIGNED_PERTURBATION_VALIDATION.json'];base=audits['B0_REPLAY/SUMMARY.json'];witness=audits['P1_EXACT_B0_WITNESS_BINDING.json']
    save(H/'TECHNICAL_ATTEMPT_HISTORY.json',dict(attempt='Initial full-model launch ended at Python parse time; no model or optimization executed',error='Unclosed parenthesis in evaluate_grid violations aggregation',preserved_source=record(H/'attempt_history/syntax_attempt_01/full_electrical_rows.py'),preserved_freeze=record(H/'attempt_history/syntax_attempt_01/FULL_MODEL_CODE_FREEZE.json'),accepted_execution_freeze=record(H/'FULL_MODEL_CODE_FREEZE_V2.json'),scientific_rule_changes=0))
    gate=dict(status='IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS',issued_utc=datetime.now(timezone.utc).isoformat(),scope='Numerical electrical preflight only; not an optimization result or production launch authorization',production_optimization_started=False,B1_search_started=False,Gurobi_optimization_calls=0,old_stopped_coefficients_reused=False,settings=dict(selected_date='2025-05-21',source_pu=1.04,all_Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF'),controls=dict(total=60,AIDC_P_fixed_PF_Q=12,MESS_P=24,MESS_Q=24,independent_AIDC_Q=0),reference_jobs=708,candidate_universe=1341947,candidate_stream_SHA256='878116c6e5d9204b8b02cf651ca669c23f1afab1f2cd03920f8620cc5fc82397',fresh_coefficient_generation=dict(wall_seconds=generation['wall_seconds'],slots=96,signed_derivative_solves=11520,step_kw_or_kvar=1.,voltage_axes=8639,line_phase_terminal_axes=12312,transformer_phase_terminal_axes=3777,transformer_winding_axes=3629),signed_exact_validation=validation,B0_metrics=base['metrics'],B0_authority_max_metric_difference=max(base['max_absolute_differences'].values()),P1_witness={k:v for k,v in witness.items() if k!='all_96_linear_grid_baselines'},full_logical_seed_model=dict(core_variables=model['global_core_variables'],core_linear_rows=model['core_linear_rows'],core_general_rows=model['core_general_rows'],electrical_linear_rows=model['electrical_linear_rows'],total_linear_rows=model['total_logical_linear_rows'],monolithic_resident=False,all_rows_validated=True,residual_extrema=residual),all_existing_authorities_unchanged=True,required_evidence=[record(H/p) for p in required],full_joint_model=record(H/'FULL_JOINT_MODEL_COMPONENT_MANIFEST.json'),binding_gate=record(BIND/'IEEE8500_V41R4_AIDC_BINDING_PASS.json'),stress_authority=record(STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json'),electrical_difference_classification='AUTHORIZED_ELECTRICAL_DIFFERENCE',numerical_scope='Local coefficients about each chronological B0 accepted tap/cap state; signed validation at +/-10 kW/kvar for all 60 controls over five slots. Not a certificate for arbitrary future optimized trajectories; final policy trajectories require exact 96-slot AC validation.')
    save(H/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json',gate)
    report=f'''IEEE8500 numerical electrical preflight: **IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS**

검증 범위는 수치 전기 preflight입니다. B0/B1/B2/B3 optimization 및 B1 4-hour search는 실행하지 않았습니다. Gurobi는 원래 모델의 build-only와 모든 제약의 seed 대입 검증에만 사용했으며 optimize 호출 수는 0입니다.

2025-05-21, source 1.0400 pu, 전체 regulator Vreg 123.5 V, alpha8500 0.50, CAPBank3 OFF를 유지했습니다. 기존 topology/PCC/mapping/resource/rating 및 binding authority와 중단 결과의 SHA가 모두 보존됐습니다. 중단 production의 전기 계수는 재사용하지 않았습니다.

| 검증 | 결과 |
|---|---|
| 신규 계수 | 96 slots × 60 controls; signed derivative solves 11,520; {generation['wall_seconds']:.3f} s |
| Control interface | 12 AIDC P + 24 MESS P + 24 MESS Q; AIDC Q는 기존 fixed PF, 독립 Q 변수 0 |
| Exact signed perturbation | 5 slots × 60 controls × 양/음 부호 = 600건 PASS; ±10 kW/kvar |
| 최대 voltage 예측 오차 | {validation['maximum_absolute_error']['voltage']:.12g} pu (기준 0.001) |
| 최대 phase-line loading 예측 오차 | {validation['maximum_absolute_error']['line']:.12g} pu (기준 0.005) |
| 최대 transformer phase-current 예측 오차 | {validation['maximum_absolute_error']['tx']:.12g} pu (기준 0.005) |
| 최대 winding-kVA loading 예측 오차 | {validation['maximum_absolute_error']['winding']:.12g} pu (기준 0.005) |
| B0 exact replay | 96/96 converged, controls settled; frozen extrema 차이 최대 {gate['B0_authority_max_metric_difference']:.3g} |
| Original B1 seed | 708 jobs; 전체 non-electrical/linear/general/electrical 제약 PASS |
| Non-electrical identity | {identity['variable_count']:,}개 변수 정의 및 P2–P5, seed SHA 동일 |
| 전체 전기 제약 | {model['electrical_linear_rows']:,} rows, 누락 없이 대입 검증 |
| 전 서비스 binding | 24 MESS service → PCC → P/Q column 및 12 AIDC P/fixed-PF 연결 PASS |

B0 exact extrema: Vmin {base['metrics']['Vmin_pu']:.12f}, Vmax {base['metrics']['Vmax_pu']:.12f}, max phase-line {base['metrics']['max_phase_line_loading_pu']:.12f}, max transformer phase-current {base['metrics']['max_transformer_phase_current_pu']:.12f}, max transformer winding-kVA {base['metrics']['max_transformer_winding_kva_pu']:.12f} pu.

P1과 exact AC의 critical witness는 동일합니다: `{witness['line_element']}`, `{witness['terminal']}/{witness['conductor']}`, bus `{witness['bus_connection']}`, native primary phase **{witness['native_primary_phase']}**, slot 32 (0-based 31), 07:45. 두 값 모두 {witness['optimizer_P1']:.15f} pu이며 차이는 0입니다.

전체 joint model은 원래 AIDC core ({model['core_linear_rows']:,} linear + {model['core_general_rows']:,} general rows)와 96개 full electrical CSR block의 합으로 보존했습니다. 각 block은 같은 원래 global PCC 변수와 단일 rho_max에 정확히 연결됩니다. 메모리 관리를 위해 affine electrical auxiliary를 대수적으로 제거하고 block별 실제 Gurobi 모델에 동일 seed를 대입했습니다. 96개를 별도로 최적화하지 않았고, 하나의 거대한 resident Gurobi 모델을 구성했다는 주장은 하지 않습니다. 총 logical linear rows는 {model['total_logical_linear_rows']:,}개입니다. 모든 residual의 최댓값은 {max(residual.values()):.12g} (기준 1e-9)입니다. 전체 matrix/RHS/공유 변수명/seed/row audit는 `full_model/electrical_blocks/`에 저장했습니다.

전기 계수의 단위를 명시합니다. Voltage는 squared pu의 affine 계수입니다. Line 및 transformer phase current는 원래 ampere rating으로 나눈 **복소 전류 실수/허수 성분**을 flow_p/flow_q API에 담습니다(이 두 current 계열의 API 이름은 kW/kvar를 뜻하지 않습니다). Winding은 실제 복소 P+jQ kVA와 원래 winding rating을 사용합니다. Line P1에는 기존 anchored 16-face polygon을 적용하고, transformer phase current와 winding kVA에는 각각 16-face thermal bounds를 적용합니다. 0-injection MESS에서도 signed 전류 방향을 보존했습니다.

계수는 각 B0 slot의 accepted regulator/capacitor 상태 주변 local 모델입니다. Signed 검증은 동일 상태를 유지한 별도 clean OpenDSS context에서 수행했습니다. Chronological B0 replay는 native controlled logic을 활성화했습니다. 이 gate는 향후 임의의 최적화 trajectory까지 AC feasible하다는 주장이 아니며, 향후 각 policy의 final 96-slot exact AC 검증은 여전히 필요합니다.

최종 candidate stream SHA256: `878116c6e5d9204b8b02cf651ca669c23f1afab1f2cd03920f8620cc5fc82397`. Candidate universe는 1,341,947개이며 재생성/축소하지 않았습니다. 원래 P5 cohort rank, BoundedLex와 AIDC power/WAN/migration semantics는 기존 binding과 동일하게 유지했습니다.

기계 판독 gate: `IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json`. 전체 산출물 SHA: `ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json` 및 `.sha256`. 초기 Python 구문 오류는 실행 전 개발 이력으로 별도 보존했고, 물리 rule이나 오차 기준은 변경하지 않았습니다.
'''
    report+='\nGurobi가 내부 materialization에서 일부 극소 계수를 생략하므로, 별도 `FULL_PRECISION_ELECTRICAL_ROW_AUDIT.json`에서 저장된 CSR의 모든 nonzero를 직접 사용해 전체 31,945,536개 전기 row를 다시 대입 검증했습니다. Full-precision CSR nonzero 수는 '+f"{precision['full_precision_CSR_nonzeros']:,}"+'개이며, 직접 대입의 최대 residual은 '+str(precision['maximum_full_precision_linear_residual'])+'입니다. 원본 CSR 계수는 삭제하거나 반올림하지 않았습니다.\n'
    report+='\n첫 모델 export는 Gurobi의 한글 resolved-path 처리 오류로 중단됐습니다. 그 전에 완료된 전체 seed audit는 그대로 보존했습니다. 같은 원래 모델을 build-only로 복원하고 전역 seed 값, 96개 coefficient SHA, PCC/rho binding 및 P2–P5 identity를 재확인한 뒤, 같은 디렉터리의 ASCII junction 경로로 MPS를 저장했습니다. `export_recovery/core/MODEL_PERSISTENCE.json`에서 gzip 해제 바이트/SHA 일치까지 확인했습니다. 이 복구에서도 optimize 호출은 0입니다.\n'
    (H/'NUMERICAL_ELECTRICAL_PREFLIGHT_REPORT.md').write_text(report,encoding='utf-8')
    excluded={'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json','ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.sha256'}
    files=[record(p) for p in sorted(H.rglob('*')) if p.is_file() and p.name not in excluded]
    save(H/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json',dict(status=gate['status'],files=files,file_count=len(files),freeze_policy='Immutable completed preflight evidence; subsequent work must use a separate workspace',self_exclusion=sorted(excluded)))
    digest=sha(H/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json')
    (H/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.sha256').write_text(digest+'  ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json\n',encoding='ascii')
    print('IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS',digest,flush=True)
if __name__=='__main__':main()
