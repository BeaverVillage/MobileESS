"""Pinned abstract service-road access audit for joint PCC reselection.

No route regeneration, Native, historical launcher, SUMO truth or AC solver.
Traffic service identities remain abstract proxies when PCCs are reassigned.
"""
from pathlib import Path
from datetime import datetime,timezone
import csv,gzip,hashlib,itertools,json,math
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/ieee8500_v42_joint_pcc_reselection'
DATA=ROOT/'ieee8500_v42/data/traffic_audit'
FLEET=ROOT/'docs/ieee8500_v42_single_case/integration_contracts/RESEARCH_FLEET_CONFIGURATION.json'
SLOTS=(0,9,48,68,72,75)
EXPECTED_INITIAL={'MESS01':'STA01','MESS02':'STA12','MESS03':'STA08','MESS04':'STA06','MESS05':'STA03','MESS06':'STA10'}
FORECAST_KEYS=('forecast_day','issue_time','max_input_timestamp','target_timestamps','link_ids',
 'model_id','model_sha','data_sha','graph_sha','normalization_sha','causality_pass','future_actual_read_count')

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(p):return dict(path=str(Path(p).resolve()),sha256=sha(p),bytes=Path(p).stat().st_size)
def write(p,v):
    p=Path(p);assert p.resolve().is_relative_to(ROOT);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def table(p,rows):
    p=Path(p);assert p.resolve().is_relative_to(ROOT);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def csvrows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def node(s):return f'TN_{int(s.removeprefix("TN_")):02d}'

def energy(row,eta,p):
    """Independent longitudinal contract algebra; no learned energy model."""
    d=row['route_distance_km']*1000.;m=p['gross_vehicle_mass_kg'];g=p['gravity_mps2'];e=p['drivetrain_efficiency']
    rolling=m*g*p['rolling_resistance_coefficient']*d/e/3.6e6
    aero=.5*p['air_density_kg_per_m3']*p['air_drag_coefficient']*p['front_surface_area_m2']*(d/eta)**2*d/e/3.6e6
    grade=m*g*(row['cumulative_ascent_m']/e-p['regenerative_braking_efficiency']*row['cumulative_descent_m'])/3.6e6
    return rolling+aero+grade+p['battery_side_auxiliary_power_kw']*eta/3600.

def source_configuration():
    # Reuse the inherited pure SHA verifier, not its launcher or audit main.
    from ieee8500_v42.traffic_mobility_audit import portable_configuration
    return portable_configuration(ROOT)

