"""One-time V41R3 fast-path authority freeze and targeted input binding."""
from pathlib import Path
from datetime import datetime, timezone
import json, shutil, hashlib
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'MobileESS_v41r2_780gpu_capacity_rebase'
OLD_RUN=OLD/'frozen_artifacts/v41r2_780'
RUN=ROOT/'frozen_artifacts/v41r3_scale'
OUT=ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze'
SCALE=ROOT/'dayahead/artifacts/v41r3_scale_rebalance'
FORENSIC=ROOT/'dayahead/artifacts/v41r3_native_voltage_control_forensic'
DAY='2025-05-04'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def record(p):
    p=Path(p).resolve()
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
    assert read(p)==v
def check(s):return (s['convergence_count']==96 and s['Vmin_pu']>=.95 and s['Vmax_pu']<=1.05 and s['rho_max_AC']<1 and s['transformer_phase_current_loading_max']<1 and s['transformer_total_kva_loading_max']<1)
def copy(p,q):
    q.parent.mkdir(parents=True,exist_ok=True)
    if q.exists():assert record(p)['sha256']==record(q)['sha256']
    else:shutil.copyfile(p,q)
    return dict(source=record(p),local=record(q))
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json').exists()
    gate=read(FORENSIC/'FINAL_FORENSIC_CONSISTENCY_GATE.json')
    assert gate['status']=='PASS' and all(g['status']=='PASS' for g in gate['gates'])
    assert gate['primary_classification']=='B) DAYAHEAD_TAP_FREEZE_CAUSES_ACTUAL_OVERVOLTAGE'
    protection=read(SCALE/'V41R3_IMMUTABILITY_VERIFICATION.json')
    # Read back certified manifests, never rescan the protected history.
    manifests=[SCALE/'PROTECTED_BEFORE.json',SCALE/'V41R3_IMMUTABILITY_VERIFICATION.json',SCALE/'V41R3_FINAL_FREEZE.json',FORENSIC/'FORENSIC_FINAL_SEAL.json',FORENSIC/'FINAL_FORENSIC_CONSISTENCY_GATE.json']
    save(OUT/'REUSED_PROTECTION_AND_FORENSIC_RECEIPT.json',dict(status='PASS',manifests=[record(p) for p in manifests],protected_file_full_rehash_count=0,forensic_replays=0,forensic_classification=gate['primary_classification']))
    selected_da=SCALE/'screen/alpha_1.600/DAYAHEAD';selected_actual=FORENSIC/'runs/alpha_1.600/B'
    candidates=[]
    for p in sorted((SCALE/'screen').glob('alpha_*/DAYAHEAD/SUMMARY.json')):
        s=read(p);a=s['alpha_BG'];ap=FORENSIC/'runs'/f'alpha_{a:.3f}'/'B/SUMMARY.json'
        actual=read(ap) if ap.exists() else None
        candidates.append(dict(alpha_BG=a,dayahead=s,actual_native=actual,dayahead_source=record(p),actual_source=record(ap) if actual else None,eligible=bool(check(s) and actual and check(actual) and .75<=s['rho_max_AC']<=.85)))
    chosen=min((c for c in candidates if c['eligible']),key=lambda c:abs(c['dayahead']['rho_max_AC']-.8))
    assert chosen['alpha_BG']==1.6
    selected_refs=[]
    for folder in (selected_da,selected_actual):
        for rel in ('SUMMARY.json','physics/OPENDSS_PHASE_ARRAYS.npz','physics/OPENDSS_SUMMARY.json','mapper/MAPPER_AUDIT.json','readback/ENGINE_MAPPING_RATINGS_SOURCE.json','readback/OPENDSS_COMPONENTS_96.parquet','grid/BUS_PHASE_VOLTAGES.parquet','grid/BRANCH_PHASE_CURRENTS.parquet','grid/FEEDER_SYSTEM_96.parquet'):
            selected_refs.append(record(folder/rel))
        assert read(folder/'mapper/MAPPER_AUDIT.json')['status']=='PASS'
        for k in ('AIDC_power_source','background_source','scaled_background'):
            ref=read(folder/'SUMMARY.json').get(k)
            if ref:assert record(ref['path'])['sha256']==ref['sha256']
    save(OUT/'V41R3_ACTUAL_NATIVE_CONTROL_AUTHORITY.json',dict(status='FROZEN',created_at=datetime.now(timezone.utc).isoformat(),forensic_gate=record(FORENSIC/'FINAL_FORENSIC_CONSISTENCY_GATE.json'),primary_classification=gate['primary_classification'],RegControl='NATIVE_AUTONOMOUS_ACTUAL',D00_initial_state='Corresponding Day-Ahead slot-0 tap/cap state',later_slots='Previous Actual final regulator tap state carried forward; native static SolveSnap response',independent_tap_resets_after_D00=0,future_information=False,lookahead=False,operator_redispatch=False,AIDC_MESS_route_migration_decisions='FROZEN',optimization_calls_in_Actual=0,CapControl_count=0,capacitors='Original fixed shunts; passive Q(V) is not switching',control_settings_changed=False))
    save(OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json',dict(status='FROZEN',selected_alpha_BG=1.6,selection_rule='Closest Day-Ahead B0 rho to 0.80 among already evaluated eligible native-Actual candidates in [0.75,0.85]; no further refinement',scaling='P_BG and Q_BG only, same factor in Day-Ahead and Actual',B1_B2_B3_USED_FOR_SELECTION=False,selection_reused_existing_replays=True,additional_alpha_replays=0,candidates=candidates,selected_measurements=chosen,reused_selected_artifacts=selected_refs,original_background_provenance=record(SCALE/'V41R3_BACKGROUND_INPUT_PROVENANCE.json')))
    save(OUT/'V41R3_MESS_POWER_AUTHORITY.json',dict(status='FROZEN',old=dict(P_MAX_kW=550,PCS_kVA=700,energy_kWh=1200),new=dict(P_MAX_kW=300,PCS_kVA=400,energy_kWh=1200),units=4,fleet_P_nameplate_MW=1.2,P_trust_radius_kW=30,Q_trust_radius_kvar=40,polygon_faces=16,service_transformer_kVA=750,energy_SOC_mobility_route_traffic_service_semantics='UNCHANGED',B0_B1='MESS_OFF',B2_B3='NOT_AUTHORIZED',Full_May='HOLD'))
    copies=[]
    for group in ('inputs/'+DAY,'actual_inputs/'+DAY):
        for p in (OLD_RUN/group).rglob('*'):
            if p.is_file():copies.append(copy(p,RUN/p.relative_to(OLD_RUN)))
    # Only the static files read by the active entry points are materialized.
    for rel in ('dayahead/artifacts/v41r1_pending_running_migration/V41_POLICY_REGISTRY_FREEZE.json',):
        copies.append(copy(OLD/rel,ROOT/rel))
    save(OUT/'TARGETED_INPUT_COPIES.json',dict(status='PASS',copies=copies,no_ML_execution=True))
    print('FAST_AUTHORITIES_FROZEN alpha=1.6 nativeActual MESS=300/400; copied',len(copies),flush=True)
if __name__=='__main__':main()
