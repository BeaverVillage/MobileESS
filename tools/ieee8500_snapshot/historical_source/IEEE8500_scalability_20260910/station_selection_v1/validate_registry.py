import csv,hashlib,json,math
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def save(name,data):
    (ROOT/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False,default=lambda x:x.item()),encoding='utf-8')
    if isinstance(data,list) and data:
        with (ROOT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader()
            for r in data:w.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()})

def shape(X,Y,names):
    x=X-X.mean(0);y=Y-Y.mean(0);xn=x/np.sqrt(np.mean(np.sum(x*x,axis=1)));yn=y/np.sqrt(np.mean(np.sum(y*y,axis=1)))
    u,s,v=np.linalg.svd(xn.T@yn);rot=u@np.diag([1,np.linalg.det(u@v)])@v
    ec=float(np.sqrt(np.mean(np.sum((xn@rot-yn)**2,axis=1))))
    dx=np.array([math.dist(X[i],X[j]) for i in range(len(X)) for j in range(i+1,len(X))]);dy=np.array([math.dist(Y[i],Y[j]) for i in range(len(Y)) for j in range(i+1,len(Y))])
    ep=float(np.sqrt(np.mean((dx/np.sqrt(np.mean(dx*dx))-dy/np.sqrt(np.mean(dy*dy)))**2)))
    nn=[]
    for i,name in enumerate(names):
        a=sorted((j for j in range(len(X)) if j!=i),key=lambda j:(math.dist(X[i],X[j]),names[j]))[:2]
        b=sorted((j for j in range(len(Y)) if j!=i),key=lambda j:(math.dist(Y[i],Y[j]),names[j]))[:2]
        nn.append({'location_id':name,'Melbourne_2NN':[names[j] for j in a],'electrical_geography_2NN':[names[j] for j in b],'retained_count':len(set(a)&set(b))})
    return {'E_coord':ec,'E_pair':ep,'nearest_neighbor_retention':sum(r['retained_count'] for r in nn)/(2*len(X)),'retained_2NN_relations':sum(r['retained_count'] for r in nn),'det_rotation':float(np.linalg.det(rot))},nn,{'melbourne_aligned':(xn@rot).tolist(),'selected_normalized':yn.tolist()}

