"""Generate required review tables and Korean source/physical conclusions."""
import shutil
import numpy as np
import pandas as pd
from .common import *


def md(name,text):
    (REPORT/name).write_text(text.strip()+'\n',encoding='utf-8')


def case(tag):return read(REPORT/'ac'/tag/'RECEIPT.json')


def run():
    authority=read(REPORT/'SOURCE_AUTHORITY.json');inputs=read(REPORT/'PLANNING_INPUT_FREEZE.json')
    actual_input=read(REPORT/'ACTUAL_EXOGENOUS_AUDIT.json')
    original=case('STATIC_PR193_P0');plan=case('FINAL_B0_PLANNING');actual=case('FINAL_B0_ACTUAL')
    assert plan['hard_constraints_PASS'] and actual['hard_constraints_PASS']
    tags=[p.name for p in sorted((REPORT/'ac').iterdir()) if (p/'RECEIPT.json').exists()]
    comparison=[];physical=[];controls=[]
    for tag in tags:
        r=case(tag)
        comparison.append({k:r.get(k,'') for k in ('stage','policy','source','static','PV_connected','rho_max',
            'Primary_rho_max','Triplex_rho_max','Vmin','Vmax','voltage_violation_cells','full_line_overload_cells',
            'transformer_current_overload_cells','transformer_nameplate_overload_cells','binding_line','binding_local_node',
            'peak_slot','Triplex_binding_slots','Primary_binding_slots','binding_line_changes','hard_constraints_PASS')})
        physical.append(dict(stage=tag,policy=r['policy'],scope='all8531nodes/all3698activeoriginalLines/bothends/all1190transformers',
            voltage_band='0.95..1.05',all96_voltage_PASS=r['voltage_violation_cells']==0,
            line_all_terminal_PASS=r['full_line_overload_cells']==0,
            CT_current_PASS=r['transformer_current_overload_cells']==0,
            CT_original_nameplate_PASS=r['transformer_nameplate_overload_cells']==0,
            original_DSS_identity=r['all_originals']['original_DSS_byte_identity'],
            original_ratings=r['all_originals']['all_original_ratings'],**{k:r[k] for k in (
            'rho_max','full_both_terminal_conductor_rho_max','transformer_current_rho_max',
            'transformer_nameplate_kva_rho_max','Vmin','Vmax','voltage_violation_cells','hard_constraints_PASS')}))
        controls+=rows(REPORT/'ac'/tag/'CONTROL_STATES_96.csv')
    table(REPORT/'TRIPLEX_PRIMARY_CONGESTION_COMPARISON.csv',comparison)
    table(REPORT/'PHYSICAL_CONSTRAINT_AUDIT.csv',physical)
    table(REPORT/'REGCONTROL_CAPCONTROL_STATE_96.csv',controls)
    table(REPORT/'VOLTAGE_CONTROL_POLICY_COMPARISON.csv',[case('POLICY_'+p) for p in ('P0','P1','P2','P3')]+[
        case('EMERGENCY_POLICY_P4'),case('EMERGENCY_POLICY_P5')])
    shutil.copyfile(REPORT/'ac/FINAL_B0_PLANNING/SLOTS.csv',REPORT/'B0_PLANNING_AC_96.csv')
    table(REPORT/'B0_ACTUAL_FRESH_AC_96.csv',rows(REPORT/'ac/FINAL_B0_ACTUAL/SLOTS.csv')+rows(REPORT/'ac/FINAL_B0_ACTUAL_FRESH/SLOTS.csv'))
    table(REPORT/'BACKGROUND_LOAD_96SLOT_AUDIT.csv',rows(REPORT/'ac/FINAL_B0_PLANNING/BACKGROUND_LOAD_AUDIT.csv')+rows(REPORT/'ac/FINAL_B0_ACTUAL/BACKGROUND_LOAD_AUDIT.csv'))
    table(REPORT/'TOP20_LINE_LOADING_96.csv',rows(REPORT/'ac/FINAL_B0_PLANNING/TOP20_LINES_96.csv')+rows(REPORT/'ac/FINAL_B0_ACTUAL/TOP20_LINES_96.csv'))
    # Preserve the exact pre-emergency P3 derivative CSV before publishing the
    # required root table as a view of the final P5 point.
    prior=REPORT/'sensitivity/P3_FIXED_TAP_ALL96.csv'
    if not prior.exists():shutil.copyfile(REPORT/'PCC_PQ_CONTROLLABILITY.csv',prior)
    old_receipt=read(REPORT/'sensitivity/RECEIPT.json')
    assert old_receipt.get('differential_csv',{'sha256':sha(prior)})['sha256']==sha(prior)
    old_receipt['differential_csv']=receipt(prior)
    write(REPORT/'sensitivity/RECEIPT.json',old_receipt)
    shutil.copyfile(REPORT/'FINAL_PCC_PQ_CONTROLLABILITY.csv',REPORT/'PCC_PQ_CONTROLLABILITY.csv')
    differential=pd.read_csv(REPORT/'FINAL_PCC_PQ_CONTROLLABILITY.csv')
    endpoints=pd.read_csv(REPORT/'final_sensitivity/AUTOMATIC_BOUNDED_ENDPOINTS.csv')
    peak_path=REPORT/'final_peak_sensitivity/AUTOMATIC_BOUNDED_ENDPOINTS.csv'
    if peak_path.exists():
        endpoints=pd.concat([endpoints,pd.read_csv(peak_path)],ignore_index=True)
    probe_slots=','.join(map(str,sorted(endpoints.slot.unique())))
    line='Line.tpx21459660c0';d=differential[differential.line==line];f=endpoints[endpoints.target_line==line]
    sensitivity=[]
    for site,g in d.groupby('PCC',sort=True):
        finite=f[f.PCC==site]
        sensitivity.append(dict(PCC=site,bus=g.bus.iloc[0],direct_downstream=bool(g.direct_downstream.any()),
            d_rho_d_P_min=g.d_rho_d_consumption_kw.min(),d_rho_d_P_max=g.d_rho_d_consumption_kw.max(),
            d_rho_d_Q_min=g.d_rho_d_consumption_kvar.min(),d_rho_d_Q_max=g.d_rho_d_consumption_kvar.max(),
            physical_P_reduction_bound_max_kw=g.P_reduction_upper_bound_kw.max(),
            fixed_tap_linear_coupled_relief_rho_max=g.linear_coupled_P_reduction_relief_rho.max(),
            automatic_sampled_relief_min=finite.target_relief_rho.min(),automatic_sampled_relief_max=finite.target_relief_rho.max(),
            automatic_test_slots=probe_slots,dispatch_certified=False))
    table(REPORT/'PCC_BINDING_LINE_SUMMARY.csv',sensitivity)
    top=[]
    for name,g in differential.groupby('line'):
        finite=endpoints[endpoints.target_line==name]
        top.append(dict(line=name,base_max_rho=g.base_rho.max(),group=g.group.iloc[0],
            directly_downstream_PCCs=','.join(sorted(g[g.direct_downstream].PCC.unique())),
            AIDC_linear_known_bound_relief_rho=max(g[g.PCC.str.startswith('AIDC')].linear_coupled_P_reduction_relief_rho),
            isolated_automatic_sampled_relief_rho_max=finite.target_relief_rho.max(),
            isolated_automatic_sampled_relief_rho_min=finite.target_relief_rho.min(),
            changed_global_binding_lines=','.join(sorted(finite.binding_line.unique())),dispatch_certified=False))
    table(REPORT/'TOP20_CONTROLLABILITY_SUMMARY.csv',sorted(top,key=lambda r:-r['base_max_rho']))
    max_a=float(f[f.PCC.str.startswith('AIDC')].target_relief_rho.max())
    max_s=float(f[f.PCC.str.startswith('STA')].target_relief_rho.max())
    six=f[f.PCC=='SIX_INITIAL_PORTS']
    config=dict(schema='IEEE8500_V42_AEMO_SINGLE_RESEARCH_DRAFT_V1',day=DAY,unseen_day=False,
        status='B0_AC_PHYSICAL_PASS_PRODUCTION_BLOCKED',selected_research_voltage_policy='P5',
        Production_configuration_frozen=False,Production_eligible=False,objective='original all-active-Line parent-terminal min rho_max',
        mapping_sha256=MAPPING_SHA,AIDC=12,STA=12,MESS=6,background_scale=.552,installed_GPU=780,
        population_multiplier=1,known_Planning_jobs=1649,Actual_jobs=2498,
        flexible_population_and_IT_C1='original V42; no extra jobs or GPU multiplier',
        original_DSS_byte_identity=True,original_ratings_and_voltage_band=[.95,1.05],
        Source_pu=1.04,all12_RegControl_Vreg_V=123.5,all_original_RegControl_bands_limits_delays=True,
        CAPBank3='zero switched step, original object enabled; no CapControl existed',
        all9_CapControl_original_logic_threshold_delays=True,CAPBank0_override_Vmax_V=7740,
        PV_objects=2354,research_installed_PV_kw=inputs['source_PV_capacity_kw'],PV_kept_Planning_Actual=True,
        LV_port=dict(P_abs_kw=5,Q_abs_kvar=3,S_kva=6,I_each_hot_A=27),
        fleet_configuration=read(PR193/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json'),
        Planning_input_sha=sha(DATA/'derived/PLANNING_INPUTS.npz'),Actual_input_sha=sha(DATA/'derived/ACTUAL_INPUTS.npz'),
        source_authorities=dict(V42=LATEST_SHA,PR193=PR193_SHA,PR62=PR62_SHA),
        original_source_file_count=31,all96_Planning_Actual_Fresh_hard_PASS=True,
        validation_rejection='P4 passedPlanning; rejectedActual1.0500161256pu. Next already registered P5 validated; no new setpoint fitting',
        causality=dict(Actual_values_in_Planning=0,GFS_publication_at_cutoff='UNVERIFIED',
                       frozen_annual_normalizer_availability='UNVERIFIED',CC4_Runtime_fit_ingestion='UNVERIFIED'),
        unresolved=['field geolocation/access/protection and LV vehicle interface',
            'full as-of-D1 calibration/GFS publication evidence','six-unit Native axis/location-efficiency SOC and ActualSUMO linkage',
            'continuous automatic-control P/Q certificate and full Native/C3A equivalence'],
        B1_B2_B3_Production_Native_calls=0,global_optimality_claim=False)
    config['canonical_research_draft_sha256']=digest(config)
    write(REPORT/'SINGLE_SCENARIO_DRAFT.json',config)
    md('SOURCE_AUTHORITY.md',f'''# Source authority

현재 V42: `{LATEST_SHA}`. 전기·배치 기준 PR193: `{PR193_SHA}`. 과거 PR62: `{PR62_SHA}`.
원본 V42 Python/HTML {authority['original_core_source_count']}개와 PR193 봉인 자료 {authority['PR193_sealed_files_byte_verified']}개는 byte identity 검증했다.
시작 시 최신 V42와 기존 core 사이 변화는 신규 파일 {authority['latest_only_additions_count']}개였으며 기존 input/reference/queue/Actual/RegControl 구현은 동일했다.
원본 IEEE8500 DSS31개, 3703 Lines(활성3698), 1190 Transformers, 2354원본 Loads, 8531노드 및 교통24개 매핑 SHA `{MAPPING_SHA}`를 보존했다.

PR62는 PV의 원본 고객 버스·상·정격 배분 방법과 전압 overlay의 역사적 근거다. 해당 overlay는 **모든12RegControl Vreg123.5**를 적용했다. P3의 feeder-only 변경과 같다고 주장하지 않는다.
PR62 rule의 PV_alpha=.5와 당시 실제 dispatch BG=.552 사이 불일치를 발견했다. 과거 dispatch는 사용하지 않고, 설치비율0.11852937486188635만 현재 V42 solar normalization으로 구동했다.
과거 알고리즘·차량 정격·AIDC 정격·좌표·스케줄은 복사 실행하지 않았다.

정확한 경로·SHA·blob은 `SOURCE_AUTHORITY.json`, 원자료·추출행은 `ieee8500_v42_aemo/data/sources/`, 최종 외부 캠페인 비교는 `CAMPAIGN_PRESERVATION.json`에 기록한다.
생성물은 새 worktree만 기록하며 기존 live소스/ledger/워커/예약 작업을 편집하거나 중단하지 않았다.
''')
    md('AUSTRALIAN_DATA_BINDING_REPORT.md',f'''# 호주 원자료 연결과 한계

2025-05-01은 이미 사용한 개발일이다. 96개 15분 구간은 고정 AEST(UTC+10), 00:00시작→다음날00:00종료다. grid자료는 interval ending, 날씨·GPU·전력입력은 대응 구간 시작을 사용한다.

* Demand Forecast: VIC1 PREDISPATCHREGIONSUM, 48개30분 MW 평균을 두 번 반복. issue Apr30 17:32:39, cutoff18:00. 지역 에너지 {inputs['raw_forecast']['demand']['original_energy_MWh']:.6f} MWh 보존.
* Rooftop Forecast: 48개30분 POWERMEAN, issue18:00. 동일 interval ending repeat2. Rooftop Actual은 MEASUREMENT의 지역 추정 출력이며 모든 고객 실측이라고 주장하지 않는다.
* Demand Actual: DISPATCHREGIONSUM INTERVENTION0의 288개5분 TOTALDEMAND를 세 개씩 평균. piecewise-constant interval power 해석으로 {actual_input['new_demand_energy_MWh']:.6f} MWh 보존. 기존 V42 15분 말점 선택은 {actual_input['old_minus_energy_preserved_MWh']:.6f} MWh 차이가 있어 새 adapter만 수정했다. 원본 producer·raw는 보존했다.
* GFS96슬롯은 Planning C1, NOAA 시간별 관측은 기존 시간 선형 보간으로 Actual C1에 각각 연결했다. GFS init16:00는 cutoff 전이지만 실제 publication 수신시각 증거는 없다.
* Kestrel Planning1649 known UID, Actual2498 UID는 원본731MB archive SHA `{read(REPORT/'ACTUAL_Kestrel_QUEUE_AUDIT.json')['raw_archive']['sha256']}`에서 submit/start/end/duration/requestedGPU를 직접 대조했다. Actual은 private service truth와 causal FCFS queue이며 duration/end를 controller에 미리 전달하지 않는다. GPU780/rack/CC4/backlog와 C1/PF.95를 유지했다.

원본2354 Load 중48Fixed는 `Status=fixed` 그대로다. OpenDSS Fixed는 전역/shape multiplier를 무시한다. 원본 P/Q에 연구BG=.552를 한 번 적용한 뒤 시계열에서는 고정한다. 2306Variable만 동일한 gross factor를 원본P/Q에 직접 적용하며 loadmult=1로 이중 배율을 막았다. 각 고객의 PF·버스·상·model1의 전압 의존성은 유지했다. Fixed/Variable의 시간변동 차이로 집계 상비율은 달라질 수 있으며 고유 상 연결과 각 상 내부 배분은 보존했다.

V42의 frozen constants는 P95=7100.2615MW, annualmax=9490.53MW, alpha=.7481417265421424, PVmax=4021.226MW다.
`solar=alpha*regional_PV/PVmax`, `gross=alpha*regional_demand/P95 + PV_ratio*solar`.
Variable P/Q=`originalP/Q*.552*gross`; Fixed P/Q=`originalP/Q*.552`.
IEEE8500 native10773.17kW에 PR62 원본부하 비율을 적용한2354개 연구Generator의 설치용량은 {inputs['source_PV_capacity_kw']:.6f}kW/kVA다. 원본에는 PV0개였다. 각 PV는 해당 원본 고객 hot/120V/conn에 접속하며 Q명령0, Planning/Actual 설치용량 동일, 시계열은 Forecast/Actual로 분리한다. BG를 PV에 중복 적용하지 않는다.
원본Generator model1과 원본 Vmin/Vmax를 보존했으므로 임계 밖에서는 실제 P가 전압의 제곱에 따라 변한다. AC 실제 출력·전력보존은 nominalP와 구분해 검산했다.

이는 **Synthetic Load Mapping**이다. 지역MW를 직접 주입하거나 개별 고객 실측을 재구성하지 않았다. IEEE123의 실측 cluster/Q변동을 IEEE8500에 무단 이식하지 않았다.
실제 forecasting 값은 cutoff검사·source분리로 Planning에 Actual0회 전달했지만, inherited annual-normalizer/CC4/Runtime calibration의 D-1 가용성 및 GFS publication은 UNVERIFIED다. 전체 pipeline 미래정보누수0 인증은 하지 않으며 Production 승격을 차단한다.
SCATS/SUMO 교통24ID와 Planning ETA/route자료는 PR193 감사 자료 및 SHA로 보존한다. B0 MESS주입0이며, 6대 Actual/SUMO·Native/SOC/location효율 통합은 UNVERIFIED다.

정확한 경로/SHA/원래 해상도/단위/시간범위는 `PLANNING_INPUT_FREEZE.json`, `ACTUAL_EXOGENOUS_AUDIT.json`, `ACTUAL_Kestrel_QUEUE_AUDIT.json`, `AEMO_PV_96SLOT_ALIGNMENT.csv`에 있다.
Fixed의 공식 의미: [OpenDSS Load properties](https://opendss.epri.com/Properties7.html). 제어 방식은 [DSS-CAPI RegControl](https://github.com/dss-extensions/dss_capi/blob/0.14.5/src/Controls/RegControl.pas), [CapControl](https://github.com/dss-extensions/dss_capi/blob/0.14.5/src/Controls/CapControl.pas) 소스를 대조했다.
''')
    from .review_ko import render
    md('FINAL_REVIEW_KO.md',render(original,plan,actual,max_a,max_s,six))
    md('REPRODUCE.md','''# 재현

Python3.11, numpy1.26.4, scipy1.14.1, pandas2.2.3, pyarrow, matplotlib, OpenDSSDirect0.9.4/DSS-Python0.15.7/DSS-CAPI0.14.5.
프로젝트root에서 다음을 실행한다. 기존외부캠페인에쓰는명령은없다.

```powershell
python -B -m ieee8500_v42_aemo.data_binding planning
python -B -m ieee8500_v42_aemo.data_binding actual
python -B -m ieee8500_v42_aemo.run_b0
python -B -m ieee8500_v42_aemo.emergency diagnose
python -B -m ieee8500_v42_aemo.emergency policies
python -B -m ieee8500_v42_aemo.emergency final
python -B -m ieee8500_v42_aemo.sensitivity --final
python -B -m ieee8500_v42_aemo.sensitivity --final --primary
python -B -m ieee8500_v42_aemo.sensitivity --final --peak
python -B -m ieee8500_v42_aemo.verify
python -B -m ieee8500_v42_aemo.report
python -B -m ieee8500_v42_aemo.figures
python -B -m unittest discover -s tests/ieee8500_v42_aemo -v
```

Fullbinding은동일SHA의원본forecastarchives와Kestrel731MBarchive및기존V42bundle경로가필요하다. raw경로는sourcefreezeJSON의content-hash resolver로찾는다. 선택된48/288행과private2498UID projection 및derivedNPZ는저장되어있어AC/CSV/그림/독립검산은그입력으로재현할수있다. 원본Kestrel전행join재실행없이sourceauthority검증을했다고주장하지말것.
OpenDSS sourceinit은매day/stage별독립,96snapshot은연속auto/static정착이다. 원본지연/deadtime을보존하지만각15분slot내정착후의quasi-staticAC이다. subslot전압과실제switch-cyclestress인증은아니다.
일일top20의양단/모든도체및endpoint전압complexphasor를보관하고모든원본노드/선로/CT하드제약배열은완전히보관한다. 나머지fullcomplexphasor는재실행으로생성한다.
현재CAMPAIGNBEFORE/AFTER는이실행의read-only스냅샷이다. 다른환경에서라이브캠페인보존실험을동일상태로재현한다고주장하지않는다.
''')
    write(REPORT/'REPORT_GENERATION_RECEIPT.json',dict(required_tables_generated=True,
        final_research_draft_sha=config['canonical_research_draft_sha256'],B0_AC_physical_PASS=True,
        Production_eligible=False,P3_derivative_preserved=receipt(prior),final_P5_derivative=receipt(REPORT/'PCC_PQ_CONTROLLABILITY.csv')))
    print('Korean report and16 required artifacts complete; B0ACPASS, ProductionBLOCKED',flush=True)


if __name__=='__main__':run()
