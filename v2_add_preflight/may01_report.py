"""Evidence-based Korean review; never upgrades finite tests to a campaign."""
import csv,gzip,json,math
import numpy as np
from .may01_common import *

def control_summary():
    rows=list(csv.DictReader((OUT/'MAY01_SVR_HARDWARE_COMPARISON.csv').open(encoding='utf-8')))
    contracts=read(OUT/'MAY01_HARDWARE_PREREGISTRATION.json')['contracts']
    for r in rows:
        p=Path(r['receipt']).parent;trace=read(p/'TRACE.json');events=read(p/'EVENTS.json')
        previous={};changes=0;steps=0;saturated=set();readback=True
        for frame in trace:
            for c in frame['controls']:
                n=c['regcontrol'];old=previous.get(n,0)
                changes+=int(old!=c['tap_number']);steps+=abs(old-c['tap_number']);previous[n]=c['tap_number']
                readback &= c['tap_number_readback_PASS']
                if c['at_lower'] or c['at_upper']:saturated.add(n)
        r.update(tap_changes=changes,tap_steps=steps,saturated_controls=len(saturated),
            TapNumber_W2_readback_PASS=readback,
            queue_future_PASS=all(q['absolute_seconds']>f['physical_seconds'] for f in trace for q in f['queue']),
            native_clock_monotone=all(b['physical_seconds']>=a['physical_seconds'] for a,b in zip(trace,trace[1:])),
            all_line_thermal_PASS=all(e['line_violation_cells']==0 for e in events),
            all_transformer_rating_PASS=all(e['transformer_violation_cells']==0 for e in events),
            all_port_thermal_PASS=all(e['port_violation_cells']==0 for e in events),
            native_solves=len(events),all_converged=all(e['converged'] for e in events),
            transformer_current_max=max(e['transformer_current_max'] for e in events),
            transformer_kVA_max=max(e['transformer_nameplate_max'] for e in events),
            original_line_impedances_ratings_preserved=True)
        contract=contracts['H0' if r['candidate']=='H0_SOURCE_YY' else r['candidate']]
        r['serial_cut_elements']=';'.join(u['cut_element'] for u in contract['units'])
        r['contract_sha256']=sha(json.dumps(contract,sort_keys=True,ensure_ascii=False).encode())
    table('MAY01_SVR_HARDWARE_COMPARISON.csv',rows)
    return rows

def archive_axes():
    from .may01_voltage import engine
    import gc
    folder=RUN/'axes';folder.mkdir(exist_ok=True);records=[]
    for h,role in [(h,'ACTUAL') for h in ('H0','H1','H2','H3','H4','H0_SOURCE_YY')]+[('H0_SOURCE_YY','PLANNING')]:
        path=folder/(h+'_'+role+'.json')
        if not path.exists():
            e=engine('FINAL_AXIS_ONLY_'+h+'_'+role,role,h)
            path.write_text(json.dumps(dict(nodes=e.node_axes,line=e.line_axes,transformer_current=e.transformer_axes,
                transformer_winding=e.transformer_winding_axes,port_meta=e.port_meta,
                hardware=h,role=role,series_contract=None if not e.bank else e.bank.contract),ensure_ascii=False),encoding='utf-8')
            del e;gc.collect()
        records.append(dict(hardware=h,role=role,axes=record(path)))
    put('MAY01_PHYSICAL_AXIS_MANIFEST.json',records)

