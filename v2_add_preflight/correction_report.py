"""Final reports use settled-slot objective and separate event/prefix safety."""
import csv,json
from pathlib import Path
import numpy as np
import pandas as pd
from .audit import ROOT,DOC,read,sha
from .correction import OUT,RUNTIME,put,csvout
from .correction_projection import CAN
from .correction_svr import SV

def md(name,text):(OUT/name).write_text(text.strip()+'\n',encoding='utf-8')
def table(df,columns):
    rows=['| '+' | '.join(label for key,label in columns)+' |','|'+'|'.join('---' for _ in columns)+'|']
    for _,r in df.iterrows():
        cells=[]
        for k,label in columns:
            v=r[k];cells.append(f'{v:.6f}' if isinstance(v,(float,np.floating)) else str(v))
        rows.append('| '+' | '.join(cells)+' |')
    return '\n'.join(rows)

def main():
    old=pd.read_csv(OUT/'RECALCULATED_B0_AND_PILOT.csv');old=old[(old.role=='ACTUAL')&(old.beta_BG==1.5)&~old.fresh]
    ob=old[old.kind=='B0'].iloc[0];om=old[old.kind=='MESS_ONLY'].sort_values('rho_max').iloc[0]
    alltime=pd.read_csv(CAN/'ALL_TIME_CASES_CANONICAL_RESULTS.csv');b0=alltime[(alltime.kind=='B0')&~alltime.fresh].copy()
    pilots=pd.concat([pd.read_csv(CAN/n) for n in ('MESS8_TEMPORAL_PILOT_COMPARISON.csv','MESS8_CHARGE_SPREAD_COMPARISON.csv')],ignore_index=True)
    pilots=pd.concat([pilots,pd.read_csv(OUT/'PEAK31_DIAGNOSTIC_CANONICAL_RESULTS.csv')],ignore_index=True)
    s1pilots=pd.read_csv(OUT/'SVR_PEAK31_DIAGNOSTIC_CANONICAL_RESULTS.csv')
    sv=pd.read_csv(SV/'S0_S1_ACTUAL_TIME_RESULTS.csv');sv=sv[~sv.fresh].copy()
    compare=pd.read_csv(CAN/'STATIC_VS_TIME_CONTROL_AUDIT.csv');aidc=read(OUT/'AIDC_REAL_FEASIBILITY.json')
    security=[];tapcaps=[];receipts=[]
    for runtime in ('correction_time100','correction_old_pilot_time100','correction_charge_spread_time100'):
        for file in sorted((RUNTIME/runtime).glob('*/RECEIPT.json')):
            p=file.parent;r=read(file);er=read(p/'EVENT_ROWS.json');events=read(p/'EVENTS.json');states=read(p/'STATES.json')
            receipts.append(dict(receipt_path=str(file),**r))
            security.append(dict(case=r['case'],scope='ALL_NATIVE_EVENTS_INCLUDING_PREFIX',role=r['scientific_inputs']['role'],beta_BG=r['scientific_inputs']['beta'],
                all_event_security_PASS=all(v['physics_PASS'] for v in er),failed_events=sum(not v['physics_PASS'] for v in er),
                Vmin=min(v['Vmin'] for v in er),Vmax=max(v['Vmax'] for v in er),rho_all_terminals=max(v['rho_all_terminals'] for v in er),
                transformer_current_max=max(v['transformer_current_max'] for v in er),transformer_nameplate_max=max(v['transformer_nameplate_max'] for v in er),
                port_current_max=max(v['port_current_max'] for v in er),PV_actual_command_error_kw=max(v['PV_total_abs_error_kw'] for v in er),
                BG_actual_command_error_kw=max(v['BG_P_abs_error_kw'] for v in er),AC_balance_max_kw_kvar=max(abs(v[k]) for v in er for k in ('balance_P_error_kw','balance_Q_error_kvar')),receipt=str(file)))
            for t,s in enumerate(states):tapcaps.append(dict(case=r['case'],slot=t,last_solve_seconds=events[t]['last_solve_seconds'],final_taps=json.dumps(s['taps'],sort_keys=True),final_caps=json.dumps(s['capacitors'],sort_keys=True)))
    csvout('TIME_EVENT_SECURITY_AND_INPUT_AUDIT.csv',security);csvout('TIME_TAP_CAP_SLOT_TRAJECTORIES.csv',tapcaps);put('CORRECTED_AC_ARCHIVE_RECEIPTS.json',receipts)
    pilots.to_csv(CAN/'MESS8_PEAK_SHIFT_ANALYSIS.csv',index=False)
    for df in (b0,sv):
        df['max_pct']=100*df.rho_objective;df['MV_pct']=100*df.rho_MV_objective;df['LV_pct']=100*df.rho_LV_objective
    actual=b0[b0.role=='ACTUAL'].sort_values('beta_BG')
    b0['rho_Triplex_objective']=b0.rho_LV_objective
    b0.to_csv(CAN/'B0_MV_LV_TRIPLEX_EXPLICIT.csv',index=False)
    eligible=[];fallback=[]
    for beta,g in b0.groupby('beta_BG'):
        a=g[g.role=='ACTUAL'].iloc[0]
        if .75<=a.rho_objective<=.85 and a.MV_LV_headroom_pp>=5 and g.physics_PASS.all():eligible.append(float(beta))
        if .70<=a.rho_objective<=.85 and a.MV_LV_headroom_pp>=5 and g.physics_PASS.all():fallback.append(float(beta))
    qualified=sv[sv.physics_PASS & sv.all_event_security_PASS & sv.rho_objective.between(.75,.85)]
    operational=sv[sv.physics_PASS & sv.evaluation_all_event_security_PASS & sv.rho_objective.between(.75,.85) & (sv.MV_LV_headroom_pp>=5)]
    freeze=dict(experiment='V2_add',status='NO_QUALIFIED_SCENARIO_AFTER_EXTENSION',assessment='Includes additional S0/S1 physical SVR screen',beta_BG=None,Primary_certified=False,
        S0_settled_both_role_target_candidates=eligible,S1_all_event_physical_target_candidates=qualified[['configuration','beta_BG']].to_dict('records'),
        S0_settled_both_role_fallback_candidates=fallback,
        Actual_evaluation96_operational_candidates=operational[['configuration','beta_BG','rho_objective','Vmin','Vmax']].to_dict('records'),
        scope='Operational96 candidates are preserved, not rejected solely for S0 voltage failure; Primary full-contract certification remains separate',
        blockers=['TIME all-event voltage/input/rating and initial/prefix safety','Planning414 FULL allowed-start mismatch','Actual nonzero causal AIDC witness NOT_VERIFIED','Source customer QoS NOT_CERTIFIED'],
        hardware_preregistration='svr/SVR_CANDIDATE_PREREGISTRATION.json',original_C2_unchanged=True,no_beta_above_2_10=True)
    put('SELECTED_SCENARIO_FREEZE.json',freeze)
    feasible=pilots[pilots.physics_PASS & pilots.all_event_security_PASS]
    evaluation_feasible=pilots[pilots.physics_PASS & pilots.evaluation_all_event_security_PASS]
    final=dict(experiment='V2_add',OBJECTIVE_CERTIFIED=True,TIME_CONTROL_CERTIFIED=True,
        measurement='Parent-terminal objective at final native solved state per slot; evaluation96; event/prefix safety separate',
        numerical_adapter='IEEE8500 electrical100 / control100, strict electrical15 failure preserved',
        PV_MAPPING='PASS_CONNECTION_CAPACITY_COMMAND_CONSERVATION; operating actual conservation is case-specific',
        C2_PCC_STA_MESS8='Research physical mapping verified; operation case-specific',SOURCE_QOS_CERTIFIED=False,AIDC_status=aidc['status'],
        Actual_evaluation96_operational_candidates=freeze['Actual_evaluation96_operational_candidates'],
        feasible_MESS_settled_pilots=int(pilots.physics_PASS.sum()),feasible_MESS_all_event_pilots=len(feasible),
        feasible_MESS_evaluation96_event_pilots=len(evaluation_feasible),
        S0_best_finite_evaluation96_improvement_pp=float(evaluation_feasible.delta_global_pp.max()),
        S1_03_beta2_finite_evaluation96_improvement_pp=float(s1pilots[s1pilots.physics_PASS & s1pilots.evaluation_all_event_security_PASS].delta_global_pp.max()),
        S1_03_beta2_cold_prefix_low_voltage_seconds=float(sv[(sv.configuration=='S1_03')&(sv.beta_BG==2.)].iloc[0].prefix_low_voltage_seconds),
        SCENARIO_SELECTED=False,G4_READY_NATIVE0=False,G4_status='G4_NOT_READY',native_optimizer_calls=0,
        gates=dict(G1='Mapping verified; operating physical/input gates case-specific',G2='All registered S0 Planning96/Actual120/Fresh and S1 Actual120/Fresh executed',
            G3='Finite MESS/local sensitivity measured; Actual nonzero AIDC/migration unverified',G4='NOT_READY; Native0 model build not executed'),
        original_evidence_preserved=True)
    put('FINAL_V2_ADD_GO_NO_GO.json',final)
    md('OBJECTIVE_CONTRACT_AUDIT_KO.md',f'''# 목적함수·측정시점 계약 감사

기존 All-Terminal Mask는 원본과 불일치했다. r043 `v42_thermal/measurement.py:branch_measurement`의 source-rooted parent terminal/원본 NormalAmps로 복원했다. `v42_native/grid.py:add_grid`의 변압기 제약은 선로 목적함수와 별도다. 독립 Dijkstra와 PR197 방향은 일치한다. 원본3703개, parent 실제도체6156개, 양단 안전도체12322개, 역방향terminal2 선로1개, disabled5개를 보존한다. LV/Triplex1177개를 포함한다.

기존56개 배열은 새 Solve 없이 재계산했다. Static β1.50 Actual B0 **{ob.rho_max*100:.12f}%**, MESS 감소 **{om.delta_global_pp:.12f}%p**다. 기존 양단56.1468981373%/0.2017599331%p와의 차이는 정의 차이에 따른다.

원본 `v44/svr11_frozen/v42_voltage_control/integration.py:PhysicalScenario.settle_actual`는 `CommonClock.settle_slot` 이후 측정한다. `v43_actual/current_ac.py:_probe`/`v44/svr11_ac.py:probe_body`도 이 상태를 읽고 `v43_actual/compare.py`의 Fresh 범위는 physical_steps[24:]다. **각 슬롯 마지막 native solved state에서 parent 비율을 구한 평가96 최대값**이 원본 목적함수다. 모든 이벤트 최대값은 안전 진단이다.

correction 루트의 기존 TIME CSV는 이벤트 envelope 중간 산출물로 보존한다. 최종 수치는 `canonical/`, SVR 수치는 `svr/`를 따른다. `CURRENT_MEASUREMENT_CONTRACT.json`과 선택 index Receipt가 이를 명시한다. 저장 배열 재투영에 추가 Solve는 없다. Prefix24/전체120 이벤트 안전도 별도 표시한다. 직접 CAPI CurrentsMagAng/NormalAmps, 원본 정격, 독립 마지막 이벤트 선택 및 float64 허용오차1e-12를 검사했다. 독립 Fresh 허용오차1e-9, 전력수지1e-4는 계산 전에 등록했다.
''')
    md('AIDC_REAL_FEASIBILITY_REPORT_KO.md',f'''# AIDC 정책·실제 실행 가능성

Planning414개는 원본 FULL WINDOWS.allowed_starts 밖의 cache Accepted start다. `v44/planning.py:golden`의 cache 수용과 도메인 인증은 별개다. V44_POLICY_OR_PHYSICAL_VIOLATION은 Planning FULL 범위에 한정한다. 원본 A1을 다시 풀거나 Actual 연구정책 구현 오류라고 단정하지 않았다.

Actual192개는 모두 Known이며 KNOWN_RESEARCH_WINDOW_ASSUMPTION 이벤트가 있다. `v43_corrective/known_window.py`/`v44/actual_policy.py`의 opt-in 연구정책에서 원래 latest/deadline/QoS는 사후 측정이다. V44_RESEARCH_POLICY_COMPLIANT_BUT_SOURCE_QOS_NOT_CERTIFIED로 분류했다. 원본 Source_authorized=False, QoS_PASS=NOT_CLAIMED를 유지한다. UID별 Window/Budget/Deadline/Intentional Burden/권한·정책·근거 Source는 두 재감사 CSV에 있다.

전체 Gang/allowed start/복수 Job/Site, Prefix·Capacity·Budget·Deadline·완전 Rebound로 확대한 동일 Site 지연 witness는0개다. 사유는 {json.dumps(aidc['expanded_search_reason_counts'],ensure_ascii=False)}이다. Pending Known1395개는1GPU, 이미 RUNNING254개 중70개는 multiGPU다. Window 후보1024개를 kW로 환산하지 않는다. Unknown849개의 양수 Budget은0개다. 이번 witness 범위의 이동GPUh/피크74 이동/Rebound는0이고 원본 C1 Actual 전력 재현오차0kW, 서비스/GPUh 변화0이다. 전체 AIDC 유연량의 상한0을 뜻하지 않는다.

Pre-site/Migration은 NOT_VERIFIED/null이다. 호환12 Site/boolean capability를 feasible kW로 인증하지 않는다. 원본 causal controller/admission/reservation, capability packet,1800초 checkpoint,WAN80GB,Rack/GPU/Residency/경로,Source/Destination 동시 점유,Restart/공유 Budget의 FULL witness가 필요하다. 같은 시작시각 Site 이동으로 Window 밖인364개를 엄격 witness로 만들 수 없다. 별도 PREPLACE_MIGRATION 감사가 이를 기록한다. 비영 Actual AIDC/Joint 성과를 주장하지 않는다.
''')
    md('V44_IEEE8500_G4_READINESS_AUDIT.md','''# G4 준비 감사

**G4_NOT_READY. Native0 Model Build와 A1/M1/A2/M2/K48/Beam/Joint MILP를 실행하지 않았다.**

G2 B0 AC는 G3 Pilot/G4 미완료와 독립 실행했다. 다음 작업은 모든 TIME 이벤트와 초기/Prefix 전압·입력·정격 계약, Planning414 cache 도메인 원인/원본 FULL 일관성, Source QoS/연구정책 권한, 비영 Actual AIDC causal Job/GPUh/Rebound/WAN FULL witness다.

그 후 Grid parent 축/LV 전부 및 양단 안전, MESS4→8 차원, SOC/Mode/P/Q/PCS16, 원래55296 Route/ETA/이동에너지, K48 FULL 하한·Beam 공동 경로·Direct Joint MILP·원래 A1/A2 도메인·LB/UB/Gap·Actual TIME/Fresh를 원래 구조로 이식한다. Planning 기본설비/Actual 추가설비 계약을 유지하고 모든 비교군에 같은 Actual 장비/제어 정책을 적용한다. IEEE123의7/43을 IEEE8500 개수로 강제하지 않는다.
''')
    bt=table(actual,[('beta_BG','β'),('max_pct','전체%'),('MV_pct','MV%'),('LV_pct','LV/Triplex%'),('MV_LV_headroom_pp','MV−LV %p'),('Vmin','최저pu'),('Vmax','최고pu'),('physics_PASS','최종 물리'),('evaluation_all_event_security_PASS','평가 이벤트 안전')])
    st=table(sv.sort_values(['configuration','beta_BG']),[('configuration','설비'),('beta_BG','β'),('max_pct','전체%'),('LV_pct','LV%'),('Vmin','최종 최저pu'),('Vmax','최종 최고pu'),('evaluation_all_event_Vmin','이벤트 최저pu'),('evaluation_all_event_Vmax','이벤트 최고pu'),('evaluation_low_voltage_seconds','저전압초'),('evaluation_high_voltage_seconds','과전압초'),('unique_original_controls_at_limit','기존 한계수'),('physics_PASS','최종 물리'),('all_event_security_PASS','전체 이벤트 안전')])
    pt=table(pilots,[('beta_BG','β'),('schedule','배치'),('delta_global_pp','전역 개선%p'),('at_original_peak_reduction_pp','원피크 개선%p'),('peak_slot','새 피크'),('physics_PASS','최종 물리'),('evaluation_all_event_security_PASS','평가 이벤트 안전'),('all_event_security_PASS','전체 이벤트 안전')])
    spt=table(s1pilots,[('schedule','S1_03 배치'),('delta_global_pp','전역 개선%p'),('peak_slot','새 피크'),('Vmin','최종 최저pu'),('Vmax','최종 최고pu'),('physics_PASS','최종 물리'),('evaluation_all_event_security_PASS','평가 이벤트 안전'),('all_event_security_PASS','전체 이벤트 안전')])
    low=[r for r in read(SV/'S0_VOLTAGE_EXTREMA_PATHS.json') if r['scope']=='SETTLED96' and r['kind']=='LOW' and r['beta_BG']>=2]
    phases={r['buses'][0].split('.')[0].lower():r['primary_phase'] for r in read(DOC/'source/PR197_PV_HOT_RECORDS.json')}
    paths='\n\n'.join(f"β{r['beta_BG']:.2f}: `{r['node']}`, Primary상{phases.get(r['node'].split('.')[0],'SEE_WIRING')}, 평가slot{r['evaluation_slot']}, {r['voltage_pu']:.9f}pu. 경로: "+' → '.join('`'+x['element']+'`' for x in r['path']) for r in low)
    units=read(SV/'SVR_CANDIDATE_PREREGISTRATION.json')['contracts']['S1_12']['units']
    positions='\n'.join(f"- {u['id']}: `{u['cut_element']}` terminal1 직렬, sense `{u['sensed_bus']}`, 상별{u['phase_kva']:.3f}kVA/{u['ctprim']:.1f}A." for u in units)
    gain=float(feasible.delta_global_pp.max()) if len(feasible) else None
    evaluation_gain=float(evaluation_feasible.delta_global_pp.max()) if len(evaluation_feasible) else None
    losses=pd.read_csv(SV/'INDEPENDENT_NEW_SVR_FINAL_SLOT_LOSSES.csv')
    loss_anchor=losses[losses.beta_BG==2.].groupby('configuration').measured_losses_kw.sum().to_dict()
    op3=sv[(sv.configuration=='S1_03')&(sv.beta_BG==2.)].iloc[0]
    action_logs={name:read(SV/file)['native_action_log_rows'] for name,file in
        [('S0','ACTION_LOG_NONINTERFERENCE_S0.json'),('S1_03','ACTION_LOG_NONINTERFERENCE_S1_03_EARLY.json')]}
    md('FINAL_V2_ADD_CORRECTION_REVIEW_KO.md',f'''# V2_add PR236 원본 동등성 및 S0/S1 검증

최종 **Primary 미인증 / G4_NOT_READY**다. S0뿐 아니라 추가3/6/12 Bank를 실제 TIME/Fresh로 평가한 뒤 판정했다. 새 실험 버전은 없다. 기존 소스·증거·Worker를 보호했고 Native 최적화0회, 강제종료0회다.

## 목적함수와 시간 계약

원래 parent terminal/원본 NormalAmps로 수정했고 LV/Triplex를 포함한다. 기존56개 배열을 독립 재계산한 Static β1.50 Actual B0는 {ob.rho_max*100:.12f}%, MESS 감소 {om.delta_global_pp:.12f}%p다. TIME은 원본 r043과 같은 **슬롯 마지막 native solved state**의 평가96 최대값이다. 모든 이벤트 envelope와 Prefix24 안전은 별도다. 최종 CSV는 canonical/ 및 svr/이며 correction 루트의 초기 TIME CSV는 보존된 중간 이벤트 envelope다.

원본 CommonClock Snapshot/TIME2/실제 Queue/경계입력 순서를 사용했다. Delay15/TapDelay2초, Cap Delay/DelayOff100~102/80~102초·DeadTime300초·전압 override를 유지했다. Prefix→평가에서 상태/Queue를 리셋하지 않았다. IEEE123 전기 반복15는 β1.50 Actual 첫점에서 비수렴했고 보존했다. IEEE8500 기존 전기 반복100만 명시적 확장했으며 제어 반복100은 동일하다. 먼저 완료한 strict15 6개는100 결과와 배열이 비트 일치했다. 물리 Delay 생략과 반복을 초로 환산하는 처리는 없다.

Static/TIME 슬롯 최종 parent 지표 최대 차이 {compare.canonical_difference_pp.abs().max():.9f}%p, Tap 최종 차이 {int(compare.final_taps_differ.sum())}/{len(compare)}, Cap 차이 {int(compare.final_caps_differ.sum())}/{len(compare)}슬롯이다. 수치 반복 실패와 수렴한 후 물리 전압 부족을 분리한다.

## PV·PCC·MESS8

PV Mapping은 **PASS(연결·용량·명령 보존)**다. PR197의2354개 .12kV Hot Leg/상 연결과 설치용량 가중치로 원본96/120 PV 총량을 배분했다. Q0/Model1/개별 설치·인버터 제한을 유지했다. 원래 IEEE8500 Generator0에2354개만 추가했고 중복 투입/부하 차감은 없다. 설치1276.937105381kVA, 원본 최대327.94786kW다. IEEE123 2.4kV Generator를 LV에 복사하지 않았다. 운영 중 전압영역 밖에서 Model1 실제 P가 명령과 달라지면 해당 이벤트는 입력 물리 FAIL이다. 연결 PASS를 모든 운영 PASS로 확대하지 않는다.

PR199 C2 AIDC12/STA12 후보는 유지했다. STA12는12.47→.48kV/750kVA, 포트600kVA/721.6878A의 **연구용 접속설비**다. 차량은 P300/Q250/PCS400, SOC440~1080, 초기·종단760이다. 원본4대와 추가4대 초기 위치/Route를 유지했다. 정지8대 동시 접속과 유한 P/Q/SOC witness를 AC에서 검증했으며 선로/변압기/포트/전압/실제PV·BG/전력수지는 사례별이다. 부적합 운영을 인증하지 않았다. 교통망/55296 Route Table은 재생성하지 않았다.

## S0 B0 실제 배율

원래9개 β와 별도 등록한1.75/1.85/1.90/1.95/2.00/2.05/2.10을 Planning96/Actual120/독립 Fresh로 실행했다. 최종 BG 배열에 β만1회 곱하고1.15를 다시 곱하지 않았다. β>2.10은 실행하지 않았다. 아래는 Actual 평가96 슬롯 최종값이다. Planning/전체 Top20/슬롯 병목·상·MV−LV 차이는 canonical/에 제공한다.

{bt}

## 기존 Tap과 추가 SVR — 요청한 8개 질문

1. **기존12개는 정상 native Tap 제어를 수행했다.** Feeder3상1 Bank와 Downstream3상3 Bank의 단상 제어기이며 모두 해당 Transformer Winding2/TapWinding2다. min/max.9/1.1,32step(.00625),Band2,PT60/CT300,Delay15/TapDelay2,MaxTapChange16이다. Source1.04/Vreg123.5/CAPBank3초기OFF를 동결했다. HVMV_Sub와 STA750kVA12대에는 자동 RegControl이 없다. 이벤트별 TapNumber와 실제 Winding Tap 일치 및 Queue/Prefix 연속성을 검사했다.

2. **한계 도달 수는 아래 표의 기존 한계수**다. 전체120 이벤트 중 한 번이라도 상/하한에 도달한 기존 단상 제어기 고유 수이며 Bank 수/최종시점 수와 다르다. 상/하한 및 남은 step은 ALL_EVENT_TAP_NUMBER_READBACK.csv.gz(무손실 압축), native Action timestamp·순서는 Raw EVENTS.json이다. overdue Queue0을 확인한다.

원본12 RegControl과9 CapControl의 EventLog 기본값은 No다. 따라서 원래40개 운전 기록의 Queue·이벤트별 Tap/Cap 전후 대조와, 같은 timestamp 안의 native 내부 실행 순서는 구분한다. β2.00 S0/S1_03에서 **로깅만 켠 보조 재생**으로 각각 {action_logs['S0']}/{action_logs['S1_03']}개 native 로그를 수집했다. S0 및 초기화 전 로깅한 S1은 원래 전압/전류/변압기/event-slot 배열과 Tap/Cap 상태가 **비트 일치**했다. Native action CSV의 순서를 보존하며, timestamp/handle 정렬 Queue를 실제 액션 순서라고 가정하지 않는다. 다른 β의 동일시각 내부 순서까지 별도 로그로 전수 인증했다고 주장하지 않는다.

초기화 **후** 로깅 Edit를 한 첫 S1 보조 시험은 최대 line-rho1.68234e-9 차이로 엄격 비트 동일성에 실패했다. Tap/Cap 상태는 같았지만 통과로 처리하지 않았고 실패 배열/Receipt를 보존했다. 원인을 단정하지 않았다. 이후 초기화 전 로깅 방식의 비트 일치 결과와 구분한다. 원래 EventLog=No 운전 기록은 수정하지 않았다.

3. **β2.00~2.10 저전압 Bus/Phase/Time/경로**는 다음과 같다. 저압 hot node의 primary phase는 원래 서비스 변압기 wiring을 따른다. 전체 저전압 노드71개 경로도 저장했다.

{paths}

4. **기존 조정기 정상 동작만으로 해결되지 않는다.** 계측된 정상 S0 제어에서도 위 저전압이 남는다. 반복15의 수치 실패와 반복100에서 남은 물리 전압 위반은 별개다. 제어기를 끄거나 지연을 생략해 수렴시킨 결과가 아니다.

5. **추가3/6/12 Bank를 사전 등록 평가했다.** 아래 순서의 앞3/6/12개이며 S0 저전압 leaf의 가장 가까운3상 MV 선로를 coverage/최저전압 순으로 정했다. 부족한 수는 상류의 다음 가까운3상 선로로 채웠다. 결과에 맞춘 사후 위치/정격/Source 조정은 없다. 채택 설비 수·위치는 모든 물리 Gate 통과 전 확정하지 않는다.

{positions}

원본 terminal1만 새 bus로 옮겨 원래bus→추가단상3개→새bus→원래선로의 직렬 경로를 만들었다. 원래3703개 선로의 bus 이외 모든 속성(임피던스/길이/코드/정격/enabled 포함)을 대조했다. 원본 선로는 목적함수에 남는다. IEEE8500 implicit bus 문법은 compiled NodeOrder1,2,3으로 확인했으며 최초 문법 제한 실패와 수정 Amendment도 보존했다. 병렬 전압설정기나 Q주입 장치를 추가하지 않았다.

추가12.47kV 3상 장비는 phase_kVA=원래선로Amp×7.199557857kV, full-power grounded-wye1:1, XHL1%, windingR각.2%, no-load.05%, Tap.9~1.1/32, Vreg120/Band2,Delay30/TapDelay2,MaxTapChange1이다. R=X=0,Reversible=No로 signed 역송전에도 하류 감시 방향을 유지한다. 이는 r043과 같은 연구용 전기 모델 가정이며 제조사/현장 인증은 아니다. 새 winding 전류/kVA·손실·노드전압, 기존 Reg/Cap 상호작용과 상류 과전압, actual signed cut P/Q를 기록했다.

β2.00 평가slot95를 저장 상태와 독립 재현한 추가 설비 손실 합계는 **3 Bank {loss_anchor['S1_03']:.6f}kW / 6 Bank {loss_anchor['S1_06']:.6f}kW / 12 Bank {loss_anchor['S1_12']:.6f}kW**다. 15개 운전점·315개 phase 설비에서 native loss와 양단 P합을 대조했고, 전체 TIME에서는 신규 손실을 포함한 계통 전력수지를 매 이벤트 검사했다. 이 표본 손실을 하루 설비 손실량으로 부르지 않는다. 새 SVR의 전 구간 최대 winding current/kVA 비율은 S0_S1_ACTUAL_TIME_RESULTS.csv에 있다. 관측한 절단 선로 P는 모두 정방향(최소8.120149kW)이므로, 미관측 역송전 운전영역까지 인증하지 않는다.

6. **TIME 위반 제거 여부는 최종 물리와 전체 이벤트 안전을 구분한다.** 아래 실제 비교와 TIME_VOLTAGE_VIOLATION_DURATIONS.csv를 따른다. 물리 Delay 중 최초/Prefix 및 평가96 위반을 감추지 않는다. 지속시간은 각 native solved state부터 다음 이벤트/입력경계까지 piecewise-constant hold 합이고 반복횟수를 초로 바꾸지 않는다. 기존 β1의1.056986pu 과전압 악화도 이벤트 최고값으로 비교했다.

7. **전체·MV/LV 민감도 변화**는 아래와 S0_S1_SLOT_MV_LV_RESULTS.csv/Top20에 기록했다. SVR로 낮은 전압이 개선돼도 임피던스·손실·Tap/Cap 동작 때문에 부하율/역송전이 달라질 수 있다. MV/LV/Triplex 어느 선로도 제외하지 않았다.

{st}

**S1_03 β2.00은 평가96 B0의 최종·모든 이벤트 물리를 통과하는 운전 후보다.** 이 사례의 Prefix 저전압 합계는 {op3.prefix_low_voltage_seconds:.0f}초다. 원본 r043 Fresh96 합격 범위와 전체120 시작 구간 안전을 분리한다. 초기 Tap을 임의로 바꾸거나 Prefix 위반을 숨겨 전체 Primary를 인증하지 않았다. 기존 단상 제어기의 상·하한 도달 수는 모든 S0 β에서0개였다.

8. **r043 Actual 구조와는 부분적 물리·시간 계약 동등성이다.** Planning 기본12, Actual 기본12+후보9/18/36개(총21/30/48)다. IEEE1237/43 숫자를 강제하지 않았다. native TIME·유한 직렬설비·Actual 전용 정보 계약은 같지만 위치/전압/정격/설비수/CapControl9/수치예산은 다르다. 모든 향후 B0/B1/B2/B3는 같은 선택 Actual 구성/정책이어야 한다. S1 시험후보를 채택 설비나 완전 동등 설비로 인증하지 않는다.

S0 진단·완료 Receipt·후보 SHA를 신규 SVR 평가 **이전** S0_DIAGNOSIS_SEAL.json으로 봉인했다. 원래 결과를 덮어쓰지 않았다.

## AIDC/MESS 제어력

Planning414 FULL 도메인 불일치와 Actual192 Known 연구정책 QoS 사후 측정을 구분했다. 고객 Source QoS는 미인증이다. 확대된 동일 Site 지연 탐색에도 비영 Actual witness는0개이며 Pre-site/Migration은 null/NOT_VERIFIED다. 원래 컨트롤러·Job/GPUh·Rebound·QoS·WAN의 causal FULL 증거 없이 제어가능 kW를 합산하지 않았다. AIDC-only Actual은0명령 기준 재생이고 Joint 비영 효과는 미인증이다. 자세한 UID/정책 Source는 별도 보고서에 있다.

MESS는 원래 STAY/ETA0/이동0의 유한96슬롯 witness다. 초기760→1080→종단760,η.95/.95, 차량당 충전336.8421kWh/방전304kWh,8대 합계2694.7368/2432kWh다. 순간2.4MW를 하루 에너지로 쓰지 않았다. 기존68~75,지연1~4,장시간68~83,stagger,Q100,충전0~23분산을 성과 확인 전에 등록했다. PCS16/SOC/PQ/충전 Rebound/포트/전압/새 피크를 검사했다. 아래는 S0 finite Pilot이며 S1 SOC제어 성과로 바꾸어 부르지 않는다.

{pt}

고부하의 실제 피크가31임을 B0에서 확인한 **이후** 27~34/24~39 방전 진단을 추가 등록했다. 기존68~75 사전 등록에 소급하지 않았다. 또한 S1_03 β2.00의 평가96 B0 통과를 확인한 뒤 같은 장비에서 이 두 유한 SOC dispatch를 별도 등록·Fresh 검사했다. 설비/β 선택을 Pilot 성과로 바꾸지 않았다. 해당 S1 개선량은 다음과 같으며 Prefix 초기 저전압 잔존을 별도 표시한다.

{spt}

평가96의 최종 물리·모든 이벤트를 통과한 S0 제한 MESS 최대 개선은 **{evaluation_gain}%p**, Prefix를 포함한 전체120 이벤트까지 안전한 S0 최대 개선은 **{gain}%p**다. 두 범위를 혼용하지 않는다. 이는 최적화 성과/최대 제어력 상한이 아니다. Q지원·완만한 충전도 전압/Cap 동작을 악화시킬 수 있어 실패를 보존했다. 기존14 Pilot 정의도 TIME/Fresh로 재검증했다. Local 고정 Tap/Cap P/Q5kW/kvar 응답 및 Top20/STA cosine 중복은 별도 민감도 CSV이며 하루 Job/SOC witness와 구분한다. B3 최적화 성과를 보고하지 않는다.

## Gate·잔여 작업

G1 연결·용량은 확인했으나 운영 전압/실제 입력 보존/정격은 사례별이다. G2는 G3/G4 미완료와 독립 실행했다. G3는 finite MESS·전기 민감도를 확보했고 비영 causal Actual AIDC는 미인증이다. G4는 미준비다. **Primary를 인증하지 않는다.**

다음 작업은 모든 이벤트·초기/Prefix 전압/입력/정격 계약, Planning414 cache 도메인 원인/해소, Source QoS 권한 및 비영 Actual AIDC FULL witness다. 이후에만 MESS8 차원/Route/PCS16/원래 A1/M1/A2/M2 수학식/LB/UB/Gap/FULL AC 이식을 진행한다. 추가 β/설비/Source/P5/지연을 무단 조정하지 않는다.

이전 HEAD `{read(OUT/'PRESERVATION_BASELINE.json')['PR236_HEAD']}`의148개 tracked 연구파일과317개 기존 runtime SHA를 보존했다. 기존59개 정적 검사를 반복해 성과로 삼지 않았다. 독립 배열 산술·측정시점·Fresh·Tap readback·series 보존·SOC/PCS/Route를 이번 결함에 맞춰 검사했다.
''')
    md('PR_BODY.md','''V2_add의 목적함수를 r043 parent terminal/원본 NormalAmps 및 TIME 슬롯 최종 상태 기준으로 수정했습니다. 기존56개 배열의 독립 재계산, 사전 등록 S0 배율 Planning96/Actual120/Fresh, 유한 MESS와 AIDC 정책 재감사를 추가하며 기존 증거를 보존합니다.

기존 RegControl12의 Winding2/TapNumber/한계/Queue를 계측하고 S0 진단을 먼저 SHA 봉인했습니다. 이후 물리적 직렬 SVR3/6/12 Bank를 β1/1.5/2/2.05/2.1에서 TIME/Fresh 비교했습니다. 원본3703 선로의 임피던스/정격/목적함수와 P5/실제 지연을 유지하며, 슬롯 최종 지표와 이벤트·Prefix 안전을 분리합니다.

추가3 Bank/β2.00의 Actual 평가96 B0는 최대75.710958%, 최소0.951568pu로 최종·이벤트 물리를 통과했습니다. 같은 구성의 유한 MESS는 전역 최대를74.139349%로1.571609%p 낮췄고 새 피크는74입니다. 기존12 제어기의 Tap 포화는0개였으며, 6/12 Bank는 중간 전압 위반을 남겼습니다. 3 Bank의 차가운 초기 Prefix 저전압23초와 평가96 합격을 구분합니다.

Primary 미인증/G4_NOT_READY입니다. Planning414 FULL 도메인과 Actual192 연구정책 QoS 측정을 구분하며 Source QoS/비영 Actual AIDC는 미인증입니다. A1/M1/A2/M2/K48/Joint MILP/장시간 Native를 실행하지 않았습니다.

상세: docs/v2_add/correction/FINAL_V2_ADD_CORRECTION_REVIEW_KO.md
최종 수치: correction/canonical/ 및 correction/svr/
독립 테스트: correction/INDEPENDENT_REGRESSION_TESTS.json
추가 SVR 독립 테스트: correction/svr/INDEPENDENT_SVR_TESTS.json (총17개 회귀 PASS)
원시 AC/이벤트·SHA는 Receipt의 격리된 V2_add_runtime 경로를 참조합니다.
''')
    plot(sv,pilots,s1pilots)
    print('CORRECTED CANONICAL S0/S1 REPORT COMPLETE',flush=True)

