"""Separate mapping, B0, controllability, and optimizer readiness gates."""
import math
from datetime import datetime,timezone
import numpy as np
import psutil
from .audit import DOC,read,save,table
from .physical import Physical,RUNTIME


def configure():
    frozen=dict(experiment_id='V2_add',P5=dict(source_pu=1.04,all12_Vreg_V=123.5,
        CAPBank3_initial_state=[0],native_RegControls=12,native_CapControls=9,
        all_other_original_control_properties='unchanged',scale_specific_retuning=False,
        slot_evolution='independent initial context per Planning/Actual; carry native taps/caps within sequence; Actual includes prefix24',
        Fresh='new DSS context and complete replay from same original/P5 initial state'),
        voltage_contract_difference='IEEE123 Planning7/Actual43 hardware is not copied. IEEE8500 native12/9 automatic static controls are used in both roles, no Actual-only SVR12 overlay. Algorithms/Jobs unchanged; physical scenario differs explicitly.',
        PV=dict(records='source/PR197_PV_HOT_RECORDS.json',count=2354,Model=1,Q_kvar=0,
            nominal_kv=.12,connection='original one-phase wye hot leg buses, no 2.4kV attachment',
            installed_capacity='unchanged PR197 per-hot original kW * original PV_ratio',
            dispatch='each V44 frozen slot total * fixed installation capacity weights',
            original_load_netting=False,duplicate_generators=False),
        STA=dict(mapping='fixed original PR199 C2 candidate',ports=12,transformer_kva=750,
            transformer='original PR199 delta12.47kV / grounded wye480V; same impedances/losses',
            interface_kva=600,interface_current_A=600/(math.sqrt(3)*.48),occupancy_per_STA=1,
            hardware_assumption='research AC model only; no field/manufacturer/protection/GIS certification'),
        vehicle=dict(units=8,P_limit_kw=300,Q_limit_kvar=250,PCS_kva=400,
            PCS_polygon='16 faces: cos(2*pi*f/16)*P+sin(2*pi*f/16)*Q <= 400*cos(pi/16)',
            SOC_min_kwh=440,SOC_max_kwh=1080,SOC_initial_kwh=760,SOC_terminal_kwh=760,
            eta_charge=.95,eta_discharge=.95,terminal_recharge_required=True),
        stages=dict(G1='INPUT_AND_PHYSICAL_MAPPING',G2='B0_FRESH_AC_AND_SCALE',
                    G3='AIDC_MESS_CONTROLLABILITY',G4='MESS8_OPTIMIZER_INTEGRATION'),
        G2_dependencies=['G1'],G2_not_dependent_on=['G3','G4'],
        G1_scope='wiring/model/capacity/input/automatic-control correspondence plus operating-point AC checks; per-beta operating feasibility belongs to G2, full network-coupled fleet dispatch region belongs to G3',
        no_long_solver=True,no_production_mutations=True)
    path=DOC/'PHYSICAL_CONFIGURATION_FREEZE.json'
    if path.exists():
        assert read(path)==frozen,'Frozen physical scenario changed'
    else:save(path.name,frozen)
    return frozen


