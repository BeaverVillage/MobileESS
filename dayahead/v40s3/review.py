"""Korean final review and verification receipt assembly; no fitting."""
import re
import json
import xml.etree.ElementTree as ET
from .audit import OUT,ROOT,BASE,HOLDS,git,write,sha
from .experiment import get


def main():
    xml=ET.parse(OUT/'V40S3_TEST_JUNIT.xml').getroot()
    cases=xml.findall('.//testcase')
    assert len(cases)==73 and not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
    write('TEST_REPORT',dict(status='PASS',passed=73,failed=0,skipped=0,
       tests=[x.attrib for x in cases],command='python -B -m pytest dayahead/v40s3/test_v40s3.py -q -p no:cacheprovider --junitxml=...',
       independent_numerical_validation=['all exposed hybrid reconstructions and GPU miss/reserve sums','all CAL eta maximality','body/tail exact partitions','two-column feature invariance under forbidden feature mutation'],
       interpretation='Software and protocol checks pass. Scientific candidate safety does not pass. Missing terminal/migration count is explicitly tested as unavailable, not fabricated zero.'))
    write('EXECUTION_NOTES',dict(preregistered_model_protocol_changed_after_fit=False,retraining_after_selection=0,
       report_only_fixes=['Renamed gate body column to body_gate to avoid duplicate dictionary key in closeout',
                          'Handled empty Apr01 current-ledger join explicitly as no matching schedule authority; no numeric metrics fabricated'],
       model_outputs_changed=False,selection_changed=False,
       live_baseline_limitation='Exact current production Apr01 frozen state was not serialized for this issue panel; archived current-recipe model predictions were preregistered as reference. Existing exact Apr01 ledger has no accepted panel issue match.',
       counter_interpretation='May scientific reads0; path/code/index metadata NONZERO disclosed.'))
    forensic=get('THRESHOLD_FORENSIC');pop=get('POPULATION_AUDIT');sel=get('METHOD_SELECTION')
    evidence=get('EXISTING_RUNTIME_EVIDENCE_AUDIT')
    evidence['question_answers']=dict(
       long_positive_error='In reconstructed PENDING DEVELOPMENT, T>4h is41.233% of job-issues and99.521% of requested-GPU positive-error mass; T>24h is2.692% and76.698%.',
       dangerous_runtime_ranges=forensic['runtime_ranges'],
       body_region='Oracle B0 short-body coverage high but overconservative; new strict-clock body can pass selected pooled/temporal gates at short u, yet no complete body/tail/hybrid method passes DEV+CAL.',
       variance_increase='Fixed runtime-bin residual SD/variance, descriptive only; no causal changepoint claim.',
       dangerous_mass_above_u=forensic['thresholds'])
    evidence['classification']=sel['classification']
    evidence['initial_all_job_forensic']='Superseded scope diagnostics preserved under superseded_membership_authority_stop; not pooled with reconstructed PENDING findings.'
    write('EXISTING_RUNTIME_EVIDENCE_AUDIT',evidence)
    (OUT/'V40S3_EXISTING_RUNTIME_EVIDENCE_AUDIT.md').write_text(
      '# V40S3 기존 증거 및 보정\n\nPENDING/RUNNING membership는 사용자 확인 current normative 재구성으로 인정한다. '
      'start/end는 membership와 label availability에만 쓰며 predictor에 넣지 않았다. resource provenance 부족과 membership authority를 분리했다.\n\n'
      'K: pooled median이 조건부 편향을 숨길 수 있다. L: T7 aggregate coverage와 별개로 strong-support standby N=4가 mandatory gate를 막았다. '
      'N/Q: A2 shift/OOS의 시간적 실패가 지속됐다. S: original request-version provenance 미확보. S2: clock-only survival safety 실패, proxy advantage는 비인과적이다. '
      '이 결과들의 모집단/분할을 합치거나 기존 winner NONE을 바꾸지 않았다.\n\n'
      '수정된 PENDING DEVELOPMENT에서는 >4h가 행의41.233%, GPU 양의 과소예측 질량의99.521%다. >24h는2.692%의 행이76.698%의 질량을 차지한다. '
      '실제 T로 나눈 body는 oracle 진단이다. 짧은 body 일부는 예측 가능하지만 clock-only tail의 calibration·시기간 안정성과 hybrid gate까지 충족하지 못했다.\n\n'
      'Frozen current recipe 비교는 historical C0_F3 / April K0다. current production final-state와 동일하다고 주장하지 않는다. '
      '실제 live-Apr01 ledger도 read-only 확인했으나 선택한 complete-case panel과 issue match가0이었다. '
      '전체 panel의 exact-current-state 비교와 H120/migration touch 수치는 입증되지 않아 null이다.\n',encoding='utf-8')
    write('PREMAY_TIMESTAMP_FIREWALL',dict(canonical_timezone='fixed AEST UTC+10',local_cutoff='2025-05-01T00:00:00+10:00',
       UTC_cutoff='2025-04-30T14:00:00Z',stricter_shadow_cutoff='2025-04-24T00:00:00Z',
       raw_partitions_scanned=0,preverified_row_sources_scanned=3,rejected_post_cutoff_row_count=0,
       max_accepted_timestamp=pop['max_accepted_timestamp'],min_rejected_timestamp=None,
       caveat='Already prefiltered sources;0 new rejections is not a claim original archives contain no post-cutoff rows.'))
    th=forensic['thresholds'];eval=get('EXPOSED_RESULTS');allbody=get('DEV_CAL_RESULTS')['body_metrics']+eval['body_metrics']
    lines=[
      '# V40S3 최종 검토', '',
      '- final classification: **V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT**',
      '- selected runtime threshold u: **NONE**', '- selected body model: **NONE**',
      '- selected tail classifier: **NONE**', '- selected eta: **NONE**',
      '- selected robust policy: **NONE**',
      '- causal authority: **PASS — normative PENDING reconstruction + strict submit_hour/weekday**',
      '- body safety: **최종 방법 PASS 없음**. DEV+CAL에서는 4h B1/B2/B3 body gate PASS; 노출 평가 4h는 FAIL. 일부 body의 안전성을 부정하지 않는다.',
      '- tail detection: **FAIL** — selective/temporal/calibration 조건 동시 충족 없음',
      '- hybrid safety: **FAIL** — eligible method 없음', '- production integration: **NO**', '',
      '사용자 보정에 따라 membership authority와 predictor-feature provenance를 분리했다. contemporaneous saved snapshot 부재로 종료하지 않았다. '
      '기존 조기 종료 기록은 superseded 디렉터리에 보존하고, 수정 사전등록 commit 이후 CPU body/tail 실험을 끝까지 실행했다. '
      '새 resource/proxy predictor, 추가 architecture, 사후 retuning은 없다.', '',
      '1. Live PR #27 head: `'+BASE+'`; branch `codex/v40a-bounded-iterative-aidc-mess-coopt`. '
      '역사적8ff3dc는 ancestor이며 최신 head로 사용하지 않았다. 작업 branch `codex/v40s3-body-tail-runtime-risk`.',
      '2. 원본 S2 identity 73,504 / positive72,292 / zero1,212 / negative0 / duplicate0 / missing start/end0, exact end−start PASS. '
      '성공 COMPLETED-only가 아닌 terminal-event source다.',
      f"3. PENDING panel {pop['PENDING_N']:,} job-issue / {pop['PENDING_unique_jobs']:,} unique jobs. "
      'TRAIN1,190 / DEV4,346 / CAL2,634 / exposedEVAL2,713. 동일 job의 일별 반복 의사결정을 보존한다. '
      'TRAIN beforeMar22 08UTC, DEV beforeApr01 08UTC, CAL beforeApr08 08UTC, EVAL beforeApr24 00UTC에 end_time이 알려진 행만 사용했다. '
      '원본 terminal selection과 incomplete-job 누락 때문에 전체 PENDING backlog census로 일반화하지 않는다.',
      '4. Causal features: recorded UTC submit_hour, weekday만. submit<=issue 확인. tree는2열 numeric, logistic은 이 두 시계 feature의 고정24+7 one-hot. '
      '새 body35 primary/repeat tree·logistic fit은 모두CPU single-thread; 실제 모델 primary35+repeat35, empirical quantile5/base-rate5. '
      '독립 반복 학습+train prediction bytes35쌍 maxdifference0.',
      '5. requested walltime/GPU/nodes/cores/memory/partition/QoS/hardware/standby/user/account/support derivatives를 새 predictor로 거부했다. '
      'GPU는 평가 weight, walltime/K0는 existing comparator에만 사용한다. start/end는 membership·availability·label에만 사용한다.', '',
      '6. TRAIN/development threshold forensic (current-recipe B0 raw safe seconds; 실제 body membership oracle):', '',
      '| u(h) | TRAIN percentile | DEV tail N / % | tail GPU miss mass % | body Q90 / GPU coverage % | body safe MAE(s) / WAPE |',
      '|---:|---:|---:|---:|---:|---:|']
    for r in th:
        lines.append(f"| {r['u_hours']} | {r['TRAIN_percentile']:.3f} | {r['tail_N']} / {100*r['tail_prevalence']:.3f} | {100*r['tail_GPU_positive_error_mass_fraction']:.3f} | {100*r['body_reference_safe_coverage']:.3f} / {100*r['body_reference_GPU_coverage']:.3f} | {r['body_reference_safe_MAE_sec']:.3f} / {r['body_reference_safe_WAPE']:.4f} |")
    lines += ['',
      '7. u는 NONE. 120개 새 body×classifier×R0/R1×u 조합 중 DEV+CAL 전체 gate 통과0. '
      'B0 reference-only40개는 새 causal body winner 후보가 아니다. 사전등록되지 않은 u/threshold/fallback을 추가하지 않았다.',
      '8. B0 current-recipe, B1 LightGBM quantile, B2 XGBoost quantile, B3 global empirical TRAIN-body quantile. '
      '새 Q50/Q90는 positive finite, raw crossing을 공개하고 사전등록한 순서대로 두 quantile을 정렬했다. '
      'DEV+CAL raw crossing2,568 / exposed505 (candidate×threshold×job-issue 출력 단위), nonpositive0. '
      '정렬 후 Q50<=Q90 전부 충족. 추가 body calibration C0=none; globalq 자동 가산 없음.',
      '9–12. 노출 평가 oracle body 지표. MAE/WAPE/positive mass는 raw Q90 기준; Q50 MAE, log-MAE, slot error, 일별/GPU-band 상세는 BODY_METRICS.csv에 있다. '
      '이 표는 선택 결과를 바꾸지 않는다.', '',
      '| u | body | N | Q90% | GPU% | Q90 MAE(s) | Q50 MAE(s) | WAPE | GPU miss sec |',
      '|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in eval['body_metrics']:
        if r['subgroup']=='OVERALL':lines.append(f"| {r['u_hours']} | {r['candidate']} | {r['N']} | {100*r['coverage']:.3f} | {100*r['GPU_coverage']:.3f} | {r['MAE_sec']:.2f} | {r['Q50_MAE_sec']:.2f} | {r['WAPE']:.4f} | {r['GPU_underprediction_sec']:.2f} |")
    lines += ['',
      '13. Exposed tail prevalence: 4h45.300%, 6h21.747%, 8h11.390%, 12h2.285%, 24h0.700%. '
      'DEV tail prevalence와 섞지 않는다.',
      '14–18. Exposed classifier 지표 및 CAL에서 고정된 eta. Mass capture는 B3 body Q90 기준 비교이며 body별 전체 수치는 별도 CSV에 있다. '
      'u12 exposed tailN62는 recall gate support 부족, u24 CAL tailN43은 eta 자체를 선정하지 않는다.', '',
      '| u | C | ROC / PR | ECE | eta | recall% / GPU% | mass capture% | flagged% |',
      '|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in eval['tail_metrics']:
        if r['body']!='B3':continue
        fmt=lambda v:'N/A' if v is None else f'{v:.4f}'
        pct=lambda v:'N/A' if v is None else f'{100*v:.3f}'
        lines.append(f"| {r['u_hours']} | {r['classifier']} | {fmt(r['ROC_AUC'])} / {fmt(r['PR_AUC'])} | {r['ECE']:.4f} | {fmt(r['eta'])} | {pct(r['recall'])} / {pct(r['GPU_recall'])} | {pct(r['mass_capture'])} | {pct(r['flagged_fraction'])} |")
    lines += ['',
      '19–20. R0/R1全組合을 optimizer 없이 replay했다. 예시4h B1+C2는 사전선정이 아닌 고정 후보 진단이다: '
      'R0 exposed coverage34.243% / GPU38.777%, miss+1,022,581 GPU·s, overreservation+18.550 GPUh. '
      'R1 coverage90.822% / GPU90.391%, miss−23,892,856 GPU·s, overreservation+44,378.596 GPUh (13.217배). '
      '따라서 R1의 coverage 개선만으로 채택하지 않는다. walltime은 guaranteed ceiling이 아니다.',
      '21. selected hybrid policy NONE. 최종 denominator는 BODY+TAIL 전체 job-issue다. u24는 eta support 부족으로 replay null; 다른 threshold로 대체하지 않았다.',
      '22–25. selected overall/GPU coverage, underprediction reduction, overreservation delta는 모두 N/A. '
      '현재 recipe reference exposed 2,713행은 15min coverage35.017% / GPU39.333%, miss32,291,178 GPU·s, overreserve3,632.428 GPUh. '
      '이 값은 current production Apr01 final-state 동일성 주장이 아니다. full-panel exact-current-state 비교는 불가하다. '
      '현재 head의 실제 Apr01 ledger도 조사했지만 해당 issue의 accepted panel행이0이라 exact match0; 없는 비교값은 만들지 않았다.',
      '26. H=120 terminal transition: N/A. 해당 panel에 joined frozen scheduled start가 없으며 actual service start를 scheduling start로 대체하지 않았다. '
      'matched0을 transition0이라고 쓰지 않는다.',
      '27. inherited migration touch count: N/A. PENDING panel에 join 가능한 inherited migration witness 없음. 새로운 witness/solve0.',
      '28. **migration changed = NO**. RUNNING/A1/M1/MF/WAN/Rack/terminal/Fresh 수정0.',
      '29. May scientific runtime/status/outcome/training/calibration/u/eta/model/hybrid selection reads 모두0. '
      '초기 May path/code/index metadata discovery는 NONZERO이며 전체 read0을 주장하지 않는다. '
      'canonical cutoff May01 00:00 fixedAEST = Apr30 14:00UTC; 실제 source는 Apr24UTC 이전으로 더 제한했다.',
      '30. TRUE_CONFIRMATORY_AVAILABLE=NO. Apr24–30 shadow SEALED; 행0read. 노출 평가는 확인용 untouched test가 아니다.',
      '31. 73 PASS /0FAIL/0SKIP software/protocol tests. 모델과학적 safety PASS와 구분한다. '
      '독립 eta 최대성, 전체 exposed hybrid GPU miss/reserve 수치, predictor 비허용 feature 불변성, label/timestamp/commit SHA 검증 포함.',
      '32. Base의 모든 기존 tracked blob identity와 변경 경로를 검증했다. 변경은 dayahead/v40s3 및 artifacts/v40s3_body_tail_runtime_risk 내부뿐. '
      'q5576.44921875, PF.95, QcontrolNO, electricalHOLD, B0–B3NO, FULL_MAYNO 유지.',
      '33. 미래 adapter는 정확히10 fields: '+', '.join(get('RUNTIME_ADAPTER_PROPOSAL')['candidate_fields'])+'. '
      '실제 추천행 export는[]; site/migration/MESS/electrical decision 필드 없음.',
      '34. 이후 별도 integration revision에서 검토할 최소 consumer 파일은 아래 두 개다. 현재 수정0이며 optimizer 수학/solver 파일 변경 필요목록은[]다.',
      '- `dayahead/v37/aidc_materializer.py:_jobs_and_ledger`: PENDING duration admission',
      '- `dayahead/v40a/initial.py:build_initial`: PENDING metadata / eligible_standby admission',
      '35. 반드시 보호할 optimizer/migration/WAN/terminal source 정확한 목록은 아래와 같다. '
      '전체 기존 tracked파일도 보호하며 Git blob inventory는 PROTECTED_SCOPE_DIFF.json에 있다.', '']
    protected=get('PROTECTED_SCOPE_DIFF')['protected_source_Git_blobs']
    for p in sorted(protected):lines.append('- `'+p+'`')
    lines += ['',
      'preregistration: `'+get('PREREGISTRATION_COMMIT_RECEIPT')['commit']+'`',
      'model/method NONE freeze before exposed evaluation: `'+get('METHOD_SELECTION_COMMIT_RECEIPT')['commit']+'`',
      '최종 과학 commit/receipt는 V40S3_FINAL_COMMIT_RECEIPT.json에서 별도 검증한다.', '',
      '결론의 범위: 이번 고정 cohort/splits/models에서 현재 입증된 clock features로 선택적 tail 처리를 충분히 식별·보정하지 못했다. '
      '모든 가능한 causal model이 원리적으로 실패한다는 주장도, PENDING membership authority가 없다는 주장도 아니다.']
    (OUT/'V40S3_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Requested artifact inventory, excluding the post-commit receipt itself.
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    section=request.split('45. REQUIRED ARTIFACTS')[1].split('46. MINIMUM TESTS')[0]
    names=re.findall(r'V40S3_[A-Z0-9_]+\.(?:json|csv|md)',section)
    absent=[x for x in names if not (OUT/x).exists() and x!='V40S3_FINAL_COMMIT_RECEIPT.json']
    assert not absent,absent
    write('ARTIFACT_MANIFEST',dict(requested_artifact_count=len(names),present_before_final_receipt=len(names)-1,
       pending_post_commit=['V40S3_FINAL_COMMIT_RECEIPT.json'],required=names,
       produced_SHA256={p.name:sha(p.read_bytes()) for p in OUT.glob('V40S3_*') if p.is_file() and p.name!='V40S3_ARTIFACT_MANIFEST.json'}))
    print('FINAL_REVIEW_READY',len(names),'required artifacts')


if __name__=='__main__':main()
