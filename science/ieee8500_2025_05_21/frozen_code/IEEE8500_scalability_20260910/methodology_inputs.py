"""Static features only. This script never chooses a 12-bus set."""
import csv, hashlib, json, math
from collections import defaultdict, Counter, deque
from pathlib import Path
import numpy as np
from scipy.spatial.distance import pdist, squareform

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'audit'
STATIC=ROOT/'static_reference'
STATIC.mkdir(exist_ok=True)
WSL=Path(r'\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline')
paths=[WSL/'04_frozen_topology/v01_reduced48_final_v2_package/v01_reduced48_nodes_v2.csv', WSL/'21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1/freeze_assets/stage8/optimizer_interface/final_service_nodes_24.csv']
manifest=[]
for p in paths:
    data=p.read_bytes(); (STATIC/p.name).write_bytes(data)
    manifest.append({'path':str(p),'local_copy':p.name,'sha256':hashlib.sha256(data).hexdigest(),'unchanged_after_read':hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(data).hexdigest()})
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
nodes=list(csv.DictReader((STATIC/paths[0].name).open(encoding='utf-8-sig')))
services=list(csv.DictReader((STATIC/paths[1].name).open(encoding='utf-8-sig')))
nd={n['transport_node_id']:n for n in nodes}
anchors=[]
for s in services:
    if s['service_type']!='IDC':continue
    n=nd[s['traffic_node']]
    assert n['node_role']=='IDC_ANCHOR'
    assert n['model_idc_id'].replace('_','')==s['service_id']
    anchors.append({'aidc_id':'A'+s['service_id'],'service_id':s['service_id'],'traffic_node':s['traffic_node'],'model_idc_id':n['model_idc_id'],'longitude':float(n['longitude']),'latitude':float(n['latitude'])})
anchors.sort(key=lambda a:a['aidc_id']);assert len(anchors)==12
lon=np.radians([a['longitude'] for a in anchors]);lat=np.radians([a['latitude'] for a in anchors])
xy=np.column_stack([(lon-lon.mean())*math.cos(lat.mean())*6371.0088, (lat-lat.mean())*6371.0088])
dm=squareform(pdist(xy)); dm_norm=dm/math.sqrt(np.mean(pdist(xy)**2))
for a,p in zip(anchors,xy):a.update(x_east_km=float(p[0]),y_north_km=float(p[1]))
anchor_pairs=[{'aidc_i':anchors[i]['aidc_id'],'aidc_j':anchors[j]['aidc_id'],'distance_km':float(dm[i,j]),'distance_rms_normalized':float(dm_norm[i,j])} for i in range(12) for j in range(i+1,12)]

buses=read(OUT/'buses.json');edges=read(OUT/'topology_edges.json');lines=read(OUT/'lines.json');bd={b['bus']:b for b in buses}
eligible=sorted(b['bus'] for b in buses if b['selection_ready'])
primary={b['bus'] for b in buses if abs(b['kv_base_sqrt3']-12.47)<0.01247 and set(b['nodes'])=={1,2,3}}
pair_edges=defaultdict(list)
for e in edges:
    if e['u'] in primary and e['v'] in primary:pair_edges[tuple(sorted((e['u'],e['v'])))].append(e)
ld={'line.'+l['name']:l for l in lines}
adj=defaultdict(dict);corridors=[]
for (u,v),ee in sorted(pair_edges.items()):
    weights=[]
    for e in ee:
        if e['kind']=='line':
            l=ld[e['element']];n=l['phases']
            weights.extend(math.hypot(l['r_matrix'][i*n+i],l['x_matrix'][i*n+i])*l['length'] for i in range(n))
    w=sum(weights)/len(weights) if weights else 0.0
    # Regulator banks are identity connectors in this static placement metric.
    adj[u][v]=w;adj[v][u]=w
    corridors.append({'u':u,'v':v,'elements':[e['element'] for e in ee],'weight_ohm':w,'regulator_identity_connector':not weights})