def load_sources():
    c=source_configuration();paths=c['paths'];services={r['service_id']:r['traffic_node'] for r in csvrows(paths['SERVICE_NODES.csv'])}
    fleet=read(FLEET);assert fleet['initial_locations']==EXPECTED_INITIAL
    assert fleet['physical']['active_power_limit_kw']==450 and fleet['physical']['pcs_kva']==600 and fleet['physical']['capacity_kwh']==1800
    assert len(services)==24 and len(set(services.values()))==24
    raw=gzip.decompress(paths['ROUTE_TABLE.json.gz'].read_bytes());routes=json.loads(raw)
    previous=read(ROOT/'docs/ieee8500_v42_single_case/TRAFFIC_MOBILITY_AUDIT.json')
    assert hashlib.sha256(raw).hexdigest()==previous['route_uncompressed_sha256']
    assert routes['service_ids']==sorted(services) and routes['departure_slots']==list(range(96))
    indexed={}
    for r in routes['routes']:
        key=(r['departure_slot_15'],r['origin_service_id'],r['destination_service_id'])
        if key in indexed:raise ValueError('DUPLICATE_ORIGINAL_ROUTE_KEY')
        indexed[key]=r
    assert set(indexed)==set(itertools.product(range(96),services,services))
    with np.load(paths['TRAFFIC_FORECAST.npz'],allow_pickle=False) as z:
        meta=json.loads(str(z['metadata']));q={k:z[k].copy() for k in ('Q10_sec','Q50_sec','Q90_sec')}
    logical=hashlib.sha256(json.dumps({k:meta[k] for k in FORECAST_KEYS},sort_keys=True,separators=(',',':')).encode())
    for a in q.values():assert a.shape==(288,509) and np.isfinite(a).all();logical.update(np.ascontiguousarray(a,dtype='<f4').tobytes())
    assert logical.hexdigest()==meta['bundle_sha']==read(paths['NATIVE_INPUT.json'])['traffic_forecast_sha']
    graph_manifest=[{k:r[k] for k in ('role','bytes','sha256')} for r in c['graph_records']]
    graph_sha=hashlib.sha256(json.dumps(graph_manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert graph_sha==meta['graph_sha']
    assert meta['forecast_day']=='2025-05-01' and meta['causality_pass'] and meta['future_actual_read_count']==0
    assert datetime.fromisoformat(meta['max_input_timestamp'])<=datetime.fromisoformat(meta['issue_time'])
    order=sorted(csvrows(paths['LINK_ORDER.csv']),key=lambda r:int(r['tensor_index']))
    assert [r['reduced_link_id'] for r in order]==meta['link_ids']
    graph={r['reduced_link_id']:(node(r['from_node']),node(r['to_node'])) for r in order};lengths={}
    with gzip.open(paths['PHYSICAL_EDGE_CATALOG.csv.gz'],'rt',encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):lengths[r['reduced_link_id']]=lengths.get(r['reduced_link_id'],0.)+float(r['length_m'])/1000.
    physics=read(paths['MOBILITY_PHYSICS.json']);assert physics['status']=='FROZEN_PHYSICS_ONLY' and not physics['mobility_energy_ml_loaded']
    assert physics['parameters']['gross_vehicle_mass_kg']==28000
    return dict(config=c,paths=paths,services=services,fleet=fleet,routes=indexed,meta=meta,quantiles=q,
        graph=graph,lengths=lengths,physics=physics,indices={s:i for i,s in enumerate(meta['link_ids'])})

def check_route(r,s):
    t=r['departure_slot_15'];origin=r['origin_service_id'];destination=r['destination_service_id'];links=r['route_link_ids']
    assert r['road_origin_node']==s['services'][origin] and r['road_destination_node']==s['services'][destination]
    cursor=s['services'][origin]
    for link in links:assert s['graph'][link][0]==cursor;cursor=s['graph'][link][1]
    assert cursor==s['services'][destination]
    quantiles=[sum(float(s['quantiles'][q][3*t,s['indices'][link]]) for link in links) for q in ('Q10_sec','Q50_sec','Q90_sec')]
    assert quantiles==[r['route_q10_eta_sec'],r['route_q50_eta_sec'],r['route_q90_eta_sec']]
    assert abs(sum(s['lengths'][link] for link in links)-r['route_distance_km'])<1e-10
    if origin==destination:
        assert not links and r['route_safe_eta_sec']==r['travel_slots_15min']==r['connection_ready_slots_15min']==r['energy_safe_kwh']==0
    else:
        assert r['route_safe_eta_sec']>=quantiles[1]
        assert r['travel_slots_15min']==math.ceil(r['route_safe_eta_sec']/900)
        assert r['connection_ready_slots_15min']==math.ceil((r['route_safe_eta_sec']+600)/900)
        modeled=[energy(r,q,s['physics']['parameters']) for q in quantiles]
        assert abs(modeled[1]-r['energy_nominal_kwh'])<1e-10 and abs(max(modeled)-r['energy_safe_kwh'])<1e-10
    for k in ('route_safe_eta_sec','route_distance_km','energy_safe_kwh'):assert math.isfinite(r[k]) and r[k]>=0
    assert r['traffic_forecast_sha']==s['meta']['bundle_sha'] and r['route_graph_sha']==s['meta']['graph_sha'] and r['physics_contract_sha']==sha(s['paths']['MOBILITY_PHYSICS.json'])

def make_rows(s):
    result=[]
    for t,unit,station in itertools.product(SLOTS,sorted(EXPECTED_INITIAL),[f'STA{i:02d}' for i in range(1,13)]):
        origin=EXPECTED_INITIAL[unit];r=s['routes'][(t,origin,station)];day0=s['routes'][(0,origin,station)]
        check_route(r,s);check_route(day0,s)
        stay=origin==station
        # Canonical route stay offsets remain zero. The new study blocks the
        # initially parked connector until600s; this is explicitly a model assumption.
        ready=t+max(r['connection_ready_slots_15min'],1 if stay and t==0 else 0)
        earliest=max(day0['connection_ready_slots_15min'],1 if stay else 0)
        after=1140-r['energy_safe_kwh']
        result.append(dict(departure_slot=t,vehicle_id=unit,initial_traffic_service=origin,destination_STA=station,
            origin_road_node=r['road_origin_node'],destination_road_node=r['road_destination_node'],
            source_safe_ETA_seconds=r['route_safe_eta_sec'],source_Q50_ETA_seconds=r['route_q50_eta_sec'],source_Q90_ETA_seconds=r['route_q90_eta_sec'],
            source_route_distance_km=r['route_distance_km'],distance_scope='ORIGINAL_ABSTRACT_ROAD_SERVICE_ROUTE_NOT_NEW_PCC_GIS',
            source_travel_slots=r['travel_slots_15min'],source_ready_offset_slots=r['connection_ready_slots_15min'],
            connection_delay_seconds=600,effective_ready_slot=ready,earliest_day0_ready_slot=earliest,
            reachable_from_initial_before_sample_slot=t>=earliest,source_safe_energy_kwh=r['energy_safe_kwh'],
            initial_SOC_kwh=1140.,after_single_move_SOC_kwh=after,original_Emin_kwh=660.,single_move_SOC_margin_kwh=after-660,
            single_abstract_move_ready_within_day=ready<96,single_abstract_move_SOC_PASS=after>=660,
            station_simultaneous_vehicle_capacity=1,connector_capacity_authority='PREREGISTERED_RESEARCH_DESIGN_NOT_FIELD',
            original_stay_offset_preserved=True,initial600s_full_slot_block_assumption=stay and t==0,
            new_electrical_PCC_bus='UNSELECTED_MAPPING_BOUND_SEPARATELY',new_PCC_physical_access='UNVERIFIED',
            field_GIS_direction_status='UNVERIFIED',strict_552_direction_scope='COMMON_PROPER_TRANSFORM_SCHEMATIC_PROXY_REQUIRED_SEPARATELY',
            full_dynamic_dispatch_or_Actual_SUMO_PASS=False,route_links='|'.join(r['route_link_ids']),
            route_forecast_sha=r['traffic_forecast_sha'],route_graph_sha=r['route_graph_sha'],physics_sha=r['physics_contract_sha']))
    return result

def audit():
    prereg=dict(schema='JOINT_TRAFFIC_ACCESS_PREREG_V1',day='2025-05-01',departure_slots=list(SLOTS),initial_locations=EXPECTED_INITIAL,
        requested_rows=6*12*len(SLOTS),origin_interpretation='independent hypothetical departure from original initial location; not vehicle position after an unmodeled previous move',
        route_selection='unchanged original unique route per servicepair/departure; no shortest-path or effect retuning',
        connection_seconds=600,initial_stay_slot0_blocked=True,station_capacity_units=1,
        station_capacity_authority='explicit research connector assumption; mutually exclusive simultaneous units required in dispatch',
        physical_PCC_access='UNVERIFIED',strict_552_constraints_relaxed=False,Actual_for_selection=False,Native_calls=0,AC_solves=0)
    target=REPORT/'TRAFFIC_ACCESS_PREREGISTRATION.json'
    if target.exists():assert read(target)==prereg,'TRAFFIC_PREREG_DRIFT'
    else:write(target,prereg)
    s=load_sources();rows=make_rows(s);assert len(rows)==432
    table(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv',rows)
    prior_May02=[record(p) for p in sorted((ROOT/'docs/ieee8500_v42_high_impact_scenario/ac').glob('*/RECEIPT.json')) if read(p).get('day')=='2025-05-02']
    write(REPORT/'TRAFFIC_ACCESS_SOURCE_RECEIPT.json',dict(schema='JOINT_TRAFFIC_SOURCE_RECEIPT_V1',
        planning_abstract_route_input_PASS=True,rows=len(rows),original24_service_identities=s['services'],
        preregistration=record(target),output=record(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv'),producer=record(Path(__file__)),
        source_manifest=record(DATA/'SOURCE_MANIFEST.json'),original_source_proof=record(DATA/'ORIGINAL_SOURCE_SHA_PROOF.json'),
        inherited_auditor=record(ROOT/'ieee8500_v42/traffic_mobility_audit.py'),fleet=record(FLEET),
        verified_portable_originals=s['config']['records'],original_route_rows=len(s['routes']),
        original_mass_kg=28000,mass_applicability_to1800kWh_pack='UNVERIFIED',physical_field_access_PASS=False,
        exact_new_PCC_route_distance_certified=False,all552_new_mapping_directions_checked_here=False,
        source_safeETA_calibration_refit=False,safeETA_as_of_ingestion='UNVERIFIED_INHERITED',
        full_six_vehicle_schedule_SOC_occupancy_or_Actual_replay_certified=False,
        May02_prior_IEEE123_exposed=True,May02_current_IEEE8500_high_case_AC_exposed=bool(prior_May02),
        May02_saved_high_case_AC_exposure_receipts=prior_May02,
        May02_new_joint_scope='separate fixed-case paired engineering check; no unseen IEEE8500 holdout claim',
        Native_calls=0,AC_solves=0,route_generation_calls=0,Actual_Sumo_reads=0,campaign_writes=0))
    print('Joint traffic source audit:',len(rows),'abstract rows; new PCC physical access UNVERIFIED',flush=True)
    return rows

if __name__=='__main__':audit()