def run():
    proc=read(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')
    for r in proc['inputs']:assert sha(BASE/r['path'])==r['sha256']
    for r in proc['files']:assert sha(ROOT/r['path'])==r['sha256']
    authority=read(ROOT/'FINAL_AIDC_HOST_AUTHORITY.json')
    original=read(BASE/authority['source_mapping_path']);assert original==authority['frozen_mapping']
    result=read(ROOT/'search_summary.json');assert result['status']=='PENDING_INDEPENDENT_VERIFICATION'
    sta=result['mapping'];assert set(sta)=={f'STA{i:02}' for i in range(1,13)}
    fixed={r['aidc_id']:r['ieee8500_bus'] for r in original};allmap={**fixed,**sta};assert len(set(allmap.values()))==24
    pool={r['bus']:r for r in read(BASE/'audit/candidate_pool_static_features.json')}
    guarded={r['bus'] for r in read(BASE/'selection_v3_source_proximity/GUARDED_CANDIDATE_POOL.json')}
    buses={r['bus']:r for r in read(BASE/'audit/buses.json')}
    anchors={r['location_id']:r for r in read(ROOT/'STATIC_24_TRAFFIC_ANCHORS.json')}
    adj=defaultdict(dict)
    for e in read(BASE/'audit/primary_corridors.json'):adj[e['u']][e['v']]=e['weight_ohm'];adj[e['v']][e['u']]=e['weight_ohm']
    root='_hvmv_sub_lsb';parent={root:None};depth={root:0.};hops={root:0};order=[root]
    for u in order:
        for v,w in sorted(adj[u].items()):
            if v not in parent:parent[v]=u;depth[v]=depth[u]+w;hops[v]=hops[u]+1;order.append(v)
    assert len(parent)==647
    paths={};paths_nodes={};registry=[]
    for name,b in sorted(allmap.items()):
        assert b in guarded and buses[b]['selection_ready'] and not buses[b]['eligibility_exclusions']
        assert set(buses[b]['nodes'])=={1,2,3} and abs(buses[b]['kv_base_sqrt3']-12.47)<.01247 and depth[b]>=1.3819547376654384
        edges=set();nodes=[];u=b
        while u is not None:
            nodes.append(u)
            if parent[u] is not None:edges.add(tuple(sorted([u,parent[u]])))
            u=parent[u]
        paths[b]=edges;paths_nodes[b]=nodes[::-1]
        registry.append({'location_id':name,'location_role':'AIDC' if name.startswith('AIDC') else 'STA','is_MESS_service_location':True,'traffic_anchor':anchors[name]['traffic_node'],'ieee8500_bus':b,'phases':'ABC','nominal_kv_ll':12.47,'bus_x':pool[b]['x'],'bus_y':pool[b]['y'],'coordinate_units':'original_unknown_CRS','feeder_depth_hops':hops[b],'electrical_root_distance_ohm':depth[b],'group_id':pool[b]['lateral_group'],'host_authority_status':'FINAL_IMMUTABLE' if name.startswith('AIDC') else 'TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE','PCC_created':False})
    reg={r['location_id']:r for r in registry}
    def pair(a,b):
        x,y=reg[a],reg[b];u=x['ieee8500_bus'];v=y['ieee8500_bus']
        common=paths[u]&paths[v];C=sum(adj[i][j] for i,j in sorted(common));union=sum(adj[i][j] for i,j in sorted(paths[u]|paths[v]));D=sum(adj[i][j] for i,j in sorted(paths[u]^paths[v]))
        return {'location_i':a,'location_j':b,'bus_i':u,'bus_j':v,'LCA_bus':next(k for k in paths_nodes[u][::-1] if k in paths_nodes[v]),'shared_upstream_impedance_ohm':C,'upstream_union_impedance_ohm':union,'shared_path_ratio':C/union,'electrical_tree_distance_ohm':D,'geographic_distance_original_units':math.hypot(x['bus_x']-y['bus_x'],x['bus_y']-y['bus_y']),'Melbourne_distance_km':math.hypot(anchors[a]['x_east_km']-anchors[b]['x_east_km'],anchors[a]['y_north_km']-anchors[b]['y_north_km'])}
    sn=sorted(sta);an=sorted(fixed);pairs=[pair(sn[i],sn[j]) for i in range(12) for j in range(i+1,12)];cross=[pair(a,b) for a in an for b in sn]
    X=np.array([[anchors[n]['x_east_km'],anchors[n]['y_north_km']] for n in sn]);Y=np.array([[reg[n]['bus_x'],reg[n]['bus_y']] for n in sn])
    metrics,neighbors,alignment=shape(X,Y,sn)
    metrics.update(min_electrical_distance_ohm=min(r['electrical_tree_distance_ohm'] for r in pairs),mean_electrical_distance_ohm=float(np.mean([r['electrical_tree_distance_ohm'] for r in pairs])),max_shared_ratio=max(r['shared_path_ratio'] for r in pairs),mean_shared_ratio=float(np.mean([r['shared_path_ratio'] for r in pairs])),min_geographic_distance_original_units=min(r['geographic_distance_original_units'] for r in pairs),min_STA_root_distance_ohm=min(depth[b] for b in sta.values()),group_occupancy=dict(Counter(reg[n]['group_id'] for n in sn)))
    assert metrics['E_coord']<=.20 and metrics['E_pair']<=.20 and metrics['nearest_neighbor_retention']>=.5
    assert metrics['min_electrical_distance_ohm']>=.9129072401559803 and metrics['min_geographic_distance_original_units']>=2221.532547954318
    assert abs(metrics['E_coord']-result['metrics']['ec'])<1e-12 and abs(metrics['E_pair']-result['metrics']['ep'])<1e-12
    cross_summary={'pair_count':144,'hard_spacing_threshold_applied':False,'same_electrical_bus_count':sum(r['bus_i']==r['bus_j'] for r in cross)}
    for field in ['shared_path_ratio','electrical_tree_distance_ohm','geographic_distance_original_units','Melbourne_distance_km']:
        cross_summary[field]={'min':min(r[field] for r in cross),'mean':float(np.mean([r[field] for r in cross])),'max':max(r[field] for r in cross)}
    cross_summary['maximum_shared_pair']=max(cross,key=lambda r:r['shared_path_ratio'])
    cross_summary['minimum_electrical_distance_pair']=min(cross,key=lambda r:r['electrical_tree_distance_ohm'])
    cross_summary['pairs_below_STA_electrical_spacing_reference']=sum(r['electrical_tree_distance_ohm']<.9129072401559803 for r in cross)
    cross_summary['pairs_below_STA_geographic_spacing_reference']=sum(r['geographic_distance_original_units']<2221.532547954318 for r in cross)
    d1=np.array([r['Melbourne_distance_km'] for r in cross]);d2=np.array([r['geographic_distance_original_units'] for r in cross])
    cross_summary['cross_pair_RMS_normalized_geographic_shape_error']=float(np.sqrt(np.mean((d1/np.sqrt(np.mean(d1*d1))-d2/np.sqrt(np.mean(d2*d2)))**2)))
    xa=np.array([[anchors[n]['x_east_km'],anchors[n]['y_north_km']] for n in an]);ya=np.array([[reg[n]['bus_x'],reg[n]['bus_y']] for n in an]);ac=xa-xa.mean(0);bc=ya-ya.mean(0)
    u,s,v=np.linalg.svd(ac.T@bc);rot=u@np.diag([1,np.linalg.det(u@v)])@v;scale=float(np.sum((ac@rot)*bc)/np.sum(ac*ac));pred=(X-xa.mean(0))@rot*scale+ya.mean(0)
    norm=float(np.sqrt(np.mean(np.sum(bc*bc,axis=1))));errors=np.linalg.norm(Y-pred,axis=1)
    cross_summary['STA_RMS_residual_to_fixed_AIDC_similarity_in_AIDC_RMS_radii']=float(np.sqrt(np.mean(errors*errors))/norm)
    cross_summary['cross_geometry_is_not_a_hard_constraint']=True
    nearest=[]
    for n in sn:
        pp=[r for r in cross if r['location_j']==n];elect=min(pp,key=lambda r:(r['electrical_tree_distance_ohm'],r['location_i']));geog=min(pp,key=lambda r:(r['geographic_distance_original_units'],r['location_i']));mel=min(pp,key=lambda r:(r['Melbourne_distance_km'],r['location_i']))
        nearest.append({'STA_id':n,'nearest_AIDC_electrical':elect['location_i'],'electrical_distance_ohm':elect['electrical_tree_distance_ohm'],'nearest_AIDC_IEEE_geography':geog['location_i'],'nearest_AIDC_Melbourne':mel['location_i'],'geographic_nearest_AIDC_preserved':geog['location_i']==mel['location_i'],'fixed_AIDC_transform_residual_original_units':float(errors[sn.index(n)])})
    cross_summary['STA_nearest_AIDC_geographic_identity_preserved_count']=sum(r['geographic_nearest_AIDC_preserved'] for r in nearest)
    first=read(ROOT/'DETERMINISM_FIRST_RUN.json');a=first['search_summary'];b=read(ROOT/'search_summary.json');a.pop('elapsed_seconds');b.pop('elapsed_seconds')
    assert a==b and all(sha(ROOT/n)==h for n,h in first['logs'].items())
    validation={'status':'TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_STA_SELECTION','all_STA_hard_criteria_pass':True,'unchanged_FINAL_AIDC_mapping':True,'distinct_service_locations':24,'AIDC_service_locations':12,'STA_service_locations':12,'STA_candidate_count':594,'independent_corridor_and_SVD_recalculation':True,'deterministic_replays':2,'decision_logs_and_mapping_identical':True,'STA_metrics':metrics,'cross_diagnostics':cross_summary,'global_optimality':'NOT_CLAIMED','PCC_transformers_created':0,'AIDC_hosts_changed':0,'background_scaling_runs':0,'B0_B1_B2_B3_runs':0}
    save('FINAL_24_LOCATION_ELECTRICAL_MAPPING',registry);save('STA_66_PAIR_METRICS',pairs);save('AIDC_STA_144_CROSS_PAIR_DIAGNOSTICS',cross);save('AIDC_STA_CROSS_DIAGNOSTIC_SUMMARY',cross_summary);save('AIDC_STA_NEAREST_AND_ALIGNMENT_DIAGNOSTICS',nearest);save('STA_GEOMETRY_AND_NEIGHBORS',neighbors);save('STA_GEOMETRY_ALIGNMENT',alignment);save('REGISTRY_VALIDATION',validation);save('SERVICE_ROOT_PATHS',[{'location_id':n,'bus':b,'root_to_host_path':paths_nodes[b]} for n,b in sorted(allmap.items())])
    lines='\n'.join(f"| {r['location_id']} | `{r['ieee8500_bus']}` | {r['feeder_depth_hops']} | {r['electrical_root_distance_ohm']:.6f} |" for r in registry)
    doc=f'''# FINAL AIDC authority + topology-only STA service registry

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_STA_SELECTION**. AIDC 12개를 v3 그대로 FINAL authority로 동결하고 STA 12개를 추가 선정했다. 모든 24개 host는 서로 다른 guard 통과 12.47-kV ABC primary bus이며 모두 MESS service location이다. AIDC host 변경=0, PCC 생성=0, background scaling=0, B0–B3 실행=0. 운영 성능 결과를 읽거나 선정에 사용하지 않았다.

| Location | IEEE8500 electrical bus | Depth (corridors) | Root distance (ohm) |
|---|---|---:|---:|
{lines}

좌표/traffic anchor/group을 포함한 전체 mapping은 FINAL_24_LOCATION_ELECTRICAL_MAPPING.csv에 있다. FINAL_AIDC_HOST_AUTHORITY.json은 원래 v3 mapping의 bytes hash와 최종 불변 authority를 기록한다.

STA geometry: E_coord={metrics['E_coord']:.9f}, E_pair={metrics['E_pair']:.9f}, 2-neighbor retention={metrics['nearest_neighbor_retention']:.2%} ({metrics['retained_2NN_relations']}/24). STA electrical distance min/mean={metrics['min_electrical_distance_ohm']:.6f}/{metrics['mean_electrical_distance_ohm']:.6f} ohm; shared-path ratio max/mean={metrics['max_shared_ratio']:.6f}/{metrics['mean_shared_ratio']:.6f}. 사전 정의한 모든 hard criteria를 독립 검증에서 통과했다. 동일 절차 2회 실행의 최종 mapping과 결정 로그가 일치했다. 전역 최적성이나 optimal siting은 주장하지 않는다.

**Cross-pair 진단의 한계:** AIDC–STA 144 pairs의 최소 electrical distance는 {cross_summary['electrical_tree_distance_ohm']['min']:.9f} ohm, 최대 shared ratio는 {cross_summary['shared_path_ratio']['max']:.9f}이다. STA–STA electrical spacing 기준보다 가까운 cross pairs는 {cross_summary['pairs_below_STA_electrical_spacing_reference']}개다. 이는 cross pair에 부과한 hard criterion이 아니므로 통과/실패 판정에 사용하지 않았다. Melbourne 최근접 AIDC의 geographic identity는 {cross_summary['STA_nearest_AIDC_geographic_identity_preserved_count']}/12 STA에서 보존된다. 따라서 24개 전체 상대 geometry나 AIDC–STA 간 전기적 독립성이 보장된다는 해석은 하지 않는다. Cross metrics는 operational benefit을 뜻하지 않는다.

66 STA pairs와 144 cross pairs, nearest-AIDC/alignment diagnostics를 CSV/JSON으로 저장했다. 그림은 원본 ABC primary topology에 fixed AIDC와 selected STA를 표시하며 SVG/PNG로 저장한다. 절차와 입력/code는 선정 전에 PROCEDURE_FREEZE_MANIFEST.json으로 동결했고 최종 산출물은 SERVICE_REGISTRY_FREEZE_MANIFEST.json으로 고정한다.
'''
    (ROOT/'FINAL_24_LOCATION_REPORT.md').write_text(doc,encoding='utf-8')
    print(json.dumps({'status':validation['status'],'STA_metrics':metrics,'cross_min_distance':cross_summary['electrical_tree_distance_ohm']['min'],'cross_max_shared':cross_summary['shared_path_ratio']['max'],'cross_nearest_AIDC_preserved':cross_summary['STA_nearest_AIDC_geographic_identity_preserved_count']},indent=2))

if __name__=='__main__':run()