root='_hvmv_sub_lsb';parent={root:None};depth={root:0.0};order=[root]
for u in order:
    for v,w in sorted(adj[u].items()):
        if v not in parent:parent[v]=u;depth[v]=depth[u]+w;order.append(v)
assert set(eligible).issubset(parent)
children=defaultdict(list)
for b,p in parent.items():
    if p is not None:children[p].append(b)
count={b:int(b in eligible) for b in parent}
for b in reversed(order):
    if parent[b] is not None:count[parent[b]]+=count[b]
threshold=math.ceil(0.05*len(eligible));spine=[];laterals=[];u=root
while True:
    spine.append(u)
    if not children[u]:break
    cc=sorted(children[u],key=lambda b:(-count[b],b));main=cc[0]
    for v in cc[1:]:
        if count[v]>=threshold:laterals.append({'root':v,'junction':u,'eligible_descendants':count[v]})
    u=main
labels={b:'TRUNK_OR_MINOR_LATERAL' for b in eligible}
for l in laterals:
    q=[l['root']]
    while q:
        u=q.pop();q.extend(children[u])
        if u in labels:labels[u]='MAJOR:'+l['root']
paths_up={}
for b in eligible:
    chain=[];u=b
    while parent[u] is not None:chain.append(u);u=parent[u]
    paths_up[b]=set(chain)
N=len(eligible);dt=np.zeros((N,N));sr=np.zeros((N,N))
for i,b in enumerate(eligible):
    for j in range(i):
        c=eligible[j];common=paths_up[b]&paths_up[c]
        shared=sum(adj[u][parent[u]] for u in common)
        dist=depth[b]+depth[c]-2*shared
        dt[i,j]=dt[j,i]=dist
        denom=depth[b]+depth[c]-shared
        sr[i,j]=sr[j,i]=shared/denom if denom else 1.0
geo=np.array([[bd[b]['x'],bd[b]['y']] for b in eligible]);gd=pdist(geo);td=dt[np.triu_indices(N,1)]
metrics={'candidate_count':N,'primary_ABC_graph_buses':len(parent),'primary_ABC_graph_corridors':len(corridors),'root':root,'major_lateral_threshold_fraction':0.05,'major_lateral_threshold_count':threshold,'major_laterals':laterals,'major_lateral_count':len(laterals),'candidate_group_sizes':dict(Counter(labels.values())),'geometry_crs':'Unknown; original Buscoords planar x/y, normalized only','electrical_distance_definition':'Sum of mean absolute diagonal entries of line series Z matrices times native DSS length; three phase-separated series links averaged over ABC; regulator banks are zero-weight identity connectors. No power-flow result.','pair_count':len(td),'electrical_pair_distance_ohm_min':float(td.min()),'electrical_pair_distance_ohm_q05':float(np.quantile(td,.05,method='linear')),'electrical_pair_distance_ohm_median':float(np.median(td)),'electrical_pair_distance_ohm_max':float(td.max()),'geographic_pair_distance_native_q05':float(np.quantile(gd,.05,method='linear')),'geographic_pair_distance_native_max':float(gd.max()),'static_model_anchors':12,'selected_sites':[],'selection_optimizer_executed':False}

def write(name,obj):
    (OUT/(name+'.json')).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
    if isinstance(obj,list) and obj:
        with (OUT/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(obj[0]));w.writeheader();w.writerows(obj)
write('melbourne_static_sources',manifest);write('melbourne_12_anchors',anchors);write('melbourne_66_pair_geometry',anchor_pairs)
write('primary_corridors',corridors);write('methodology_inputs',metrics)
write('candidate_pool_static_features',[{'bus':b,'x':bd[b]['x'],'y':bd[b]['y'],'primary_upstream_impedance_ohm':depth[b],'lateral_group':labels[b],'selected':False} for b in eligible])
np.savez_compressed(OUT/'candidate_pair_metrics.npz',buses=np.array(eligible),electrical_tree_distance_ohm=dt,shared_upstream_path_ratio=sr,geographic_xy=geo)
print(json.dumps(metrics,indent=2))
