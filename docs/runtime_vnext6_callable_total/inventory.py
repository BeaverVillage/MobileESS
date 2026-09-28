"""Inventory bytes/metadata only; never load April/May data or metric arrays."""
from paths import *
from datetime import datetime,timezone
def main():
    roots=[
      ('V35R3D',WORK/'MobileESS_v35r3d_kestrel_runtime_authority_closure/dayahead/cache/v35r3d_kestrel_runtime_authority_closure','Historical point+empirical safe margin; not a Q90 bundle',True),
      ('V40I',NATIVE/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v40i_authority_electrical_closure','Forensic evidence; no new promoted estimator',False),
      ('V40J',NATIVE/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v40j_runtime_redesign','Runtime redesign research; preserve rejection gates',False),
      ('V40K',NATIVE/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v40k_central_runtime','Central runtime research; preserve conditional/tail limits',False),
      ('V40S3',NATIVE/'MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s3_body_tail_runtime_risk','Body/tail research; request-version provenance unresolved',False),
      ('V40S4',NATIVE/'MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk','Explicit scheduler-request proxy, not immutable original requests',False),
      ('V40S5',NATIVE/'MobileESS_v40s5_uncertainty_aware_direct_runtime/dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime','Direct runtime uncertainty research',False),
      ('V40S5R1',NATIVE/'MobileESS_v40s5r1_rolling_origin_runtime/dayahead/artifacts/v40s5r1_rolling_origin_runtime','Rolling-origin total/remaining research; optimizer_use_allowed false',False),
      ('runtime-vNext',OLD,'Pending total and independent Running remaining; mixed pre/April/May issue family',False),
      ('runtime-vNext2',WORK/'runtime_vnext2_q95_pr/docs/runtime_vnext2_q95_operational_bound','Q95 diagnostic; not Q90 promotion',False),
      ('runtime-vNext3',WORK/'runtime_vnext3_adaptive_pr/docs/runtime_vnext3_adaptive_running_bound','Adaptive Running bounds; total authority unchanged',False),
      ('runtime-vNext4',WORK/'runtime_vnext4_gpu_censored_pr/docs/runtime_vnext4_gpu_censored_running','GPU-weighted remaining quantiles and AFT; excluded from total package',False),
      ('runtime-vNext5',WORK/'runtime_vnext5_calibration_pr/docs/runtime_vnext5_r2_causal_calibration','Remaining residual calibration; Pending R0 unchanged',False)]
    families=[];records=[]
    for name,folder,semantics,legacy in roots:
        files=[p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts] if folder.exists() else []
        models=[p for p in files if p.name.endswith(('.txt.gz','.pkl.gz','.joblib','.pickle','.ubj','.model'))]
        preprocess=[p for p in files if 'preprocess' in p.name.lower() or 'preprocessing' in p.parts]
        calibrations=[p for p in files if 'calibrat' in p.name.lower() or 'correction' in p.name.lower()]
        predictions=[p for p in files if 'prediction' in p.name.lower() or 'predictions' in p.parts or 'window_predictions' in p.parts]
        for p in files:records.append(dict(family=name,**record(p)))
        families.append(dict(family=name,path=str(folder),exists=folder.exists(),research_evidence_exists=bool(files),serialized_model_exists=bool(models),serialized_model_count=len(models),model_paths=[str(p.relative_to(folder)) for p in models],preprocessing_artifact_count=len(preprocess),calibration_artifact_count=len(calibrations),prediction_artifact_count=len(predictions),callable_new_job_provider='NOT_DEMONSTRATED_BY_INVENTORY; serialized research booster is not approved provider',optimizer_use_allowed='HISTORICAL_RECIPE_ONLY_NOT_NEW_PREAPRIL_CALLABLE_AUTHORITY' if legacy else False,production_promoted='HISTORICAL_RECIPE; current task promotion separate' if legacy else False,training_cutoff='PER_ISSUE; inspect selected pre-April receipt; never infer cutoff from folder name',target_semantics=semantics))
        print('INVENTORY',name,len(files),len(models),flush=True)
    protected=[V42/'v42/runtime_provider_contract.py',V42/'docs/v42_runtime_temporal_successor/V42_RUNTIME_PROVIDER_REQUIRED_BUNDLE.json',V42/'docs/v42_runtime_temporal_successor/duration_forensic.py',V42/'docs/v42_prefix_policy/replay_prefix.py',NATIVE/'MobileESS_v41r3_scale_rebalance/dayahead/v41r2/reference.py']
    records.extend(dict(family='READ_ONLY_V42_INTERFACE_OR_QUEUE_SOURCE',**record(p)) for p in protected if p.exists())
    write('RUNTIME_EXISTING_MODEL_INVENTORY.json',dict(time=datetime.now(timezone.utc).isoformat(),base_commit=BASE_SHA,PR_lineage={65:'d3ec564854f65f62b3587f49c857d2f86575ad2c',66:'9835f3b3a4dea6f34439f31e10773b3d2b2b8237',68:'d078bdc3d849f62ccd12db8baee6f95e67c0d2be',71:'1702abdd14db3ad6e5a63211459b9b99d6a8a054',72:BASE_SHA},families=families,scope='Listed lineage directories and explicit read-only interface/queue sources; not a global filesystem absence claim',scientific_payload_read='No April/May observations or metric arrays loaded by this inventory; hashes do not enter model selection. Prior failure/selection metadata remain lineage evidence only.'))
    write('LINEAGE_SOURCE_HASHES.json',dict(files=records,read_only=True,negative_results_preserved=True))
    lines=['# Runtime-vNext6 계보 감사','', '기준은 PR #72의 '+BASE_SHA+'다. 이전 결과를 수정하지 않고 디렉터리별 바이트 해시를 보존했다. 연구 모델, 직렬화 모델, 임의 새 작업 호출 가능성, optimizer 권한은 서로 다른 조건이다.','', '| 계보 | 파일 존재 | 직렬화 모델 수 | 타깃·제한 |','| --- | --- | --- | --- |']
    for r in families:lines.append(f"| {r['family']} | {r['exists']} | {r['serialized_model_count']} | {r['target_semantics']} |")
    lines += ['', '기존 vNext 분할의 CALIBRATION은 2025-04-02~04-07이므로 이번 pre-April 선택에 재사용하지 않는다. vNext4/5의 R2 등은 Running remaining 모델이며 이번 총 실행시간 후보가 아니다. 역사적 운영 recipe나 저장 booster가 있다는 이유만으로 새로운 제출 작업에 대한 승인된 provider라고 주장하지 않는다.', '', '비교 B0 후보는 실제 저장된 vNext의 2025-03-14T08:00Z PENDING Q50/Q90 총 실행시간 booster다. 180일 end-window/14일 반감기 recipe와 같은 시각 전처리 artifact를 검증해 재현한다. 사용자·계정 등은 기존 피처로만 처리하며 identity lookup은 예측에 사용하지 않는다. 이는 과거 생산계 전체의 재승인이 아니라 재현 가능한 pre-April 연구 기준이다.', '', 'V35R3D의 point+5576.44921875초 empirical margin은 Q90이라는 이름으로 바꾸지 않는다. 원 legacy 보정의 earliest availability가 4월인 부분도 pre-April bundle에 가져오지 않는다. May-only 생산 snapshot은 목록·해시 수준으로만 보존하고 이번 학습·선택·평가 입력으로 쓰지 않는다.', '', '요청값은 final accounting archive에 있으나 원본 제출 버전·수집 시각·수정 이력은 미확인이다. 기존 연구의 proxy 권한과 정확한 역사적 원본성은 구분한다. 새 작업의 feature receipt는 실제 관측 시각과 source hash를 요구해야 하며, 과거 학습의 provenance 한계를 성공 플래그로 덮지 않는다.', '', 'April/May는 새 실험의 모델·피처·보정·백엔드 선택에 사용하지 않는다. April은 모델/번들 동결 후 별도 잠금 평가를 수행하고, May 결과는 본 작업에서 열지 않는다.']
    (ROOT/'RUNTIME_LINEAGE_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
if __name__=='__main__':main()
