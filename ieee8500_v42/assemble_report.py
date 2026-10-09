"""Assemble the one blocked study draft; never promote a failed AC case."""
from pathlib import Path
import shutil
import csv
import numpy as np
from .common import ROOT, REPORT, DATA, read, write, table, sha
from .geometry import read_csv
from .integration import digest, comparison_plan, verify_source_identity
from .selected_case_v3 import MAPPING


def ref(path):
    path=Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path))


def archive_earlier_outputs():
    history=REPORT/'historical_fixed_v3_outputs'
    names=('FINAL_STA_MAPPING.csv','RELATIVE_POSITION_AUDIT.csv','SCALE_SCREENING.csv',
           'REGCONTROL_TAP_VALIDATION.csv','LINE_LOADING_REPORT.csv','AIDC_CAPACITY_AUDIT.csv')
    history.mkdir(exist_ok=True)
    for name in names:
        # An existing archive is never replaced by a later-stage main file.
        if not (history/name).exists():shutil.copyfile(REPORT/name,history/name)
    write(history/'SCOPE.json',dict(scope='EARLIER_FIXED_V3_DIAGNOSTICS_NOT_CURRENT_SELECTION',
        superseded_by_user_joint_relocation_and_simulation_design_authorization=True,
        outputs={name:ref(history/name) for name in names}))
    return history


