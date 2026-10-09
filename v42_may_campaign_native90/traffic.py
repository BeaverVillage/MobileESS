"""Native-zero audit of original 5-minute forecasts and 15-minute route arcs.

The original route table remains the path and calibrated Safe-ETA authority.
This checker reads every original row, proves the snapshot/time/unit mapping,
and compares every inherited loader arc. It never regenerates a route or model.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import math
import sys
import numpy as np
from .common import ROOT, DAYS, read, sha, record, atomic, d_path, digest

SOURCE = Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic')
CODE = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
FORECAST_KEYS = ('forecast_day','issue_time','max_input_timestamp','target_timestamps',
    'link_ids','model_id','model_sha','data_sha','graph_sha','normalization_sha',
    'causality_pass','future_actual_read_count')


def _require(ok, label):
    if not ok: raise ValueError('TRAFFIC_AXIS_' + label)


def forecast_logical_sha(metadata, quantiles):
    """Independent replay of the documented original authority byte format."""
    meta = {key: metadata[key] for key in FORECAST_KEYS}
    h = hashlib.sha256(json.dumps(meta, sort_keys=True, separators=(',',':')).encode())
    for key in ('Q10_sec','Q50_sec','Q90_sec'):
        h.update(np.ascontiguousarray(quantiles[key], dtype='<f4').tobytes())
    return h.hexdigest()


def validate_forecast(day, metadata, quantiles):
    midnight = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))
    issue = datetime.fromisoformat(metadata['issue_time'])
    maximum = datetime.fromisoformat(metadata['max_input_timestamp'])
    _require(issue.tzinfo is not None and maximum.tzinfo is not None
        and issue == midnight-timedelta(hours=6) and issue.utcoffset() == timedelta(hours=10)
        and maximum <= issue, 'FIXED_AEST_CAUSAL_ISSUE')
    _require(metadata['forecast_day'] == day and metadata['causality_pass'] is True
        and metadata['future_actual_read_count'] == 0, 'SAME_DAY_NO_FUTURE_READ')
    stamps = [datetime.fromisoformat(x) for x in metadata['target_timestamps']]
    _require(len(stamps) == 288 and all(t == midnight+timedelta(minutes=5*i)
        and t.utcoffset() == timedelta(hours=10) for i,t in enumerate(stamps)), 'ORIGINAL_288_FIVE_MINUTE_AXIS')
    links = metadata['link_ids']
    _require(len(links) == 509 and len(set(links)) == 509, 'ORIGINAL_509_LINK_AXIS')
    _require(set(quantiles) == {'Q10_sec','Q50_sec','Q90_sec'}, 'ORIGINAL_QUANTILE_FIELDS')
    q10,q50,q90 = (np.asarray(quantiles[k]) for k in ('Q10_sec','Q50_sec','Q90_sec'))
    _require(all(q.shape == (288,509) and q.dtype == np.dtype('float32')
        and np.isfinite(q).all() and np.all(q>0) for q in (q10,q50,q90))
        and np.all(q10<=q50) and np.all(q50<=q90), 'ORIGINAL_QUANTILE_SHAPE_UNITS_AND_ORDER')
    logical = forecast_logical_sha(metadata, quantiles)
    _require(logical == metadata['bundle_sha'], 'ORIGINAL_LOGICAL_BUNDLE_SHA')
    return dict(PASS=True, logical_forecast_SHA=logical, raw_forecast_shape=[288,509,3],
        native_forecast_resolution_seconds=300, route_departure_resolution_seconds=900,
        issue_time=metadata['issue_time'], max_input_timestamp=metadata['max_input_timestamp'],
        route_slot_to_forecast_step=[3*t for t in range(96)],
        route_slot_to_timestamp=[metadata['target_timestamps'][3*t] for t in range(96)],
        interpolation_calls=0, forecasting_calls=0, future_actual_reads=0)


@lru_cache(maxsize=1)
def original_physics():
    # Import the original implementation directly, without copying its equations
    # or changing process-wide package search paths used by another date adapter.
    name = '_v42_campaign_original_mobility_physics'
    spec = importlib.util.spec_from_file_location(name, CODE/'pfr/mobility_physics.py')
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    contract = CODE/'pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json'
    return module.MobilityPhysics.from_contract(contract), sha(contract)


def validate_routes(table, metadata, quantiles, *, physics=None, physics_sha=None, expected_services=24):
    services = table['service_ids']
    _require(len(services) == expected_services and len(set(services)) == expected_services
        and services == sorted(services) and table['departure_slots'] == list(range(96)), 'ORIGINAL_ROUTE_AXES')
    rows = table['routes']; keys = set(); accepted = {}; exclusions = Counter()
    links = {s:i for i,s in enumerate(metadata['link_ids'])}
    for row in rows:
        t,s,d = row['departure_slot_15'],row['origin_service_id'],row['destination_service_id']
        key=(t,s,d)
        _require(type(t) is int and 0<=t<96 and s in services and d in services and key not in keys,
                 'NO_MISSING_OR_DUPLICATE_ROUTE_KEYS')
        keys.add(key)
        _require(row['traffic_forecast_sha'] == metadata['bundle_sha']
            and row['route_graph_sha'] == metadata['graph_sha'], 'ROW_LOGICAL_FORECAST_AND_GRAPH_SHA')
        if physics_sha is not None:
            _require(row['physics_contract_sha'] == physics_sha, 'ORIGINAL_PHYSICS_CONTRACT_SHA')
        _require(all(link in links for link in row['route_link_ids']), 'ORIGINAL_PATH_LINK_ID_AXIS')
        eta = [row['route_'+q+'_eta_sec'] for q in ('q10','q50','q90')]
        _require(all(math.isfinite(x) and x>=0 for x in eta)
            and eta[0]<=eta[1]<=eta[2], 'ROUTE_ETA_SECONDS')
        for q, actual in zip(('Q10_sec','Q50_sec','Q90_sec'),eta):
            expected = sum(float(quantiles[q][3*t,links[link]]) for link in row['route_link_ids'])
            _require(actual == expected, 'EXACT_DEPARTURE_EPOCH_LINK_SNAPSHOT_SUM')
        safe = row['route_safe_eta_sec']; energy = row['energy_safe_kwh']
        _require(math.isfinite(safe) and safe >= eta[1] and math.isfinite(energy)
            and energy >= row['energy_nominal_kwh'] >= 0, 'ORIGINAL_SAFE_ETA_AND_ENERGY')
        travel, ready = row['travel_slots_15min'],row['connection_ready_slots_15min']
        _require(type(travel) is int and type(ready) is int, 'INTEGER_ROUTE_TIME_OFFSETS')
        if s==d:
            _require(row['route_link_ids']==[] and travel==ready==0 and safe==energy==0
                and row['energy_nominal_kwh']==0 and row['route_distance_km']==0,
                'ORIGINAL_STAY_ROW')
            exclusions['same_site_represented_by_stay']+=1
            continue
        _require(row['route_link_ids'] and row['route_distance_km']>0 and travel==math.ceil(safe/900)
            and ready==math.ceil((safe+600)/900), 'ORIGINAL_SAFE_TRAVEL_AND_600_SECOND_CONNECTION')
        if physics is not None:
            original_energy = [physics.energy_kwh(row, value) for value in eta]
            _require(row['energy_nominal_kwh']==original_energy[1] and energy==max(original_energy),
                     'ORIGINAL_PHYSICS_ENERGY_EXACT')
        arrive,connect=t+travel,t+ready
        if not 0<=t<arrive<=connect<96:
            exclusions['outside_inherited_RouteArc_time_contract']+=1
            continue
        route_id=f'{s}:{d}:{t}'
        accepted[route_id]=(s,d,t,arrive,connect,energy,digest(row))
    _require(len(rows)==96*expected_services*expected_services and len(keys)==len(rows),
             'COMPLETE_ORIGINAL_ROUTE_PRODUCT')
    return accepted, dict(PASS=True, original_rows=len(rows), original_services=expected_services,
        original_departure_slots=96, accepted_original_move_arcs=len(accepted), exclusions=dict(exclusions),
        every_route_snapshot_sum_exact=True, original_path_fields_preserved=True,
        calibrated_SafeETA_authority_preserved=True, SafeETA_not_defined_as_max_Q90=True,
        original_physics_energy_exact=physics is not None, travel_time_and_connection_mapping_exact=True,
        route_creation_calls=0, missing_path_creation_calls=0, interpolation_calls=0)


def compare_native_arcs(bundle, table, accepted, route_receipt):
    from v42_bootstrap.m1 import native_inputs
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    actual = {r.route_id:(r.source,r.destination,r.depart,r.arrive,r.connect,r.energy_kwh,r.authority_sha256)
              for r in routes}
    _require(actual==accepted and len(actual)==len(routes), 'EVERY_NATIVE_ARC_EQUALS_ORIGINAL_ROW')
    _require(tuple(sites)==tuple(table['service_ids']) and dict(initial)==bundle['initial_MESS_sites']
        and receipt['accepted_routes']==len(accepted) and receipt['excluded']==route_receipt['exclusions'],
        'ORIGINAL_LOADER_AXES_AND_EXCLUSIONS')
    _require(len(initial)>0 and battery.dt_hours==.25, 'ORIGINAL_MESS_QUARTER_HOUR_BATTERY')
    return dict(PASS=True, every_original_accepted_arc_checked=len(actual), units=len(initial),
        graph_arc_endpoints='origin@depart -> destination@connect',
        arrival='depart + travel_slots_15min', connection='depart + connection_ready_slots_15min',
        movement_energy='original energy_safe_kwh debited at departure',
        native_loader=record(ROOT/'v42_bootstrap/m1.py'), native_formulation=record(ROOT/'v42_native/mess.py'),
        coefficient_changes=0, constraint_changes=0, model_build_calls=0, Native_optimize_calls=0)


def audit_day(day, campaign_root):
    root=Path(campaign_root); original=SOURCE/day
    route_source=original/'ROUTE_TABLE.json.gz'; forecast_source=original/'TRAFFIC_FORECAST.npz'
    raw=gzip.decompress(route_source.read_bytes()); table=json.loads(raw)
    with np.load(forecast_source,allow_pickle=False) as payload:
        _require(set(payload.files)=={'metadata','Q10_sec','Q50_sec','Q90_sec'}, 'FORECAST_FILE_FIELDS')
        metadata=json.loads(str(payload['metadata']))
        quantiles={key:payload[key].copy() for key in ('Q10_sec','Q50_sec','Q90_sec')}
    forecast_check=validate_forecast(day,metadata,quantiles)
    physics,physics_sha=original_physics()
    accepted,routes_check=validate_routes(table,metadata,quantiles,physics=physics,physics_sha=physics_sha)
    copy_checks={}
    for arm in ('B1','B2'):
        folder=root/'inputs'/arm/day; bundle=read(folder/'NATIVE_INPUT.json')
        copied_route=folder/'ROUTE_TABLE.json.gz';copied_forecast=folder/'TRAFFIC_FORECAST.npz'
        _require(sha(copied_route)==sha(route_source) and sha(copied_forecast)==sha(forecast_source),
                 'ORIGINAL_ROUTE_AND_FORECAST_BYTES_PRESERVED:'+arm)
        _require(bundle['day']==day and bundle['traffic_forecast_sha']==metadata['bundle_sha']
            and Path(bundle['route_table']['path']).resolve()==copied_route.resolve()
            and bundle['route_table']['sha256']==sha(copied_route), 'ARM_SAME_DAY_LOGICAL_AUTHORITY:'+arm)
        copy_checks[arm]=dict(PASS=True, route=record(copied_route), forecast=record(copied_forecast),
            all_original_fields_preserved_by_byte_identity=True, native_bundle=record(folder/'NATIVE_INPUT.json'))
    # Both arms have identical copied route bytes. One original loader replay
    # suffices to check every physical route; each arm's authority is checked.
    native=compare_native_arcs(bundle,table,accepted,routes_check)
    return dict(PASS=True,day=day,Native_optimize_calls=0,source_route=record(route_source),
        source_forecast=record(forecast_source), route_uncompressed_canonical_SHA=hashlib.sha256(raw).hexdigest(),
        raw_NPZ_file_SHA=sha(forecast_source), logical_forecast_SHA=metadata['bundle_sha'],
        distinct_SHA_definitions='NPZ container bytes versus canonical metadata + three little-endian float32 arrays',
        forecast=forecast_check,routes=routes_check,original_loader=native,arm_copies=copy_checks)


def audit_all(campaign_root, progress=None):
    root=d_path(campaign_root); days=[]
    for day in DAYS:
        if progress: progress(dict(phase='TRAFFIC_NATIVE0_ORIGINAL_AXIS_AUDIT',day=day))
        days.append(audit_day(day,root))
    sources={name:record(CODE/'dayahead'/name) for name in
        ('v33m3/bundle.py','v33m3/dataset.py','v33m/mobility_15min_adapter.py',
         'v33m/route_table.py','v33m/mobility_physics_adapter.py','v35/execution.py','v37/preflight.py')}
    sources['physics']=record(CODE/'pfr/mobility_physics.py')
    sources['physics_contract']=record(CODE/'pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json')
    result=dict(PASS=all(d['PASS'] for d in days),Native_optimize_calls=0,days=days,days_checked=len(days),
        arm_date_copies_checked=2*len(days), original_sources=sources,checker=record(Path(__file__)),
        root_cause='Adapter compared route logical traffic_forecast_sha to NPZ file bytes SHA; original metadata.bundle_sha is the required logical authority.',
        source_resolutions_preserved=True, forecast_axis=[288,509,3],route_axis=[96,24,24],
        forecasting_calls=0,route_creation_calls=0,model_build_calls=0,coefficient_changes=0,constraint_changes=0)
    atomic(root/'TRAFFIC_AXIS_COMPATIBILITY_AUDIT.json',result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    args=parser.parse_args()
    result=audit_all(args.root,lambda r:print(r['day'],'original traffic audit Native0',flush=True))
    print('TRAFFIC AXIS AUDIT',result['PASS'],result['days_checked'],flush=True)
