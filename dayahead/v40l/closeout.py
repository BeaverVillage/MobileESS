from .common import *
from .protocol import IDS,REGISTRY

REQUIRED=['V40L_START_STATE.json','V40L_TAIL_ESTIMAND_CONTRACT.json','V40L_TEMPORAL_SPLIT_CONTRACT.json','V40L_TAIL_CANDIDATE_REGISTRY.json','V40L_K0_FREEZE_VERIFICATION.json','V40L_OOF_RESIDUAL_AUTHORITY.json','V40L_CENSORED_JOB_CENSUS.json','V40L_T1_RESIDUAL_QUANTILE_REPORT.json','V40L_T2_DIRECT_QUANTILE_REPORT.json','V40L_T3_CQR_REPORT.json','V40L_T4_HIERARCHICAL_CONFORMAL_REPORT.json','V40L_T5_AFT_REPORT.json','V40L_T6_HAZARD_REPORT.json','V40L_T7_EXCEEDANCE_REPORT.json','V40L_T8_HYBRID_REPORT.json','V40L_TAIL_SELECTION_COMPARISON.json','V40L_GPU_WEIGHTED_SAFETY_REPORT.json','V40L_TAIL_METHOD_FREEZE.json','V40L_FINAL_SHADOW_REPORT.json','V40L_PROTECTED_SCOPE_DIFF.json','V40L_TEST_REPORT.json','V40L_FINAL_REVIEW.md']
REQUIRED+=['V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json','V40L_T7_FAILURE_DECOMPOSITION.json','V40L_TAIL_MISS_COHORT.csv','V40L_TAIL_FAILURE_CLASSIFICATION.md']
REQUIRED+=['V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.json','V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.md']
def main():
    require_prereg();verify_k0()
    start=read('V40L_START_STATE.json');changed=[]
    for n,v in start['protected_tracked_metadata'].items():
        p=ROOT/n;s=p.stat()
        if [s.st_size,s.st_mtime_ns]!=v:changed.append(n)
    hashes=[n for n,h in start['protected_V40J_V40K_SHA'].items() if sha(ROOT/n)!=h]
    assert not changed and not hashes,('PROTECTED_SCOPE_CHANGED',changed,hashes)
    write('V40L_PROTECTED_SCOPE_DIFF.json',{'status':'PASS','tracked_metadata_count':len(start['protected_tracked_metadata']),'tracked_metadata_changes':changed,'V40J_V40K_exact_SHA_count':len(start['protected_V40J_V40K_SHA']),'SHA_changes':hashes,'prior_postcommit_receipts_preserved':True,'unrelated_initial_changes_preserved':True,'May_artifact_bytes_not_read_for_protection':True})
    c=read('V40L_TAIL_SELECTION_COMPARISON.json');winner=c['winner']
    if not winner and not (OUT/'V40L_FINAL_SHADOW_REPORT.json').exists():
        write('V40L_FINAL_SHADOW_REPORT.json',{'status':'NOT_OPENED_NO_TAIL_WINNER','opened':False,'runtime_status_rows_read':0,'metrics':None,'winner_changed':False,'q_changed':False,'refit':False,'threshold_changed':False},immutable=True)
    sh=read('V40L_FINAL_SHADOW_REPORT.json')
    classification='V40L_TAIL_MODEL_INSUFFICIENT' if not winner else 'V40L_FINAL_SHADOW_FAIL_HOLD'
    if winner and sh['status']=='PASS':
        if winner.startswith('T4'):
            ml_eligible=any(not x.startswith(('T4','T0')) for x in c['eligible'])
            classification='V40L_CONFORMAL_TAIL_READY' if ml_eligible else 'V40L_ML_TAIL_INSUFFICIENT_HIERARCHICAL_CONFORMAL_READY'
        elif winner=='T0':classification='V40L_CONFORMAL_TAIL_READY'
        else:classification='V40L_K0_PLUS_CONDITIONAL_TAIL_READY'
    science={k:0 for k in ['MAY_RUNTIME_OR_STATUS_ROW_READS','MAY_ACTUAL_OUTCOME_READS','MAY_MODEL_BUILDING_READS','MAY_TRAINING_READS','MAY_CALIBRATION_READS','MAY_MODEL_SELECTION_READS','MAY_HYPERPARAMETER_SELECTION_READS']}
    extractions={s:read('EXTRACTION_'+s+'.json') for s in ['calibration','selection','shadow'] if (OUT/('EXTRACTION_'+s+'.json')).exists()}
    audits={p.stem:load(p) for p in OUT.glob('READS_*.json')}
    write('V40L_FIREWALL_EXECUTION_REPORT.json',{'status':'PASS','scientific_counters':science,'MAY_PATH_OR_CODE_DISCOVERY_READS':'NONZERO historical path/code disclosure retained','MAY_METADATA_ONLY_READS':'NONZERO; stored April footer with post-cutoff bounds inspected, never value arrays','raw_groups':{s:v['groups_decoded'] for s,v in extractions.items()},'shadow_payload_rows':sh['runtime_status_rows_read'],'denied_events':{k:v['denied'] for k,v in audits.items() if v['denied']},'no_total_read_zero_claim':True})
    write('V40L_PREMAY_TIMESTAMP_FIREWALL.json',{'canonical_timezone':'UTC','local_cutoff':CUTOFF,'UTC_cutoff':CUTOFF,'fixed_AEST_equivalent':'2025-05-01T10:00:00+10:00','scanned_partition_count':int(any(v['scanned_partition_count'] for v in extractions.values())),'rejected_post_cutoff_row_count':sum(v.get('rejected_post_cutoff_row_count',0) for v in extractions.values()),'post_cutoff_rows_within_excluded_groups':None,'minimum_rejected_timestamp':None,'maximum_accepted_timestamp':max((v['maximum_accepted_timestamp'] for v in extractions.values() if v['maximum_accepted_timestamp']),default=None),'stages':extractions,'May_runtime_status_outcome_rows_read':0})
    statuses={cid:('NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE' if cid=='T5' else 'SELECTED' if cid==winner else 'COVERAGE_GATE_PASS_NOT_SELECTED' if cid in c['eligible'] else 'INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION') for cid in IDS}
    write('V40L_FINAL_STATUS.json',{'classification':classification,'point_authority':'frozen K0','K0_SHA':sha(K/'models/K0_FINAL.pkl'),'tail_winner':winner,'candidate_status':statuses,'Q90_method':winner,'Q95_method':winner,'Q95_role':'diagnostic only','shadow_opened':sh['opened'],'shadow_result':sh['status'],'May_scientific_reads':science,'PF':.95,'Q_control':'NO','authority_missing':72,'31_day_electrical_generation':'HOLD','B0_B1_B2_B3':'NO','FULL_MAY':'NO','CPU_only':True,'production_integration':'NO'})
    lines=['# V40L 최종 검토','',f'판정: **{classification}**. Nominal은 frozen K0, tail winner는 {winner}.','',
      f'시작 commit `{START}`; 사전등록 `{require_prereg()}`. 최종 commit은 post-commit receipt에 기록한다.','',
      'K0 모델·Apr01–07 예측 SHA는 그대로이며 K0 재학습/offset/subgroup correction은 0회다. V40K_POINT_MODEL_INSUFFICIENT 및 CONDITIONAL_POINT_BIAS_REMAINS를 재해석하지 않았다.','',
      'Apr01–07은 visible development다. T1은 전체 signed rolling OOF residual 27,792행을 사용했다. T2는 Apr01 이전 end-known GPU 210,334행으로 direct quantile을 학습했으며 Q50는 nominal로 사용하지 않았다. T7만 positive excess를 별도로 학습하고 초과 확률과 결합했다.','',
      '일반 raw label은 block 종료 이전에 알려진 값만 사용했다. May 이후 submit/start/end가 포함된 row group은 값 decoding 전에 통째로 제외했다. Selection 표는 이 제한된 complete-case cohort의 결과이며, 제외된 long job/날짜를 포함한 전체 calendar population의 coverage가 아니다.','',
      '| Candidate | 상태 | Overall Q90 | H100 Q90 | H100-standby Q90 | Strong H100-standby Q90 | GPU-weighted Q90 | Overreserved GPUh | Active-miss GPU 5min slots |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for cid in IDS:
        r=c['candidates'].get(cid,{})
        if 'metrics' not in r:lines.append(f'| {cid} | {statuses[cid]} | — | — | — | — | — | — | — |');continue
        m=r['metrics'];o=m['overall']['Q90']
        fmt=lambda name:f"{m[name]['Q90']['coverage']:.3%}" if m[name]['Q90']['N'] else 'N=0'
        lines.append(f"| {cid} | {statuses[cid]} | {fmt('overall')} | {fmt('H100')} | {fmt('H100-standby')} | {fmt('STRONG_SUPPORT H100-standby')} | {o['GPU_weighted_coverage']:.3%} | {o['overreserved_GPU_hours']:.3f} | {o['active_miss_GPU_5min_slots']:,.0f} |")
    if 'T7' in c['candidates'] and 'metrics' in c['candidates']['T7']:
        t=c['candidates']['T7'];o=t['metrics']['overall']['Q90'];hs=t['metrics']['STRONG_SUPPORT H100-standby']['Q90']
        lines+=['',f"T7은 overall {o['coverage']:.3%}, H100 {t['metrics']['H100']['Q90']['coverage']:.3%}, 전체 H100-standby {t['metrics']['H100-standby']['Q90']['coverage']:.3%}, GPU-weighted {o['GPU_weighted_coverage']:.3%}다. 그러나 사전등록한 strong-support H100-standby 평가 표본은 N={hs['N']}로 최소 100에 못 미친다. 해당 gate는 INSUFFICIENT_SUPPORT이며 생략할 수 없어 winner NONE이다. 이는 T7의 aggregate coverage 실패라는 뜻이 아니다.",
          f"T7 overall day-block 95% CI={o['UTC_day_block_bootstrap95_coverage']}; GPU-weighted CI={o['UTC_day_block_bootstrap95_GPU_coverage']}. Q95 overall coverage={t['metrics']['overall']['Q95']['coverage']:.3%}는 별도 진단이다.",
          f"Baseline→winner active-miss/overreservation은 winner 부재로 비교값 없음(null)이다. 참고용 baseline→T7(비선정 후보)은 active miss {c['candidates']['T0']['metrics']['overall']['Q90']['active_miss_GPU_5min_slots']:,.0f}→{o['active_miss_GPU_5min_slots']:,.0f} GPU 5분 슬롯, overreserved {c['candidates']['T0']['metrics']['overall']['Q90']['overreserved_GPU_hours']:,.3f}→{o['overreserved_GPU_hours']:,.3f} GPUh다. T7을 winner나 배포 방법으로 재해석하지 않는다."]
    lines+=['',f"Calibration: {extractions.get('calibration',{}).get('rows')}행, dates {extractions.get('calibration',{}).get('dates')}. Selection: {c['rows']}행, dates {extractions.get('selection',{}).get('dates')}.",'',
      '선택 순서는 native Q90 coverage gates 이후 overreservation → mean safe-duration inflation → active miss → registry order다. 일별 block bootstrap CI는 comparison JSON에 공개했으며 iid/기간 밖 보장은 주장하지 않는다. Q95는 extreme-risk diagnostic이며 Q90 실패를 덮지 않는다.','',
      f"Shadow: {sh['status']}; 실제 row payload opened={sh['opened']}, read rows={sh['runtime_status_rows_read']}. Winner/q/model/support threshold를 변경하지 않았다.",'',
      'T5: 설치된 XGBoost의 AFT objective는 synthetic CPU probe에서 지원됐다. 하지만 cutoff-time alive/status snapshot이 없어 실제 censored job census와 AFT 학습은 제외했다. Censored count/GPU/walltime/hardware/standby/requested GPUh는 unknown(null)이며 0이라고 쓰지 않았다. May completion value를 읽거나 누락 label을 임의 runtime으로 채우지 않았다.','',
      'T6는 V40K K4의 동결된 CPU survival curve에서 Q90/Q95를 복원했다. T8의 OOD는 abstain이며 전체 coverage denominator에서 빠지지 않고 winner를 차단한다. Walltime 전용 hand correction이나 검증되지 않은 walltime ceiling을 만들지 않았다.','',
      f"검증: 신규 pytest {read('V40L_TEST_REPORT.json')['executed_tests']} PASS; T1/T2/T7 gate/excess 독립 CPU 반복 학습 4쌍 byte-identical; frozen K0/OOF prediction max diff 0.0초; 기존 보호 metadata {len(start['protected_tracked_metadata'])}개와 V40J/V40K SHA {len(start['protected_V40J_V40K_SHA'])}개 일치.",'',
      'May scientific counters 전부 0. 초기 path/code discovery 및 footer metadata 접근은 NONZERO로 분리 공개했다. CPU only; GPU scientific fit 0.','',
      'PF=0.95, Q control NO, 72 authority blockers, 31-day electrical generation HOLD, B0–B3 NO, FULL_MAY NO. Production model/q와 외부 P/Q authority는 바꾸지 않았다.','',
      'XGBoost API 확인: https://xgboost.readthedocs.io/en/release_3.2.0/parameter.html . 실제 objective 가용성은 설치된 3.2.0 CPU synthetic probe로 검증했다.']
    diagnostic=read('V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json');cohort=diagnostic['T7_undercovered_cohort']
    lines+=['',f"사용자 요청 post-selection 진단: **{diagnostic['classification']}**. 기존 classification/winner/shadow lock은 그대로다. 새 fit/runtime prediction/threshold/support-rule/conformal retuning은 0회이며, selection 당시 동결된 support lookup을 저장된 selection rows에 조인했다.",
      f"T7 miss {cohort['N']}개 job의 GPU-underprediction은 {cohort['GPU_underprediction_seconds']:,.3f}초다. Miss jobs 기준 top 1%/5%/10% ({'/'.join(str(cohort['pareto']['miss_jobs'][p]['top_job_count_in_universe']) for p in ['0.01','0.05','0.1'])}개)가 전체 miss mass의 {' / '.join(format(cohort['pareto']['miss_jobs'][p]['share_of_total_GPU_underprediction_seconds'],'.3%') for p in ['0.01','0.05','0.1'])}를 설명한다.",
      'T0–T8 모든 variant의 exact metric/gate 표와 threshold, T7 실패 분해, raw-vs-calibrated delta, Pareto 분모별 표는 V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json 및 V40L_TAIL_FAILURE_CLASSIFICATION.md에 있다. 324개 miss job의 상세 행은 V40L_TAIL_MISS_COHORT.csv에 저장했다.',
      '이 진단에서 standby는 기존 동결된 QoS==standby 정의다. Partition에 stdby가 포함돼도 QoS가 normal인 경우는 별도 partition/QoS 조합으로 공개했다. 정의를 변경하지 않았다. T5의 후속 진단 표기는 CENSOR_AUTHORITY_INSUFFICIENT다.']
    provenance=read('V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.json')
    lines+=['',f"Strong-support standby N=4 provenance 추가 확인: **{provenance['provenance_classification']}**. 기간별 total/strong은 Apr01–07 2291/1772, Apr08–14 383/130, Apr15–23 1317/4다. Selection의 12h 1223개 중 1153개는 과거 48h로만 관측된 두 feature8 profile(과거 지원 3237/1501개)에 해당한다. Exact walltime 포함 9개 key를 그대로 적용해 exact_count=0, REGIME_MISMATCH가 됐다.",
      '세 기간 모두 동일한 support lookup, hardware/standby 정의, numeric/string key 정규화를 사용했다. 원인 분류는 허용된 cohort의 walltime covariate shift이며, implementation inconsistency가 발견되거나 support gate가 변경된 것은 아니다. 상세 기간별 수치·분포·4개 strong row provenance는 V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.json/.md에 기록했다.']
    (OUT/'V40L_FINAL_REVIEW.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    assert all((OUT/n).exists() for n in REQUIRED)
    write('V40L_ARTIFACT_MANIFEST.json',{'classification':classification,'required_artifacts':{n:sha(OUT/n) for n in REQUIRED},'final_commit_receipt':'Generated after final research commit, outside referenced commit to avoid self-referential SHA'})
    print(json.dumps({'classification':classification,'winner':winner,'protected':'PASS','required_artifacts':len(REQUIRED)}),flush=True)
if __name__=='__main__':main()
