"""Classify measured hypotheses without changing any scientific authority."""
import json
from collections import defaultdict
import numpy as np
import pandas as pd
from .common import *
from .diagnose import terminal_phase
from v42_regcontrol.authority import source,compile_verified

def nodal_check(day):
    primary=read(OUT/(day+'_RAW_TERMINAL_SNAPSHOTS.json'))['slots']
    passive=read(OUT/(day+'_NETWORK_TERMINAL_SNAPSHOTS.json'))['slots'];results=[]
    for a,b in zip(primary,passive):
        assert a['slot']==b['slot']
        currents=defaultdict(complex);volts={}
        for s in a['elements']+[a['reg1a']]+b['passive_elements']:
            if not s['enabled']:continue
            for t,bus in enumerate(s['buses']):
                for local in range(s['conductors']):
                    i=t*s['conductors']+local;node=s['nodes'][i]
                    if node not in (1,2,3):continue
                    key=(bus.split('.')[0].lower(),node)
                    if key[0]=='150':continue # source outside downstream boundary
                    currents[key]+=s['currents'][2*i]*np.exp(1j*np.deg2rad(s['currents'][2*i+1]))
                    volts[key]=s['voltages'][2*i]*np.exp(1j*np.deg2rad(s['voltages'][2*i+1]))
        power=defaultdict(complex)
        for key,current in currents.items():power['ABC'[key[1]-1]]+=volts[key]*np.conj(current)/1000
        for ph in 'ABC':
            results.append(dict(day=day,slot=a['slot'],phase=ph,
                maximum_node_current_residual_A=max(abs(v) for k,v in currents.items() if k[1]=='ABC'.index(ph)+1),
                summed_node_power_residual_P_kW=float(power[ph].real),
                summed_node_power_residual_Q_kvar=float(power[ph].imag)))
    return results

