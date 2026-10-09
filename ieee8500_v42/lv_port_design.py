"""Authorized simulation dock: small split-phase bidirectional interface.

These new interface design assumptions do not alter any original IEEE8500
object/rating or certify an installed station. Vehicle main PCS remains separate.
"""
from __future__ import annotations
import math
import json
from .common import REPORT


PRIMARY_SOURCES=[
    {'id':'manufacturer_datasheet','title':'Schneider XW Pro UL Datasheet, DS20230313',
     'url':'https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Datasheet.pdf',
     'pages':[1,2],'access_date':'2026-10-09'},
    {'id':'manufacturer_NA_operation','title':'Schneider XW Pro NA Operation Guide 990-91227F-01',
     'url':'https://solar.se.com/us/wp-content/uploads/sites/7/2023/02/990-91227F-01.pdf',
     'pages':[140,141,143,150,163,164,165,166],'access_date':'2026-10-09'},
    {'id':'manufacturer_installation','title':'Schneider XW Pro NA Installation Guide 990-91228D-01',
     'url':'https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-NA-Installation-Guide_990-91228.pdf',
     'access_date':'2026-10-09'},
    {'id':'manufacturer_certificate','title':'Schneider XW Pro UL Certificate of Compliance',
     'url':'https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Certificate-of-Compliance.pdf',
     'access_date':'2026-10-09'},
    {'id':'IEEE_interconnection','title':'IEEE SCC21, IEEE Std1547-2018 and UL1741 Supplement SB',
     'url':'https://sagroups.ieee.org/scc21/standards/1547rev/','access_date':'2026-10-09'},
    {'id':'UL_interactive_equipment','title':'UL1741, Edition3, scope for interactive power conversion',
     'url':'https://www.shopulstandards.com/ProductDetail.aspx?productId=UL1741','access_date':'2026-10-09'},
]

