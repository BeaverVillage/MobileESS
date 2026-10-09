"""Grid-blind stationary six-unit LV dispatch with explicit battery losses.

This is a research replay, not a Native optimizer or field access certificate.
The workload remains the original B0 reference (zero AIDC control).
"""
import numpy as np
from .common import *
from ieee8500_v42.integration import port_battery_energy_delta


def preregister_schedule():
    document=dict(schema='HIGH_IMPACT_SCHEDULE_CLARIFICATION_V1',
        original_preregistration=receipt(REPORT/'SCENARIO_PREREGISTRATION.json'),
        user_workload_preservation='same original UID/GPU_gang/Runtime/submission/requiredGPUh; capacity-specific Reference/Queue/occupancy/C1/PCC replay; no synthetic or arrivals multiplier',
        old_idle_only_screen='preserved historical diagnostic; recomputed-capacity screen supersedes it',
        screening_count='15 historical idle-only AC trials retained; 15 authoritative recomputed trials required by latest user correction; no outcome-based interpolation',
        timing_typo='literal 40slots was a text error; original explicit slots8..15 and68..75 remain authoritative (16 active slots)',
        charge_slots=list(range(8,16)),discharge_slots=list(range(68,76)),
        Q_kvar=0.,movement=False,route_distance_km=0.,route_energy_kwh=0.,
        initial_vehicle_locations=read(PR193/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json')['initial_locations'],
        connection_delay_seconds=600,slot0_blocked_entirely=True,
        L0_main_eta=.95,L0_auxiliary_eta=.90,L0_effective_eta=.855,
        power_rule='Pdis=min(portPmax*eta_ch*eta_dis,(Einitial-Emin)*eta_dis/2,(Emax-Einitial)*eta_ch*eta_dis/2); Pch=Pdis/(eta_ch*eta_dis)',
        charge_cap_correction='the original formula omitted the coupled charge ceiling; this physical correction is frozen before dispatch AC',
        L0_port_P_kw=5.,L0_port_Q_kvar=3.,L0_port_S_kva=6.,L0_each_hot_I_A=27.,
        mobility_scope='same original six initial STAs, stationary parking; original ETA/network unchanged, no newly feasible travel claimed',
        field_access_GIS_protection='UNVERIFIED',
        MV_interface_selection='M1/M2/M3 unavailable under complete fixed-AIDC common-proper-rotation domain certificate; L0 preserved comparator only',
        AIDC_control='0; nonzero QoS/WAN/checkpoint/rebound certificate unavailable; no synthetic flex expansion',
        no_effect_driven_schedule_tuning=True,Native_calls=0)
    path=REPORT/'SCHEDULE_PREREGISTRATION_CLARIFICATION.json'
    if path.exists():assert read(path)==document,'SCHEDULE_PREREG_MUTATION'
    else:write(path,document)
    return document


def stationary_schedule():
    p=preregister_schedule(); eta=p['L0_effective_eta']; pdis=min(5*eta*eta,480*eta/2,480*eta*eta/2)
    pch=min(5.,pdis/(eta*eta));pdis=pch*eta*eta;fleet=p['initial_vehicle_locations'];schedule=[];rows96=[]
    energy={u:1140. for u in fleet}
    for t in range(96):
        changed={}
        for unit,site in fleet.items():
            ch=pch if t in p['charge_slots'] else 0.;dis=pdis if t in p['discharge_slots'] else 0.
            before=energy[unit];delta=port_battery_energy_delta(ch,dis,mode='LV_AUX_DOCK')
            energy[unit]+=delta;changed[site]=(ch-dis,0.)
            assert 660-1e-9<=energy[unit]<=1620+1e-9 and max(ch,dis)<=5+1e-9
            rows96.append(dict(slot=t,unit=unit,site=site,P_charge_AC_kw=ch,P_discharge_AC_kw=dis,Q_kvar=0.,
                P_consumption_AC_kw=ch-dis,E_before_kwh=before,E_after_kwh=energy[unit],
                deltaE_kwh=delta,eta_charge=eta,eta_discharge=eta,arrived_seconds=0,connected_after_seconds=600,
                available=t>0,port_occupancy_units=1,route_energy_kwh=0.,route_distance_km=0.,
                terminal_required_kwh=1140.,hardware_or_field_certificate=False))
        schedule.append(changed)
    assert max(abs(x-1140) for x in energy.values())<1e-9
    table(REPORT/'MESS_SCHEDULE_SOC_96.csv',rows96)
    write(REPORT/'MESS_SCHEDULE_RECEIPT.json',dict(research_physical_schedule_PASS=True,units=6,
        Pcharge_per_unit_kw=pch,Pdischarge_per_unit_kw=pdis,aggregate_Pcharge_kw=6*pch,aggregate_Pdischarge_kw=6*pdis,
        E_min_kwh=min(r['E_after_kwh'] for r in rows96),E_max_kwh=max(r['E_after_kwh'] for r in rows96),
        terminal_error_kwh=max(abs(x-1140) for x in energy.values()),
        route_and_connection_assumption='initial stationary access research assumption; 600s connection; slot0 no power',
        Native_schedule_certificate=False,field_verified=False,Production_ready=False,Native_calls=0))
    return schedule


def audit_ac_ports(tag,schedule):
    records=read(REPORT/'ac'/tag/'PORT_96.json');desired={(t,s):x for t,a in enumerate(schedule) for s,x in a.items()}
    expected={(t,f'STA{i:02d}') for t in range(96) for i in range(1,13)}
    actual=[(r['slot'],r['site']) for r in records]
    assert len(actual)==len(expected) and len(set(actual))==len(actual) and set(actual)==expected,'PORT_AXIS_COVERAGE'
    errors=[];worst_i=0.;worst_pq=0.
    for r in records:
        assert np.isfinite([r['P_kw'],r['Q_kvar'],r['S_kva'],r['I_max_A'],*r['per_conductor_A']]).all(),'NONFINITE_PORT_READBACK'
        assert np.isfinite(np.asarray(r['per_conductor_PQ'])).all(),'NONFINITE_PORT_LEGS'
        target=desired.get((r['slot'],r['site']),(0.,0.))
        error=max(abs(r['P_kw']-target[0]),abs(r['Q_kvar']-target[1]));worst_pq=max(worst_pq,error);worst_i=max(worst_i,r['I_max_A'])
        if error>1e-6 or abs(r['P_kw'])>5+1e-8 or abs(r['Q_kvar'])>3+1e-8 or r['S_kva']>6+1e-8 or r['I_max_A']>27+1e-8:
            errors.append(dict(slot=r['slot'],site=r['site'],pq_error=error,I_A=r['I_max_A']))
        # split-phase interface has equal opposing-hot current magnitudes.
        assert abs(r['per_conductor_A'][0]-r['per_conductor_A'][1])<1e-6
        if r['slot']==0:assert abs(r['P_kw'])<1e-8 and abs(r['Q_kvar'])<1e-8,'CONNECTION_DELAY'
    result=dict(tag=tag,port_limits_PASS=not errors,errors=errors,actual_AC_PQ_max_error_kw_kvar=worst_pq,
        all12_ports_all96_slots=True,max_hot_current_A=worst_i,split_phase_legs_verified=True,
        stationary_SOC_verified=True,field_GIS_access_protection='UNVERIFIED',Native_calls=0)
    write(REPORT/'ac'/tag/'PORT_SCHEDULE_AUDIT.json',result)
    assert result['port_limits_PASS'],result
    return result