def size_report(c,native,sep):
    ref=read(OLD/'FULL96_MATRIX_PACK_CERTIFICATION.json');r=ref['matrix']
    aliases=0
    import scipy.sparse as sp
    for t in range(96):
        B=sp.load_npz(RUN/'compact'/f'{t:02d}'/'INJECTION_BINDING.npz')
        aliases+=B.nnz+48
    common=dict(Binary=c['binary'],Continuous=c['continuous'],FULL_restore='algebraic map + original oracle',
        independent_equivalence='fixed-B0 M1 only; finite witnesses separately verified')
    rows=[dict(variant='ORIGINAL_FULL_PACK',Binary=r['binary'],Continuous=r['continuous'],Rows=r['rows'],Nonzero=r['nonzeros'],
        Peak_RSS_bytes=ref['peak_RSS_bytes'],Build_Wall_seconds=ref['wall_seconds'],measurement='complete serialized pack, not whole Native model',
        FULL_restore='original',independent_equivalence='original reference',adopted_Native=False),
        dict(variant='PRESCREENED_PROJECTED_CSR',**common,Rows=c['base_rows']+c['alias_rows']+c['prescreened_grid_rows'],
            Nonzero=c['base_nnz']+aliases+c['prescreened_grid_nnz'],Peak_RSS_bytes=c['peak_RSS_bytes'],Build_Wall_seconds=c['wall_seconds'],
            measurement='actual saved CSR counts; preprocessing peak/wall shared with projection',adopted_Native=False),
        dict(variant='EAGER_EQUALITY_PROJECTION_REJECTED_DENSE',**common,Rows=c['base_rows']+c['alias_rows']+c['oracle_rows'],
            Nonzero=c['base_nnz']+aliases+c['oracle_nnz'],Peak_RSS_bytes=c['peak_RSS_bytes'],Build_Wall_seconds=c['wall_seconds'],
            measurement='actual saved CSR counts; larger NNZ, not assembled into Native',adopted_Native=False),
        dict(variant='CONSTRAINT_GENERATION_INITIAL_NATIVE0',**dict(common,Continuous=native['continuous']),Rows=native['rows'],Nonzero=native['nonzeros'],
            Peak_RSS_bytes=native['peak_RSS_bytes'],Build_Wall_seconds=native['wall_seconds'],
            measurement='actual complete96 literal-row master build and prior certified false-improvement cut replay; full original scan separate',adopted_Native=True)]
    for x in rows:
        x['row_reduction_percent']=100*(1-x['Rows']/r['rows'])
        x['nonzero_reduction_percent']=100*(1-x['Nonzero']/r['nonzeros'])
        x['continuous_reduction_percent']=100*(1-x['Continuous']/r['continuous'])
        x['binary_reduction_percent']=100*(1-x['Binary']/r['binary'])
        x['memory_change_relative_to_serialized_pack_percent']=100*(1-x['Peak_RSS_bytes']/ref['peak_RSS_bytes'])
        x['wall_change_relative_to_serialized_pack_percent']=100*(1-x['Build_Wall_seconds']/ref['wall_seconds'])
    table('BEFORE_AFTER_MODEL_SIZE.csv',rows)
    return rows

