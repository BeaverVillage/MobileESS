"""Korean prestart report generated from measured evidence; never grants RUN."""
from pathlib import Path
import csv,json
from .prestart import ROOT,DOC,OUT,RUN,read,put,record,INITIAL,SOURCE,BASE

def md(name,text):
    (OUT/name).write_text(text.strip()+'\n',encoding='utf-8')

def main():
    electrical=read(OUT/'FINAL_ELECTRICAL_PRESTART_CERTIFICATION.json')
    manifest=read(OUT/'MAY01_07_PRESTART_INPUT_MANIFEST.json')
    native=read(OUT/'MESS8_NATIVE0_BUILD_REPORT.json');builds={b['units']:b for b in native['builds']}
    aidc=read(OUT/'AIDC_CAUSAL_FLEXIBILITY_CERTIFICATION.json');reject=read(OUT/'AIDC_CAUSAL_DIAGNOSTIC_REJECTION.json')
    loc=read(OUT/'LOCATION_AUDIT_SUMMARY.json');fleet=read(OUT/'MESS8_ROUTE_SOC_PQ_PORT_CERTIFICATION.json')
    pilots=list(csv.DictReader((OUT/'TWO_PEAK_CONTROLLABILITY_ANALYSIS.csv').open(encoding='utf-8')))
    split=next((x for x in pilots if x['schedule']=='PRESTART_ORIGINAL4_MORNING_EXTRA4_EVENING'),None)
    tests=read(OUT/'PRESTART_TEST_RESULTS.json') if (OUT/'PRESTART_TEST_RESULTS.json').exists() else None
    gates={
      'G1':dict(status='BLOCKED',reason='S1_03 beta2 Prefix low23s/high18s; Planning native event overvoltage; causal preceding8500 control history unavailable',evidence=['FINAL_ELECTRICAL_PRESTART_CERTIFICATION.json','PREFIX_AND_PLANNING_NATIVE_VIOLATIONS.csv']),
      'G2':dict(status='BLOCKED',reason='414 original FULL starts rejected through actual adapter; no new accepted A1; nonzero causal diagnostic rejected for reference mismatch/work/carryout/FULL gaps; migration not certified',evidence=['PLANNING_CACHE_ORIGINAL_FULL_REJECTION.json','AIDC_CAUSAL_DIAGNOSTIC_REJECTION.json']),
      'G3':dict(status='PARTIAL_NOT_CERTIFIED',reason='C2 all24 layout directions pass and72 local perturbations measured; physical GIS/road and ideal AIDC MV PCC equipment rating not certified; GPU scale not changed',evidence=['AIDC12_PCC_LOCATION_AUDIT.csv','LOCATION_AUDIT_SUMMARY.json']),
      'G4':dict(status='PARTIAL_NOT_CERTIFIED',reason='Original initial8/SOC preserved; STA hardware and finite STAY independent validator pass; Native24-service IDC charging facility gap and full moving-fleet grid feasibility unresolved',evidence=['MESS8_ROUTE_SOC_PQ_PORT_CERTIFICATION.json','STA12_LOCATION_AND_ELECTRICAL_RESPONSE.csv']),
      'G5':dict(status='FINITE_ELECTRICAL_WITNESS_ONLY',reason='Two-peak pilot improves global maximum1.920869pp or1.966819pp; new peak76; not a Joint MILP/B3 result; Prefix fails',evidence=['TWO_PEAK_CONTROLLABILITY_ANALYSIS.csv','TWO_PEAK_FRESH_CHECKS.json']),
      'G6':dict(status='BLOCKED',reason='Real4/8car original mobility Native0 built; full96 IEEE8500 coefficients/grid rows/K48/Beam/Joint/FULL-case authority not bound',evidence=['IEEE8500_V44_R043_FULL_EQUIVALENCE.json','MESS8_NATIVE0_BUILD_REPORT.json']),
      'G7':dict(status='BLOCKED',reason='May01_07 original input receipts verified; May02_07 new8500 AC/Fresh and realFULL handlers missing. Scheduler/checkpoint/hold prepared; campaign not executable',evidence=['MAY01_07_PRESTART_INPUT_MANIFEST.json','B0_B1_B2_B3_STAGE_WIRING_CERTIFICATION.json','CAMPAIGN_EXECUTION_HOLD.json'])}
    put('FINAL_PRESTART_GO_NO_GO.json',dict(status='PRESTART_BLOCKED_WITH_EVIDENCE',experiment='V2_add',PR=236,baseline_commit=BASE,source_commit=SOURCE,
        gates=gates,READY=False,Primary_Scenario_certified=False,final_beta_frozen=False,priority_beta_candidate=2.,
        official_campaign_started=False,Native_optimizer_calls=0,long_solver_runs=0,new_experiment_versions=0,
        original_data_Worker_or_campaign_modified=False,test_result=tests,
        next_actions=['Obtain/derive and certify causal IEEE8500 predecessor input/control history; replay all120 safety without changing frozen P5/delays',
          'Bind same-source r043 Actual controller/FCFS and certify nonzero whole-work/carryout/QoS/JobFULL schedule',
          'Resolve native24-service MESS charging authority at IDC12 without dropping routes or attaching480V PCS toMV',
          'Generate all96 Planning8500 affine coefficients/all line+tx ratings; bind original K48/Beam/DirectJoint and independentFULL proofs',
          'Complete real8500/8car fullNative0 plus May02_07 physical/Fresh and actual stage checkpoint/resume/budget tests',
          'Only after all gates pass freeze one scenario and obtain separate explicit human campaign approval']))
    md('SVR3_PREFIX_AND_TIME_SECURITY_KO.md',f'''
# V2_add SVR3 Prefix 및 TIME 안전 감사

판정: **미인증**. 기존 S0/S1_03/S1_06/S1_12 및 모든 기존 AC/Fresh 파일은 보존했다.

S1_03/β2.00의 평가96 B0 최대 선로부하율은75.710958%, Vmin0.951568pu이고 평가 이벤트 Vmax1.049088pu이다. 그러나 Prefix 첫 슬롯에서 저전압23초와 과전압18초가 발생한다. 전체120 PASS로 확대하지 않았다.

첫 수렴 해 t=0에서 sx3312692a.1이0.893556516pu이며, 기존 조정기 Delay15초 이후2초 간격 동작 중 t=23까지 저전압이다. 신규 SVR의30초 지연과 기존 조정기 동작이 겹치며 t=30–48에190-8593.1 과전압이 지속되고 최대1.072061933pu이다. CSV는 각 Native solved state와 다음 물리 이벤트까지의 유지 시간을 기록한다. 전기적 반복25회는25초가 아니며 MaxIterations15→100 진단과 이 물리 지연 현상을 혼동하지 않는다.

동결 초기 Tap/Cap과 빈 Queue에서 출발한 자동제어 초기 과도이다. 정상 직전 운전 상태와 동일하다는 증거가 없다. 기존 입력은 전일18AEST부터120슬롯이며 그 이전의 IEEE8500 부하·PV·실행 Job 전력·Tap/Cap·제어기 내부 이력을 함께 동결한 자료가 없다. 원시 AEMO/Job 과거 관측의 존재만으로 모델상 초기 위치와 실행 이력까지 유일하게 복원되지는 않는다. IEEE123 Tap이나 이후 평가 상태를 복사하거나 Prefix를 반복해 초기 상태로 삼지 않았다. 제공 자료 범위에서 인과적 선행 상태 복원은 미인증이다.

배경/PV의 명령–실제 출력 오차는 위반 이벤트 CSV에 보존했다. t=32에서 BG 오차 약1.076kW, PV 약0.001957kW가 나타나며 기존 전압 의존 물리 모델의 영역 이탈도 별도 불일치이다. 이를 임의 정전력 모델로 바꾸지 않았다. 수렴 실패나 반복 부족으로 위반 시간을 지우지 않았다.

Planning S0/β2의 첫 슬롯에도 m1069533.3 최대1.051828941pu 등의 TIME 과전압이 남는다. Planning 기본12개와 Actual 기본12+SVR3의 정보·물리 계약은 구분하며 P5 Source1.04/Vreg123.5/CAPBank3 초기OFF 및 원래 Delay/정격을 유지했다. 기존12개는 정상 TapNumber–Winding2 대응이며 앞선 감사에서 포화0개였다. 추가 설비로 이 초기 이력 문제를 해결했다고 주장할 근거가 없어 신규 SVR 후보를 늘리지 않았다.

근거: FINAL_ELECTRICAL_PRESTART_CERTIFICATION.json, PREFIX_AND_PLANNING_NATIVE_VIOLATIONS.csv 및 기존 correction/svr 감사. 필수 후속은 인과적 이전 운전 자료와 제어기 내부 상태를 보존하는 재생 원점의 인증, Planning/Actual 전체 시간축 안전 재생이다.
''')
    md('AIDC_SOURCE_QOS_AND_FLEXIBILITY_KO.md',f'''
# V2_add AIDC 원본 QoS 및 실행 유연성

원본 FULL Job1499개(1GPU1489개, 4GPU10개)의 생성자와 validate/resources_used/resource_limit을 재사용했다. 원래 WINDOWS를 다시 바인딩한 실제 A-stage 수용 Adapter에서 기존 캐시414개의 START_WINDOW 위반을 거부한다. 캐시의 accepted 표시로 우회하지 않는다. 동일 수용 경로가 새 A1/A2 결과에도 적용되도록 execute_a_stage를 구현했지만 실제 IEEE8500 A1 호출기의 전체 연결은 아직 완료되지 않았다. 새로운 A1 accepted 해나 Global LB를 만들지 않았다.

Actual의 과거192개는 opt-in Known 연구정책의 사후 측정이라는 분류를 유지한다. Source 고객의 QoS 인증이 아니다. 기존1024개 Window 유연 Job 수를 kW로 환산하지 않는다. 기존 전체 gang/allowed-start/완전 rebound 검색에서 비영 시간 이동 witness는0개였지만 이 값은 전체 사전배치·이주의 불가능성 상한이 아니다.

원본 FULL 개별 Job 도메인에서 PENDING1395개가 다른 사이트 사전배치 선택을 가진다. 용량·rack·residency·서비스량·Window 검사를 수행하고 AC 성과를 보지 않는 UID/목적지 순서로8632483→AIDC02 명령을 선택했다. 원본 이벤트 엔진으로 인과적 실행과 독립 Fresh를 수행했으며 의도적 QoS 초과0개, GPU 용량 초과0개였다. 미래 실행시간은 simulator 내부에만 두었다.

그러나 이 실행은 **인증된 비영 유연성 witness로 거부**했다. 대조 전력이 동결 r043 FCFS와 최대{aidc['baseline_vs_existing_frozen_P_max_kw']:.8f}kW 다르고, B0/B1의 flexible admission 경로 차이도 포함된다. 일내 compute GPUh 차이는{aidc['GPUh_total_change']:.8f}이며 carryout을 포함한 전체 작업량/완료 동등성과 Original FULL 공동 Job·Grid 검증이 닫히지 않았다. 관측 슬롯31의 IT/PCC 차이{abs(aidc['slot31']['signed_PCC_delta_total_kw']):.8f}kW와 슬롯74의0kW를 제어 가능한 전력으로 보고하지 않는다. 인증된 비영 Actual 유연전력/GPUh는 **미확정(null)** 이며0이라는 전체 상한도 아니다. 당시 재생/전력/Job/Queue 결과는 Runtime SHA Manifest에 보존했다.

Time-shift, Pre-site, checkpoint1800초, Multi-GPU gang, GPUh/완전 서비스, WAN/1개 동시 transfer, checkpoint/restart, rack/residency, 인과적 도착 및 Known/Unknown 구분은 원본 제약으로 유지해야 한다. 별도의 고객 권한/실행 capability 없이 Can_Checkpoint_Migrate를 켜지 않았다. Migration 실행 witness와 FULL 재생은 미인증이다. Unknown849개의 원래 양수 지연 budget은0개라는 앞선 감사를 재사용한다. 고객의 데이터 이동 동의는 설치 GPU나 초기 연구 위치로부터 추론하지 않는다.

필요한 구현: 현재 r043 FCFS/Actual 정책의 동일 원본 기준 재생, 초기·tail·완료 작업량 보존, 실행 capability·WAN/residency의 실제 바인딩, Planning/Actual C1 및 FULL 검증기/Global LB의 동일 case 연결이다. 단순 kW/GPU UID 복제로 이를 대신하지 않는다.
''')
    md('AIDC_CAPACITY_SCENARIO_REVIEW_KO.md','''
# AIDC 용량 확장 검토

현재780GPU를 유지한다. 비영 Actual 유연성·완전 서비스·원본 FULL 공동 검증이 미인증이므로 용량 확대가 필요하다는 결론을 내릴 수 없다. 현재 실패의 직접 원인은 설치 GPU 수 부족으로 증명되지 않았다.

| 독립 후보 | 총 GPU 예시 | 상태 |
|---|---:|---|
|×1.00|780|원본 기준, 미변경|
|×1.25|975|새 Workload/정수 사이트 GPU/rack/WAN/Deadline/C1 입력이 없어 미정의|
|×1.50|1170|같음|
|×2.00|1560|같음|

총량의 산술 예시는 새 과학 시나리오 인증이 아니다. 사이트별 GPU 설치, idle/swing IT와 Cooling, 원본 UID를 복제하지 않는 실제 추가 수행 Workload, 완전 서비스·Deadline·rack·WAN을 함께 정의하기 전에는 확장 AC/최적화를 실행하지 않는다. B3 결과를 보고 용량/PCC를 선택하지 않았고 기존780GPU 입력을 변경하지 않았다.
''')
    md('MESS8_INITIAL_SITE_SELECTION_KO.md',f'''
# MESS8 초기 위치 및 두 피크 제어

기준 초기 위치는 {json.dumps(INITIAL,ensure_ascii=False)} 이다. 첫4대는 V44 원본 초기 상태이며 추가4대는 기존 PR236의 사전 등록 후보이다. 8대 최적 배치 결과로 표현하지 않는다. 미래 Actual 피크로 위치를 재선정하지 않았고 Planning만으로 다른 조합이 우월하다는 인증도 없어 기준 위치를 유지한다.

각 STA는 MV3상→480V/750kVA 전용 연구 설비, port600kVA/721.6878A, 동시1대이다. 차량은 P300/Q250/PCS400과 inner16, SOC440–1080/초기·종단760kWh, 효율0.95를 유지한다. 두 피크 Pilot은 원본 STAY Route만을 사용하는 실행가능성 witness이며 이후 최적화기의 MOVE/STAY를 고정하지 않는다. 원본 Native0에서8대 모두 각각 약5만 개의 도달 가능한 MOVE binary와 약2200개 STAY binary를 가진다.

각 차량320kWh를 충전하고 출력단304kWh를 오전27–34 및 저녁68–75에 절반씩 분배했다. 충전8–15에서168.4211kW, 두 방전 구간에서각76kW이며 초기/종단760kWh이다. 8대의 총 충전2694.736842kWh/방전2432kWh이며 순간2.4MW를 하루 방전량으로 간주하지 않는다. 원본 독립 차량 validator와 별도 Q250·STA 점유 검사를 통과했다.

P-only: 전역 최대75.710958%→{100*float(pilots[0]['rho_objective']):.6f}%, 개선{float(pilots[0]['improvement_pp']):.6f}%p. Q50 지원: →{100*float(pilots[1]['rho_objective']):.6f}%, 개선{float(pilots[1]['improvement_pp']):.6f}%p. 두 후보 모두 평가96 이벤트 안전 및 독립 Fresh가 PASS이나 Prefix 위반은 보존되며 Primary/B3 인증이 아니다. 새로운 피크는76으로 이동했다. 전체96 슬롯 및 모든 원본 선로/상(Triplex 포함)을 측정했다.

두 시간대24개 PCC의72개 P/Q 교란과 Top20 응답을 기록했다. 위치별 반응의 방향뿐 아니라 크기·상·원본 전기 경로를 CSV로 제공한다. 출발35에서 다른 STA에 저녁 이전 도착 가능한지 및 이동 에너지와 목적지 응답 차이는 MESS8_MOVE_REACHABILITY_AND_LOCAL_VALUE.csv에 보존했다. 아직 시간·SOC·P/Q와 경로를 동시에 최적화한 MOVE 이득은 없다.

기존4대를 오전, 추가4대를 저녁에 사용하는 별도 사전 등록 witness도 실행했다. 결과는 전역 최대{100*float(split['rho_objective']):.6f}%, 개선{float(split['improvement_pp']):.6f}%p이며 같은 총8대/같은 에너지로 서로 다른 차량군이 두 피크를 담당한다. 평가96 이벤트 안전 및 독립 Fresh는 PASS이고 Prefix는 동일하게 실패한다.

원본 Route24개 서비스 중 IDC12에도 방문/충전 변수가 생기지만 현재 IEEE8500 Adapter는 STA12에만480V MESS 접속설비를 갖는다. MV AIDC Load를480V 차량 접속 포트로 취급하지 않았다. IDC 방문 Route를 삭제해 문제를 축소하지도 않았다. 이 물리 계약을 해결하기 전 전체8대 이동 Native FULL을 인증하지 않는다. 10/12대 증설은 실행하지 않았다.
''')
    summary_rows='\n'.join(f"|{n}대|{b['model']['binary']:,}|{b['model']['continuous']:,}|{b['model']['linear_constraints']:,}|{b['model']['nonzeros']:,}|{b['wall_seconds']:.2f}|{b['peak_RSS_bytes']/2**20:.1f}|" for n,b in builds.items())
    answers=[
      ('SVR3으로 Prefix/전체 시간대를 인증했는가?','아니다. 평가96 PASS, Prefix 저23초/고18초 및 Planning TIME 과전압이 남는다.'),
      ('최종 β와 모든 날짜 안전성은?','β2.00은 우선 후보이며 최종 동결이 아니다. May02–07 IEEE8500 안전 재생은 미실행이다.'),
      ('원본780GPU 실제 유연전력은?','인증된 비영 값은 미확정. 관측 비영 사전배치 재생은 기준 FCFS/C1 불일치와 작업량/tail/FULL 미완료로 거부했다.'),
      ('AIDC 확대가 필요한가?','입증하지 못했다. GPU/kW/UID 복제로 확대하지 않았고 원본780을 유지한다.'),
      ('C2 위치와 교통망은 적합한가?','MV3상 연결과 공통 도식 방향276쌍 PASS. layout 오차2.54–14.73km 상당이며 실제 GIS/도로 접근성은 미인증이다.'),
      ('MESS8 초기 위치 유지가 적합한가?','기준으로 유지한다. 추가4대는 기존 사전 등록 가정이며 우월한 최적 배치 인증은 아니다.'),
      ('8대로 오전/저녁 피크를 동시에 낮출 수 있는가?','평가96에서 유한 STAY Pilot 개선1.920869/1.966819%p와 Fresh를 확보했다. 새 피크76이며 B3/MOVE 최적화는 아니다.'),
      ('8대 P/Q/SOC/MOVE/STAY가 원본과 일치하는가?','원본 이동/PQ/SOC 생성자와 Q250 overlay로8대 Native0를 만들었다. STA 점유 추가 물리 계약, IDC 충전, 전체 Grid FULL 동등성은 미완료다.'),
      ('A1–M1–A2–M2/K48/Beam/Joint 이식이 끝났는가?','아니다. Native 네 Stage 소형 호출 경로와 이동 모델은 확인했지만 전체 IEEE8500 계수·원본 case/authority·K48/Beam/Joint 연결은 남았다.'),
      ('FULL 및 UB/LB/Gap 계약은 정상인가?','기존 함수/수학은 보존하고 캐시414를 실제 Adapter에서 거부한다. 새 FULL feasible point/독립 Global LB/Gap은 미인증이다.'),
      ('May01–07 입력과 환경은 준비됐는가?','7일 원본 파일 SHA는 모두 PASS. 신규8500 날짜별 AC/Fresh/전체 Native0 및 실제 Stage handlers가 없어 캠페인 환경 전체는 미완료다.'),
      ('공식 캠페인 전 차단 사유는?','초기 인과 운전 이력/전체 전압, AIDC 동일 기준 FULL witness, IDC12 차량 포트, 전체8500 FULL/K48/Joint 이식, 날짜 간 검증이 남는다.')]
    qa='\n'.join(f'{i}. **{q}** {a}' for i,(q,a) in enumerate(answers,1))
    md('FINAL_PRESTART_REVIEW_KO.md',f'''
# V2_add PR #236 최종 Prestart 검토

**PRESTART_BLOCKED_WITH_EVIDENCE**. READY가 아니다. 공식 B0/B1/B2/B3 캠페인·장시간 A1/M1/A2/M2/K48·월간 Worker를 실행하지 않았다. 같은 Draft PR #236, 기준 `{BASE}`, 원본 `{SOURCE}`를 유지했다.

실제 진척은 두 피크의 전체96 AC/Fresh Pilot,72개 위치별 AC 응답, 원본 FULL Job 캐시 수용 차단, 거부 사유를 포함한 인과적 Job 재생,4/8대 원본 이동/PQ/SOC Native0 모델 생성과 실행 HOLD/Checkpoint 스케줄러이다. 기존308개 V2_add 파일과 과거 S0/S1 기록은 변경하지 않았다.

| 이동 블록 실측 | Binary | Continuous | Rows | Nonzeros | Build초 | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
{summary_rows}

이 표는 **Grid rows가 없는 원본 이동 블록+Q250+STA 점유의 실제 생성**이다. 실제 IEEE8500 FULL 모델 생성이나 성능 인증으로 표현하지 않는다. IEEE8500 DSS 모델/AC 배열과 Native 이동 모델을 각각 만들었지만 둘을 합친96슬롯 FULL 계수/Matrix는 미완료다. K48 Root/Pricing/DirectJoint 시간과 FULL Native 예상 시간은 null이다. 원래 budget을 줄이거나 Route를 추가 삭제하지 않았다. 첫 생성의 과도한 자원 관측 overhead는 자체 진단만 종료하여 보존했고 동일 수학으로 다시 생성했다. 생산 Worker는 종료하지 않았다.

{qa}

## 비교 계약과 후속 구현

Planning은 기본 IEEE8500 Reg12, Actual은 Reg12+SVR3 후보이며 같은 Actual 설비·정책을 모든 arm/날짜에 적용해야 한다. 기존 IEEE1237/43 및120개 변압기 current-row guard를 숫자만 치환해 통과시키지 않았다. 원본3703선로/1177Triplex/Parent 목적함수/양단 안전/.95–1.05/모든 원본 변압기와 신규 SVR 정격은 AC에서 유지한다. Native FULL에 같은 축의 계수를 생성·바인딩해야 한다.

`prestart_acceptance`는 캐시 및 새 A1/A2 결과를 Original FULL Job·공동 자원·동일 case Grid·독립 LB/Gap에 연결하는 수용 경로이다. `prestart_execution`은 원본 CHAINS, 동일 case hash, artifact SHA, 실패 날짜 격리, 재시작 시 미정산 ledger 차단과 OS 중복 방지를 구현한다. 테스트용 handler는 실제 Stage 연결 인증이 아니다. 실제 r043 Worker/Current AC/독립 FULL/프리픽스 상태·계수 Authority와 연결한 전체 검증이 남아있으므로 `real_FULL_stage_adapters_bound=false`로 유지한다.

May01은 이미 노출된 개발일이다. May02–07 원본 Forecast/Actual/PV/Weather/Job/GPU/C1/교통/초기 상태의 파일들은 manifest로 확인했으며 신규 계통 날짜 간 적합성을 확인한 것은 아니다. May08–31 확장은 별도이며 새 Worker를 만들지 않았다.

실행 명령과 Runtime/budget/worker/시작 점검은 CAMPAIGN_EXECUTION_HOLD.json에 기록했다. 명령은 현재 차단된다. 모든 Gate가 실제로 통과한 뒤 동일 시나리오·원본 정책을 동결하고 별도의 명시적 사용자 캠페인 실행 허가가 필요하다. 현 단계에서는 실행 허가를 요청하지 않는다.

검증 결과: {tests['tests'] if tests else '실행 대기'}개 새 검사, PASS={tests['PASS'] if tests else '미판정'}. 이전17개 검사는 기존 봉인 결과로 재사용하며 이번 실행 숫자에 합치지 않는다. Fixture 통과만으로 READY를 만들지 않는다.
''')
    md('PR_BODY_KO.md',f'''
## V2_add IEEE8500 캠페인 전 준비 — PRESTART_BLOCKED_WITH_EVIDENCE

동일 PR #236과 기준 `{BASE}`에서 추가했다. 공식 캠페인/장시간 Native/Worker는 실행하지 않았다.

- 두 피크 에너지 분할 실제 AC/Fresh: B0 75.710958% → P-only73.790090%, Q50지원73.744139%. 평가96 이벤트 PASS, 새 피크76. Prefix 저23초/고18초는 그대로이며 B3 성과가 아니다.
- 원본 FULL1499 Job 검증으로 기존 캐시414개 START_WINDOW 위반을 실제 수용 Adapter에서 거부한다. 인과적 사전배치 진단은 재생/Fresh를 했으나 기존 FCFS 전력 및 작업량/tail 동등성이 없어 인증 witness로 거부했다.
- 실제 원본 이동/P300/Q250/PCS400/SOC/Route Native0를4대와8대로 생성했다.8대 각각 MOVE/STAY 자유를 보존한다. 전체 IEEE8500 계수/Grid/K48/Beam/Joint/FULL 연결과 IDC12 충전설비는 미완료다.
- PCC72개 교란과24개 서비스 방향276쌍, May01–07 원본 입력 SHA, Stage scheduler/checkpoint/resume/중복 실행/HOLD를 추가했다. GIS/모든 날짜8500 AC/실제 FULL Stage handlers 미인증을 숨기지 않는다.
- 기존308개 V2_add 파일/과거 AC 기록 보존. 새 검사 {tests['tests'] if tests else 'pending'}개 PASS={tests['PASS'] if tests else 'pending'}, Native optimizer0.

최종 한국어 보고: docs/v2_add/prestart/FINAL_PRESTART_REVIEW_KO.md. 필수16개 산출물 및 Runtime SHA Manifest 포함. READY/Primary를 인증하지 않으며 자동 실행을 차단한다.
''')

if __name__=='__main__':main()
