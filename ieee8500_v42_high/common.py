from ieee8500_v42_aemo.common import *

AEMO_REPORT=REPORT
BALANCED_REPORT=ROOT/'docs/ieee8500_v42_balanced_case'
REPORT=ROOT/'docs/ieee8500_v42_high_impact_scenario'
PARENT='35079f458fc9d87a469ebd79e0e5d2cb7bd5fe1e'
SOURCE=ROOT/'ieee8500_v42/data/feeder'
BG_CANDIDATES=(.552,.65,.75,.85,.95)
CAPACITY_CANDIDATES=('C0','C1','C2')


def preregister():
    REPORT.mkdir(parents=True,exist_ok=True)
    document=dict(schema='HIGH_IMPACT_PREREG_V1',parent_commit=PARENT,development_day='2025-05-01',
        independent_date_priority=['2025-05-02'],date_rule='earliest next date with complete pinned inputs, before any AC outcome; prior IEEE123 exposure disclosed',
        BG_candidates=list(BG_CANDIDATES),capacity_candidates=dict(C0=780,C1=1170,C2=1560),
        interpolation_allowed=False,maximum_BG_full_day_trials=15,all_trials_Planning_only=True,
        candidate_priority='minimum installed expansion C0 then C1 then C2; within first capacity having target+AC eligible candidates, minimum abs(rho_all-.8), then lowerBG',
        Planning_target_range=[.75,.85],target_center=.8,hard_voltage=[.95,1.05],all_original_ratings=True,
        selected_Actual_fail='reportFAIL; do not refitBG orGPU orpolicy',
        PV_capacity_and_shapes_unchanged=True,Fixed_BG_scaled_once_no_time_shape=True,
        P5=dict(source=1.04,Vreg_all12=123.5,CAPBank3=[0],original_CapControls=9),
        facility_extension='same job IDs/occupancy/service; additional GPUs idle only; missing rack/server/cooling/nameplate remainsUNVERIFIED',
        MESS_interfaces=dict(L0=dict(P_kw=5,Q_kvar=3,S_kva=6,I_hot_A=27),M1=dict(P_kw=150,S_kva=600),
                             M2=dict(P_kw=300,S_kva=600),M3=dict(P_kw=450,S_kva=600)),
        vehicle=dict(units=6,P_kw=450,S_kva=600,E_kwh=1800,Emin_kwh=660,Emax_kwh=1620,Einitial_kwh=1140,Eterminal_kwh=1140,eta_ch=.95,eta_dis=.95),
        same_STA_MV_rule='exact original upstream-primary proxy must have continuous12.47kV ABC, elseFAIL',
        relocation_rule='separateengineeringcase, fixedAIDC12, all606 sourceguardedABC domains, geometricdistance/tieIDs only, all276pair signs, frozenproperfit; noACeffectranking',
        relocation_GIS_ETA_protection='UNVERIFIED field; originaltrafficID/ETA proxy unchanged and audited; not certifiedphysicalaccess',
        interface_selection_priority=['L0','M1','M2','M3'],interface_selection='all96 bounded schedule security+engineeringlimits before anyB1-B3; reportall, noeffect thresholdretuning',
        finite_slots=[0,9,48,72,75],finite_peak_rule='addselectedB0 globalpeak andPrimarypeak',
        nonzero_AIDC_schedule='onlyoriginalQoS/wholegang/service/deadline/WAN/backlogcertificate; otherwiseFAIL andzero-control replay',
        MESS_schedule='sixinitialports stationary, slot0connectionblock600s, gridblind40slotscharge/dischargeenergybalanced withinoriginalSOC; noeffect-driven timing',
        MESS_timing_rule='charge slots8..15 (02:00-04:00), discharge slots68..75 (17:00-19:00), equalbatteryenergy; restzero; Q=0; fixedbeforeAC',
        MESS_discharge_schedule_limit='min(portPmax, (Einitial-Emin)*eta_dis/(8*.25), (Emax-Einitial)*eta_ch*eta_dis/(8*.25))',
        all_phase_P_Q='threephase PCS equalbalancedP/Q; notBphase-only',
        latest_algorithm_edits=False,B1_B2_B3_Native_calls=0,final_paper_or_Production_freeze=False)
    path=REPORT/'SCENARIO_PREREGISTRATION.json'
    if path.exists():assert read(path)==document,'PREREGISTRATION_MUTATION'
    else:write(path,document)
    return document


def inputs(capacity='C0',source='PLANNING',day='2025-05-01'):
    if day=='2025-05-01':
        path=ROOT/'ieee8500_v42_high/data/facility'/f'{capacity}_{source}_INPUTS.npz'
        if capacity=='C0' and not path.exists():path=DATA/'derived'/f'{source}_INPUTS.npz'
    else:path=ROOT/'ieee8500_v42_high/data/validation'/day/'derived'/f'{source}_INPUTS.npz'
    return path