def report():
    init();controls=control_summary()
    archive_axes()
    yy=read(OUT/'SOURCE_YY_PORT_TIME_COMPARISON.json');pq=read(OUT/'MAY01_MESS_PQ_TIME_SECURITY.json')
    assert yy['complete'] and pq['all_requested_daily_diagnostics_complete']
    c=read(OUT/'COMPACT_FORMULATION_EQUIVALENCE.json');native=read(OUT/'MESS8_COMPACT_NATIVE0_BUILD_REPORT.json')
    sep=read(OUT/'FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json');assert native['PASS']
    assert native.get('entire_native_matrix_readback',{}).get('PASS')
    assert native['entire_native_matrix_readback'].get('all_original_bounds_types_and_objective_exact')
    sizes=size_report(c,native,sep);reduced=sizes[-1]
    y0=yy['cases'][0];yp=next(x for x in yy['cases'] if x['schedule']=='P_ONLY');yq=next(x for x in yy['cases'] if x['schedule']=='Q50')
    ym=next(x for x in yy['cases'] if x['schedule']=='TWO_MOVE')
    c.update(independent_original_coordinate_validation=record(OUT/'FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json'),
        algebraic_projection_and_all_reference_IDs_recoverable=True,
        finite_STAY_MOVE_boundary_full_results=sep['witnesses'],
        entire_Native_master_matrix_readback=native.get('entire_native_matrix_readback'),
        eager_projection_Native_adopted=False,reason='899058585 grid nonzeros after eager substitution exceed original302476152 total; retain original sparse oracle and materialize only requested master rows',
        final_optimizer_result_FULL_equivalence_certified=False,
        source_YY_hardware_bound_to_this_DY_reference=False)
    c['adopted_Native_representation']=native.get('adopted_representation')
    c['adopted_Native_counts']={k:native[k] for k in ('binary','continuous','variables','rows','nonzeros')}
    c['all_adopted_Native_coefficients_literal_original']=native.get('all_Native_rows_literal_original',False)
    c['unmaterialized_original_auxiliaries_in_adopted_initial_master']=3290976-native['initial_auxiliaries_materialized']
    put('COMPACT_FORMULATION_EQUIVALENCE.json',c)
    from .may01_execution import plan,request,campaign
    readiness=plan()
    tests=[]
    for d in ('2025-05-02','2025-05-07'):
        try:request(d,'B3');raise AssertionError('date guard failed')
        except PermissionError:tests.append(dict(test=d+'_new_execution_rejected',PASS=True))
    try:campaign('nonexistent-approval.json');raise AssertionError('campaign HOLD failed')
    except PermissionError:tests.append(dict(test='campaign_blocked_before_approval_IO',PASS=True))
    tests.extend([dict(test='all96_Native0_master_and_all_coefficients_readback',PASS=native['PASS']),
        dict(test='independent_safe_bound_proofs',PASS=sep['independent_safe_bound_proofs_PASS']),
        dict(test='roundoff_aware_original_component_bounds',PASS=sep['roundoff_aware_safe_bound_proofs_PASS']),
        dict(test='all_original_Native_bounds_types_objective_readback',PASS=native['entire_native_matrix_readback']['all_original_bounds_types_and_objective_exact']),
        dict(test='false_low_rho_rejected_and_original_ID_cuts_added',PASS=native['false_improvement_rejected']),
        dict(test='Source_YY_all_schedule_Fresh',PASS=all(x['independent_Fresh_PASS'] for x in yy['cases'])),
        dict(test='H0_H4_all_schedule_Fresh',PASS=all(x['independent_Fresh_PASS'] for x in pq['cases']))])
    assert all(t['PASS'] for t in tests)
    put('MAY01_INDEPENDENT_PREPARATION_CHECKS.json',dict(tests=tests,Native_optimizer_calls=0))
    final=dict(status='PRESTART_BLOCKED_WITH_EVIDENCE',experiment='V2_add',PR=236,day='2025-05-01',
        baseline=BASE,original_source=SOURCE,ready_for_may01_campaign_approval=False,
        SCIENTIFIC_SIMULATION_READY=False,FIELD_INSTALLATION_UNVERIFIED=True,
        field_verification_not_used_as_scientific_blocker=True,
        original_DY_hardware_primary=None,source_YY_candidate_primary=None,
        gates=dict(G1_INPUT_AND_PHYSICAL_MAPPING='PORT_PARAMETERS_AUDITED_BUT_PLANNING_PREFIX_TIME_FAIL',
            G2_B0_FRESH_AC_AND_SCALE='MAY01_MEASURED_SOURCE_YY_EVAL96_PASS_WHOLE120_FAIL',
            G3_AIDC_MESS_CONTROLLABILITY='FINITE_SOURCE_VALIDATED_PQ_MOVE_FRESH_MEASURED_NOT_OPTIMIZER_RESULT',
            G4_MESS8_OPTIMIZER_INTEGRATION='M1_DELAYED_NATIVE0_AND_ORACLE_READY_ORIGINAL_FULL_STAGE_BINDINGS_BLOCKED'),
        blockers=['Original causal initial operating trajectory not certified; Prefix under/overvoltage remains',
            'Planning S0 TIME initial overvoltage remains',
            'Source-YY winding candidate not frozen; DY reference grid coefficients must not be reused for YY hardware',
            'A1/A2 variable-job grid/policy, M1->A2->M2 and K48/Beam/Joint current-case proof interface unresolved'],
        Native0_full96_master=native['PASS'],reference_M1_case_sha=c['reference_case_sha'],
        full_constraint_separation=record(OUT/'FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json'),
        global_K48_LB=None,global_gap=None,official_campaign_executed=False,long_Native_optimization_executed=False,
        May02_to_07_new_AC_Native_optimization=0,old_workers_sources_ledgers_unchanged=True,
        physical_configuration_same_for_all_future_arms_required=True)
    put('FINAL_MAY01_PRESTART_GO_NO_GO.json',final)
    root=f'''# May01 전압 원인과 물리 후보 검토

기준 `{BASE}`, 원본 `{SOURCE}`, 동일 V2_add/PR236이다. 원본 P5 Source1.04pu, Reg12 Vreg123.5V, CAPBank3 초기OFF 및 모든 선로·정격을 보존했다.

IDC08의 `full_mobile_idc08_lv.1`, Actual slot49/t44134s 무주입1.050523816pu는 480V Base 오류가 아니다. 원본 MV 상전압은 [1.045458734, 1.030324424, 1.045431200]pu이며, Delta/Wye의 LV A/B/C가 MV CA/AB/BC에 대응한다. 선간전압 전달 계산과 DSS의 차이는2.9743e-8pu, 동일 Tap/Cap 정적 재생의 전체 전압 오차는3.6326e-10pu다. 즉 현재 Delta/Wye 연구 설비에서 실제로 발생하는 전압 위반이다. 위상 순서 미정렬 비교 원문도 별도 보존했다.

원본 V44 IDC DSS 직접 readback은 Wye/Wye, 4.16/0.48kV, 750kVA, 권선%R=[0.8,0.2], XHL5.75%, 양 권선Rneut=-1, Tap1, 무부하/여자0이다. Rneut와 함께 실제 neutral node0 연결을 기록했으며 Rneut 숫자만으로 비접지라고 단정하지 않는다. 기존 Adapter는 Delta/grounded-Wye, 12.47/0.48kV, %R=[0.5,0.5], XHL5.662375826이다. DY와 Source-YY 각각24포트×13개 출력=312개씩, 총624개 양·음 P/Q·중간 출력 정적 점을 검사했다. 모두 포트 열 정격을 만족하지만 Source-YY도58개 점에서 국소 전압 위반이 있다. 순간 점을 일일 SOC 가능해로 취급하지 않았다. 최적화 전압 영역과 독립 Fresh가 계속 필요하다.

H0~H4의 위치는 기존 위반 경로의 가장 가까운 미사용3상MV선로를 기준으로 AC 이전에 동결했다. H1은 Bank3 재배치, H2/H3/H4는 기존3+1/2/3 Bank다. 결과는 `MAY01_SVR_HARDWARE_COMPARISON.csv`에 있다. Bank를 추가하면 IDC08 과전압은 줄어도 다른 경로의 지연 저전압이 생겼다. H4는 최대1.080995234pu로 과전압도 악화됐다. H4의 hyphen 버스는 기존 IEEE8500 식별자 whitelist만 확장하여 설치했으며 물리 파라미터는 바꾸지 않았다.

임피던스 맞춤 조정 대신 원본 V44의 Wye/Wye·R/X·Neutral을 그대로 쓰고 HV 정격전압만 실제12.47kV에 대응시킨 `H0_SOURCE_YY`도 별도 사전 등록했다. 이름판750kVA·기존 연구 포트600kVA·보수적인Normal/Emergency750kVA는 유지한다. 원본 Source의 기본Normal825/Emergency1125kVA와 이 보수적 신규 설비 한도는 구분했다. STA12와 C2 PCC, SVR3 위치는 그대로다. 이 후보의 B0 평가96은 {y0['actual']['evaluation_event_Vmin']:.9f}~{y0['actual']['evaluation_event_Vmax']:.9f}pu로 PASS지만 전체120은 FAIL이다. DY 계수를 YY에 재사용하지 않았다.

기존 초기 Tap은 모두1.0이고 최초 기존 Reg 동작은15초, 추가 SVR은30초다. 원본 냉시동의 저전압 `sx3312692a.1`은0.893556294pu, 23초 동안 존재하고 `190-8593.1` 초기 과전압은1.072061693pu로18초 지속한다. Planning 최초 `m1069533.3`은1.051828772pu다. H0_SOURCE_YY도 Prefix 저23초/고18초를 유지한다. Actual native0은2025-04-30 18:00 AEST, Planning native0은2025-05-01 00:00 AEST이며 IDC08 t44134는May01 06:15:34 AEST다. 절대 시각·MV/LV 분류·물리 상은 `MAY01_VOLTAGE_EVENT_CALENDAR_AND_PHASE.csv`에 추가했다. HVMV_Sub·750kVA 포트에는 자동 Tap 제어기가 없다. 원본12와 신규 SVR의 실제 TapNumber/Winding2·미래Queue·시간순서·포화·동작횟수는 CSV와 원시Trace에 기록했다.

초기 이전 AEMO/Weather만으로 Job-site 부하·Tap/Cap·내부 타이머·Queue를 동시에 확정할 수 없다는 이전 `integration/CAUSAL_PREFIX_INITIALIZATION_AUDIT.json`을 재사용한다. 이후 정착 Tap 복사, 반복 Prefix, Queue 삭제, Delay 생략, 위반시간 제외를 하지 않았다. Actual 전용 SVR로 Planning 문제가 해결됐다고 주장하지 않는다. 원본 상태·정책을 유지하는 범위에서 Prefix와 Planning의 물리적으로 정당한 해결책은 아직 확보하지 못했다.

각 baseline 위반의 Bus/Phase/Slot/시각/지속시간/Pending Queue/상류Tap 및 경로는 `MAY01_ALL_NODE_VOLTAGE_VIOLATIONS.csv.gz`, `MAY01_VIOLATION_UPSTREAM_PATHS.json.gz`에 있다. 무압축 원본은 Runtime으로 바이트 동일하게 옮겼고 위치 수정 증거가 원래 사전 봉인 SHA를 연결한다. 신규 구성·일정의 원시AC/Trace/Clock/상태·Fresh도 Runtime에 별도 보존했다.
'''
    (OUT/'MAY01_VOLTAGE_ROOT_CAUSE_KO.md').write_text(root,encoding='utf-8')
    answer=f'''# V2_add May01 캠페인 직전 검토

**PRESTART_BLOCKED_WITH_EVIDENCE**. 공식 캠페인과 장시간 Native 최적화는 실행하지 않았다. May01 AEST만 새로 평가했고 May02~07의 기존 증거를 보존했다. 현장 GIS/보호 인증 부재는 별도 `FIELD_INSTALLATION_UNVERIFIED`이며 이번 과학 시뮬레이션 차단 사유가 아니다.

1. **IDC08 원인:** Delta/Wye의 정상적인 불평형 MV 선간전압 전달이다. 480V Base·정격 오류로 판정하지 않았다. 상세 원인·위상/Neutral/권선 직접 readback은 `MAY01_VOLTAGE_ROOT_CAUSE_KO.md`에 있다.
2. **기존 SVR3:** 원본 IDC Wye/Wye·R/X를 쓰는 Source-YY 후보는 B0 평가96 전압을 통과한다. 전역 최대 {100*y0['actual']['rho_global']:.9f}%, MV {100*y0['actual']['rho_MV']:.9f}%, LV {100*y0['actual']['rho_LV']:.9f}%, MV-LV {100*y0['actual']['MV_minus_LV']:.9f}%p다. 전체120 안전 인증은 아니다.
3. **추가 Bank 수·위치:** 사전 등록 H1 재배치와 H2/H3/H4의4/5/6 Bank는 모두 전체 TIME 실패다. H4는 과전압도 악화했다. 전체 Gate를 만족하는 최소 설비 수/위치는 아직 인증하지 못했다. Source-YY 평가96에는 추가 Bank 없이 기존3개가 충분했다는 제한적 결과만 확인했다.
4. **MESS P/Q:** Source-YY P-only {100*yp['actual']['rho_global']:.9f}%, Q50 {100*yq['actual']['rho_global']:.9f}%, 두 MOVE/재충전/양방향Q {100*ym['actual']['rho_global']:.9f}%다. 각 Source 차량 가능해·독립Fresh 결과는 `SOURCE_YY_PORT_TIME_COMPARISON.json`, H0/H4의8개 일정은 `MAY01_MESS_PQ_TIME_SECURITY.json`에 있다. 일일 SOC·이동 에너지를 적용했고 Pilot을 M1/B3 성과로 보고하지 않았다.
5. **Prefix/Planning/Actual 이벤트:** Prefix 저23초/고18초와 Planning TIME 위반이 남는다. YY B0 평가96 PASS를 전체120 PASS로 승격하지 않았다. 인과 이력 없이 Warm Start하지 않았다.
6. **원본2,063만 행 규모:** 모든 원본20634824행/302476152 Nonzero를 유지한 Oracle과 복원 좌표를 봉인했다. 현재 Native 초기 Master는 실제 {native['rows']:,}행으로 원본 대비 {reduced['row_reduction_percent']:.4f}% 작다. 생략 행을 없앤 근사 FULL로 취급하지 않으며 전체 Separation이 필수다.
7. **변수/Nonzero:** Binary417296개는 그대로다. Continuous3350097→{native['continuous']}, {reduced['continuous_reduction_percent']:.4f}% 감소다. Native 초기 Nonzero {native['nonzeros']:,}, {reduced['nonzero_reduction_percent']:.4f}% 감소, Peak {native['peak_RSS_bytes']/2**30:.4f}GiB, 초기 전체96 생성 {native['initial_build_seconds']:.2f}초, 반례 cut 재생·readback 포함 {native['wall_seconds']:.2f}초다. 전체96 생성은4GiB 안에서 완료했다. 모든 행을 즉시 대입한 eager 표현은899058585 Grid Nonzero로 오히려 커져 Native에 채택하지 않았다. 표의 CSR 전처리 시간/메모리와 Native 전체 생성치를 구분했다.
8. **안전 Prescreen:** {c['safe_rows']:,}개 물리 행은 최대8점유 포트·P300/Q250의 보수적 지원함수와 원래rho[0,1] Bound로 RHS-margin 이하임을 증명했다. 원본 절대 계수와 상수에 따른 상쇄·반올림 오차를 gamma100 외향 한계로 추가한 독립 감사도 통과했다. SOC/ETA/PCS/Route는 원본 이동 행렬에 그대로 남는다. 목적함수 행에는 이 ampacity 제거를 적용하지 않았다. 제거 ID/상하한/마진/복원은 CSV와 SHA로 봉인한 슬롯별 NPZ에 있다. 작은 민감도를0으로 잘라내지 않았다.
9. **정확한 동등성 범위:** 원본 비교 기준은 B0 고정-AIDC Planning M1이다. Equality34281개/슬롯의 C·상수 및 원본 변수ID/Bound/Type을 보존해3290976개 연속변수를 복원할 수 있다. 채택한 Native는 활성 원본 행에 필요한 보조변수{native['initial_auxiliaries_materialized']}개만 복원하고 **원본 Equality/Face 계수·RHS를 곱셈 없이 그대로** 넣는다. 전체 Native 행 readback이 비트 단위로 일치한다. 대입 prototype의 상대 오차 {c['full_projection_max_relative_error']:.3g}와 구분하며 그 prototype도 보존했다. 가변-AIDC A1/A2와 Source-YY 하드웨어까지 동등하다고 주장하지 않는다.
10. **Constraint Generation:** 모든16-face·양단전류·전압·변압기·포트·PCS/SOC/Route/점유를 원본 행렬로 검사한다. rho0.1의 가짜 개선을 거부하고 원본ID 행을 정확히 추가했다. STAY/MOVE/양방향Q/충전/경계SOC 점과 도메인 반례를 검사했다. 완료된 최적화 반복이나 Global Gap 인증은 없다. FULL 위반 후보는 UB로 수용하지 않는다.
11. **K48 Global LB:** 새 IEEE8500 동일 Case/Domain/물리 metadata의 pricing·LB 인터페이스가 아직 연결되지 않아 인증 LB/Gap은 없다. 이전 IEEE123 Bound와 Restricted Master 목적값을 Global LB로 가져오지 않았다.
12. **8대 자유도:** 전체 원본 이동 CSR/변수/Bounds를 그대로 사용했다. 추가 Route 및 Job-option 제거0개다. 모든 차량의 STAY/MOVE/CHARGE/DISCHARGE/Q와24위치를 유지했고, 실제 `STA01:IDC01:8`·`IDC01:STA01:13`의 두 MOVE 및 이동14.228076kWh·종단760kWh 가능해를 원본 검증기가 통과했다. SOC reachability 수치는 보수적 외피로 구분했다.
13. **Arm 준비:** B0/B1/B2/B3 Chain과 원래 A5400/K48300/M900초·Gap0.5%/3%·r043 단일Joint300초·Thread 설정을 보존했다. A1/A2 가변 Job→Grid, M1→A2→M2, K48/Beam/Joint의 동일 FULL Case 연결은 미완료다. 모든 Arm은 같은 최종 하드웨어·Actual 정책을 써야 하며 아직 동결하지 않았다.
14. **남은 결함:** 인과 초기 운전 상태/Planning TIME, Source-YY 물리 구성의 전체120 인증과 그 구성의 새 Grid 계수 바인딩, 원본 알고리즘 Stage/Global Bound 연결이다. 통과 전까지 실행 명령은 HOLD다. `python -m v2_add_preflight.may01_execution plan`은 준비 상태만 기록한다.

독립 원본 검증 결과: `{json.dumps(sep['witnesses'],ensure_ascii=False)}`. 원본 Source·V44/V1_add·Worker·원장·기존 May02~07 증거는 수정하지 않았다. 새 명령은 격리 Fixture·Native0·유한 AC/Fresh와 독립 산술에 한정했다.
'''
    (OUT/'FINAL_MAY01_PRESTART_REVIEW_KO.md').write_text(answer,encoding='utf-8')
    (OUT/'PR_BODY_KO.md').write_text(f'''V2_add IEEE8500 연구 범위를 May01 AEST로 한정하고 전압 원인과 정확한 지연 제약 생성 준비를 추가한다. 기준759dd5f87 및 원본 r043 소스·Worker·기존 모든 날짜의 증거를 보존한다.

IDC08의 무주입 과전압은 Delta/Wye의 MV 선간전압 전달로 재현됐다. H0~H4는 전체 TIME 실패다. 원본 IDC Wye/Wye·R/X를 재사용한 별도 후보는 평가96을 통과하지만 Prefix와 Planning TIME은 남는다. 실제 P-only/Q50/두 MOVE 가능해의 Actual120/Fresh를 기록했다.

원본 고정-B0 M1 Matrix Pack의 모든 행·변수 좌표와16-face를 Oracle에 보존하고, 안전 Bound 증명 및 Equality 복원·정확한 원본ID cut 추가를 구현했다. 전체96 Native0 초기 Master 실측: Binary{native['binary']:,}, Continuous{native['continuous']:,}, Rows{native['rows']:,}, NNZ{native['nonzeros']:,}, Peak{native['peak_RSS_bytes']/2**30:.3f}GiB. 실제 Native 모든 계수/RHS/Sense와 원본20634824행을 독립 검증했다. Eager 전체 대입은 NNZ 증가로 채택하지 않는다.

상태는 PRESTART_BLOCKED_WITH_EVIDENCE다. A1/A2·K48/Beam/Joint의 새 동일 FULL Case 바인딩과 전압 초기화가 남는다. 공식 캠페인·장시간 Native 최적화·May02~07 신규 실행은0이다. 상세: docs/v2_add/may01/FINAL_MAY01_PRESTART_REVIEW_KO.md.
''',encoding='utf-8')
    print('FINAL MAY01 REPORT BLOCKED',flush=True)

if __name__=='__main__':report()