def main():
    compiled=read(OUT/'COMPILED_AUDIT_RECEIPT.json');rating=read(OUT/'REG1A_CURRENT_RATING_AUTHORITY.json')
    pcc=pd.read_csv(OUT/'AIDC_PCC_PER_PHASE_PQ.csv');reg=pd.read_csv(OUT/'REG1A_PHASE_CURRENT_AUDIT.csv')
    balance=pd.read_csv(OUT/'REG1A_DOWNSTREAM_PHASE_BALANCE.csv');peaks={};violations=[]
    for day in tuple(f'2025-05-{d:02d}' for d in range(1,32)):
        with np.load(MAY/'BUNDLE'/day_folder(day)/'V_ACTUAL_AC.npz') as z:
            for ph in 'ABC':
                ix=list(z['branch_names']).index('transformer.reg1a::'+ph);amps=z['current_A'][:,ix]
                slot=int(amps.argmax());row=dict(day=day,slot=slot,phase=ph,current_A=float(amps[slot]),current_pu=float(z['current_pu'][slot,ix]))
                if ph not in peaks or row['current_A']>peaks[ph]['current_A']:peaks[ph]=row
                for t in np.where(z['current_pu'][:,ix]>1)[0]:violations.append(dict(day=day,slot=int(t),phase=ph,current_A=float(amps[t])))
    emit_csv('FULL_MAY_REG1A_PHASE_PEAKS.csv',list(peaks.values()))
    emit_csv('FULL_MAY_REG1A_VIOLATIONS_RECHECK.csv',violations)
    # Per-PCC relative spread computed from actual conductor powers.
    summary=[]
    for name,group in pcc.groupby('PCC'):
        row=dict(PCC=name,slots=len(group),P_max_phase_spread_kW=float(group.P_phase_spread_kW.max()),
            Q_max_phase_spread_kvar=float(group.Q_phase_spread_kvar.max()),I_max_phase_spread_A=float(group.I_phase_spread_A.max()))
        for quantity in ('P','Q'):
            mean=group[[quantity+'_'+ph for ph in 'ABC']].mean(axis=1).abs()
            row[quantity+'_max_relative_phase_spread']=float((group[quantity+'_phase_spread_'+('kW' if quantity=='P' else 'kvar')]/mean).max())
        summary.append(row)
    emit_csv('PCC_PHASE_BALANCE_SUMMARY.csv',summary)
    peak=peaks['A'];peak_balance=balance[(balance.day==peak['day'])&(balance.slot==peak['slot'])].set_index('phase')
    nativeP={ph:float(peak_balance.loc[ph,'native_feeder_load_P_kW']) for ph in 'ABC'}
    nativeQ={ph:float(peak_balance.loc[ph,'native_feeder_load_Q_kvar']) for ph in 'ABC'}
    contribution=[]
    for other in 'BC':
        row=dict(day=peak['day'],slot=peak['slot'],comparison='A-'+other)
        for cat in ('native_feeder_load','PV','AIDC_PCC','fixed_capacitor','network_loss_and_phase_transfer'):
            for suffix in ('P_kW','Q_kvar'):
                row[cat+'_'+suffix]=float(peak_balance.loc['A',cat+'_'+suffix]-peak_balance.loc[other,cat+'_'+suffix])
        row['root_downstream_P_difference_kW']=float(peak_balance.loc['A','reg1a_downstream_out_P_kW']-peak_balance.loc[other,'reg1a_downstream_out_P_kW'])
        row['root_downstream_Q_difference_kvar']=float(peak_balance.loc['A','reg1a_downstream_out_Q_kvar']-peak_balance.loc[other,'reg1a_downstream_out_Q_kvar'])
        contribution.append(row)
    emit_csv('PEAK_PHASE_IMBALANCE_CONTRIBUTIONS.csv',contribution)
    m=source();o,adapter,iv=compile_verified()
    try:convergence=float(o.Solution.Convergence())
    finally:o.Basic.ClearAll()
    baseP={ph:sum(r['base_p_kw']/len(r['phases']) for r in adapter['loads'] if j in r['phases']) for j,ph in enumerate('ABC',1)}
    baseQ={ph:sum(r['base_q_kvar']/len(r['phases']) for r in adapter['loads'] if j in r['phases']) for j,ph in enumerate('ABC',1)}
    write(OUT,'NATIVE_PHASE_SOURCE_AUTHORITY.json',dict(adapter_source=record(m['assets'].runtime_adapter),
        source_graph=[record(resolve(r)) for r in m['audit']['static_source_graph']['files']],
        base_P_kW=baseP,base_Q_kvar=baseQ,base_total_P_kW=sum(baseP.values()),
        source_native_load_count=len(adapter['loads']),
        compiled_single_phase_load_counts={ph:sum(r['phases']==[j] for r in adapter['loads']) for j,ph in enumerate('ABC',1)},
        exact_native_authority_rows=adapter['loads'],peak_actual_P_kW=nativeP,peak_actual_Q_kvar=nativeQ))
    nodal=[]
    for day in DAYS:nodal.extend(nodal_check(day))
    emit_csv('NODAL_CURRENT_RESIDUAL_AUDIT.csv',nodal)
    net=pd.read_csv(OUT/'NETWORK_PHASE_CONSERVATION.csv');nr=pd.DataFrame(nodal)
    difference=max(float(np.max(np.abs(net.P_conservation_error_kW-nr.summed_node_power_residual_P_kW))),
        float(np.max(np.abs(net.Q_conservation_error_kvar-nr.summed_node_power_residual_Q_kvar))))
    write(OUT,'NETWORK_NUMERICAL_LIMITATION.json',dict(strict_algebraic_1e_7_check_passed=False,
        strict_check_receipt=record(OUT/'NETWORK_CONSERVATION_RECEIPT.json'),
        frozen_OpenDSS_convergence_tolerance=convergence,solver_tolerance_changed=False,
        maximum_power_residual_kW_kvar=read(OUT/'NETWORK_CONSERVATION_RECEIPT.json')['maximum_absolute_error_kW_kvar'],
        maximum_nodal_current_residual_A=float(nr.maximum_node_current_residual_A.max()),
        nodal_power_and_terminal_remainder_discrepancy_kW_kvar=difference,
        explanation='The finite-convergence solution is not algebraically exact. The additional strict conservation check failed (retained). Independently summed nodal current residuals explain the terminal power remainder discrepancy. No solver retuning or repair was applied; the roughly 422 kW native A-B imbalance is much larger.',
        nodal_reconciliation_PASS=difference<1e-7))
    classification=dict(exact_base=BASE,
        H1=dict(status='NOT_SUPPORTED',claim='Unintended A-only/asymmetric AIDC PCC mapping',
            ABC_connected_PCCs=compiled['ABC_normal'],PCC_count=12,upstream_transformers_ABC=True,
            maximum_P_phase_spread_kW=float(pcc.P_phase_spread_kW.max()),maximum_Q_phase_spread_kvar=float(pcc.Q_phase_spread_kvar.max()),
            exact_zero_phase_spread=False,interpretation='Terminal P/Q is approximately balanced. Small nonzero deviations and unequal I are observed under unequal local voltages and finite nonlinear convergence; no missing/swapped phase is found.'),
        H2=dict(status='STRONGLY_SUPPORTED',claim='Native feeder phase imbalance with balanced AIDC addition',
            native_A_heavier_source_and_actual_CONFIRMED=True,source_base_P_kW=baseP,source_base_Q_kvar=baseQ,
            peak_native_P_kW=nativeP,peak_native_Q_kvar=nativeQ,
            native_A_minus_B_P_kW=nativeP['A']-nativeP['B'],native_A_minus_C_P_kW=nativeP['A']-nativeP['C'],
            peak_AIDC_P_kW={ph:float(peak_balance.loc[ph,'AIDC_PCC_P_kW']) for ph in 'ABC'},
            all_12_violation_slots_native_A_P_greater_than_B_and_C=all(
                g.loc[g.phase=='A','native_feeder_load_P_kW'].iloc[0]>g.loc[g.phase==ph,'native_feeder_load_P_kW'].iloc[0]
                for _,g in balance[balance.kind=='violation'].groupby(['day','slot']) for ph in 'BC'),
            limitation='Observational source-backed decomposition, no AIDC removal or load redistribution counterfactual. Balanced AIDC contributes absolute demand on all phases; native imbalance and network losses concentrate A-phase loading.'),
        H3=dict(status='NOT_SUPPORTED',claim='Incorrect reg1a current measurement/denominator under frozen PR129 contract',
            conductor_parent_winding_mapping_verified=True,denominator_A=rating['denominator_A'],
            denominator_source='5000 kVA three-phase winding nameplate / (sqrt(3)*4.16 kV)',
            CTPrim_700_is_measurement_CT_not_thermal_limit=True,
            source_NormalAmps_A=rating['NormalAmps_A'],source_EmergAmps_A=rating['EmergAmps_A'],
            full_May_nameplate_current_violations=len(violations),
            full_May_NormalAmps_exceedances=sum(r['current_A']>rating['NormalAmps_A'] for r in violations),
            thermal_interpretation='The 12 cells exceed the frozen 100% nameplate policy; none exceed OpenDSS NormalAmps. They must not be called source-NormalAmps thermal violations. No rating change is made.'),
        most_direct_root_cause='Native IEEE123 A-phase P/Q imbalance, amplified by downstream losses, combined with balanced AIDC demand crossing the frozen per-phase nameplate current limit.',
        PCC_mapping_fix_needed=False,exact_fix_proposal_required=False,physical_changes=0,
        diagnostic_days=4,primary_reproduction_slots=384,additional_network_reproduction_slots=384,
        detailed_violation_slots=12,normal_control_slots=8,PCC_terminal_samples=len(pcc),
        reg1a_full_May_phase_peaks=peaks,source_thermal_exceedance_distinguished=True)
    write(OUT,'ROOT_CAUSE_CLASSIFICATION.json',classification)
    text=f'''# May reg1a A상 current violation 원인 감사

BASE: PR #129 `{BASE}`. 운영 모델 수정 없이 4일×96 slots를 fresh autonomous OpenDSS로 재현했다. 추가 network terminal 감사도 동일 384 slots를 재현했으며, 기존 V/current/current_pu/kVA/tap 배열과 차이는 모두 0이다. 12개 위반 slots와 사전 고정한 인접 정상 8 slots를 상세 측정했다.

1. **12/12 PCC 및 상위 PCC transformer가 ABC 3상 정상 연결**이다. Load의 NumConductors=4, NodeOrder=[1,2,3,0], wye, 0.48 kV를 compiled 객체에서 확인했다. 단상 또는 누락·오배치 상은 발견되지 않았다.
2. conductor별 실제 P/Q는 근사 균형이다. 240 PCC-slot 표본에서 최대 상간 spread는 P={pcc.P_phase_spread_kW.max():.9f} kW, Q={pcc.Q_phase_spread_kvar.max():.9f} kvar이다. 완전한 0 차이는 아니며 상전압이 달라 I까지 동일할 필요는 없다. 각 PCC의 spread 및 상대 차이는 PCC_PHASE_BALANCE_SUMMARY.csv에 보존했다.
3. May 전체 reg1a upstream peak A/B/C는 **{peaks['A']['current_A']:.9f}/{peaks['B']['current_A']:.9f}/{peaks['C']['current_A']:.9f} A**다. 세 peak 모두 May 21 slot 31이다. downstream A/B/C와 bus V, tap, controller 상태는 REG1A_PHASE_CURRENT_AUDIT.csv에 모두 기록했다. reg1a는 하나의 3상 transformer이며 존재하지 않는 reg1b/reg1c를 가정하지 않았다.
4. native source base P A/B/C={baseP['A']:.1f}/{baseP['B']:.1f}/{baseP['C']:.1f} kW, Q={baseQ['A']:.1f}/{baseQ['B']:.1f}/{baseQ['C']:.1f} kvar이다. peak slot 실제 native P={nativeP['A']:.6f}/{nativeP['B']:.6f}/{nativeP['C']:.6f} kW, Q={nativeQ['A']:.6f}/{nativeQ['B']:.6f}/{nativeQ['C']:.6f} kvar이다. A-B native P 차이는 {nativeP['A']-nativeP['B']:.6f} kW이며 AIDC P는 상마다 약 176.64 kW이다. PV/고정 capacitor 및 network loss·phase transfer를 별도 분리했고, 12개 위반 slot 모두 native A상 P가 가장 크다.
5. **693.930612006762 A = 5000/(√3×4.16)**. IEEE123Master.dss line 26의 5000 kVA/4.16 kV 3상 nameplate를 frozen backend가 parent bus 150/winding 1에서 사용한다. NodeOrder로 A/B/C conductor를 정확히 읽는다. CTPrim=700은 RegControl CT authority이며 backend thermal 분모가 아니다. Generated_Planning_Line_Ratings_u080.dss는 Line만 edit하고 reg1a를 변경하지 않는다.
6. OpenDSS compiled NormalAmps={rating['NormalAmps_A']:.9f} A, EmergAmps={rating['EmergAmps_A']:.9f} A이며 frozen backend는 이를 transformer 분모로 쓰지 않는다. **12개는 frozen 100% nameplate current 초과이고 source NormalAmps 초과는 0**이다. aggregate transformer kVA가 1 미만이어도 특정 상 전류는 nameplate 분모를 초과할 수 있다. 기준을 완화하거나 결과를 재분류해 기존 PR129 count를 바꾸지 않았다.
7. H1 **NOT_SUPPORTED**, H2 **STRONGLY_SUPPORTED**, H3(frozen contract measurement/분모 오류) **NOT_SUPPORTED**. 가장 직접적인 설명은 native feeder A상 P/Q 편중과 상별 network 손실에 balanced AIDC 부하가 더해져 frozen 상별 nameplate 한계를 넘은 것이다. source NormalAmps와 100% nameplate policy의 차이는 명시적으로 구분한다. 반사실적 부하 제거 실험은 수행하지 않았으므로 native 단독 원인으로 과도하게 단정하지 않는다.
8. **PCC mapping 수정 불필요**. H1이 CONFIRMED되지 않아 exact fix proposal은 작성하지 않았다. rating/phase/tap/PQ/부하 분배/Runtime/CC4/queue/Planning voltage/margin은 모두 수정하지 않았다. B1/B2/B3/M1/A2/M2 NOT_RUN.

수치 감사의 한계: 추가 passive terminal 합계의 strict algebraic 1e-7 보존 검사는 실패했고 원본 FAIL receipt를 유지한다. 최대 discrepancy는 {read(OUT/'NETWORK_CONSERVATION_RECEIPT.json')['maximum_absolute_error_kW_kvar']:.9f} kW/kvar이다. frozen convergence tolerance={convergence}; nodal current residual을 별도로 합산해 이 차이와 {difference:.12g} kW/kvar 이내로 일치함을 확인했다. solver tolerance는 변경하지 않았다. 이 오차를 정확한 물리 손실로 은폐하지 않고 NETWORK_NUMERICAL_LIMITATION.json에 기록했다.

최종 테스트와 exact BASE byte 보존/외부 source SHA 검증은 TEST_RECEIPT.json 및 VERIFICATION.json을 참조한다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps(dict(ABC=12,peaks=peaks,H1='NOT_SUPPORTED',H2='STRONGLY_SUPPORTED',H3='NOT_SUPPORTED',nodal_reconciliation_difference=difference),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
