"""Independent archived 12-case AC constraint audit; no AC or Native calls."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .common import ROOT,DATA,REPORT,read,write,receipt,sha
from .geometry import read_csv

FOLDER=REPORT/'joint_selection_v3/selected_ac'


def close(actual,expected,label):
    error=abs(float(actual)-float(expected))
    if error>1e-10:raise ValueError('SELECTED_AC_SUMMARY_MISMATCH:'+label)
    return error


def review():
    policy=read(FOLDER/'PREREGISTRATION.json');cases=read_csv(FOLDER/'SCALE_SCREENING.csv')
    mapping=REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv'
    if sha(mapping)!=policy['mapping']['sha256']:raise ValueError('AC_MAPPING_CHANGED_AFTER_PREREGISTRATION')
    assigned=read_csv(mapping)
    if len(assigned)!=24 or len({r['candidate_bus'] for r in assigned})!=24:
        raise ValueError('SELECTED_24_DISTINCT_PORTS_REQUIRED')
    inventory=read(REPORT/'ORIGINAL_FEEDER_INVENTORY.json')
    for name,expected in inventory['source_sha256'].items():
        if sha(DATA/'feeder'/name)!=expected:raise ValueError('ORIGINAL_FEEDER_BYTE_DRIFT')
    combinations={(float(r['background_scale']),float(r['capacity_scale'])) for r in cases}
    if len(cases)!=12 or combinations!={(b,c) for b in (1.,.8,.65,.552) for c in (1.,1.25,1.5)}:
        raise ValueError('PREDEFINED_12_SCALE_CASES_REQUIRED')
    source_nodes={f"{bus['bus']}.{node}" for bus in inventory['buses'] for node in bus['nodes']}
    caps={r['name'] for r in inventory['capacitors']}
    controlled={r['transformer'] for r in inventory['regcontrols']}
    records=[];maxerror=0.;inputs=[Path(__file__),ROOT/'ieee8500_v42/selected_case_v3.py',mapping,
        FOLDER/'PREREGISTRATION.json',FOLDER/'SCALE_SCREENING.csv',FOLDER/'RECEIPT.json']
    for case in cases:
        tag=case['case'];folder=FOLDER/tag
        slots=read_csv(folder/'SLOT_ELECTRICAL_SUMMARY.csv')
        lines=read_csv(folder/'ALL_LINE_96_SLOT_MAX.csv')
        nodes=read_csv(folder/'ALL_NODE_96_SLOT_MIN_MAX.csv')
        taps=read_csv(folder/'REGCONTROL_TAPS.csv');states=read(folder/'CONTROL_STATES.json')
        if len(slots)!=96 or {int(s['slot']) for s in slots}!=set(range(96)):
            raise ValueError('FULL_96_SLOT_AC_COVERAGE_REQUIRED:'+tag)
        if any(s['converged']!='True' or s['control_actions_done']!='True' or int(s['control_queue_size'])!=0 for s in slots):
            raise ValueError('AC_ORIGINAL_CONTROLS_NOT_SETTLED:'+tag)
        if set(r['node'] for r in nodes)!=source_nodes:raise ValueError('ORIGINAL_ALL_NODE_AXIS_COVERAGE_REQUIRED')
        if len(lines)!=sum(r['ncond']*r['nterm'] for r in inventory['lines']):
            raise ValueError('ALL_ORIGINAL_LINE_TERMINAL_CONDUCTOR_AXES_REQUIRED')
        source_lines={r['element']:r for r in inventory['lines']}
        for r in lines:
            original=source_lines[r['element']]
            if float(r['normal_amps'])!=original['normal_amps']:raise ValueError('ORIGINAL_LINE_NORMALAMPS_CHANGED')
            expected_mask=original['enabled'] and int(r['node'])>0 and int(r['terminal'])==original['parent_terminal']
            if (r['objective_included']=='True')!=expected_mask:raise ValueError('CANONICAL_SOURCE_PARENT_MASK_CHANGED')
        peak=max(slots,key=lambda s:float(s['rho_max']))
        canonicalmax=max(float(r['maximum_96slot_rho']) for r in lines if r['objective_included']=='True')
        maxerror=max(maxerror,close(case['rho_max'],canonicalmax,tag+' rho line-array'),
            close(case['rho_max'],peak['rho_max'],tag+' rho slot-summary'),
            close(case['Vmin'],min(float(r['minimum_96slot_pu']) for r in nodes),tag+' allnode Vmin'),
            close(case['Vmax'],max(float(r['maximum_96slot_pu']) for r in nodes),tag+' allnode Vmax'))
        if int(case['peak_slot'])!=int(peak['slot']) or case['binding_line']!=peak['binding_line']:
            raise ValueError('ORIGINAL_CANONICAL_PEAK_IDENTITY_MISMATCH')
        with np.load(folder/'ALL_TRANSFORMER_96_SLOT_MAX.npz',allow_pickle=False) as tx:
            maxerror=max(maxerror,close(case['transformer_current_rho_max'],tx['current_rho'].max(),tag+' CTcurrent'),
                close(case['transformer_nameplate_kva_rho_max'],tx['nameplate_kva_rho'].max(),tag+' CTnameplate'))
        violation_names=('voltage_violation_cells','line_overload_conductor_cells',
            'transformer_overload_conductor_cells','transformer_nameplate_overload_winding_cells')
        totals={name:sum(int(s[name]) for s in slots) for name in violation_names}
        if any(int(case[name])!=totals[name] for name in violation_names):raise ValueError('VIOLATION_COUNT_AGGREGATE_MISMATCH')
        expected_pass=all(count==0 for count in totals.values())
        if (case['AC_constraints_pass']=='True')!=expected_pass:raise ValueError('GLOBAL_AC_QUALIFICATION_FLAG_MISMATCH')
        if expected_pass or totals['voltage_violation_cells']==0 or float(case['Vmax'])<=1.05:
            raise ValueError('ALL_12_REPORTED_GLOBAL_FAILS_MUST_BE_RETAINED')
        if case['original_source_identity']!='True' or float(case['AIDC_PQ_readback_error'])>1e-6:
            raise ValueError('AIDC_READBACK_OR_SOURCE_IDENTITY_FAILED')
        if case['production_ready']!='False' or int(case['Native_calls'])!=0:raise ValueError('UNAUTHORIZED_PRODUCTION_OR_NATIVE_CLAIM')
        if len(taps)!=96*12 or any(r['enabled']!='True' or r['control_actions_done']!='True' or
            float(r['original_Vreg'])!=(126.5 if r['name'].startswith('feeder_reg') else 125.) for r in taps):
            raise ValueError('ORIGINAL_12_REGCONTROL_POLICY_CHANGED')
        if len(states)!=96 or any(set(s['taps'])!=controlled or set(s['capacitors'])!=caps for s in states):
            raise ValueError('ALL_ORIGINAL_CONTROL_STATE_AXES_REQUIRED')
        if int(case['installed_GPU'])!=int(780*float(case['capacity_scale'])) or float(case['workload_scale'])!=1.:
            raise ValueError('GPU_CAPACITY_ONLY_EXPANSION_CONTRACT_FAILED')
        records.append(dict(case=tag,background_scale=float(case['background_scale']),capacity_scale=float(case['capacity_scale']),
            slots=96,canonical_rho_max=float(case['rho_max']),Vmin=float(case['Vmin']),Vmax=float(case['Vmax']),
            **totals,canonical_and_allterminal_thermal_pass=totals['line_overload_conductor_cells']==0,
            original_CT_current_and_nameplate_pass=totals['transformer_overload_conductor_cells']==0 and totals['transformer_nameplate_overload_winding_cells']==0,
            original_global_voltage_pass=False,AC_constraints_pass=False,simulation_design_authorized=True,
            production_ready=False))
        inputs.extend(folder/name for name in ('SLOT_ELECTRICAL_SUMMARY.csv','ALL_LINE_96_SLOT_MAX.csv',
            'ALL_NODE_96_SLOT_MIN_MAX.csv','ALL_TRANSFORMER_96_SLOT_MAX.npz','REGCONTROL_TAPS.csv','CONTROL_STATES.json','AC_RECEIPT.json'))
    reference=FOLDER/'bg0p552_gpu1p0'
    axis=read(reference/'AC_AXES.json')
    if set(axis['nodes'])!=source_nodes:raise ValueError('REFERENCE_RAW_NODE_AXES_CHANGED')
    with np.load(reference/'AC_96.npz',allow_pickle=False) as raw:
        if raw['line_rho'].shape!=(96,len(axis['lines'])) or raw['node_voltage_pu'].shape!=(96,len(axis['nodes'])):
            raise ValueError('REFERENCE_RAW_96_AC_AXIS_SHAPE_MISMATCH')
        mask=np.array(axis['objective_mask'],bool)
        rawrho=float(raw['line_rho'][:,mask].max());rawvmin=float(raw['node_voltage_pu'].min());rawvmax=float(raw['node_voltage_pu'].max())
        selected=next(r for r in records if r['case']=='bg0p552_gpu1p0')
        maxerror=max(maxerror,close(rawrho,selected['canonical_rho_max'],'raw reference rho'),
            close(rawvmin,selected['Vmin'],'raw reference Vmin'),close(rawvmax,selected['Vmax'],'raw reference Vmax'))
    inputs.extend(reference/name for name in ('AC_96.npz','AC_AXES.json'))
    report=dict(status='PASS_INDEPENDENT_ARCHIVED_12_CASE_CONSTRAINT_AUDIT_ALL_GLOBAL_FAIL',
        cases=12,slots=1152,case_records=records,maximum_aggregate_numeric_error=maxerror,
        all12_cases_global_AC_FAIL_preserved=True,feasible_case_count=0,production_ready=False,
        original_source_SHA_unchanged=True,original_minrho_parentphase_contract_preserved=True,
        all96_controls_settled_and_original_Vreg_policy_preserved=True,
        mapping_SHA_matches_pre_AC_preregistration=True,reference_choice_is_preregistered_counterfactual=True,
        reference_bg0552_gpu1p0_is_not_operationally_accepted=True,
        remaining=['All12 source/control cases have global voltage failures; smallest rho is not global AC feasibility',
            'Zero-MESS B0 screening is not full finite port5kW/3kvar or optimized A/M dispatch',
            'Static BG scales are declared counterfactuals, not measured daily demand',
            'Primaryproxy geometry and modeled port design do not certify field accessibility/protection'],
        Native_calls=0,AC_solves=0,full_model_builds=0,
        inputs={str(p.relative_to(ROOT)):receipt(p) for p in inputs})
    write(FOLDER/'INDEPENDENT_SCALE_REVIEW.json',report)
    rows=['# 선정 V3 사례: 12개 스케일 AC 제약 독립 검토','',
        '기존 산출물만 읽어 12개 사전 고정 BG/GPU 조합, 1,152개 실제 AC 슬롯을 독립 집계했다. 새 AC·Native·전체 모형 실행은 0회다. **12개 모두 원 전역 AC 제약 FAIL**이며 적격 사례 수는 0이다. 낮은 선로 ρ를 전압 적격으로 바꾸거나 실패한 연구 기준을 최종 운영 B0로 선언하지 않았다.','',
        '| BG | GPU scale | 최대 canonical ρ | Vmin | Vmax | 전압 위반 셀 | 선로 과부하 셀 | 전역 |',
        '|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in records:rows.append(f"| {r['background_scale']} | {r['capacity_scale']} | {r['canonical_rho_max']:.9f} | {r['Vmin']:.9f} | {r['Vmax']:.9f} | {r['voltage_violation_cells']} | {r['line_overload_conductor_cells']} | FAIL |")
    rows.extend(['','각 사례의 96개 슬롯 수렴·원 제어 정착·빈 제어 큐, 원 12개 조정기 Vreg와 전체 탭/커패시터 상태 축, AIDC 실제 P/Q 읽기 오차≤1e-6을 확인했다. 원 3,703개 선로의 모든 단자/도체와 모든 원 노드, 원 변압기 정상 전류 및 각 권선 엄격 nameplate kVA를 집계했다. 선로 정격과 canonical 소스 방향 단자/활선 마스크는 원 inventory와 일치하며 원 feeder 바이트 SHA가 모두 같다. 원 코드가 node>0 마스크를 쓰는 이 자료의 선로 노드 라벨은 1/2/3뿐이다.','',
        'BG .552의 세 GPU 스케일은 선로·CT 열제약을 통과하지만 모두 과전압을 가진다. .552/1.0 기준은 사전 등록된 역사적 counterfactual이며 ρ=.921957508, Vmax=1.052725879로 최종 운영 자격이 없다. 정적 BG 비율을 관측된 당일 고객 부하로 해석하거나 .80–.85 ρ 목표에 맞춘 승자로 선정하지 않았다.','',
        '사전 등록한 24개 AIDC/STA mapping SHA가 실제 입력과 같다. GPU 스케일만780/975/1170로 변하며 workload_scale=1이고 source/Vreg/원 정격을 낮추지 않았다. 이 검토는 zero-MESS B0 결과이며 실제 포트 유한±5kW/±3kvar·복합 운전, 전체 A/M QoS/WAN/routing/SoC 최적화와 독립 평가일 성능을 인증하지 않는다.','',
        f'전체 집계와 원 기준96슬롯 rawNPZ 비교의 최대 수치 오차는 {maxerror:.3g}이다. 각 입력 SHA와 제약 별 결과는 `INDEPENDENT_SCALE_REVIEW.json`에 있다. 재현은 `python -B -m ieee8500_v42.review_selected_ac_v3`이며 추가 AC를 수행하지 않는다.',''])
    (FOLDER/'INDEPENDENT_SCALE_REVIEW_KO.md').write_text('\n'.join(rows),encoding='utf8')
    return report


if __name__=='__main__':print(review()['status'])
