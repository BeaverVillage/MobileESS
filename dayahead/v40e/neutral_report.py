"""Finalize the neutral-move audit and stop decision, without changing science."""
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,reference
from dayahead.v40e.audit import REL


def finish(repo):
    repo=Path(repo).resolve();root=repo/REL;out=root/'neutral_move_forensic';s=root/'smoke/2025-05-01'
    path=root/'V40E_B1_NEUTRAL_MOVE_ACCEPTANCE_FORENSIC.json';r=read(path)
    intervention=read(out/'V40E_PCC_ONLY_CURRENT_ATTRIBUTION.json')
    protected=read(root/'V40E_FINAL_PROTECTED_ARTIFACT_DIFF.json')
    sources=read(root/'V40E_FINAL_INHERITED_PRODUCTION_SOURCE_DIFF.json')
    assert intervention['status']==protected['status']==sources['status']=='PASS'
    r['PCC_only_intervention']=intervention
    r['protected_artifacts']=protected;r['inherited_production_sources']=sources
    r['tolerances']['Fresh_physical_violation_tolerance']=1e-9
    r['decision_delta']['start_slot_origin']='D-1 18:00 fixed AEST; slot=900 seconds; D00=24, H=120'
    r['decision_delta']['realized_runtime_unit']='seconds, identical per UID in both cases'
    planned={}
    for c in ('B0','B1'):
        with np.load(s/(c+'_PRE_MESS_AIDC.npz')) as z:planned[c]={k:z[k] for k in z.files}
    r['neutral_grid_peak_explanation']={
        'Planning_Fresh_critical_line':'line.l10','phase':'A','slot':72,'time_AEST':'18:00',
        'B0_GPU_by_site_at_DA_peak':planned['B0']['gpu'][72].tolist(),
        'B1_GPU_by_site_at_DA_peak':planned['B1']['gpu'][72].tolist(),
        'GPU_exact_equal_at_DA_peak':bool(np.array_equal(planned['B0']['gpu'][72],planned['B1']['gpu'][72])),
        'PCC_P_max_difference_at_DA_peak_kw':float(abs(planned['B0']['pcc'][72]-planned['B1']['pcc'][72]).max()),
        'interpretation':'Both plans fill all 624 GPUs at the binding 18:00 grid peak despite different job identities, starts and planned runtimes. The reported grid maximum therefore does not improve.'}
    d=r['critical_slot'];delta_same=d['B1_rho_same_coordinate']-d['B0_rho_same_coordinate']
    r['maxima_decomposition']={'same_coordinate_rho_increase':delta_same,
        'B0_max_minus_B0_at_B1_critical':r['objectives']['J_B0_ACTUAL']-d['B0_rho_same_coordinate'],
        'B1_max_minus_B0_max':r['objectives']['J_B1_ACTUAL']-r['objectives']['J_B0_ACTUAL'],
        'identity':'B1max-B0max = [B1(t*,l*,ph*)-B0(t*,l*,ph*)] - [B0max-B0(t*,l*,ph*)]'}
    write_json(path,r)
    forensic_path=root/'b0_b1_forensic/V40E_B0_B1_END_TO_END_FORENSIC.json'
    previous=read(forensic_path);previous.update(forensic_verdict=r['classification'],FULL_MAY_AUTHORIZED='NO',
        neutral_move_acceptance_forensic=reference(path),method_changed=False)
    write_json(forensic_path,previous)
    write_json(root/'V40E_CURRENT_EXECUTION_STOP_GATE.json',{'status':'STOP','reason':r['classification'],
        'Delta_Actual':r['objectives']['Delta_ACTUAL'],'PRIMARY_IMPROVEMENT_SIGNIFICANT':'NO',
        'FULL_MAY_AUTHORIZED':'NO','B2_B3_AUTHORIZED':'NO','B2_B3_execution_started':False,'full_May_execution_started':False,
        'method_changed':False,'UNASSIGNED_44_case_blocker':'PRESERVED','evidence':reference(path)})
    # Current sidecar supersedes the preliminary rerun sequence; historical files
    # remain unchanged and cannot serve as valid electrical result reuse authority.
    blast_path=root/'V40E_BACKGROUND_DEFECT_BLAST_RADIUS.json';blast=read(blast_path)
    blast['rerun_sequence']=['Preserve RW/reference decisions and all valid upstream inputs',
        'Repair native allocation; regenerate AC anchors and all dependent sensitivities',
        'Rebuild May-01 B0 evaluation and B1/A0 from inherited methods; corrected Fresh and Actual',
        'STOP: resolve neutral A0 acceptance METHOD_DESIGN_GAP. No B2/B3 or full May authorization.']
    blast['FULL_MAY_AUTHORIZED']='NO';write_json(blast_path,blast)
    invalid=[]
    for day in pd.date_range('2025-05-01','2025-05-31').strftime('%Y-%m-%d'):
        for c in ['B0','B1','B2','B3']:
            invalid.append({'day':day,'case':c,'Planning_Fresh_electrical_result_status':'INVALIDATED_BY_BACKGROUND_MAPPING_DEFECT',
                'Actual_status':'INVALIDATED_BY_BACKGROUND_MAPPING_DEFECT' if day=='2025-05-01' else 'NOT_EXECUTED_IN_V40D',
                'RW_reference_input_preserved':c in ['B0','B2'],'old_electrical_result_reuse_authorized':False})
    write_json(root/'V40E_INVALIDATED_HISTORICAL_RESULTS.json',{'scope':'Preserved original V40A/V40B/V40D electrical results only; corrected V40E is separate',
        'historical_files_modified':False,'rows':invalid,'FULL_MAY_AUTHORIZED':'NO'})
    def link(label,p):return f'[{label}]({Path(p).as_posix()})'
    text=['**판정: C. METHOD_DESIGN_GAP. FULL_MAY_AUTHORIZED = NO. B2_B3_AUTHORIZED = NO.**',
        'B1/A0에는 B0 대비 유의한 grid 목적함수 개선 또는 RW 보존을 요구하는 승인 규칙이 없다. 이번 감사에서는 방법과 기존 결정을 변경하지 않았다. D의 “meaningful DA gain” 조건은 충족되지 않는다.',
        '**전체 정밀도 목적함수** — 저장된 binary64 값을 재현하는 17자리 십진수. Delta = B0 − B1.',
        '| 지표 | B0 | B1 | Delta |','|---|---:|---:|---:|']
    for n in ['DA','FRESH','ACTUAL']:
        f=r['objectives']['binary64_full_precision_decimal'];text.append(f"| {n} | {f['J_B0_'+n]} | {f['J_B1_'+n]} | {f['Delta_'+n]} |")
    text += ['', '**PRIMARY_IMPROVEMENT_SIGNIFICANT = NO.** 기존 V40A의 진단 기준 1e-6보다 훨씬 작고, DA delta는 음수다. A0 자체에는 B0 비교/개선 acceptance tolerance가 정의되어 있지 않다.',
        '| 허용오차/설정 | 실제 값 및 적용 범위 |','|---|---|']
    for k,v in r['tolerances']['A0_solver'].items():text.append(f'| A0 {k} | {v} |')
    text += ['| Planning 물리 gate tolerance | 1e-7 |','| A0 voltage range | [0.9499999, 1.0500001] pu |',
        '| Fresh 물리 위반 판정 tolerance | 1e-9 |','| A1/MF primary nondegradation | 1e-6; B1/A0에는 미적용 |',
        '','A0의 MIPGap=0 및 OPTIMAL은 상수 0 목적함수에 대한 feasible optimum이다. Grid rho optimality 증명이 아니다. Secondary/tertiary objective와 그 lexicographic tolerance는 이 A0 호출에 없다.',
        '', '**정확한 결정 변경량**', '| 항목 | 값 |','|---|---:|']
    counts=r['decision_delta']
    for k in ['JOB_COUNT','START_CHANGED_JOB_COUNT','START_ADVANCED_JOB_COUNT','START_DELAYED_JOB_COUNT','SITE_CHANGED_JOB_COUNT','MIGRATION_CHANGED_JOB_COUNT','PLANNED_DURATION_CHANGED_JOB_COUNT','changed_GPU_slots','changed_GPU_hours']:
        text.append(f'| {k} | {counts[k]} |')
    text += ['', 'Site 변경 1,255 = 실제 site→site 703 + UNASSIGNED→site 552. 후자 552는 운영일 이전 완료의 inherited site label 44개와 B0 post-H 미배정에서 B1 계획 site를 가진 508개로 나뉜다. Actual에서 대체 site를 만든 것이 아니다. RUNNING migration 변경은 0이다.',
        'changed_GPU_slots는 job UID별 전체 **계획** site×slot 점유의 대칭차에 GPU를 곱한 합이다. Hours는 ×0.25이며, 제거·추가를 모두 센다. UNASSIGNED는 결정 비교용 label로 유지한다. RW/RSP 계획 duration 자체도 1,395개에서 다르므로 이를 순수 이동 서비스량으로 해석하면 안 된다. Realized runtime은 두 case에서 job별 exact identical이다.',
        link('1,649-job 결정 비교 CSV',out/'B0_B1_EXACT_DECISION_DELTA.csv')+'; '+link('Parquet',out/'B0_B1_EXACT_DECISION_DELTA.parquet')+'. Start/delta 단위는 15분 slot, 원점은 Apr-30 18:00 AEST이며 timestamp도 저장했다. realized_runtime 단위는 초다.',
        '', '**B1이 선택된 코드 경로와 기존 규칙**',
        '1. 기존 RSP는 QoS → submit time → UID 순서의 earliest-feasible first-fit이다. RW는 요청 walltime, RSP는 causal safe runtime으로 계획한다. 이는 전기계통 rho를 비교하는 temporal optimizer가 아니다.',
        '2. `v40a.initial.build_initial`은 고정 RSP starts/ends를 읽고 `plan_fixed_temporal_schedule(..., allow_running_migration=False)`를 호출한다. 이 solver의 목적함수는 `setObjective(0.0, MINIMIZE)`이다. Capacity와 corrected voltage 제약을 만족하는 배치를 고정된 ordering/seed로 선택하며 RW occupancy-deviation 최소화가 없다.',
        '3. `v40e.smoke.prepare`는 `jobs[B1] = deepcopy(a0.jobs)`로 결과를 사용한다. Placement OPTIMAL, case/terminal/capacity 검사, Planning PASS, 이후 Fresh PASS가 gate이다. B0−B1 rho 개선을 비교해 RW로 되돌리는 분기는 없다.',
        '4. rho → occupancy deviation → deterministic tie 규칙은 B3의 A1 feedback에만 있다. 기준도 B0가 아니라 accepted A0이다. 이 B1에서는 호출되지 않았다. A1/MF monotone은 동률을 허용한다.',
        '5. 기존 V39E full_preflight는 feasible RSP를 `TEMPORAL_ONLY_SUFFICIENT`로 선택한다고 명시한다. V40A README/contract/tests와 제공된 요청에서 B0→B1 neutral move 시 RW 보존 요구는 확인되지 않았다. 따라서 기존 보존 규칙의 미준수라고 판정할 근거가 없으며 **METHOD_DESIGN_GAP**이다. 보존 규칙 또는 grid-primary A0의 도입은 별도 방법 변경이므로 수행하지 않았다.',
        '실제 A0 solver event: status=2/OPTIMAL, solution count=1, solver runtime=0.44700002670288086 s. RSP scheduler rerun=0; 새 placement solve=1.',
        'Planning/Fresh 최대점은 둘 다 line.l10/A/slot72(18:00)이다. 그 시점 두 계획은 site별 [64,32,64,32,80,64,32,64,32,64,32,64], 합 624 GPU로 동일하다. 해당 slot PCC P의 site별 최대 차이는 3.277733640061342e-11 kW다. Job 일정이 크게 바뀌어도 이 최대점에서의 전기 부하는 개선되지 않았다.',
        '', '**Actual critical slot과 전력 차이**',
        'Slot 번호는 0-based이며 고정 AEST다. B0 최대점: line.sw2/A/slot73(18:15), rho=0.58923579670058079. B1 최대점: line.l10/A/slot30(07:30), rho=0.59740782885567589.',
        '| line.l10/A/slot30 | B0 | B1 |','|---|---:|---:|',
        f"| rho | {d['B0_rho_same_coordinate']:.17g} | {d['B1_rho_same_coordinate']:.17g} |",
        f"| 전류 A / rating 698 A | {d['B0_current_A']:.17g} | {d['B1_current_A']:.17g} |"]
    for field in ['background_P_kw','background_Q_kvar','PV_P_kw','AIDC_P_kw','AIDC_Q_kvar','P_net_kw','Q_net_kvar']:
        text.append(f"| {field} | {d['B0_components'][field]:.17g} | {d['B1_components'][field]:.17g} |")
    text += ['', '아래 P/Q 단위는 kW/kvar이며 표만 소수 6자리로 표시한다. CSV/JSON에는 전체 정밀도가 있다.',
        '| Site | GPU B0→B1 (Δ) | B0 P / Q | B1 P / Q | ΔP / ΔQ | 순서 고정 ΔI A |',
        '|---|---:|---:|---:|---:|---:|']
    ir={x['site_changed_this_step']:x['Delta_current_A_from_previous'] for x in intervention['rows']}
    for x in d['site_rows']:
        text.append(f"| {x['site_id']} | {x['B0_occupied_GPU']}→{x['B1_occupied_GPU']} ({x['Delta_occupied_GPU']:+d}) | {x['B0_P_PCC_kW']:.6f} / {x['B0_Q_PCC_kvar']:.6f} | {x['B1_P_PCC_kW']:.6f} / {x['B1_Q_PCC_kvar']:.6f} | {x['Delta_P_PCC_kW']:+.6f} / {x['Delta_Q_PCC_kvar']:+.6f} | {ir[x['site_id']]:+.9f} |")
    text += ['', 'GPU 합계 347→528 (+181), PCC +99.1380279168286 kW / +32.58509399503996 kvar. Slot30에서 B1-only 225개/225 GPU, B0-only 44개/44 GPU, 공통 active 167개이므로 순증은 181 GPU다. 이 중 시작 변경 job이 +179 GPU를 설명한다. 나머지 +2 GPU는 시작 계획/site가 같은 UID 8632537/8632538의 same-site queue delay로 설명된다: B0 실제 시작 Apr-30 18:00, B1은 각각 20:00/20:15, runtime은 양쪽 모두 43,210초다.',
        'Background/PV/weather는 96개 slot 전체 exact identical이다. Slot30의 wet-bulb=6.6394385506595555°C, RH=88.05530905561002%로 동일하다. Feeder topology/mapping/ratings/source도 동일하다.',
        'Regulator 순서: '+', '.join(d['regulator_order'])+'. 두 case taps: '+str(d['B0_regulator_taps'])+'.',
        'Capacitor 순서: '+', '.join(d['capacitor_order'])+'. 두 case states: '+str(d['B0_capacitor_states'])+'. Native control 상태는 96 slot 전체 동일하다.',
        '추가 전력계통 진단은 B0의 모든 PCC에서 출발해 AIDC01→12 순으로 각 site의 P/Q만 B1 값으로 대입했다. 두 끝점은 저장된 B0/B1의 전체 96-slot 전류/전압 배열을 오차 0으로 재현했다. 위 ΔI의 합은 11.179158606611168 A다. 이 합은 전기적 설명을 직접 검증한다. 개별 ΔI는 순서에 의존하는 비선형 분해이며 유일한 causal share나 실행 가능한 혼합 job 정책을 뜻하지 않는다.',
        '특히 AIDC12 +20.265784 kW가 +3.120611765 A, AIDC10 +13.145374 kW가 +2.020070327 A를 설명한다. AIDC01의 +25.743024 kW는 이 line-phase에 약 0.000013137 A만 기여한다. Site별 전기적 영향이 다르다.',
        '최대점이 다르므로 정확한 최대 rho 차이는 `(0.5974078288556759 − 0.581391842313253) − (0.5892357967005808 − 0.581391842313253) = 0.0081720321550951`이다. AIDC P/Q 외의 input 차이는 0이다.',
        link('critical site 전체 정밀도 CSV',out/'ACTUAL_CRITICAL_SLOT_SITE_GPU_PQ.csv')+'; '+link('PCC-only 전류 분해',out/'V40E_PCC_ONLY_CURRENT_ATTRIBUTION.json')+'.',
        '', '**Horizon redistribution과 critical 시간대 연결**',
        '기존 +3,310.2741666666666 GPU-h는 V40D의 이전 B1 placement 값이다. Corrected A0를 다시 풀어 site와 같은 site에서의 queue가 달라진 이번 결과는 +3,333.846666666667 GPU-h다. 차이 +23.5725 GPU-h를 버전 차이로 기록했다.',
        '| Half-open window AEST | B0 exact GPU-h | B1 exact GPU-h | 순증 | D-day 순증 대비 |','|---|---:|---:|---:|---:|']
    for w in r['critical_windows']:
        text.append(f"| {w['start_AEST'][11:16]}–{w['end_exclusive_AEST'][11:16]} ({w['window']}) | {w['B0_exact_GPU_hours']:.9f} | {w['B1_exact_GPU_hours']:.9f} | {w['Delta_exact_GPU_hours']:.9f} | {100*w['net_fraction_of_corrected_Dday_delta']:.6f}% |")
    text += ['', '±1 h: job별 증가 418.520000 − 감소 75.840277778 = 순증 342.679722222 GPU-h. ±2 h: 증가 666.160000 − 감소 167.555833333 = 순증 498.604166667 GPU-h. 정확한 실행시간 overlap 적분이다. PCC를 만드는 15분 sampled GPU-h 순증은 각각 345.5, 496.75이며 적분 값과 구분해 저장했다.',
        '전체 service는 양쪽 35,639.25361111111 GPU-h로 같다. Corrected ΔDday=+3,333.846666667, ΔpreD00=−26.0725, ΔpostH=−3,307.774166667이며 합은 부동소수 오차 범위에서 0이다. Runtime/GPU/job universe는 동일하고 duplication, missing-service, case-specific runtime, asymmetric clipping 검사도 통과했다. 이러한 service 시간 분배와 위 직접 PCC 진단을 연결할 수 있지만, 유의한 DA gain을 가진 정책의 out-of-sample degradation으로 분류할 수는 없다.',
        link('시간 창별 job 서비스 ledger',out/'CRITICAL_WINDOW_PER_JOB_SERVICE.parquet')+'.',
        '', '**증거 및 실행 상태**',
        f"B0 Actual run ID: `{r['actual_run_ids']['B0']}`. B1 Actual run ID: `{r['actual_run_ids']['B1']}`.",
        '요구된 workload identity, B0/B1 data-center presence, background mapping, rebuilt Planning electrical authority, power-scale parity, AIDC spatial binding gate는 모두 PASS다. 이는 성능 승인과 별개다.',
        f"기존 protected artifacts {protected['files_checked']:,}개 SHA diff=0; inherited production source {sources['files_checked']:,}개 SHA diff=0. B2/B3와 full May는 실행하지 않았다. 독립적인 UNASSIGNED spillover 44-case blocker도 유지한다.",
        link('canonical forensic JSON',path)+'; '+link('current STOP gate',root/'V40E_CURRENT_EXECUTION_STOP_GATE.json')+'.',
        '', '근거 코드/명세:']
    for e in r['source_evidence']:
        text.append('- '+link(e['source']['path'].split('\\')[-1],e['source']['path']+':'+str(e['start_line']))+': '+e['finding'])
    report=root/'V40E_MAY01_B0_B1_FINAL_REPORT.md';report.write_text('\n\n'.join(text) .replace('\n\n|','\n|').replace('|\n\n','|\n'),encoding='utf-8')
    print('FINAL REPORT '+str(report),flush=True)
    return report
