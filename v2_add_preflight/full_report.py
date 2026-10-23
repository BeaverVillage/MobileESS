"""Truthful Korean final integration report; matrix readiness is not operation."""
import csv,json,subprocess,time
import numpy as np
from .full_common import *

def report():
    init();resources()
    days=read(OUT/'MAY01_07_FULL_READINESS.json')['days'];assert len(days)==7 and all('actual' in d for d in days)
    matrix=read(OUT/'FULL96_MATRIX_PACK_CERTIFICATION.json');assert matrix['matrix_domain_pack_PASS']
    native=read(OUT/'MESS8_FULL_NATIVE0_REPORT.json');jobs=read(OUT/'AIDC_SAME_POLICY_STUDY.json')
    aidc=read(OUT/'AIDC_STRICT_SAME_POLICY_AC.json');mess=read(OUT/'MESS8_CURRENT24_FINITE_AC.json')
    # Correct only an observer flag after checking the actual captured Source
    # matrix row names. Preserve the raw failed-build report and all counts.
    raw=OUT/'MESS8_FULL_NATIVE0_RAW_RUN_REPORT.json'
    if not raw.exists():put(raw.name,native)
    with np.load(RUN/'FULL96_MATRIX_PORT_PACK/MOBILITY_DOMAIN.npz') as z:
        occupied=int(np.count_nonzero(z['row_names']=='all24_mobile_port_occupancy'))
    assert occupied==2304
    native.update(all24_occupancy_added=True,objective_materialized_only_on_complete_build=False,
        explicit_mobile_port_current_kVA_rows_in_this_attempt=False,
        scope='Measured partial monolithic core-grid attempt before explicit600kVA port rows; not current whole-case Native0 certification',
        observer_flag_correction=dict(raw_report=record(raw),evidence_actual_occupancy_matrix_rows=occupied,
            reason='Old observer used optimizer-capture-reached as occupancy flag although2304 rows were inserted before grid construction'))
    put('MESS8_FULL_NATIVE0_REPORT.json',native)
    # Standalone port thermal qualification is distinct from an all-node voltage
    # operating certificate. Preserve the failed whole-evaluation flag as well.
    mr=read(RUN/'MESS_CURRENT24/2025-05-01_ACTUAL/ROWS.json')[24:]
    mess.update(simultaneous8_port_thermal_PASS=all(r['port_violation_cells']==0 and r['transformer_violation_cells']==0 for r in mr),
        all_node_evaluation96_voltage_PASS=mess['actual']['evaluated_TIME_PASS'])
    put('MESS8_CURRENT24_FINITE_AC.json',mess)
    rows=[]
    for d in days:
        p=d['planning'];a=d['actual'];j=d['input_receipt']['independent_job_work']
        rows.append(dict(day=d['day'],Planning_rho_pct=100*p['rho_global'],Actual_rho_pct=100*a['rho_global'],MV_pct=100*a['rho_MV'],
            LV_pct=100*a['rho_LV'],MV_minus_LV_pp=100*a['MV_minus_LV'],eval_event_Vmin=a['evaluation_event_Vmin'],eval_event_Vmax=a['evaluation_event_Vmax'],
            all120_Vmin=a['event_Vmin'],all120_Vmax=a['event_Vmax'],low_seconds=a['voltage_violation_seconds']['low'],high_seconds=a['voltage_violation_seconds']['high'],
            Planning_TIME_PASS=p['full_TIME_PASS'],Actual120_PASS=a['full_TIME_PASS'],eval96_TIME_PASS=a['evaluated_TIME_PASS'],
            independent_Fresh=d['independent_Fresh'],Job_work_PASS=j['PASS'],completed_jobs=j['completed'],carryout_jobs=j['carryout'],
            Compute_GPUh=j['compute_GPUh'],remaining_service_GPUh=j['remaining_service_GPUh']))
    table('MAY01_07_B0_MV_LV_AND_FULL_SECURITY.csv',rows)
    port=read(OUT/'IDC12_PORT_CERTIFICATION.json');port.update(full120_operating_voltage_PASS=False,
        all_node_May01_eval96_operating_PASS=False,limitation='New IDC08 unloaded480V node reaches1.0505238155pu; thermal/PQ qualification does not certify the whole network')
    put('IDC12_PORT_CERTIFICATION.json',port)
    checks=read(OUT/'INDEPENDENT_INTEGRATION_TESTS.json')
    cert=dict(experiment_id='V2_add',status='PRESTART_BLOCKED_WITH_EVIDENCE',baseline=BASE,source=SOURCE,
        READY_FOR_USER_CAMPAIGN_APPROVAL=False,SCIENTIFIC_SIMULATION_READY=False,FIELD_INSTALLATION_UNVERIFIED=True,
        field_missing_is_scientific_blocker=False,Primary_Scenario_certified=False,
        candidate=read(OUT/'CAMPAIGN_EXECUTION_HOLD.json')['candidate'],
        completed=dict(exact_B0_FCFS_GPU_C1_Fresh=True,all2498_B0_Job_work_and_tail=True,source_FULL_reject414_cache=True,
            standalone24_ports_thermal=True,all24_occupancy=True,all96_grid_coefficients=True,
            complete_M1_fixed_B0_matrix_domain_pack=matrix['matrix_domain_pack_PASS'],independent_FULL_STAY_point=matrix['all_rows_independent_STAY_PQ0_point_PASS'],
            all7_dates_actual_and_independent_Fresh=True,all7_Job_work=True,source_ingestion_defects_fixed_without_new_flexibility=True),
        remaining=dict(P1='Causal prior IEEE8500 Job-site/power/controls/queue state missing; cold Prefix and Planning TIME violations remain',
            P2='Strict finite same-policy preplace is not complete r043 Known/Unknown/C0/C1/Current-AC/FULL optimizer integration; completion/carryout pattern differs',
            P3='New IDC LV event voltage above1.05pu; adopted delta/wye research hardware differs from original V44 wye/wye, operational domain not certified',
            P4='Whole monolithic Native0 exceeded4GiB; original AIDC-variable grid, K48/Adaptive Beam/DirectJoint and independent original current-case proof interface not bound',
            P5='Seven dated inputs/Fresh/Job work prepared; whole TIME voltage fails. Optimizer response kernels currently May01 only; dated Stage handlers/Worker campaign not admitted'),
        independent_tests=checks['PASS'],matrix_case_sha=matrix['case_sha'],matrix=matrix['matrix'],
        gates=dict(G1='MODEL_MAPPING_COMPONENTS_PASS_NEW_IDC_OPERATING_VOLTAGE_FAIL',
            G2='ALL7_B0_ACTUAL_FRESH_MEASURED_TIME_OPERATION_FAIL',G3='FINITE_PILOTS_MEASURED_CAMPAIGN_AIDC_FULL_NOT_CERTIFIED',
            G4='COMPLETE_M1_MATRIX_PACK_PASS_MONOLITHIC_AND_ORIGINAL_STAGE_INTEGRATION_BLOCKED'),
        Native_optimizer_calls=0,official_campaign_executed=False,source_workers_or_ledgers_changed=False)
    put('FINAL_INTEGRATION_CERTIFICATION.json',cert)
    tablelines='\n'.join(f"|{r['day'][5:]}|{r['Planning_rho_pct']:.6f}|{r['Actual_rho_pct']:.6f}|{r['MV_pct']:.6f}|{r['LV_pct']:.6f}|{r['MV_minus_LV_pp']:.6f}|{r['eval_event_Vmin']:.6f}–{r['eval_event_Vmax']:.6f}|{r['low_seconds']:.0f}/{r['high_seconds']:.0f}|FAIL|PASS|" for r in rows)
    c=matrix['matrix'];n=native['model'];base=read(OUT/'B0_INDEPENDENT_FULL_WORK.json');jc=jobs['independent_work']
    text=f'''# V2_add PR #236 FULL 통합 준비 검토

**PRESTART_BLOCKED_WITH_EVIDENCE**. `READY_FOR_USER_CAMPAIGN_APPROVAL`과 전역 `SCIENTIFIC_SIMULATION_READY`는 FALSE다. `FIELD_INSTALLATION_UNVERIFIED`는 별도이며 GIS·현장 보호 인증의 부재를 이번 과학 시뮬레이션 차단 사유로 쓰지 않았다. 기준 HEAD `{BASE}`, 원본 `{SOURCE}`, 동일 Draft PR #236을 유지했다. 공식 캠페인, A1/M1/A2/M2/K48/Joint 최적화를 실행하지 않았다. Native0 생성자의 optimizer/presolve는 차단했다.

## 수정과 독립 검증

1. **원본 B0 FCFS 수정 완료.** Generic JobEventController를 B0로 사용했던 오차를 제거하고 원본 BaselineController/OriginalFCFS 및 CorrectedReference를 연결했다. 동결 GPU·C1 전력 최대 오차 모두0이며 새 독립 재생 이벤트도 동일하다. 2,498 Job 중 완료{base['completed']}, Carryout{base['carryout']}; 계산량{base['compute_GPUh']:.9f}GPUh + 잔여{base['remaining_service_GPUh']:.9f}GPUh = 원본 서비스{base['required_service_GPUh']:.9f}GPUh다. Job별 잔차0초, 전체 시간·사이트 GPU 재적분 오차는1e-13 수준이다. Carryout을 삭제하거나 GPUh를 훼손한 반례는 검증기가 거부한다.
2. **AIDC 제한적 진척.** 원본1499 Job 전체 옵션/공유 GPU·WAN/Rack 도메인 검증을 통과하는 UID8665305의 사전 배치1개를 얻었다. 기존414개 시작시간 위반 캐시는 계속 거부한다. 같은 strict B1 제어기끼리 비교한 최대 전력 차이는{jobs['nonzero_power']:.9f}kW, 의도적 QoS 초과0, 독립 재생 동일이다. 그러나 이 비교의 기준은 원본 FCFS B0가 아니다. 계산 GPUh 차이{jobs['daily_compute_GPUh_difference']:.9f}, 완료{jc['SAME_POLICY_BASE']['completed']}→{jc['SAME_POLICY_PRESITE']['completed']}, Carryout{jc['SAME_POLICY_BASE']['carryout']}→{jc['SAME_POLICY_PRESITE']['carryout']}이며 서비스 총량만 정확히 보존된다. 같은 정책의 AC 전역 최대 개선은{aidc['global_rho_reduction_percentage_points']:.12f}%p로 사실상0이다. 완성된 r043 FULL 운전 가능해나 B1/B3 성과로 승격하지 않았다. Source QoS와 Known 완화 정책을 구분하고 GPU Scaling은 실행하지 않았다.
3. **IDC 물리 계약을 추적했다.** 원본 DSS는 IDC마다 건물1500kVA와 별도 MESS750kVA 변압기·Generator/Load를 갖는다. IDC는 방문 전용이 아니며 P/Q가 허용된다. 같은 C2 MV 지점에 독립750kVA/480V, 포트600kVA·721.6878A·점유1을 추가했고 AIDC 건물 소비와 차량 주입을 분리했다. 12 IDC × P/Q 네 모서리48개 포트 열·전류 검증은 PASS다. 원본 IDC는 wye/wye, 현재 Adapter는 PR199 계열 delta/grounded-wye·각R0.5%·XHL5.6624%라는 연구 설비 가정이므로 전기적 완전 동일성을 주장하지 않는다. 기존 STA12·도로24위치·Route/ETA/이동 에너지는 유지했다.
4. **중요한 신규 전압 결함.** May01 평가96에서 기존 노드 최대는1.049087915pu지만 신규 `full_mobile_idc08_lv.1`은 t=44134초에1.050523816pu다. 무주입480V 포트도 안전성 검사에 포함했다. 이전 STA12 모델의 평가96 PASS는 이번24포트 모델의 PASS가 아니다. 열 정격 PASS와 운영 전압 PASS를 분리했으며 설비·Source·P5·SVR·PCC를 결과에 맞춰 조정하지 않았다.
5. **날짜별 입력 결함 수정.** May02/07의 원본 hourly wet-bulb 결측2건은 원본 SHA/행을 보존한다. 완전한 직전 관측쌍을 기존 as-of 전진 유지 정책으로 사용하며 최대 관측 나이6300초는 원래7200초 한도 안이다. 보간·미래 조회·원본 값 채움은 없다. May03/07의 Planning 비대상 초기 Running7개는 새 Window/유연성을 만들지 않고 기존 외부 Running의0유연 계약으로 서비스·초기 사이트를 계속한다. 추가 Provider/Case SHA도 별도 바인딩했다. 일곱 날짜 모두 원본 FCFS 재생·Job 작업량·Actual120·독립 Fresh를 확보했다.

## 실제 B0 날짜별 수치

전역 목적함수는 원본 선로 parent terminal의 평가96 **각 슬롯 마지막 TIME 해** 최대다. 이벤트 극값·전체120 안전은 별도이며 MV/LV를 목적함수에서 제외하지 않았다. 저/고 위반 시간은 전체120의 Native 해가 다음 물리 이벤트까지 유지되는 시간이다.

|날짜|Planning 최대%|Actual 전역%|MV%|LV%|MV−LV %p|평가 이벤트 Vmin–Vmax|전체 저/고 초|전체TIME|Fresh|
|---|---:|---:|---:|---:|---:|---|---:|---|---|
{tablelines}

모든 날짜 β_BG2.00/Actual SVR3/C2/GPU780/MESS8로 동일하다. Fresh는 새 DSS 문맥이며 모든 저장 배열이 같았다. 상세 선로·상별 슬롯 병목과 Top20은 `ALL_DATES_SETTLED_SLOT_BOTTLENECKS.csv`, `ALL_DATES_SETTLED_TOP20.csv`에 있다. 모든 전압 위반과 선로·변압기·포트 검사 원본은 Runtime에 보존했다. May02 이후 β/PCC를 재선정하지 않았다.

## TIME 및 제어 Authority

Planning은 원래 Reg12/CapControl9, Actual은 원래 Reg12 + 추가3상 Bank3개/Reg9 = Reg21이다. P5 Source1.04/Vreg123.5/CAPBank3 초기OFF, 원래 Delay15/TapDelay2와 추가 SVR의 Vreg120/Delay30/TapDelay2/MaxTapChange1을 유지했다. 7일 모든 Native TapNumber–Winding2 대조·시간 순서·미래 Queue 검증 PASS, 포화 설비0개다. HVMV_Sub·STA750·IDC750에는 자동 RegControl이 없다. 수치 반복100은 물리 지연을 생략하지 않는다.

원시 이전 AEMO/Weather 관측은 존재한다. 그러나 원본 May01 초기 사이트는 모델상 배치이며 이전 IEEE8500의 연속 Job-site 전력·Tap/Cap 내부 상태·Queue를 함께 고정한 이력은 없다. IEEE123 Tap, 이후 정착 상태 또는 반복 Prefix를 인과 초기 상태로 복사하지 않았다. 냉시동 저23초/고18초를 삭제하지 않았으며 신규 IDC 평가 이벤트 과전압13초도 추가 기록했다. Planning TIME과 다른 날짜의 위반도 남는다. 초기 이력만 고치면 전체 날짜가 해결된다는 인증은 없다.

## 전체 Grid + MESS8 Native0

원본3703개 선로/1177 Triplex/정격·비활성5개와 원본 변압기를 보존했다. 96슬롯 × 60 controls(AIDC12 부하,24 차량 사이트 P/Q)의 실제 IEEE8500 계수를 생성했다. Parent6156셀, 양단12322셀, 전압8603노드, 변압기 전류7310셀·kVA3605 winding을 유지한다. Planning96의 이전/현재 Tap·Cap 상태는 모두 동일하며 앵커 차이는 전류비1.4e-9·전압제곱1.33e-9다. 5kW/kvar 독립 holdout27건의 최대 전류비 오차0.0003623·전압제곱5.024e-7을 기록했다. 이는 전역 AC 정확도 증명이 아니며 Actual/Fresh가 필요하다.

단일 실제 Gurobi 모델은 보호 한도에서 중단됐다: Binary{n['binary']:,}, Continuous{n['continuous']:,}, Rows{n['linear_constraints']:,}, Nonzero{n['nonzeros']:,}, {native['wall_seconds']:.2f}초, Peak RSS{native['peak_RSS_bytes']/1024**3:.4f}GiB. 완료23슬롯+다음 슬롯 일부의 **부분 모델 실측**이며 전체 FULL PASS가 아니다. 이 첫 코어 시도 이후 추가한600kVA 포트 명시 행은 아래 전체 팩에 포함된다.

메모리를 제한한 실제 Native0 이동 모델과 실제 Native0 전기 블록96개를 생성하고, 임시 포트 alias만 ±1 가중치로 원본8대 Pdis−Pch/Q에 정확히 대입해 전체 행렬·변수 도메인을 저장했다. 행이나 Route를 줄이지 않았다. 전압 equality+bound, 원본16face 전류 보정식, 양단전류, 모든 transformer winding current/kVA,24포트 전류/600kVA16face, 원본 flow/mode/PCS16/P300/Q250/SOC/이동에너지 및2304점유 행이 들어 있다. Gurobi가 작은 비영 계수를 버리지 않도록 양의2거듭제곱 행 배율을 기록했고 원본 Solver budget/Gap은 바꾸지 않았다.

완성 행렬 팩 실측: **Binary{c['binary']:,}, Continuous{c['continuous']:,}, 전체 변수{c['columns']:,}, Rows{c['rows']:,}, Nonzero{c['nonzeros']:,}**. Case SHA `{matrix['case_sha']}`. Source 원본 차량 검증기와 독립 전체 행/box/integrality 검증을 통과하는 B0 고정-AIDC STAY/PQ0 점을 얻었다(ρ={matrix['witness_rho']:.12f}). STAY/MOVE 변수 도메인은 자유이며 이 점만 STAY 증인이다. 최적화·LB·Gap·B3 성과가 아니다. **전체 행렬 팩과 단일96슬롯 Gurobi 생성 성공을 구분한다.**

기존 Q50 두 피크 유한 Pilot도24포트 모델에서 재생했다. B0{100*days[0]['actual']['rho_global']:.6f}%→{100*mess['actual']['rho_global']:.6f}%, 개선{mess['global_rho_reduction_percentage_points']:.6f}%p, Source SOC/PCS/초기종단760 검증 및 Fresh 동일이다. 그러나 신규 IDC 무주입 과전압과 Prefix 때문에 전체 운영 PASS는 아니다. 2.4MW 순간 정격을 하루 에너지로 계산하지 않았다.

## 남은 단계와 실행 HOLD

완료한 M1 팩은 **May01 B0 고정 AIDC의 Planning affine FULL 모델**이다. May02–07의 optimizer용 응답 계수, A1/A2의 CC4/Job/GPU→C1→전체 Grid 가변 연결, 실제 r043 C0/C1/Current-AC/완화 Known 정책의 분리된 수용 검사, K48/Adaptive Beam/Direct Joint의 새 행렬·도메인·물리 metadata와 독립 Global-LB 인터페이스, 고정 M1→A2→M2 handoff 및 실제 Stage handler/Worker는 남는다. 원래7/43·120행·4대 guard를 숫자만 치환해 통과시키지 않았다. 예전 bounds·Golden414·restricted bounds를 이식하지 않았다.

독립 검사{len(checks['checks'])}개 및 그 안의 기존 수용·Checkpoint·HOLD 회귀8개를 통과했다. 원본 B0/B1/B2/B3 Chain과 Checkpoint/Resume/중복 OS lease/원장 재조정·Budget 보존 fixture를 재검증했다. A5400초/K48300초/M900초/Gap0.5%·3% 및 r043 Q250_M4의 실제 Joint call cap300초·M4 threads/A1 thread1을 기록했다. 이번 작업의 Heavy Native optimizer 호출은0이며 기존 Worker·Source·원장·V1_add는 수정하지 않았다. 기준368개 V2_add 파일은 모두 같은 SHA다.

`python -m v2_add_preflight.full_execution plan`으로 보류 설정과 준비 명령을 확인할 수 있다. 실제 캠페인 명령은 필수 결함과 실제 handler 연결이 해소될 때까지 fail-closed다. 별도 사용자 캠페인 승인을 요구할 수 있는 READY 상태로 아직 승격하지 않는다. 현장 인증의 부재와 과학 모델의 전압·수학/알고리즘 통합 미완료를 혼동하지 않는다.
'''
    (OUT/'FINAL_FULL_INTEGRATION_REVIEW_KO.md').write_text(text,encoding='utf-8')
    # Compact PR description for a reviewer who has not read this conversation.
    body=f'''V2_add의 잘못된 B0 FCFS 비교와 IDC 차량 접속 누락을 수정하고, IEEE8500 전체96 전기 계수·24포트·MESS8 행렬 팩 및 May01–07 Actual120/Fresh를 준비합니다. 공식 캠페인과 Native 최적화는 실행하지 않았습니다.

- B0 GPU/C1 오차0,2498 Job의 compute+carryout 서비스 보존 및 독립 재생 PASS. Golden414 거부 유지.
- 원본 IDC 별도750kVA 계약 추적,24포트 current/600kVA/점유, 원본3703선로·1177Triplex·parent 목적함수 유지.
- 전체 행렬 팩: Binary{c['binary']:,}, Continuous{c['continuous']:,}, Rows{c['rows']:,}, NNZ{c['nonzeros']:,}. 원본 이동+96 Native0 전기 블록의 전체행 STAY 증인 PASS. 단일 Gurobi FULL 생성은4GiB 보호 한도로 실패했으며 별도 기록.
- 7일 B0 Actual 전역 최대: {', '.join(f"{r['day'][5:]} {r['Actual_rho_pct']:.4f}%" for r in rows)}. 모든 날짜 Fresh 및 Job 작업량 PASS, TIME 전압 운영 인증 FAIL.
- 신규 IDC08 LV 평가 과전압1.050524pu와 Prefix/Planning 위반 보존. Source Known/Unknown/Current-AC FULL 및 K48/Beam/Joint 실제 Stage 연결도 잔여.
- 상태 **PRESTART_BLOCKED_WITH_EVIDENCE**. SCIENTIFIC_SIMULATION_READY FALSE, FIELD_INSTALLATION_UNVERIFIED 별도. β/PCC/SVR/차량 수를 결과에 맞춰 조정하지 않음.

한국어 상세 보고: docs/v2_add/integration/FINAL_FULL_INTEGRATION_REVIEW_KO.md
독립 검증: docs/v2_add/integration/INDEPENDENT_INTEGRATION_TESTS.json
전체 행렬/도메인: docs/v2_add/integration/FULL96_MATRIX_PACK_CERTIFICATION.json
'''
    (OUT/'PR_BODY_KO.md').write_text(body,encoding='utf-8')
    print('FINAL INTEGRATION',cert['status'],flush=True)

if __name__=='__main__':report()
