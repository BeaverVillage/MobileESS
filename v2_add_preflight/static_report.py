"""Report measured static preparation honestly, with arm-specific blockers."""
import re,subprocess
from collections import Counter
import numpy as np
import scipy.sparse as sp
from .static_common import *

def optional(name):
    p=OUT/name
    return read(p) if p.exists() else {'PASS':False,'status':'NOT_COMPLETED','missing':name}

def provenance():
    row=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    assert row['day']=='2025-05-01'
    # These are pre-existing frozen authorities, not newly synthesized input.
    p=DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz'
    data=dict(day=row,raw_electrical_totals=record(p),original_source=SOURCE,
        native_4_to_8_initial_adapter=INITIAL,all_source_jobs_GPU_PV_traffic_and_routes_preserved=True,
        historical_DY_case_is_not_Source_YY_case=True,
        timing='Explicit provenance linkage added after numerical derivative generation; hardware freeze and derivative bytes unchanged')
    put('SOURCE_YY_INPUT_PROVENANCE_BINDING.json',data)
    coef=optional('SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')
    if coef.get('PASS'):
        link=dict(numeric_case_sha=coef['case_sha'],numeric_certificate=record(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json'),
            provenance=record(OUT/'SOURCE_YY_INPUT_PROVENANCE_BINDING.json'))
        put('SOURCE_YY_COMPLETE_INPUT_CASE_IDENTITY.json',dict(**link,input_bound_case_sha=digest(link)))

def census():
    from .static_pack import PACK
    from .static_screen import CACHE
    tally=Counter()
    for t in range(96):
        with np.load(PACK/f'{t:02d}'/'ROWS.npz') as z:names=z['local_names']
        with np.load(CACHE/f'{t:02d}'/'STATIC_SELECTION.npz') as z:cls=z['classification']
        families=np.array([re.sub(r'_\d\d\[\d+\]$','',str(n)) for n in names])
        for family in np.unique(families):
            m=families==family;tally[str(family),'before']+=int(m.sum())
            for kind in ('RETAIN','SAFE_REMOVE','EXACT_REDUNDANT','EXACT_SUBSTITUTION','UNRESOLVED'):
                tally[str(family),kind]+=int(np.sum(cls[m]==kind))
    rows=[]
    for family in sorted({k for k,kind in tally}):
        rows.append(dict(family=family,scope='SOURCE_YY_FIXED_B0_M1_GRID',before_rows=tally[family,'before'],
            after_rows=tally[family,'RETAIN'],SAFE_REMOVE=tally[family,'SAFE_REMOVE'],
            EXACT_REDUNDANT=tally[family,'EXACT_REDUNDANT'],EXACT_SUBSTITUTION=tally[family,'EXACT_SUBSTITUTION'],
            UNRESOLVED_retained=tally[family,'UNRESOLVED']))
    mob=read(OUT/'ORIGINAL_STATIC_PRESOLVE_MESS8.json')
    rows.append(dict(family='ORIGINAL_MOBILITY_AND_EXACT_NODE_FLOW',scope='SOURCE_ORIGINAL_COMPACT_PRESOLVE',
        before_rows=mob['original']['rows'],after_rows=mob['selected']['rows'],
        added_exact_node_rows=mob['proof']['compact_rows']-mob['proof']['original_rows'],
        deleted_exact_presolve_rows=mob['proof']['deleted_row_implications_checked']))
    table('FULL_CONSTRAINT_FAMILY_BEFORE_AFTER.csv',rows)

def report():
    init();provenance()
    from .static_execution import interfaces,no_cg_proof
    interfaces();no_cg_proof()
    alg=optional('V44_R043_ALGORITHM_IDENTITY_AUDIT.json');cg=optional('NO_NEW_GRID_CONSTRAINT_GENERATION_PROOF.json')
    coef=optional('SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')
    raw=optional('SOURCE_YY_ORIGINAL_FULL_REFERENCE.json');screen=optional('IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json')
    eq=optional('IEEE8500_EXACT_COMPACT_EQUIVALENCE.json');native=optional('IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json')
    phy=optional('MAY01_PHYSICAL_EVALUATION_CONTRACT.json');fix=optional('ORIGINAL_STAGE_AND_CHECKPOINT_FIXTURES.json')
    if screen.get('PASS'):census()
    model=native.get('model') or {};nativepass=native.get('PASS',False)
    failed=optional('SOURCE_YY_ORIGINAL_FULL_REFERENCE_RACE_FAILURE.json')
    accumulated_pack_wall=raw.get('wall_seconds',0)+failed.get('wall_seconds',0)
    accumulated_pack_peak=max(raw.get('peak_RSS_bytes',0),failed.get('peak_RSS_bytes',0))
    reference_rows=[dict(model='IEEE123 original FULL (user-provided reference)',binary=208312,continuous=108431,rows=961472,nonzeros=8587630,
        build_seconds='',peak_RSS_bytes='',measurement='Historical reference; no new IEEE123 execution'),
        dict(model='IEEE8500 DY original FULL (preserved prior reference)',binary=417296,continuous=3350097,rows=20634824,nonzeros=302476152,
            build_seconds='',peak_RSS_bytes='',measurement='Prior complete matrix pack, not completed monolithic Native0'),
        dict(model='IEEE8500 Source-YY original FULL',binary=raw.get('binary',''),continuous=raw.get('continuous',''),rows=raw.get('rows',''),nonzeros=raw.get('nonzeros',''),
            build_seconds=accumulated_pack_wall,peak_RSS_bytes=accumulated_pack_peak,measurement='Actual96 component pack: accepted88 + resumed8; accumulated wall includes producer wait; not monolithic Native0'),
        dict(model='Historical delayed initial master (prohibited official path)',binary=417296,continuous=68609,rows=431255,nonzeros=3071592,
            build_seconds='',peak_RSS_bytes='',measurement='Historical incomplete master; never Static Complete'),
        dict(model='Source-YY Static Complete M1 Native0' if nativepass else 'Source-YY Static Native0 MEASURED PARTIAL',
            binary=model.get('binary',''),continuous=model.get('continuous',''),rows=model.get('rows',''),nonzeros=model.get('nonzeros',''),
            build_seconds=native.get('build_seconds',native.get('wall_seconds','')),peak_RSS_bytes=native.get('peak_RSS_bytes',''),
            measurement='Actual complete Native0/readback' if nativepass else str(native.get('error',native.get('status'))))]
    table('IEEE123_IEEE8500_MODEL_SIZE_COMPARISON.csv',reference_rows)
    remaining=[
        'A1의 가변 Job/GPU/Rack/WAN/QoS/CC4와 Source-YY 전체 계통 FULL Native0·독립 수용 검증이 아직 연결되지 않았다.',
        '전체96 원본 K48의 현재 Case 물리 메타데이터·배율 Helper View·Beam·Direct Joint 연결은 미인증이다. 단일 슬롯 Helper와8대 분할 검증은 범위가 더 좁다.',
        'A2의 실제 채택 M1 고정과 M2의 실제 A2 고정 입력·가변 영역 증명·Native0가 아직 연결되지 않았다.',
        'Actual B1/B3의 현재 AC·Controller, 전체 Migration·서비스·Carryout 독립 검증 및 실제 Checkpoint/Budget/Worker Handler 연결은 미인증이다.']
    if not nativepass:remaining.insert(0,'Complete M1 Native0/readback failed or is incomplete: '+str(native.get('error',native.get('status'))))
    if not eq.get('PASS'):remaining.insert(0,'Independent all-row Source-YY static equivalence proof incomplete or failed.')
    criteria=dict(original_algorithm_unchanged=bool(alg.get('algorithm_source_unchanged')),
        new_grid_CG_official_path_zero=bool(cg.get('PASS')),Source_YY_96_coefficient_generation=bool(coef.get('PASS')),
        fixed_B0_M1_screening_proof=bool(screen.get('PASS')),fixed_B0_M1_exact_equivalence=bool(eq.get('PASS')),
        fixed_B0_M1_complete_Native0=bool(nativepass),MESS8_route_freedom=True,
        variable_AIDC_A1_A2_domain_screening=False,A1_M1_A2_M2_real_stage_handlers=False,
        K48_Beam_Joint_whole_current_case_interface=False,
        original_B0_Planning96_Actual96_prefix24_and_Fresh_physics=bool(phy.get('source_YY_B0_Planning96_Actual96_Fresh_PASS')),
        all_arms_hardware_and_evaluation_policy_frozen=True,
        checkpoint_worker_budget_fixture=bool(fix.get('PASS')),real_production_handler_binding=False,
        official_campaign_not_executed=True)
    ready=all(criteria.values());status='READY_FOR_MAY01_CAMPAIGN_APPROVAL' if ready else 'PRESTART_BLOCKED_WITH_EVIDENCE'
    result=dict(experiment='V2_add',PR=236,baseline=BASE,source=SOURCE,day='2025-05-01',status=status,
        criteria=criteria,remaining=remaining,SCIENTIFIC_SIMULATION_READY=ready,FIELD_INSTALLATION_UNVERIFIED=True,
        field_installation_is_not_the_blocker=True,Source_YY_B0_scientific_tick_physics_PASS=criteria['original_B0_Planning96_Actual96_prefix24_and_Fresh_physics'],
        event_envelope_full120_PASS=False,no_violation_deleted=True,
        numeric_Global_LB=None,numeric_Global_UB=None,numeric_Global_Gap=None,
        missing_numeric_bounds_before_campaign_are_not_an_automatic_blocker=True,
        official_campaign_executed=False,Native_optimization_calls=0,May02_to_07_new_scientific_runs=0)
    put('MAY01_CAMPAIGN_PRESTART_READINESS.json',result);put('FINAL_PRESTART_GO_NO_GO.json',result)
    case_link=optional('SOURCE_YY_COMPLETE_INPUT_CASE_IDENTITY.json')
    actual=next((r for r in phy.get('results',[]) if r['schedule']=='ZERO' and r['role']=='ACTUAL' and not r['fresh']),{})
    planning=next((r for r in phy.get('results',[]) if r['schedule']=='ZERO' and r['role']=='PLANNING'),{})
    reduction=dict(variables=raw.get('variables',0)-model.get('variables',0),rows=raw.get('rows',0)-model.get('rows',0),
        nonzeros=raw.get('nonzeros',0)-model.get('nonzeros',0)) if nativepass else None
    put('PRESTART_MEASURED_METRICS.json',dict(native=native,full_reference=raw.get('case_sha'),
        actual=actual,planning=planning,complete_model_reduction=reduction,input_bound_case=case_link))
    lines=[f'# V2_add PR #236 — May01 원본 알고리즘 보존 및 정적 모델 검토',
        '',f'판정: **{status}**. 공식 캠페인과 Native 최적화 호출은 모두 0회다.',
        '',f'원본 r043 `{SOURCE}`의 감사 대상 알고리즘 파일은 Git 정규화 Blob과 외부 SHA 핀 기준으로 변경이 없다. 일부 작업 파일의 CRLF 차이는 별도로 기록했다. 원본 K48/Beam/Direct Joint 코드는 보존했다.',
        '', '이전 431,255행 지연 Master는 역사적 진단으로 보존했다. 새 공식 준비 경로는 해당 클래스를 가져오거나 호출하지 않는다. 원본 K48 Pricing은 계속 허용하며, 새 Grid CG·Lazy Callback·후보 후 행 추가·재최적화 루프는 사용하지 않는다.',
        '', '| 모델 | Binary | Continuous | Rows | Nonzero |', '|---|---:|---:|---:|---:|']
    for r in reference_rows:lines.append('| '+r['model']+' | '+' | '.join(str(r[k]) for k in ('binary','continuous','rows','nonzeros'))+' |')
    lines += ['',f'정적 Native0 완성·전체 계수/RHS/Sense/Bound/Type/목적함수 Readback: **{nativepass}**. 실제 Build/전체 Wall은 {native.get("build_seconds","미완료")} / {native.get("wall_seconds","미완료")}초, Peak RSS는 {native.get("peak_RSS_bytes",0)/1024**3:.6f}GiB다. 4GiB 및 시스템 여유 5GiB 보호를 적용했다. 부분 모델은 FULL로 승격하지 않는다.',
        '',f'완성 모델의 원본 Source-YY 대비 감소량: {reduction if reduction is not None else "미완료이므로 산출하지 않음"}. 단위는 변수/행/Nonzero다. IEEE123 대비 수치는 CSV에서 각 측정 범위를 구분한다.',
        '',f'정적 제거 분류: {screen.get("classification",{})}. 안전 제약은 보수적 8포트 P300/Q250 외부 영역과 원본 성분의 반올림 오차 상계로 검증했다. 목적함수 면은 Ampacity 안전으로 제거하지 않고, 유지된 원본 면에서 함의되는 rho 하한으로 별도 증명했다. 미해결 행은 모두 남겼다.',
        '',f'독립 원본 FULL 동등성: **{eq.get("PASS",False)}**, 범위는 **고정 B0 AIDC의 M1**이다. 원본 전체 행, 생략 Bound, 복원식, 목적함수 및 LP 영역을 확인한다. STAY·다중 MOVE·P/Q·충방전·SOC 경계 유한 가능해는 정식화 전체 증명의 대체물이 아니다. A1/A2 가변 AIDC 및 M2의 A2 고정 영역은 이 증명의 범위 밖이다.',
        '', '원본 node-flow Compact와 정적 Presolve를 재사용한 이동 블록은 Binary417,296→18,680이다. 변수489,321/행432,529/Nonzero2,974,415이며, Alias592개 및 삭제 행 근거1,167개를 원본 독립 유리수 검증기가 확인했다. 8대의 자유로운 STAY/MOVE·다중 이동·충방전·SOC·P/Q·PCS16 및24개 서비스 위치를 보존했다.',
        '',f'Source-YY 실제 OpenDSS 계수 재생성: **{coef.get("PASS",False)}**. Planning96, 독립 AIDC P/Q24축과 차량24개 위치 P/Q48축을 사용한다. 기존 DY 또는 IEEE123 계수는 재사용하지 않았다. 수학 Case SHA: `{raw.get("case_sha","미완료")}`. 원본 입력 SHA를 명시적으로 묶은 Case는 `{case_link.get("input_bound_case_sha","미완료")}`다. 원본 Source Wye/Wye IDC/480V와 기존 STA/750kVA, P5 및 SVR3를 동결했다. 유한 차분은 원본 알고리즘의 국소 선형화이며 전 제어 영역의 비선형 AC 인증을 뜻하지 않는다.',
        '',f'원본 평가 시점은 CommonClock의 실제 TIME 제어 처리 뒤 마지막 상태다. Source-YY B0 Planning96 전압 {planning.get("eval_Vmin")}~{planning.get("eval_Vmax")}pu, Actual96/Fresh 전압 {actual.get("eval_Vmin")}~{actual.get("eval_Vmax")}pu다. Prefix24의 최종 상태도 PASS다.',
        '',f'Actual96 전역/MV 최대 선로부하율은 {100*actual.get("rho_global",0):.8f}%, LV는 {100*actual.get("rho_LV",0):.8f}%, MV–LV 차이는 {100*(actual.get("rho_MV",0)-actual.get("rho_LV",0)):.8f}%p다. 기존 유한 P-only73.790115%, Q50 73.744164%는 Pilot이며 B2/B3 성과가 아니다.',
        '', 'Native TIME 전체 이벤트 안전은 FAIL로 보존한다. Prefix 저전압23초·과전압18초와 Planning 초기 과전압15초를 삭제하거나 초기 Tap/Queue/Delay를 바꾸지 않았다. 원본 소스는 제어 반복 중 모든 초의 전압을 최적화 안전 Gate로 검사하지 않으므로 이를 새로운 제약으로 추가하지 않았다. 원본 슬롯 최종 상태 판정과 추가 이벤트 진단을 분리했다.',
        '', '원본 Stage 연결 상태:', '']
    lines += ['- '+s for s in remaining]
    lines += ['', '원본 K48에 원시 IEEE8500 Helper를 직접 넣은 검사에서는 HELPER_PIVOT_AMBIGUOUS가 발생했다. 양의2진수 배율을 정확히 정규화한 Helper View는 실제 한 슬롯의 원본 exact_cut을 통과했다. 8대 분할도 차원 Guard만 바꾼 독립 계수 검증을 통과했다. 두 결과를 전체96 K48/Beam/Joint 통합 PASS로 승격하지 않는다.',
        '', '원본 START_WINDOW 위반414개 캐시는 계속 거부한다. AIDC 전체 가변 Job 도메인, 실제 QoS/서비스/Carryout 및 Migration 검증을 고정 B0 또는 단일 Job 예제로 대체하지 않았다. GPU Scaling·경로 삭제·강제 STAY/MOVE·Budget/Gap 변경도 없다.',
        '', 'Checkpoint/Resume·실패 Stage 격리·중복 Worker 차단·입력 변조 거부 Fixture는 실제 과학 모델 인증과 분리한다. 기존 Native 원장과 Worker는 수정하지 않았다. 실제 최적화 전이므로 LB/UB/Gap 수치는 null이며, 이것 자체를 자동 실패 원인으로 삼지 않았다.',
        '', f'`SCIENTIFIC_SIMULATION_READY={ready}`, `FIELD_INSTALLATION_UNVERIFIED=True`. 현장 GIS/보호설비 인증 부재가 현재 시뮬레이션 차단 원인은 아니다. 물리 B0 후보는 원본 평가 계약에서 성립하지만, 전체 알고리즘 캠페인 Primary 인증은 남은 Gate 통과 전까지 보류한다.',
        '', '준비 명령:', '', '```powershell',
        "& '..\\V2_add_runtime\\.venv\\Scripts\\python.exe' -X utf8 -m v2_add_preflight.static_execution proof",
        "& '..\\V2_add_runtime\\.venv\\Scripts\\python.exe' -X utf8 -m v2_add_preflight.static_execution native0",
        "& '..\\V2_add_runtime\\.venv\\Scripts\\python.exe' -X utf8 -m v2_add_preflight.static_verify",
        '```', '', '미실행 캠페인 명령 형식은 `python -m v2_add_preflight.static_execution campaign --approval <user-approval.json>`이다. 현재는 HOLD가 먼저 거부하며, 준비되지 않은 IEEE123 Worker로 우회하지 않는다. May02~07 신규 과학 실행은 하지 않았다.']
    (OUT/'FINAL_PRESTART_REVIEW_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':report()