def plot(sv,pilots,s1pilots):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,3,figsize=(17,4.5),layout='constrained')
    colors=plt.rcParams['axes.prop_cycle'].by_key()['color']
    for i,(config,g) in enumerate(sv.groupby('configuration')):
        color=colors[i];g=g.sort_values('beta_BG');ax[0].plot(g.beta_BG,g.max_pct,'o-',label=config,color=color)
        ax[1].plot(g.beta_BG,g.Vmin,'o-',label=config,color=color);ax[1].plot(g.beta_BG,g.evaluation_all_event_Vmin,':',alpha=.7,color=color);ax[1].plot(g.beta_BG,g.evaluation_all_event_Vmax,'--',alpha=.7,color=color)
    ax[0].axhspan(75,85,color='green',alpha=.1);ax[0].set(xlabel='Background beta',ylabel='Parent-terminal loading (%)',title='Actual settled96 objective');ax[0].legend(fontsize=8)
    ax[1].axhspan(.95,1.05,color='green',alpha=.1);ax[1].set(xlabel='Background beta',ylabel='Voltage (pu)',title='Eval96: solid settled min; dotted event min; dashed max');ax[1].legend(fontsize=6)
    rows=[pilots[(pilots.beta_BG==beta)&(pilots.schedule==name)].iloc[0] for beta,name in [(1.5,'ORIGINAL_68_75'),(1.5,'LATE_1'),(1.5,'CHARGE24_LATE4'),(2.,'PEAK31_27_34')]]+[s1pilots[s1pilots.schedule=='S1_03_PEAK31_27_34'].iloc[0]]
    ax[2].bar(range(5),[r.delta_global_pp for r in rows],color=['steelblue' if r.evaluation_all_event_security_PASS else 'salmon' for r in rows])
    ax[2].set(xticks=range(5),xticklabels=['S0 1.5\noriginal','S0 1.5\nlate+1','S0 1.5\nslow charge','S0 2.0\npeak31*','S1_03 2.0\npeak31*'],ylabel='Global improvement (percentage points)',title='Finite MESS: blue Eval96 PASS; red FAIL')
    ax[2].tick_params(axis='x',labelsize=8);ax[2].text(.5,-.22,'* Cold Prefix remains unsafe; no B3 optimization',transform=ax[2].transAxes,ha='center',fontsize=8)
    fig.savefig(OUT/'CORRECTED_TIME_STRESS_AND_PILOTS.png',dpi=160);fig.savefig(OUT/'CORRECTED_TIME_STRESS_AND_PILOTS.svg');plt.close(fig)
    svg=OUT/'CORRECTED_TIME_STRESS_AND_PILOTS.svg'
    svg.write_bytes(('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n').encode('utf-8'))

if __name__=='__main__':main()