def line_report(archive):
    axes=read(archive/'AC_AXES.json')
    # NPZ indexing decompresses a member on every access. Materialize these
    # two arrays once before the whole-feeder355008row CSV loop.
    with np.load(archive/'AC_96.npz',allow_pickle=False) as packed:
        a={key:packed[key] for key in ('line_amps','line_rho')}
    groups={}
    for k,row in enumerate(axes['lines']):
        if axes['objective_mask'][k]:groups.setdefault(row['element'],[]).append(k)
    with (REPORT/'LINE_LOADING_REPORT.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(('scope','slot','line','parent_terminal','binding_local_node','I_A','NormalAmps','rho'))
        for t in range(96):
            for line,indices in groups.items():
                k=max(indices,key=lambda i:a['line_rho'][t,i]);r=axes['lines'][k]
                writer.writerow(('STUDY_DRAFT_BLOCKED',t,line,r['terminal'],r['node'],
                    float(a['line_amps'][t,k]),r['normal_amps'],float(a['line_rho'][t,k])))
    return len(groups)*96


def assemble():
    scale_path=REPORT/'joint_selection_v3/selected_ac/SCALE_SCREENING.csv'
    scales=read_csv(scale_path)
    if len(scales)!=12 or any(r['AC_constraints_pass']=='True' for r in scales):
        raise ValueError('REPORT_MUST_REVIEW_CHANGED_SCALE_RESULT_BEFORE_ASSEMBLY')
    ports=read_csv(REPORT/'joint_selection_v3/selected_port_ac/PORT_QUALIFICATION_SUMMARY.csv')
    if len(ports)!=12:raise ValueError('TWELVE_PORT_AC_REPORTS_REQUIRED')
    bounded=read(REPORT/'joint_selection_v3/selected_response/RECEIPT.json')
    replay=read(REPORT/'joint_selection_v3/fresh_selected_b0_replay/RECEIPT.json')
    if not replay['PASS']:raise ValueError('FRESH_REPLAY_REQUIRED')
    history=archive_earlier_outputs()
    chosen=read_csv(MAPPING);byid={r['location_id']:r for r in chosen}
    portdict={r['site']:r for r in ports}
    original={r['location_id']:r for r in read_csv(DATA/'geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv')}
    main=[]
    for r in chosen:
        if r['role']!='STA':continue
        p=portdict[r['location_id']]
        main.append(dict(sta_id=r['location_id'],traffic_node_id=r['traffic_node_id'],
            original_mv_bus=original[r['location_id']]['ieee8500_bus'],study_selected_lv_bus=r['candidate_bus'],
            original_transformer=r['original_service_transformer'],original_transformer_kva=r['original_transformer_kva'],
            original_triplex_lines=r['support_triplex_lines'],original_Triplex_NormalAmps=r['original_triplex_normal_amps'],
            simulation_design_P_charge_kw=5,simulation_design_P_discharge_kw=5,simulation_design_Q_abs_kvar=3,
            simulation_design_S_kva=6,simulation_design_hot_A=27,
            sampled_8_commands_96slot_local_PASS=p['full_box_local_grid_PASS'],
            sampled_8_commands_96slot_hardware_PASS=p['hardware_full_box_PASS'],
            modeled_direction_status='ASSUMED_PROXY_DIRECTION_PASS',field_geography='UNVERIFIED',
            continuous_control_domain='UNVERIFIED',reverse_power_protection='UNVERIFIED',
            study_mapping_snapshot_frozen=True,is_final_operational_selection=False,production_ready=False))
    table(REPORT/'FINAL_STA_MAPPING.csv',main)
    shutil.copyfile(MAPPING.parent/'RELATIVE_POSITION_AUDIT.csv',REPORT/'RELATIVE_POSITION_AUDIT.csv')
    shutil.copyfile(scale_path,REPORT/'SCALE_SCREENING.csv')
    capacities=read_csv(history/'AIDC_CAPACITY_AUDIT.csv')
    for r in capacities:
        r['historical_v3_bus']=r.pop('fixed_bus');r['study_selected_MV_bus']=byid[r['aidc_id']]['candidate_bus']
        r['status']='AUTHORIZED_MV_AGGREGATE_STUDY_FACILITY_HARDWARE_UNVERIFIED'
        r['historical_overlay_transformer_kVA_NOT_original_installed']=r.pop('historical_overlay_transformer_kVA')
    table(REPORT/'AIDC_CAPACITY_AUDIT.csv',capacities)
    taps=[]
    for case in scales:
        taps.extend(read_csv(REPORT/'joint_selection_v3/selected_ac'/case['case']/'REGCONTROL_TAPS.csv'))
    table(REPORT/'REGCONTROL_TAP_VALIDATION.csv',taps)
    archive=REPORT/'joint_selection_v3/selected_ac/bg0p552_gpu1p0'
    line_rows=line_report(archive)
    source=verify_source_identity(ROOT,read(REPORT/'V42_SOURCE_SHA_MANIFEST.json'))
    write(REPORT/'FINAL_V42_BYTE_IDENTITY.json',source)
    reference=next(r for r in scales if r['case']=='bg0p552_gpu1p0')
    config=dict(schema='IEEE8500_V42_SINGLE_RESEARCH_CONFIGURATION_V3',
        status='STUDY_CONFIGURATION_DRAFT_BLOCKED',day='2025-05-01',
        development_date_already_exposed=True,independent_evaluation_date=None,
        source_git_sha=source['v42_git_sha'],source_content_manifest=ref(REPORT/'V42_SOURCE_SHA_MANIFEST.json'),
        source_feeder_manifest=ref(DATA/'FEEDER_SOURCE_MANIFEST.json'),
        objective='min overall original canonical source-parent phase current / original NormalAmps',
        no_original_model_objective_or_rating_relaxation=True,background_scale=.552,
        background='uniform original static snapshot counterfactual, not an observed IEEE8500 daily customer curve',
        AIDC_capacity_scale=1.,installed_GPU=780,workload_multiplier=1.,PF=.95,PV_active_objects=0,
        source_pu=1.05,feeder_Vreg=126.5,other_Vreg=125.,voltage_band_pu=[.95,1.05],
        original_RegControls=12,original_CapControls=9,original_Capacitors=10,
        automatic_controls='original controls sequential across96slots; no Planning control states imported in fresh replay',
        MESS_count=6,service_location_count=24,
        vehicle=dict(P_max_kw=450,PCS_kva=600,nameplate_energy_kwh=1800,
            original_fraction_Emin_kwh=660,original_fraction_Emax_kwh=1620,
            initial_and_terminal_energy_kwh=1140,original_charge_discharge_efficiency=.95,
            LV_auxiliary_interface_efficiency_assumption=.90,
            LV_AC_charge_to_battery_multiplier=.855,LV_AC_export_battery_debit_divisor=.855,
            mass_kg=28000,mass_evidence='original traffic assumption, not measured1800kWh vehicle',
            initial_locations=read(REPORT/'joint_selection_v3/selection_scores/PREREGISTRATION.json')['original_six_initial_locations']),
        LV_station_design=dict(docks=12,P_charge_kw=5,P_discharge_kw=5,Q_abs_kvar=3,S_kva=6,
            hot_current_A=27,voltage_dependent_limit='S<=27*actual_abs(V1-V2)/1000 kVA',
            connection='120/240V split-phase original customer .1.2 bus',
            interpretation='one redesigned study dock per existing STA; no original transformer or station-count additions',
            field_installed=False,complete_assembly_or_independent_Q_product_certified=False),
        mapping=ref(MAPPING),source_proximity_guard='original q05 MVrootimpedance guard retained',
        common_coordinate_transform=read(MAPPING.parent/'GEOMETRY_RESULT.json')['proper_common_transform'],
        modeled_geometry='all276pairs and552strictaxis PASS on source/MVprimaryproxy coordinates',
        field_geography='UNVERIFIED; original CRS/unit/compass and exact customer access unknown',
        selection_policy=ref(REPORT/'joint_selection_v3/selection_scores/PREREGISTRATION.json'),
        hardware_design=ref(REPORT/'LV_PORT_SIMULATION_DESIGN.json'),
        B0_archive=ref(archive/'AC_96.npz'),
        B0=dict(rho_max=float(reference['rho_max']),Vmin=float(reference['Vmin']),Vmax=float(reference['Vmax']),
            voltage_violation_node_slot_cells=int(reference['voltage_violation_cells']),
            original_line_transformer_constraints_PASS=True,all_original_voltage_constraints_PASS=False),
        sampled_LV_commands=dict(fixed_endpoints=9216,independent_auto_endpoints=384,
            eight_full_rating_commands_per_port_per_slot=True,
            all_sampled_local_limits_PASS=all(r['full_box_local_grid_PASS']=='True' for r in ports),
            all_sampled_hardware_limits_PASS=all(r['hardware_full_box_PASS']=='True' for r in ports),
            continuous_domain_certificate=False),
        actual_job_dispatch_QoS_WAN_native_window_compatibility='UNVERIFIED',
        six_vehicle_native_route_SOC_location_efficiency_adapter='UNVERIFIED',
        exact_FULL_Compact_C3A_grid_equivalence='UNVERIFIED',
        Actual_SUMO_six_vehicle_and_unseen_day_validation='NOT_RUN',
        original_campaign_mutations=0,B1_B2_B3_Native_calls=0,production_ready=False)
    fleet_path=REPORT/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json'
    config['six_unit_research_fleet_authority']=ref(fleet_path)
    config['simulation_authorization_contract']=ref(REPORT/'integration_contracts/RESEARCH_SIMULATION_AUTHORITY.json')
    write(REPORT/'STUDY_CONFIGURATION_DRAFT.json',config)
    scenario_sha=digest(config)
    write(REPORT/'STUDY_CONFIGURATION_SHA256.json',dict(canonical_configuration_sha256=scenario_sha,
        file_sha256=sha(REPORT/'STUDY_CONFIGURATION_DRAFT.json'),
        mapping_sha256=sha(MAPPING),status='FROZEN_REVIEW_SNAPSHOT_NOT_OPERATIONAL_SELECTION'))
    write(REPORT/'COMPARISON_PLAN_BLOCKED.json',comparison_plan(config))
    write(REPORT/'FINAL_SINGLE_SCENARIO.json',dict(status='NO_QUALIFIED_OPERATIONAL_SCENARIO',
        selected_operational_scenario=None,selected_and_frozen_production_configuration=None,
        single_research_draft=ref(REPORT/'STUDY_CONFIGURATION_DRAFT.json'),research_configuration_sha256=scenario_sha,
        research_reference_reason='predeclared historical-reference BG.552 and original780GPU, not Bpolicy outcome or forcedrho target',
        scale_candidates=12,qualified_scale_candidates=0,
        hard_failure='all12original96slotAC cases violate unchanged all-node voltage band',
        unresolved_conditions=['field geolocation/access/protection and LV vehicle→48Vinterface',
            'continuous P/Q and automatic-control affine certificate',
            'current V42 reference versus Native windows and causal QoS/WAN coupling',
            'six-unit Native axis, location efficiency SOC and original FULL/Compact/C3A exact equivalence',
            'independent Actual/SUMO/Fresh and unexposed evaluation day'],
        min_rho_objective_preserved=True,ratings_and_source_Vreg_unchanged=True,
        B1_B2_B3_Native_calls=0,production_ready=False))
    write(REPORT/'ASSEMBLY_RECEIPT.json',dict(status='CURRENT_REVIEW_ARTIFACTS_ASSEMBLED',
        mapping_sha256=sha(MAPPING),canonical_configuration_sha256=scenario_sha,
        whole_original_line_day_report_rows=line_rows,all12scale_constraints_FAIL=True,
        selected_48_bounded_actions_local_PASS=bounded['all_48_actions_local_PASS'],
        Native_calls=0,original_V42_source_identity=source))
    narrative(chosen,original,ports,scales,reference,scenario_sha)
    print('one blocked research draft assembled; qualified operational scenario=0',flush=True)


def narrative(chosen,original,ports,scales,reference,scenario_sha):
    lines=['# IEEE8500 V42 중간 보고 — 공동 연구 배치와 운영 승격 차단','',
        '**AIDC 12곳·저압 STA 12곳 공동 연구 배치를 구성했지만 최종 적격 운영 시나리오는 미선정이다. V42 전체 Native 이식은 미완료다.** '
        '24개 원 교통ID·네트워크·ETA와6대 MESS를 보존했다. 원 선로·변압기·전압 제약 및 전체 `min rho_max`는 그대로다. '
        '12개 사전 스케일 모두 원 전역 전압 제약을 실패하므로 Source/Vreg 변경 없이 Production을 차단했다. '
        'B1/B2/B3 Native·전체 모델·장시간 정책 Solver 실행은0회다. 현재 실행 캠페인에는 쓰지 않았다.','',
        '**기존 v3 방향 충돌 원인.** 원 AIDC12 좌표와 교통12 좌표의66쌍/132축을 독립 검사했다. '
        '원 XY를 그대로 쓰면115축, 공통 proper similarity 진단 정합 후에도17쌍/17축이 충돌한다. '
        '좌우 제약 AIDC02–03/07–11/11–12의 signed원벡터는 양의 가중치(.4739314708,.4681085601,.0579599691)로0이 된다. '
        '상하 AIDC09–12/10–12/11–12도(.3168031544,.6142251063,.0689717393)로0이다. '
        '각 벡터의 동일 선형 투영을 모두 양수로 요구하면 그 가중합도 양수여야 하므로0과 모순된다. '
        '독립 검토는 원 decimal을 정확한 Fraction으로 계산했다. 이는 고정된 이전12버스의 허용 공통 선형 정합에 대한 certificate이며 '
        '최적화 실패를 수학적 불가능으로 바꾼 주장도, 새 버스 재선정의 불가능 증명도 아니다. '
        '모든 쌍의 이름·교통/원XY/정합XY·차이·부호는 [66쌍 CSV](AIDC_66_DIRECTION_AUDIT.csv), '
        '[전체 충돌 CSV](AIDC_DIRECTION_CONFLICTS.csv), [exact certificate](GEOMETRY_INDEPENDENT_REVIEW.json)에 있다.','',
        '**현재 방향 검증.** 사용자 변경에 따라 이전 v3 버스 고정을 풀었다. '
        '모든 위치에 동일한 `(x′,y′)=(u·x−v·y+tx,v·x+u·y+ty)`를 적용했다. '
        '`u=-.0011398737189343131, v=-.00023721373007232747, tx=-1000.2819244675629, ty=14393.330183925018`, '
        '회전−168.2442350517°, 양의 균일척도.001164294829, det=1.355582448852e−6이다. 반사·개별 회전·방향 완화는0회다. '
        '선정 전 동결한 축/근접쌍1m 공차에서 AIDC66+STA66+교차144=276쌍,552축 전부 strict PASS이며 면제축은0이다. '
        '원 좌표 CRS/거리단위/나침반 방향과 정확한 고객 좌표는 검증되지 않았다. LV는 상위 원 서비스 변압기1차버스 좌표 Proxy다. '
        '정합 RMS는5.6960111 layout-equivalent km, 최대9.5434310으로 실제 지리 오차가 아니다. '
        'EPRI [BusCoordinates](https://opendss.epri.com/BusCoordinates.html)는 회로도 XY를, '
        '[GISCoords](https://opendss.epri.com/GISCoords1.html)는 위경도를 별도로 정의한다. '
        '따라서 **모델/Proxy 방향 PASS, 실제 지리 UNVERIFIED**로 표시한다.','',
        '| 위치 | 원 교통ID | 이전 v3 MV버스 | 현재 연구 MV버스 |','|---|---|---|---|']
    for r in chosen:
        if r['role']=='AIDC':lines.append(f"| {r['location_id']} | {r['traffic_node_id']} | {original[r['location_id']]['ieee8500_bus']} | {r['candidate_bus']} |")
    lines+=['','| STA | 원 교통ID | 현재 LV버스 | 원 서비스CT(kVA) | Triplex(A) |','|---|---|---|---:|---:|']
    for r in chosen:
        if r['role']=='STA':lines.append(f"| {r['location_id']} | {r['traffic_node_id']} | {r['candidate_bus']} | {float(r['original_transformer_kva']):g} | {float(r['original_triplex_normal_amps']):g} |")
    lines+=['',
        '**0.912 pu의 물리 원인.** 원 Master 정적 BG1·PV0·AIDC0·MESS0·Source1.05·feederVreg126.5/기타125·원10Caps/9CapControls에서 '
        '`sx2748781a.2`가109.450401 V다. 원 DSS120.088856 V기준 .911411805pu, 정확한 nameplate120V기준 .912086675pu다. '
        '원 source부터127요소를 따라 feeder출력1.048950805→MV l2748781.1 .939214655→37.5kVA CT hot2 .930124003→'
        '50ft/4·0Triplex 고객.911411805로 떨어진다. MV 누적하락.10973615, CT.009090652, Triplex.018712198pu다. '
        '해당 두 레그 부하1.826097/11.473903kW(PF.97)가 불균형하고 Model1은 이 전압에서 정전력 구간이다. '
        '해당 Triplex108.074A/156A와CT14.169kVA/37.5kVA는 정격 이내다. 긴 MV 경로의 전류·임피던스에 의한 누적하락과 말단 불균형이 원인이다. '
        '전체 최대혼잡 Line.tpx21459660c0의ρ1.75421678은 다른 지점이다.','',
        '원 자동 탭 제어12개는 실제 동작했다. 최저전압 경로의 FEEDER_REGA만 +2/1.0125이며125.866V로126.5±1Vband 안이고 제한에 닿지 않았다. '
        'VREG2/3/4는 이 고객 경로 상류에 없다. 다른 분기 VREG3_A는+16/1.10 상한, monitor123.7116V로125±1Vband 아래다. '
        '수렴·queue0·ControlActionsDone은 전체 전압 적격을 보장하지 않는다. '
        '이 원 정적 실행에서 capbank0a/b/c(각400kvar), capbank1a/b/c(각300kvar), capbank2a/b/c(각300kvar), '
        'capbank3(900kvar)는10개 모두 enabled, settledstate=[1]이다. 원9개CapControl을 자동운영했으며 '
        '명판합3900kvar와 실제전압에서의 AC 무효주입4073.675kvar를 구분한다. '
        '[127요소 경로](LOWEST_VOLTAGE_PATH.csv), '
        '[12개 제어 상태](LOW_VOLTAGE_REGCONTROL.csv), [원인 보고](VOLTAGE_ROOT_CAUSE_KO.md)에 상세값을 저장했다. '
        '원 배경만 .552로 한 반사실은ρ.923825088/Vmin.987290597/Vmax1.050049498이다. '
        '과거 BG.552 실험은 시간변동 AEMO부하·PV·옛AIDC2.4·Source1.04·Vreg123.5·CAPBank3OFF·추가36PCC CT로 조건이 다르다. '
        '과거 정책 성과와 현재 원 정적 실험을 섞지 않았다.','',
        '**선정의 전기적 근거와 한계.** 원 Source proximity guard와12.47kV ABC 적격성을 통과한606MV, '
        '원 CT/Triplex 고객하류1177LV의 실제 P/Q 중앙 AC 민감도를 개발4슬롯(0,9,48,75)·사전20혼잡선로에 계산했다. '
        'AIDC는 원1649UID의 활성GPU·C1·swing만으로 얻은 known-only 감소 상한(최대43.8179kW/사이트, '
        '동시 system상한342.8752kW)과PF.95의Q/P.328684105를 사용했다. 시설idle·CC4·설비확장을 flexible전력으로 세지 않았다. '
        'STA는 원 local전압/CT/Triplex 선형여유와 포트한도 교집합, 동일시점 모든20선로에 하나의P/Qvector, '
        '원6개 초기위치에서 unchanged safeETA+600초 연결지연의 도달가중치를 적용했다. '
        '6/12노출계수는 연구 heuristic이며12동시방전·route/SOC의 적격 증명이 아니다. '
        '20선로×4시점에 역효과2배벌점을 둔 입지 surrogate는 기존 최종운영 `min rho_max`를 대체하지 않는다. '
        '최종 입지는 one/two-site local exchange 결과이며 global 최적성이 아니다. B3 결과를 보고 재선정·정격튜닝하지 않았다. '
        '[선정 근거](joint_selection_v3/score_selection/SCORE_SELECTION_REPORT_KO.md), '
        '[21,396행 독립 점수검토](joint_selection_v3/selection_scores/JOINT_SCORE_REVIEW_KO.md)를 참고한다.','',
        '개발일2025-05-01은 이전 IEEE8500 분석에 이미 노출된 날짜다. 독립 미노출 평가일은 미선정/미실행이다. '
        '현재 modelable B0 reference와 Native windows 사이1024개 시작 시점 불일치가 발견되었고 QoS/WAN/재시작의 결합 dispatch를 풀지 않았다. '
        '따라서 known-job 전력은 유연성의 상한이며 실현 가능한 전체 스케줄이라고 주장하지 않는다. '
        '[원 Job 감사](FLEXIBLE_WORKLOAD_AUDIT_KO.md)와 [교통/ETA 감사](TRAFFIC_MOBILITY_AUDIT_KO.md)에 원 데이터 보존·도달 한계를 명시했다.','',
        '**저압 접속 설계와 AC 증거.** 12개STA 모두 원 고객측 split-phase120/240V `.1.2` 버스다. '
        '새 변압기/추가STA 없이 별도 소출력 인버터·절연·보호 dock을 연구 설계했다. '
        '[Schneider XW Pro6848NA 제조사 사양](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Datasheet.pdf)의 '
        'grid-sell6kW/27A,120/240V,48V배터리를 근거로 P±5kW/Q±3kvar/S6kVA 및실제VLL×27A 상한을 정의했다. '
        '60A relay는 인버터정격으로 쓰지 않았다. Q±3kvar 독립제어·차량고전압→48V DC/DC·BMS·절연·역송보호·접속승인은 전체조립품 자료가 없어 '
        'UNVERIFIED 연구 가정이다. 차량450kW/600kVA 전체는 저압에 주입하지 않는다.','',
        '각12포트×96슬롯×8정격 P/Q점=9216fixed제어 AC와 별도384automatic AC를 실행했다. '
        '9216점 모두 실제두hot/KCL/PQ, 포트전류, 원국부전압·Triplex·CTcurrent/nameplate한도를 통과했다. '
        'actualPQ 오차 최대6.844e−9, hotKCL0A다. 선정48개 bounded조합도 새 공동배치 국부AC PASS다. '
        '최초384auto글로벌기록을 보존하고 국부PCC읽기를 보강한384auto재검사도 수행했다. '
        '국부/하드웨어표본 전부PASS, 실제최대hot24.279982A, PQ오차7.432e−9이며384개tap/cap상태SHA를 저장·독립검토했다. '
        '[자동 국부 증거와 고정/자동 독립검토](joint_selection_v3/selected_port_ac/INDEPENDENT_PORT_REVIEW_KO.md)를 제공한다. '
        '이는 표본점을 검증한 것이며 연속P/Q영역·자동탭영역·6대route/SOC전체정책의 인증은 아니다. '
        '방전5kW에서 개별CT leg역송과 일부hot 전류절댓값 증가를 관측했다. hot별phasor/branch실전력이 저장되지 않아 동일hot의 직접인과까지 단정하지 않으며 모든레그 전류가 감소한다고 주장하지 않는다. '
        '원 Krön-reduced Triplex는 독립neutralampacity가 없어 재구성neutral전류만 출력했다. '
        '[포트별96슬롯 요약](joint_selection_v3/selected_port_ac/PORT_QUALIFICATION_SUMMARY.csv), '
        '[모든hot전류](joint_selection_v3/selected_port_ac/TRIPLEX_ALL_HOT_CURRENT96.csv), '
        '[순간 공동기여 반사실](joint_selection_v3/selected_response/INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv)은 '
        'B0–B3 성과 또는 가능한스케줄을 뜻하지 않는다. '
        '선정된포트는 사전상위7개Triplex혼잡선로의 직접하류가 아니다. 따라서 그선로에는 전압/상호결합의 간접제어가 주이고 '
        '국부Triplex 전류감소를 전체최대ρ개선으로 확대해석할 수 없다. 여러상위MV선로에는 AIDC·STA가 함께하류에 연결된다. '
        '[20개 선로 모두의 경로·허용전력·유한AC기여](joint_selection_v3/selected_response/ALL20_CONTROLLABILITY_KO.md)를 별도로 작성했다.','',
        '| STA | 방전5kW hot전류변화 범위(A) | 충전5kW 최대ρ | 모든8점×96 국부 | 상위CT역송 |',
        '|---|---:|---:|---|---|']
    for p in ports:
        lines.append(f"| {p['site']} | {float(p['minimum_discharge5kw_hot_current_change_A']):.3f}…{float(p['maximum_discharge5kw_hot_current_change_A']):.3f} | {float(p['maximum_charge5kw_rho']):.6f} | {p['full_box_local_grid_PASS']} | {p['reverse_service_primary_power_seen']} |")
    lines+=['','**스케일을 분리한 B0 검증.** BG는 원 정적 부하의 균일배율, GPU설비는780/975/1170, '
        '실제 Job 모집단/유연Job비율은1.0으로 유지했다. 시설PCC는 원V42 C1/대기전력/날씨/원logicalpool식을 그대로 썼다. '
        '기존780GPU case에서 시설전체소비전력193.5367–568.2575kW이며 이것이 유연Workload전력과 같지 않다. '
        'MV시설rack/cooling/전용CT실물정격은 UNVERIFIED로 남겼다. PV0,Source1.05,Vreg126.5/125, '
        '원caps와원모든선로/CT정격은12case에서 동일하다. 다음각행은96슬롯 실제AC다.','',
        '| BG | GPU scale | 전체최대ρ | Vmin | Vmax | 전압위반 node×slot | 적격 |',
        '|---:|---:|---:|---:|---:|---:|---|']
    for s in scales:lines.append(f"| {s['background_scale']} | {s['capacity_scale']} | {float(s['rho_max']):.8f} | {float(s['Vmin']):.8f} | {float(s['Vmax']):.8f} | {s['voltage_violation_cells']} | FAIL |")
    lines+=['',
        f"BG.552/780GPU 연구 기준은 전체최대ρ={float(reference['rho_max']):.9f}, Vmin={float(reference['Vmin']):.9f}, "
        f"Vmax={float(reference['Vmax']):.9f}, 전압위반1373 node×slot이다. 원모든선로·CT열제약은 이case에서 통과하지만 원전압상한을 실패한다. "
        '가장 큰ρ는 Line.tpx21459660c0이다. 0.80–0.85 목표를 강제하지 않았다. '
        '고정된 연구기준 .552/1.0은 역사적 counterfactual/최소설비확장 기준이며 B정책성과 승자가 아니다. '
        '다른날짜/부하형상/설치설계를 별도로 정당화하지 않고 적격운영case라고 선언할 근거는 없다. '
        'Fresh96슬롯 source-only 재현의6개 전류/전압/CT배열 최대오차와tap/cap상태차이는 모두0이다. '
        '[독립 스케일감사](joint_selection_v3/selected_ac/INDEPENDENT_SCALE_REVIEW_KO.md)에 모든조건/위반셀을 기록했다.','',
        '**단일 연구 snapshot과 V42 준비 상태.** '
        f'연구구성 canonicalSHA256은 `{scenario_sha}`, mappingSHA256은 `{sha(MAPPING)}`다. '
        '[STUDY_CONFIGURATION_DRAFT.json](STUDY_CONFIGURATION_DRAFT.json)은 하나의 검토용 연구 snapshot이며 '
        '[FINAL_SINGLE_SCENARIO.json](FINAL_SINGLE_SCENARIO.json)의 최종운영/Production구성은 null이다. '
        'A/M/B0–B3 인터페이스와append-onlyPCC제약이 준비되어도 현Native IEEE123/4대/고정그리드축·six-unit교통SOC·'
        'LV효율 .90×원배터리 .95=.855·source-causal windows·FULL/Compact/C3A동치·96슬롯연속affinecontrolcertificate·'
        '독립SUMOActual/Fresh·미노출평가일 및 현재전압FAIL이 해결되기 전 Production은 실행하지 않는다. '
        'A1/M1/A2/M2 실행budget/gap과sameSHA 요청만 마련했고 solver를 대체하지 않았다. '
        '[이식 보고](V42_INTEGRATION_REPORT.md), [동일SHA B0–B3 요청](COMPARISON_PLAN_BLOCKED.json), '
        '[캠페인 보존](CAMPAIGN_PRESERVATION_CHECK.json), [전체검증](FINAL_LIGHTWEIGHT_TEST_RECEIPT.json)을 함께 검토할 수 있다. '
        '검토시작의138개권위파일·44개예약작업 등록은 보존됐으나 작업도중외부RecoveryV10작업3개와CONTINUATION_V10_MANIFEST가 새로관측됐다. '
        '전체live상태가완전히동일하다고 주장하지 않으며 본작업의캠페인/예약작업쓰기는0회다. '
        '분석기준source는 시작시점de6f79로 고정했다. 종료검토에서 v42원격87480938로의진행을 관측했으며 '
        '[시작점 이후 source진행 감사](SOURCE_ADVANCE_SINCE_REVIEW.json)와 이식보고에 차이를 남긴다. '
        '새source 전체Native연결이 인증됐다고 주장하지 않는다.','',
        '각 PCC와20혼잡선로 민감도/전기적경로·허용전력·ETA기여는 '
        '[상세 위치감사](joint_selection_v3/score_selection/SELECTED_LOCATION_AUDIT_KO.md)에, '
        'Python/SVG/PNG계통도·히트맵은 같은score_selection폴더와figures에 저장했다. '
        '이전v3고정시점의루트MAIN결과는 `historical_fixed_v3_outputs/`에 보존했다. '
        '현재상대276쌍/STA/scale/line/tap/capacity루트CSV는새공동배치결과다. '
        '과거시험의약1.36%p차이를 이번정책개선수치로이전하지 않았고 B0–B3성능차이는 아직측정하지 않았다.','']
    (REPORT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf8')
    (REPORT/'README.md').write_text('''# IEEE8500 V42 결과 인덱스

현재 권위: [한국어 중간 보고](FINAL_REVIEW_KO.md), [단일 연구 snapshot](STUDY_CONFIGURATION_DRAFT.json), [운영 미선정/승격 차단](FINAL_SINGLE_SCENARIO.json).

공동 선정 current stage는 `joint_selection_v3/score_selection/`이며 mapping SHA는 바뀌지 않았다. 모든 276쌍/552축은 source/primaryproxy좌표에서 PASS다. 원 지리/하드웨어 실물/continuous control영역은 UNVERIFIED다. 12스케일 모두 원 global voltage 제약 FAIL이며 B1–B3 Native는0회다.

루트 `FINAL_STA_MAPPING`, `RELATIVE_POSITION_AUDIT`, `SCALE_SCREENING`, `LINE_LOADING_REPORT`, `REGCONTROL_TAP_VALIDATION`, `AIDC_CAPACITY_AUDIT`는 현재 공동 배치 결과다. 이전 동일 이름 파일은 `historical_fixed_v3_outputs/`에 byte 보존했다.

루트 `PREREGISTRATION.json`, `GEOMETRY_STATUS`, `DIRECTION_ROOT_CAUSE_AUDIT`, `GEOMETRY_LV_REPORT`와 `diagnostics/`는 **사용자가 AIDC v3 고정을 해제하기 전** 독립 진단이다. `joint_selection_v2/`는 이후 all-MV geometric witness/개발 민감도이며 최종 입지가 아니다. 현재 절차는 v3 `GEOMETRY_PREREGISTRATION`, `SCORING_PREREGISTRATION`, `selection_scores/PREREGISTRATION`, `selected_ac/PREREGISTRATION`, `selected_port_ac/PREREGISTRATION`에 각각 실행 전 동결됐다. 원 기록을 사후 수정한 pre-registration이라고 주장하지 않는다.

루트 `SENSITIVITY_RESULTS.csv`는 BG1 이전 진단이며 현재 .552 전체 후보 응답은 `joint_selection_v3/mv_sensitivity/`와 `lv_sensitivity/`에 있다. Source series Reactor 누락 경로 메타데이터의 사후 정정은 `PATH_METADATA_CORRECTION.json`으로 수치불변을 증명한다. 현재 root 보고 CSV의 lineρ는 전원 방향 parent 단자 활성상 기준이며 둘다단자·CT권선·원모든노드 fullarrays는 selected_ac/bg0p552_gpu1p0/AC_96.npz 및 AC_AXES.json에 있다.

모든 발전·부하·도체·변압기 sourcebyte/962개 V42파일은 보존했다. `COMPARISON_PLAN_BLOCKED.json`은 동일SHA arm요청만 구성한다. 독립 미노출 평가일과 Production은 아직 없으며 `execute_production`은 항상 차단된다.
''',encoding='utf8')


if __name__=='__main__':assemble()
