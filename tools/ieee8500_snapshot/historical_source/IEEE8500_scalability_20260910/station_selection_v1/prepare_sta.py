import csv,json,hashlib,difflib,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
nodes={r['transport_node_id']:r for r in csv.DictReader((BASE/'static_reference/v01_reduced48_nodes_v2.csv').open(encoding='utf-8-sig'))}
services=list(csv.DictReader((BASE/'static_reference/final_service_nodes_24.csv').open(encoding='utf-8-sig')))
allrows=[]
for r in services:
    n=nodes[r['traffic_node']]
    name='A'+r['service_id'] if r['service_type']=='IDC' else r['service_id']
    allrows.append({'location_id':name,'role':'AIDC' if r['service_type']=='IDC' else 'STA','traffic_node':r['traffic_node'],'longitude':float(n['longitude']),'latitude':float(n['latitude'])})
assert len(allrows)==24
lon=np.radians([r['longitude'] for r in allrows]);lat=np.radians([r['latitude'] for r in allrows])
xx=(lon-lon.mean())*math.cos(lat.mean())*6371.0088;yy=(lat-lat.mean())*6371.0088
for r,x,y in zip(allrows,xx,yy):r.update(x_east_km=float(x),y_north_km=float(y))
sta=sorted([r for r in allrows if r['role']=='STA'],key=lambda r:r['location_id'])
assert [r['location_id'] for r in sta]==[f'STA{i:02}' for i in range(1,13)]
for n,r in [('STATIC_24_TRAFFIC_ANCHORS',allrows),('STA_12_TRAFFIC_ANCHORS',sta)]:
    (ROOT/(n+'.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
authority=read(ROOT/'FINAL_AIDC_HOST_AUTHORITY.json');aidc={r['ieee8500_bus'] for r in authority['frozen_mapping']}
guarded=read(BASE/'selection_v3_source_proximity/GUARDED_CANDIDATE_POOL.json')
pool=[r for r in guarded if r['bus'] not in aidc];assert len(pool)==594
(ROOT/'STA_CANDIDATE_POOL.json').write_text(json.dumps(pool,indent=2),encoding='utf-8')
old=(BASE/'selection_v2/select_sites.py').read_text(encoding='utf-8')
new=old.replace("anchors=read(BASE/'audit/melbourne_12_anchors.json')","anchors=read(ROOT/'STA_12_TRAFFIC_ANCHORS.json')")
marker='    dmx=float(D.max());gmx=float(G.max())\n'
extra='''    authority=read(ROOT/'FINAL_AIDC_HOST_AUTHORITY.json')
    fixed={r['ieee8500_bus'] for r in authority['frozen_mapping']}
    rootdist=np.array([f['primary_upstream_impedance_ohm'] for f in features])
    cutoff=float(np.quantile(rootdist,.05,method='linear'))
    assert cutoff==1.3819547376654384
    keep=np.flatnonzero((rootdist>=cutoff)&np.array([b not in fixed for b in ids]))
    ids=ids[keep];xy=xy[keep];groups=groups[keep]
    D=D[np.ix_(keep,keep)];R=R[np.ix_(keep,keep)];G=G[np.ix_(keep,keep)]
    assert len(ids)==594 and set(ids)=={r['bus'] for r in read(ROOT/'STA_CANDIDATE_POOL.json')}
'''
new=new.replace(marker,marker+extra).replace('np.arange(638)','np.arange(len(ids))').replace("f'AIDC{i+1:02}'","f'STA{i+1:02}'")
(ROOT/'select_sta.py').write_text(new,encoding='utf-8')
(ROOT/'SELECTOR_ADAPTATION.diff').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='immutable_v2_selector',tofile='station_selector')),encoding='utf-8')
inputs=['audit/candidate_pool_static_features.json','audit/candidate_pair_metrics.npz','audit/melbourne_12_anchors.json','audit/melbourne_66_pair_geometry.json','audit/primary_corridors.json','audit/methodology_inputs.json','audit/buses.json','static_reference/final_service_nodes_24.csv','static_reference/v01_reduced48_nodes_v2.csv','selection_v3_source_proximity/GUARDED_CANDIDATE_POOL.json','selection_v3_source_proximity/AIDC01_AIDC12_IEEE8500_MAPPING.json','selection_v3_source_proximity/GUARDED_SELECTION_FREEZE_MANIFEST.json']
files=['AGENTS.md','STA_SELECTION_PROCEDURE.md','prepare_sta.py','select_sta.py','SELECTOR_ADAPTATION.diff','FINAL_AIDC_HOST_AUTHORITY.json','STATIC_24_TRAFFIC_ANCHORS.json','STA_12_TRAFFIC_ANCHORS.json','STA_CANDIDATE_POOL.json']
f={'freeze_id':'STA_TOPOLOGY_ONLY_PROCEDURE_BEFORE_SELECTION','original_freeze_sha256':sha(BASE/'FREEZE_MANIFEST.json'),'files':[{'path':n,'sha256':sha(ROOT/n)} for n in files],'inputs':[{'path':n,'sha256':sha(BASE/n)} for n in inputs]}
assert not (ROOT/'PROCEDURE_FREEZE_MANIFEST.json').exists()
(ROOT/'PROCEDURE_FREEZE_MANIFEST.json').write_text(json.dumps(f,indent=2),encoding='utf-8')
print('STA pool',len(pool),'pre-selection freeze',sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json'))
