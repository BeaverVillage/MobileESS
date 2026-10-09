"""Seal the single May01 research configuration without Production promotion."""
from .run_ac import REPORT,HIGH,ROOT,DAY,read,write,receipt,sha,rows


REQUIRED=('JOINT_PLACEMENT_PREREGISTRATION.json','PRIOR_MV_STA_INFEASIBILITY_SCOPE_AUDIT.md',
    'AIDC_MV_CANDIDATES.csv','STA_MV_LV_CANDIDATES.csv','ELECTRICAL_REGION_DISPERSION_AUDIT.csv',
    'TRAFFIC_ETA_ACCESS_AUDIT.csv','AIDC_CONTROLLABILITY_SCORES.csv','MESS_CONTROLLABILITY_SCORES.csv',
    'JOINT_LOCATION_SELECTION.csv','P0_PCC_MAPPING_COMPARISON.csv','MV_PORT_RATING_AUDIT.csv',
    'BG085_B0_PLANNING_AC_96.csv','FINAL_B0_PLANNING_ACTUAL_FRESH.csv','CRITICAL_CORRIDOR_CONTROL_AUDIT.csv',
    'AIDC_MESS_JOINT_PRECHECK.csv','PHYSICAL_CONSTRAINT_AUDIT.csv','FINAL_SCENARIO_DECISION_KO.md','FINAL_REVIEW_KO.md')


def run():
    path=REPORT/'SINGLE_MAY01_RESEARCH_CONFIGURATION_SHA.json'
    if path.exists():raise RuntimeError('RESEARCH_FREEZE_ALREADY_EXISTS; preserve rather than silently rewrite')
    for name in REQUIRED:assert (REPORT/name).is_file(),name
    config=read(REPORT/'SELECTED_RESEARCH_CONFIGURATION.json')
    mapping=REPORT/'JOINT_LOCATION_SELECTION.csv'
    assert sha(mapping)==config['mapping']['sha256']
    verification=read(REPORT/'INDEPENDENT_VERIFICATION.json')
    assert verification['all_case_grid_security_PASS'] and len(verification['cases'])==19
    assert all(r['day']==DAY for r in verification['cases'])
    records=read(REPORT/'RUN_RECEIPT.json')['records'];assert len(records)==4
    maps=rows(mapping);assert len(maps)==24 and len({r['candidate_bus'] for r in maps})==24
    assert sum(r['role']=='STA' and r['connection_mode']=='MV_3PH' for r in maps)==12
    facts=dict(schema='SINGLE_MAY01_ENGINEERING_RESEARCH_FREEZE_V1',day=DAY,slots=96,case='C2',BG=.85,
        installed_GPU=780,AIDC_count=12,STA_count=12,STA_MV=12,STA_LV=0,MESS_units=6,
        MESS_Pmax_kw=450,MESS_Smax_kva=600,MESS_E_kwh=1800,MESS_Emin=660,MESS_Emax=1620,
        MESS_initial_terminal_kwh=1140,dedicated_port_transformers=12,dedicated_port_transformer_kva=750,
        MV_port_VLL=480,MV_port_phase_current_limit_A=721.6878364870322,new_primary_conductors=0,
        source_pu=1.04,all12_Vreg=123.5,CAPBank3_OFF=True,common_P5=True,
        all_original_DSS_ratings_preserved=True,original_min_rho_max_preserved=True,
        original_May01_UID_GPUgang_runtime_submission_requested_GPUh_preserved=True,
        synthetic_or_replicated_workload=False,admissible_AIDC_action_in_this_validation_kw=0,
        nonzero_AIDC_QoS_WAN_checkpoint='UNVERIFIED; zero action does not prove zero physical potential',
        snapshot_MESS_schedule='fixed original six initial sites, charge8..15 discharge68..75 Q0; proxy access assumption',
        per_vehicle_charge_kw=252.6315789473684,per_vehicle_discharge_kw=228,
        field_hardware_GIS_protection_access_ETA='UNVERIFIED',
        full_P450_Q300_rectangle='NOT_CERTIFIED: 20 of190 instantaneous endpoints overvoltage',
        optimizer_B0_B1_B2_B3_performance='NOT_RUN; no long Solver calls; no effect-based retuning',
        research_frozen_before_long_policy_optimization=True,Production_configuration_frozen=False,
        Production_status='BLOCKED_UNVERIFIED',Native_calls=0,
        evidence={n:receipt(REPORT/n) for n in ('MAY01_EXECUTION_SCOPE_OVERRIDE.json','MAY01_SENSITIVITY_EXECUTION_REUSE.json',
            'SELECTED_RESEARCH_CONFIGURATION.json','JOINT_LOCATION_SELECTION.csv','RUN_RECEIPT.json',
            'INDEPENDENT_VERIFICATION.json','PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.json','LOCAL_DENSE_AC_RETENTION.json',
            'JSON_TRANSPORT_ROUNDTRIP_VERIFICATION.json','CAMPAIGN_PRESERVATION_REFERENCE.json','EXECUTION_EFFICIENCY.json')},
        source_files={str(p.relative_to(ROOT)):receipt(p) for d in ('ieee8500_v42_high','ieee8500_v42_joint')
            for p in sorted((ROOT/d).glob('*.py'))})
    write(path,facts)
    (REPORT/'SINGLE_MAY01_RESEARCH_CONFIGURATION_SHA.sha256').write_text(sha(path)+'  '+path.name+'\n',encoding='ascii')
    return facts

if __name__=='__main__':run()