def main():
    configure()
    if (DOC/'PREFLIGHT_GATES.json').exists() and read(DOC/'PREFLIGHT_GATES.json')['G1']['status']=='PASS':
        print('REUSE existing G1 physical mapping certification; no repeated probes',flush=True)
        return
    p=psutil.Process()
    try:
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        efficient=[i for i in p.cpu_affinity() if i>=12]
        if efficient:p.cpu_affinity(efficient[:1])
    except (AttributeError,psutil.AccessDenied):pass
    e=Physical('G1')
    pvrows=[]
    for role in ('PLANNING','ACTUAL'):
        values=e.inputs[role+'_PV_P_kw'].sum(1)
        q=e.inputs[role+'_PV_Q_kvar']
        for t,total in enumerate(values):
            allocation=e.pv_weights*total
            pvrows.append(dict(role=role,slot=t,total_kw=float(total),
                installed_kva=math.fsum(e.pv_capacity),max_individual_capacity_ratio=float(np.max(allocation/e.pv_capacity)),
                total_command_error_kw=float(abs(math.fsum(allocation)-total)),Q_zero=not bool(np.any(q[t]))))
    table('PV_MAPPING_216_SLOT_CAPACITY_CHECK.csv',list(pvrows[0]),pvrows)
    probes=[];portrows=[]
    # Predetermined source-based extremes, not chosen to improve an AC outcome.
    for role in ('PLANNING','ACTUAL'):
        ts=sorted({0,int(np.argmax(e.inputs[role+'_BG_P_kw'].sum(1))),
                   int(np.argmax(e.inputs[role+'_PV_P_kw'].sum(1)))})
        for t in ts:
            e.apply(role,t,1.)
            row,_,_,ports=e.measure(role,t,1.,state=e.initial_state)
            probes.append(row);portrows.extend(dict(role=role,slot=t,**r) for r in ports)
            print('G1',role,t,'rho',row['rho_global'],'V',row['Vmin'],row['Vmax'],'balance',row['balance_P_error_kw'],flush=True)
    e.check_parameters()
    table('G1_AC_MAPPING_PROBES.csv',list(probes[0]),probes)
    table('G1_STA_PORT_PROBES.csv',list(portrows[0]),portrows)
    polygon_slack=min(400*math.cos(math.pi/16)-math.cos(2*math.pi*f/16)*p-math.sin(2*math.pi*f/16)*q
        for p in (-300,300) for q in (-250,250) for f in range(16))
    mapping_ok=all(r['max_individual_capacity_ratio']<=1+1e-10 and r['Q_zero'] and r['total_command_error_kw']<1e-9 for r in pvrows)
    mapping_ok &= all(r['converged'] and r['controls_done'] and
        max(abs(r[k]) for k in ('balance_P_error_kw','balance_Q_error_kvar','PV_total_abs_error_kw','PV_actual_kvar','BG_P_abs_error_kw','BG_Q_abs_error_kvar'))<1e-4 for r in probes)
    gate=dict(experiment_id='V2_add',UTC=datetime.now(timezone.utc).isoformat(),
        G1=dict(status='PASS' if mapping_ok else 'FAIL',PV_mapping='PASS' if mapping_ok else 'FAIL',
            PV_generator_count=2354,PV_installed_kva=math.fsum(e.pv_capacity),
            per_slot_capacity_ratio_max=max(r['max_individual_capacity_ratio'] for r in pvrows),
            command_total_error_max_kw=max(r['total_command_error_kw'] for r in pvrows),
            actual_PV_total_error_max_kw=max(r['PV_total_abs_error_kw'] for r in probes),
            balance_max_abs=max(abs(r[k]) for r in probes for k in ('balance_P_error_kw','balance_Q_error_kvar')),
            C2_AIDC_MV=12,C2_STA_MV=12,dedicated_STA_transformers=12,
            original4_initial_locations_preserved=True,additional4_locations='STA02/03/04/05; same fixed C2 ports and one-per-port occupancy',
            simultaneous8_connection='distinct electrically instantiated STA ports; full-power fleet operating points evaluated separately under G3/G2 network constraints',
            P300_Q250_box_inside_original_PCS16=polygon_slack>=0,minimum_PCS16_slack_kva=polygon_slack,
            full_box_network_feasibility='not universally assumed; network voltage/current/transformer constraints can tighten the PCS box',
            P5_configuration='PHYSICAL_CONFIGURATION_FREEZE.json',
            source_verification='reuse PR236 59 checks and 190/190 receipt rows, no repeated source restoration/audit'),
        G2=dict(status='READY' if mapping_ok else 'BLOCKED_G1',depends_on=['G1']),
        G3=dict(status='PENDING_B0',not_a_G2_dependency=True),
        G4=dict(status='NOT_VERIFIED',not_a_G2_dependency=True,long_solver_allowed=False))
    save('PREFLIGHT_GATES.json',gate)
    save('PV_MAPPING_AUDIT.json',dict(status=gate['G1']['PV_mapping'],
        per_hot_installations='exact PR197 location, primary-phase label, kV, kVA, Model1, .88/1.05 V characteristics',
        V44_2_4kV_generator_copied=False,PV_time_series_scaled=False,net_load_substitution=False,
        original_phase_and_capacity_roster='source/PR197_PV_HOT_RECORDS.json',
        PV_command_ratio_max=gate['G1']['per_slot_capacity_ratio_max'],
        operating_AC_check='G1 extreme-slot probes; every G2 slot independently records actual injection and AC power balance',
        actual_power_tolerance_kw=1e-4))
    save('C2_PORT_PHYSICAL_MAPPING.json',dict(status='PASS_MAPPING_RESEARCH_MODEL' if mapping_ok else 'FAIL',
        STA_ports=e.port_meta,AIDC='original fixed C2 3-phase MV ideal PCC elements, all host network limits retained',
        region='original vehicle PCS16 intersect P±300/Q±250, interface S600/current721.688A, dedicated transformer750kVA, full network AC constraints',
        hardware_field_certification=False,geometry_and_actual_road_ETA='original logical road-service/route proxy retained, no regenerated routes'))
    print('G1',gate['G1']['status'],flush=True)
    if not mapping_ok:raise SystemExit(1)


if __name__=='__main__':main()
