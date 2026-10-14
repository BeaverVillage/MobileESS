"""Read-only numeric migration authority and named packet fixtures; Native0."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import pickle
import sys

ROOT=Path('D:/v42_experimental_flex_qos_20261014')
NATIVE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
OUT=ROOT/'audit/migration'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from v42_integration.policy import migration_guard,ReservationLedger,digest


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def record(p):
    p=Path(p);b=p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def write(name,doc):(OUT/name).write_text(json.dumps(doc,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


OUT.mkdir(parents=True,exist_ok=True)
static=Path('D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01/dates/B1/2025-05-01/output/STATIC/DATA/DATA.pkl')
template=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
power_path=template.with_name('POWER_AUTHORITY.json')
manifest_path=Path('D:/MobileESS_V42/docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_MANIFEST.json')
contract_path=NATIVE/'pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json'
authority_path=NATIVE/'dayahead/v38/authority.py'
manifest=read(manifest_path)
rows=manifest.get('files',manifest if isinstance(manifest,list) else [])
for target in (contract_path,authority_path):
    expected=next(r for r in rows if Path(r['path'])==target)
    actual=record(target)
    assert actual['bytes']==expected['bytes'] and actual['sha256']==expected['sha256']
with static.open('rb') as stream:data=pickle.load(stream)
saved,resources=data[0],data[3]
current=read(template);contract=read(contract_path);power=read(power_path)
wan=saved['WAN']
assert wan==current['WAN']
assert resources.bytes_per_gpu==wan['bytes_per_gpu']==80000000000
assert resources.restart_slots==1 and resources.max_active_transfers==wan['maximum_active_transfers']==1
links={}
for row in contract['undirected_links']:
    link='--'.join(sorted((row['a'],row['b'])))
    per5=math.floor(row['capacity_mbps']*1000000/8*300)
    per15=3*per5
    assert wan['link_capacity_bytes_15min'][link]==[per15]*96
    assert all(resources.wan_capacities[link,t]==per15 for t in range(24,120))
    assert all(resources.wan_capacities[link,t]==0 for t in range(24))
    links[link]=dict(capacity_Mbit_per_second=row['capacity_mbps'],bytes_per_5min=per5,
        bytes_per_15min=per15,bandwidth_bytes_per_second=per15/900,constant_96_slots=True)
routes={}
for row in wan['paths']:
    src,dst=row['source'],row['destination'];path=tuple(row['links'])
    assert resources.paths[src,dst]==path
    route='OD'+src[-2:]+'_'+dst[-2:]+'_FIXED'
    routes[route]=dict(source=src,destination=dst,links=list(path),hop_count=len(path),
        bottleneck_bytes_per_15min=min(links[l]['bytes_per_15min'] for l in path),
        bandwidth_bytes_per_second=min(links[l]['bandwidth_bytes_per_second'] for l in path))
assert len(routes)==132 and len(links)==15
sources=[record(p) for p in (static,template,manifest_path,contract_path,authority_path,
    NATIVE/'pfr/migration.py',NATIVE/'dayahead/v38/contracts.py',power_path,
    ROOT/'v42_temporal/native.py',ROOT/'v42_job_capability.py',ROOT/'v42_integration/policy.py',
    ROOT/'v42_integration/actual.py',ROOT/'tests/test_v42_integration_actual.py')]
base=dict(schema='EXPERIMENTAL_MIGRATION_SOURCE_NUMERIC_AUTHORITY_V1',
    policy_id='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',written_utc=datetime.now(timezone.utc).isoformat(),
    mode='SOURCE_NUMERIC_AUDIT_AND_NAMED_GUARD_FIXTURE_ONLY',source_receipts=sources,
    Native_Optimize_calls=0,Actual_runs=0,AC_calls=0,code_edits=0,
    future_Actual_runtime_or_UID_inputs_used=False,Raw_modified=False,
    old_PR222_PR223_and_budget_ledgers_unchanged=True)
numeric=dict(checkpoint_interval_seconds=1800,control_slot_seconds=900,bytes_per_GPU=80000000000,
    historical_restart_seconds=300,current_conservative_restart_seconds=resources.restart_slots*900,
    maximum_active_transfers_network_wide=1,maximum_migrations_per_job=1,
    WAN_link_count=15,WAN_OD_route_count=132,network_capacity_mbps_values=[2480.,9920.],
    bandwidth_bytes_per_second_values=[310000000.,1240000000.],
    source_residency='PRESTAGED_AT_ALL_12_IDCS_DECLARED_CASE_STUDY',
    source_Kestrel_measured_checkpoint_bytes=False,source_Kestrel_observed_WAN_geography=False)
write('MIGRATION_SOURCE_NUMERIC_AUTHORITY.json',dict(base,status='FROZEN_NUMERIC_WAN_PAYLOAD_RESTART_PASS;REQUEST_CAPABILITY_IS_EXPERIMENTAL',
    exact_original_May_manifest_contract_and_authority_SHA=True,saved_static_WAN_equals_current_template=True,
    all_static_native_24to119_capacities_equal_original_96_slot_WAN=True,
    native_0to23_WAN_capacity_is_zero=True,scalar_authority=numeric,links=links,routes=routes,
    route_length_counts=dict(Counter(r['hop_count'] for r in routes.values())),
    equations=dict(payload='80_000_000_000 * observed_requested_GPU * explicit_payload_factor',
        rate='floor(capacity_Mbit_per_sec*1_000_000/8*300)*3/900 bytes/sec',
        route_transfer='max(900,ceil(payload_bytes/bottleneck_bytes_per_second/900)*900)',
        restart='ceil(physical_restart_seconds/900)*900;minimum900 in common guard',
        interruption='ceil(physical_checkpoint/900)*900 - physical_checkpoint + source_wait + transfer + restart',
        shared_budget='additional_start_delay + cumulative_migration_interruption + new_interruption <= contract_budget',
        link_payload='Each ordered route link receives full checkpoint payload;not payload divided by hop count'),
    source_vs_assumed=dict(SOURCE_FROZEN_MODEL_VALUES=numeric,
        ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT='E1/E2 participating observed requests only;not Kestrel checkpoint capability observation',
        ASSUMED_EXPERIMENTAL_GPU_MODEL_COMPATIBILITY='Logical rack/gang model capacity is source-backed;raw request GPUtype provenance remains unconfirmed unless present',
        ASSUMED_DATA_RESIDENCY='Reuse declared prestaging all12 case-study;missing input bytes is not silently zero-filled',
        HOLD_PHASE_CHOICE='Old JSON has no source_hold_until/destination_hold_from. Common fixture supports source_until_transfer_start,destination_from_transfer_end;tag explicit experimental protocol choice.',
        SOURCE_WAIT='Default0 means immediate earliest transfer attempt subject to ledger feasibility;not measured latency or zero transfer/restart.',
        LATENCY='NO_AUTHORITATIVE_LATENCY_AVAILABLE;no separate RTT/propagation field in frozen model',
        CHECKPOINT_SERIALIZATION='No separate checkpoint-save IO delay/power coefficient found;payload transfer model scope must be disclosed',
        WAN_ENERGY='No frozen joules_per_byte/network_power coefficient found;NULL/UNMODELED_NOT_ZERO'),
    energy=dict(idle_kW_per_installed_GPU=power['current_IT_idle_kW_per_installed_GPU'],
        active_swing_kW_per_GPU=power['current_IT_swing_kW_per_active_GPU'],power_factor=power['PF_AIDC'],
        IT_formula='idle*installed_GPU + swing*physical_GPU_occupation including explicit source/destination holds',
        PCC_formula='exact frozen C1 IT/weather callback;Q=P*tan(acos(.95))',
        hold_incremental_IT_kWh='swing_kW_per_GPU * gang_GPU * held_seconds /3600;installed idle baseline retained',
        occupancy_is_compute=False,compute_paused_during_transfer_restart=True,
        total_compute_service_preserved=True,separate_WAN_transfer_energy_kWh=None,
        separate_checkpoint_serialization_energy_kWh=None,missing_energy_assumed_zero=False,
        total_migration_energy_full_physics_claim='NOT_ESTABLISHED;GPUholdC1included,WAN/serialization coefficients unbound'),
    horizon_scope=dict(original_native_restart_end_strictly_before_control_end=120,
        historical_episode_boundary_policy=contract['placement_optimizer']['episode_boundary_policy'],
        common_Actual_engine_can_persist_cross_midnight_inflight=True,
        required_disclosure='Native planning episode constraint and commonActualcarry semantics differ;no post96grid/AC certificate may be inferred. Inherit native bound if claiming that exact planning contract.'),
    approved_source_parameter_factors=contract['checkpoint']['january_development_sensitivity_factors'],
    user_new_research_sensitivity_factors=[.5,1.,2.],
    expanded_factor2_is_old_source_authority=False))

rows=[]
for gang in (1,4,16,32,64,80,100):
    compatible=[s for s in current['capacities'] if gang<=current['capacities'][s] and
        gang<=max(r['compatibility_GPU_limit'] for r in current['racks'] if r['aidc_id']==s)]
    for bandwidth in (310000000.,1240000000.):
        for payload_factor in (.5,1.,2.):
            for restart_factor in (.5,1.,2.):
                payload=80000000000*gang*payload_factor
                transfer=max(900,math.ceil(payload/bandwidth/900)*900)
                restart=max(900,math.ceil(900*restart_factor/900)*900)
                interruption=transfer+restart
                rows.append(dict(gang=gang,compatible_model_sites=compatible,
                    distinct_source_destination_rack_pair_exists=len(compatible)>=2,
                    bandwidth_bytes_per_second=bandwidth,payload_factor=payload_factor,payload_bytes=payload,
                    physical_restart_sensitivity_seconds=900*restart_factor,conservative_restart_seconds=restart,
                    transfer_seconds=transfer,interruption_seconds_at_aligned_checkpoint=interruption,
                    checkpoint_roundup_wait_seconds=0,source_wait_seconds=0,
                    E1_Normal30m_budget_fits=interruption<=1800,E1_Standby60m_budget_fits=interruption<=3600,
                    E2_Normal60m_budget_fits=interruption<=3600,E2_Standby120m_budget_fits=interruption<=7200,
                    source_or_experimental='SOURCE_BASE_NUMERIC' if payload_factor==restart_factor==1 else 'EXPLICIT_USER_RESEARCH_SENSITIVITY'))
write('MIGRATION_PAYLOAD_RESTART_SENSITIVITY.json',dict(base,rows=rows,
    sensitivity_changes_authority_or_source_inputs=False,original_numeric_baseline_unchanged=True,
    physical_zero_transfer_restart_forbidden=True,
    restart_half_factor_effect='450secondsconservativelyceilsto900;no hidden sub-control-grid restart reduction',
    budget_fit_is_not_whole_gang_resource_or_grid_certificate=True,real_eligible_job_counts='NOT_EVALUATED_HERE'))

protocol=dict(source_hold_until='transfer_start',destination_hold_from='transfer_end',
    label='EXPLICIT_EXPERIMENTAL_HOLD_PROTOCOL_REUSING_VALIDATED_COMMON_FIXTURE')
packet_source_sha=digest(dict(sources=sources,protocol=protocol,policy=base['policy_id']))
def packet(gang,route):
    r=routes[route]
    return dict(source_sha=packet_source_sha,checkpoint_authorized=True,allowed_destinations=[r['destination']],
        gpu_type_confirmed=True,rack_gang_confirmed=True,data_residency_confirmed=True,wan_path=route,
        bandwidth_bytes_per_second=r['bandwidth_bytes_per_second'],payload_bytes=80000000000*gang,
        restart_seconds=900,source_wait_seconds=0,source_hold_until=protocol['source_hold_until'],
        destination_hold_from=protocol['destination_hold_from'],assumption=True,
        assumption_class='ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT',route_links=r['links'],
        measured_Kestrel_capability=False,capability_confirmation_basis='FROZEN_MODEL_COMPATIBILITY_AND_EXPLICIT_EXPERIMENTAL_RIGHTS')
fixture_results=[]
for gang,route,budget in ((1,'OD01_02_FIXED',1800),(4,'OD01_06_FIXED',1800),(4,'OD01_06_FIXED',3600),(16,'OD01_06_FIXED',7200)):
    cap=packet(gang,route);r=routes[route]
    metadata=dict(uid='NAMED_MIGRATION_NUMERIC_FIXTURE',is_observed=True,state='RUNNING',migration_count=0,
        migration_capability=cap,current_site=r['source'],gpu=gang,additional_start_delay_seconds=0,
        cumulative_migration_interruption_seconds=0)
    receipt=dict(uid=metadata['uid'],budget_seconds=budget)
    ledger=ReservationLedger(current['capacities'],{route:r['bandwidth_bytes_per_second']})
    result,reason=migration_guard(metadata,receipt,now=1800,accumulated_compute_seconds=1800,
        destination=r['destination'],remaining_nominal_seconds=3600,reservations=ledger,checkpoint_at=1800)
    fixture_results.append(dict(evidence_kind='NAMED_GUARD_FIXTURE_NOT_REAL_JOB',gpu=gang,route=route,budget=budget,
        packet=cap,reason=reason,receipt=result,Native_Optimize_calls=0,Actual_runs=0,AC_calls=0))
assert fixture_results[0]['reason']=='AUTHORIZED' and fixture_results[1]['reason']=='SHARED_DELAY_INTERRUPTION_BUDGET_EXCEEDED'
assert fixture_results[2]['reason']==fixture_results[3]['reason']=='AUTHORIZED'
write('MIGRATION_PACKET_API_HANDOFF.json',dict(base,packet_source_sha=packet_source_sha,
    common_guard='v42_integration.policy.migration_guard',common_Actual_recorder='JobEventController._record_migration',
    packet_required_fields=list(packet(1,'OD01_02_FIXED')),example_packets_and_guard_results=fixture_results,
    construction_recipe='Build per observedGPU/currentSource/destination,bindoriginal132ODroute+80GBperGPU+900restart+explicitE1/E2assumptionreceipt;never inspect futureactualruntime/UID.',
    per_destination_packet_required=True,one_generic_wan_path_for_multiple_destinations_forbidden=True,
    ledger_WAN_capacities={route:r['bandwidth_bytes_per_second'] for route,r in routes.items()},
    route_bottleneck_proxy_equivalence=dict(conditions=['all15linkcapacitiesconstant96','globaloneactiveWANtransfer',
        'fullpayloadcarriedoneachrouteLink','sameconservative15mintransferquantization'],
        capacity_and_transfer_duration_equivalent=True,full_per_link_ledger_identity=False,
        last_slot_bandwidth_reservation_can_exceed_payload=True,
        transmitted_bytes_proof='EmitactualpayloadonEACHorderedlink;bandwidth*roundedtransfer is reservation upper bound,not transmittedbytes'),
    source_wait_zero_is_not_zero_transfer_or_restart=True,
    shared_30min_Normal_budget_minimum='transfer900+restart900 leaveszero roomforroundup/sourcewait/priorStartDelay;unalignedcheckpoint maylegallyfail',
    policy_no_forced_migration=True,protocol=protocol,
    precise_energy_scope='GPUholdoccupation flows through existingFrozenPowerModel/C1;separateWAN/saveIOenergyNULLunmodeled,not zero',
    request_level_authority='EXPERIMENTAL_ASSUMPTION_NOT_SOURCE_VERIFIED_Kestrel_capability'))
print(json.dumps(dict(links=len(links),routes=len(routes),numeric=numeric,sensitivity_rows=len(rows),
    fixture_reasons=[r['reason'] for r in fixture_results],Native_Optimize_calls=0,Actual_runs=0,AC_calls=0)))