DESIGN={
    'status':'AUTHORIZED_SIMULATION_INTERFACE_DESIGN_NOT_INSTALLED_HARDWARE',
    'product_anchor':'Schneider Electric XW Pro 6848 NA, 865-6848-21, 120/240V configuration',
    'inference':'Study envelope conservatively bounded by commercial grid-interactive ratings; arbitrary per-slot Q/DC-DC supervisory integration remains a declared engineering assumption',
    'source_grid_sell_kw':6.,'source_grid_sell_current_A':27.,
    'source_standalone_output_kw_25C':6.8,'source_standalone_output_kw_40C':6.,
    'source_battery_voltage_nominal_V':48.,'source_battery_voltage_range_V':[40.,64.],
    'source_battery_discharge_current_A':180.,'source_battery_charge_current_A':140.,
    'source_bypass_or_relay_current_A_NOT_inverter_output':60.,
    'P_export_max_kw':5.,'P_import_max_kw':5.,'S_max_kva':6.,'Q_abs_max_kvar':3.,
    'I_each_hot_max_A':27.,'nominal_AC_voltage_LL_V':240.,'nominal_AC_voltage_LN_V':120.,
    'connection':'L1,L2,N,PE; balanced current injection between original bus.1 and bus.2',
    'stationary_inverter_placement':'One fixed/permanently connected interface at each study STA; vehicle DC dock attachment is a separate unverified engineering design, not a certified mobile use of this product',
    'AC_model_mode':'LV_SPLIT_240','DSS_connection':'1phase delta bus.1.2 kv=0.24',
    'phase_power_rule':'One combined 240V two-hot port; do not apply full P/Q twice to two 120V loads',
    'independent_LV_leg_modes_authorized_for_this_design':False,
    'positive_sign':'P>0/Q>0 means injection; DSS Load kW=-P, kvar=-Q',
    'instantaneous_constraints':['-5 <= P_kw <= 5','abs(Q_kvar) <= 3','P_kw^2+Q_kvar^2 <= 6^2',
        'sqrt(P_kw^2+Q_kvar^2)*1000/abs(V_hot1-V_hot2) <= 27',
        'All original line terminal/conductor NormalAmps, transformer winding nameplate kVA, and original node voltage limits remain binding'],
    'one_shared_dock_per_STA':True,'aggregate_multiple_vehicle_power_must_obey_same_dock_bound':True,
    'STA_count_unchanged':True,'MESS_count_unchanged':True,'original_service_transformers_unchanged':True,
    'original_triplex_and_neutral_unchanged':True,'new_feeder_transformer_count':0,
    'vehicle_main_PCS_kw_NOT_LV_port':450.,'vehicle_main_PCS_kva_NOT_LV_port':600.,
    'vehicle_main_energy_kwh_NOT_port_output':1800.,
    'DC_interface':'Separate isolated bidirectional DC/DC + BMS interlock, vehicle pack -> regulated 48V interface bus; vehicle main PCS is bypassed in LV dock mode',
    'vehicle_pack_voltage_V':'UNVERIFIED','isolated_DC_DC_product_and_voltage_ratio':'UNVERIFIED',
    'study_auxiliary_conversion_efficiency':.90,'efficiency_scope':'Explicit conservative simulation assumption for auxiliary interface; not a manufacturer efficiency guarantee or a change to original vehicle energy/capacity',
    'study_dc_bus_minimum_for_current_audit_V':40.,
    'study_DC_discharge_A_at_5kw_eta090_40V':5e3/.90/40.,
    'study_DC_charge_A_at_5kw_eta090_40V':5e3*.90/40.,
    'reactive_support_evidence':'NA operation guide Q(V), Q(P), adjustable power factor support both reactive signs; active power may be curtailed to meet reactive demand',
    'arbitrary_independent_Q_setpoint_firmware_and_gateway':'UNVERIFIED_PRODUCTION_ENGINEERING_ASSUMPTION_FOR_STUDY',
    'fixed_PF_charge_mode_source':.98,
    'study_controls':'Quasistatic externally commanded P/Q within conservative envelope; hardware autonomous grid-profile interactions require implementation validation',
    'temperature_assumption':'Interface maintained <=40C for the 5kW study envelope; higher-temperature derating not modeled',
    'field_grid_profile_and_anti_islanding_settings':'UNVERIFIED; retain compliant grid-following disconnect/ride-through, no source RegControl override',
    'source_certification_claim':'Manufacturer lists UL1741-SA/SB and IEEE1547-2018; not proof that the proposed complete mobile DC/DC+dock system is certified',
    'certificate_evidence_limit':'The linked2020 certificate explicitly covers permanently connected fixed equipment and UL1741-SA/older IEEE1547; its contents alone do not independently verify the later datasheet SB/2018 claim or a mobile docking assembly',
    'study_connect_delay_seconds':600,'delay_authority':'User-authorized original V42 delay; physical docking timing not observed',
    'partial_slot_energy_availability':'Only time after actual arrival plus600 seconds contributes; first-slot energy scales by available seconds/900; instantaneous AC ceiling stays5kW/6kVA',
    'safe_finite_difference_step_kw_or_kvar':.1,'meaningful_nonlinear_validation_step_kw':1.,
    'full_power_validation_required_kw':5.,'full_power_validation_required_kvar':3.,
    'study_electrical_eligibility':'Declared hardware design is a simulation input; original feeder/rating/control AC screening still decides each host/slot/direction',
    'production_eligible':False,'field_installation_certified':False,
    'primary_sources':PRIMARY_SOURCES,
}


def command_check(P_kw,Q_kvar,V_hot1,V_hot2):
    """Only the interface envelope, not full feeder/SOC/route feasibility."""
    if not all(math.isfinite(float(x)) for x in (P_kw,Q_kvar)):
        raise ValueError('Non-finite command')
    voltage=abs(complex(V_hot1)-complex(V_hot2))
    if not math.isfinite(voltage) or voltage<=0:raise ValueError('Invalid actual line-to-line voltage')
    apparent=math.hypot(P_kw,Q_kvar);amps=1000*apparent/voltage
    checks={'P_export':P_kw<=5+1e-10,'P_import':P_kw>=-5-1e-10,
        'Q_abs':abs(Q_kvar)<=3+1e-10,'PQ_circle':apparent<=6+1e-10,
        'hot1_current':amps<=27+1e-10,'hot2_current':amps<=27+1e-10}
    return {'interface_envelope_PASS':all(checks.values()),'checks':checks,
        'actual_voltage_LL_V':voltage,'apparent_kva':apparent,'hot1_amps':amps,'hot2_amps':amps,
        'implied_inverter_neutral_current_A':0.,'neutral_rating_invented':False,
        'full_original_AC_constraints_checked':False,'route_SOC_QoS_access_checked':False,
        'field_certification':False}


