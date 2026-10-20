"""Read original traffic authority and retain exact route/XY identities."""
from .preflight import *
import gzip
import shutil
import xml.etree.ElementTree as ET

SUMO=Path('//wsl.localhost/Ubuntu-MobileESS-D/home/jaewon/mobile_ess_sumo/research_pipeline')
FREEZE=SUMO/'21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1/freeze_assets'
NODES=SUMO/'04_frozen_topology/v01_reduced48_final_v2_package/v01_reduced48_nodes_v2.csv'
SERVICES=FREEZE/'stage8/optimizer_interface/final_service_nodes_24.csv'
LINKS=SUMO/'10_ml_stage1_multires_traffic_v1/graph/link_order_509.csv'
NET=SUMO/'24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile/network/network_elevated_conditioned.net.xml'

def readcsv(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def prepare():
    native_path=Path('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1/2025-05-01/NATIVE_INPUT.json')
    native=json.loads(native_path.read_text(encoding='utf-8-sig'))
    declared=json.loads((ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json').read_text())['days'][0]['files']
    for key in ['native','route_table','traffic_forecast']:
        if sha(declared[key]['path'])!=declared[key]['sha256']:raise ValueError('R043_TRAFFIC_SHA_DRIFT:'+key)
    route=Path(declared['route_table']['path']);forecast=Path(declared['traffic_forecast']['path'])
    table=json.loads(gzip.decompress(route.read_bytes()))
    services=readcsv(SERVICES);nodes=readcsv(NODES);links=readcsv(LINKS)
    historical_manifest=Path('D:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v40d_actual_realized_replay/pre_day_complete_preflight/INPUT_SOURCE_MANIFEST.json')
    historical=json.loads(historical_manifest.read_text())['files'];upstream=[]
    for source in [SERVICES,LINKS,NET]:
        expected=next(r for k,r in historical.items() if Path(k).name==source.name)
        actual=sha(source)
        if actual!=expected['sha256']:raise ValueError('UPSTREAM_TRAFFIC_AUTHORITY_DRIFT:'+source.name)
        upstream.append(dict(path=str(source),sha256=actual,historical_sha256=expected['sha256'],PASS=True))
    topology_manifest=NODES.parent/'v01_reduced48_topology_manifest_final_v2.json'
    expected=json.loads(topology_manifest.read_text())['source_file_sha256'][NODES.name]
    if sha(NODES)!=expected:raise ValueError('FROZEN_NODE_COORDINATE_AUTHORITY_DRIFT')
    junctions={r['junction_id'] for r in nodes};xy={}
    for _,el in ET.iterparse(NET,events=['end']):
        if el.tag=='junction' and el.get('id') in junctions:xy[el.get('id')]=(float(el.get('x')),float(el.get('y')))
        el.clear()
    if len(xy)!=len(junctions):raise ValueError('ORIGINAL_SUMO_XY_MISSING')
    by={r['transport_node_id']:r for r in nodes};rows=[]
    for s in services:
        n=by[s['traffic_node']];x,y=xy[n['junction_id']]
        routes=[r for r in table['routes'] if r['origin_service_id']==s['service_id']]
        if {r['road_origin_node'] for r in routes}!={s['traffic_node']}:raise ValueError('SERVICE_NODE_MAPPING_DRIFT')
        rows.append(dict(service_id=s['service_id'],aidc_id=s['service_id'].replace('IDC','AIDC') if s['service_type']=='IDC' else '',
            type=s['service_type'],traffic_node=s['traffic_node'],junction_id=n['junction_id'],x=x,y=y,
            longitude=n['longitude'],latitude=n['latitude'],original_feeder_bus=s['feeder_bus']))
    csvout('ORIGINAL_TRAFFIC_SERVICES.csv',rows)
    csvout('ORIGINAL_TRAFFIC_NODES.csv',[dict(**n,x=xy[n['junction_id']][0],y=xy[n['junction_id']][1]) for n in nodes])
    target=RUNTIME/'traffic';target.mkdir(exist_ok=True)
    receipts=[]
    for p in [route,forecast,NODES,SERVICES,LINKS]:
        dest=target/p.name;shutil.copyfile(p,dest)
        if sha(dest)!=sha(p):raise ValueError('TRAFFIC_COPY_DRIFT')
        receipts.append(dict(source=str(p),copy=str(dest),sha256=sha(p),bytes=p.stat().st_size))
    receipts.append(dict(source=str(NET),sha256=sha(NET),bytes=NET.stat().st_size,copied=False))
    save('TRAFFIC_IDENTITY_VERIFICATION.json',dict(route_table_PASS=True,service_ID_and_XY_PASS=True,
        full_network_file_hash_recorded=True,service_sites=24,IDC=12,STA=12,
        route_count=len(table['routes']),slots=table['departure_slots'],
        immutable_route_fields=list(table['routes'][0]),receipts=receipts,
        traffic_forecast_sha=native['traffic_forecast_sha'],
        source_algorithm_sha=FROZEN,original_IDC_to_AIDC_alias='IDCnn traffic service corresponds to AIDCnn workload; no ID permutation',
        charging_capability='Native FULL gives STAY/PQ variables at every service site; separate port-count authority not found in native input. No port capacity PASS asserted.',
        movement_only_site_definition='Not separately represented in audited native solve; unresolved physical infrastructure authority',
        scope='Exact r043 May01 route/forecast receipts and original upstream service/node/network authority; SCATS model not re-executed'))
    identity=json.loads((DOC/'TRAFFIC_IDENTITY_VERIFICATION.json').read_text())
    identity.update(upstream_historical_authority=upstream,historical_manifest=str(historical_manifest),
                    topology_node_SHA_PASS=True,topology_manifest=str(topology_manifest))
    save('TRAFFIC_IDENTITY_VERIFICATION.json',identity)
    save('AIDC_JOB_AUDIT.json',dict(source_path=str(native_path),source_sha=sha(native_path),
        sites=native['capacities'],racks=native['racks'],battery=native['battery'],
        total_jobs=len(native['known_population']),
        descriptor_permission_counts={k:sum(bool(r[k]) for r in native['known_population'])
            for k in ['can_timeshift','can_prestart_place','can_checkpoint_migrate','FLEX','FIX']},
        actual_flexibility_certified=False,
        reason='Count of descriptors is not a feasible timeshift/migration witness; Ckt24 PCC/AC and exact scheduler replay required',
        descriptor_keys=list(native['known_population'][0])))
    print('TRAFFIC_VERIFIED',len(rows),len(xy),len(table['routes']))

if __name__=='__main__':prepare()