def available_seconds(slot_start_seconds,arrival_seconds,slot_seconds=900):
    """Original600s connection delay, preserving partial-slot energy availability."""
    if slot_seconds<=0:raise ValueError('Positive slot duration required')
    return max(0.,min(float(slot_seconds),slot_start_seconds+slot_seconds-max(slot_start_seconds,arrival_seconds+600.)))


def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'LV_PORT_SIMULATION_DESIGN.json').write_text(json.dumps(DESIGN,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text='''# 저압 포트의 시뮬레이션 설계

사용자가 허용한 연구용 설계 입력으로 **STA마다 하나의 공용 120/240V split-phase 보조 포트**를 선택한다. 원래 12 STA·6 MESS·IEEE8500의 CT/Triplex/phase/rating을 유지한다. 차량의 450kW 주 PCS는 이 저압 포트를 통과하지 않으며 별도의 저출력 양방향 DC/DC–인버터 경로를 사용한다. 현장 설치 증거가 없어도 이 가정을 명시한 연구 AC 선별은 계속할 수 있다. Production 승인과 설치 적합성은 별도다.

상용 근거는 Schneider XW Pro 6848 NA(865-6848-21)의 split-phase 배터리 inverter/charger다. 제조사는 standalone6.8kW(25C), standalone6.0kW(40C), **grid-sell6.0kW·27A**, DC40–64V/48V nominal, discharge180A·charge140A를 제시한다. 60A transfer/bypass는 inverter 출력으로 쓰지 않았다. [제조사 데이터시트, 2023 개정](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Datasheet.pdf)

이 상용 제품 certificate는 permanently connected fixed equipment 용도다. 따라서 연구 설계는 STA에 고정된 인버터와 차량의 별도 DC dock을 가정하며, 제품을 차량에 싣고 이동하는 사용이 인증되었다고 주장하지 않는다. 열람한2020 certificate는 SA·과거 IEEE1547 시험 범위를 명시하고 있어2023 데이터시트의 후속 SB/2018 표기를 그 certificate만으로 독립 검증할 수는 없다. 이 차이와 완전한 mobile docking 조합의 인증은 Production 검증 사항으로 남긴다.

연구 입력은 더 보수적인 **P∈[-5,+5]kW, |Q|≤3kvar, P²+Q²≤6²kVA², 각 hot 전류≤27A**로 고정한다. positive P/Q는 계통 주입이다. 명령의 실제 hot 전류는 |S|×1000/|V1−V2|이며 실제 전압에 따라 S≤27|V1−V2|/1000도 동시에 적용한다. 240V에서6kVA는25A, 228V에서는26.316A이다. 현재 P/Q box corner(5,3)는5.831kVA이다. 각 차량과 여러 차량의 합계는 공용 포트 ceiling을 모두 만족해야 한다. 차량450kW나 서비스156A를 곱한37.44kVA는 이 포트의 출력 권한으로 승격하지 않는다.

NA operation guide는 reactive injection/absorption, VoltVar/WattVar, adjustable PF 및 reactive 우선의 P curtailment를 지원한다. 그러나 이것이 임의의 per-slot 독립 Q command API를 직접 인증하는 것은 아니다. 연구의 독립 Q supervisory-control은 명시적 구현 가정이며 실제 firmware/gateway·charging-PF0.98·자율 grid-code 제어와의 조합 검증을 요구한다. 해당 문서에서 연속 grid-interactive output28.3A와 grid-sell27A를 구별하므로 이 연구는27A를 사용한다. [제조사 NA 운용 가이드](https://solar.se.com/us/wp-content/uploads/sites/7/2023/02/990-91227F-01.pdf)

전기 등가는 기존 LV bus.1.2에 1phase delta, kv0.24인 양방향 constant-P/Q 포트다. 240V 총 P/Q를 두120V load에 각각 복제하지 않는다. 현실 AC 단자는 L1/L2/N/PE이며 balanced injection의 neutral 기여는0이다. 원본 Kron-reduced service neutral에는 독립 ampacity를 만들어 넣지 않았다. LV_LEG1_120/LV_LEG2_120 단일-leg mode는 별도 민감도 시험만 했으며 이 split-phase 제품 설계의 허용 운전모드로 쓰지 않는다.

차량 battery pack의 DC voltage/BMS는 아직 알려져 있지 않다. 따라서 차량→regulated48V bus의 **별도 isolated bidirectional DC/DC와 DC/AC disconnect, 보호·접지·neutral bonding·interlock**은 설계 요구조건이며 선정·조합 인증은 미검증이다. 보조 경로의 보수적 연구 효율0.90을 명시한다. 5kW에서40V 기준 discharge138.889A, charge112.5A로 인버터의 DC ceiling보다 낮지만 이것만으로 DC/DC나 실제 차량 pack 호환성을 증명하지 않는다. 원본 차량 에너지1800kWh·주PCS450kW/600kVA·SOC 제한을 확대하지 않고 보조 경로 손실을 해당 study SOC 계산에 반영해야 한다.

제조사 자료는 UL1741-SA/SB·IEEE1547-2018을 기재하지만 제안한 전체 mobile DC/DC+dock 인증을 의미하지 않는다. interactive inverter 규격과 IEEE1547.1 시험/UL1741-SB의 관계는 [UL1741 공식 scope](https://www.shopulstandards.com/ProductDetail.aspx?productId=UL1741), [IEEE SCC21 공식 안내](https://sagroups.ieee.org/scc21/standards/1547rev/)로 확인했다. 계통 추종 anti-islanding·ride-through·reconnect 기능을 유지하는 가정이며 원본 source/RegControl을 대체하지 않는다. 읽은 [제조사 설치 가이드](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-NA-Installation-Guide_990-91228.pdf)·[제품 certificate](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Certificate-of-Compliance.pdf)는 제품 근거이며 field docking 절차를 실증하지 않는다. 모든 URL 열람일은2026-10-09다.

공용 dock 입력이 존재하는 연구 후보라도 **기존 모든 line terminal/conductor NormalAmps, 모든 CT winding nameplate kVA, original node voltage0.95–1.05, source1.05 및 원본 자동 Reg/CapControl**을 각 slot·수입/수출·P/Q 조합에서 검사한다. CT5kVA나 기존 preload가 큰 Triplex는 이6kVA 포트를 그대로 허용하지 않을 수 있다. 여러 포트가 같은 CT를 공유하면 합성 operating point를 검사한다. 원래156/580A나37.5kVA를 변경하거나 설비를 늘려 통과시키지 않는다. 원본 background1.0 상태 자체가 저전압/선로 과부하이므로 hardware design만으로 전 계통 pass를 선언하지 않는다.

사용자 승인한 연결 지연600초를 유지한다. 실제 도착 시각+600초 이후 구간만900초 slot 에너지에 반영하고, 부분 첫 slot의 평균에너지가 작아져도 순간 P/S/current ceiling은 그대로다. 차량 routing/access/SOC는 원본 V42 권한을 따르며 임의 ETA·동시 접속 수를 만들지 않는다. 작은 중앙차분은±0.1kW/kvar, 독립 nonlinear 점검은1kW와 최대5kW/3kvar operating point를 사용한다. fixed tap 민감도만으로 원본 자동 제어를 포함한 실행 가능성을 인증하지 않는다.
'''
    (REPORT/'LV_PORT_SIMULATION_DESIGN.md').write_text(text,encoding='utf-8')
    print(json.dumps({k:DESIGN[k] for k in ('status','P_export_max_kw','P_import_max_kw','S_max_kva','Q_abs_max_kvar','I_each_hot_max_A')},indent=2))


if __name__=='__main__':main()
