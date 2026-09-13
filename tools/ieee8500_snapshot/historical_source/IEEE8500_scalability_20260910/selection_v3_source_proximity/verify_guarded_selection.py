"""Independent scalar tree/geometry verification; never imports selector metrics."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
import csv,hashlib,json,math
from collections import defaultdict,Counter
import numpy as np
from scipy.spatial import ConvexHull
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def save(name,rows):
    (ROOT/(name+'.json')).write_text(json.dumps(rows,indent=2,ensure_ascii=False,default=lambda x:x.item()),encoding='utf-8')
    if isinstance(rows,list) and rows:
        with (ROOT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
            for r in rows:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def run():
    proc=read(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')
    assert sha(BASE/'FREEZE_MANIFEST.json')==proc['original_freeze_sha256']
    for r in proc['inputs']:assert sha(BASE/r['path'])==r['sha256']
    for r in proc['files']:assert sha(ROOT/r['path'])==r['sha256']
    result=read(ROOT/'search_summary.json');selected=result['mapping'];assert len(selected)==12 and len(set(selected.values()))==12
    pool={p['bus']:p for p in read(BASE/'audit/candidate_pool_static_features.json')}
    buses={p['bus']:p for p in read(BASE/'audit/buses.json')}
    anchors={p['aidc_id']:p for p in read(BASE/'audit/melbourne_12_anchors.json')}
    corridors=read(BASE/'audit/primary_corridors.json');adj=defaultdict(dict)
    for e in corridors:adj[e['u']][e['v']]=e['weight_ohm'];adj[e['v']][e['u']]=e['weight_ohm']
    root='_hvmv_sub_lsb';parent={root:None};depth={root:0};hops={root:0};order=[root]
    for u in order:
        for v,w in sorted(adj[u].items()):
            if v not in parent:parent[v]=u;depth[v]=depth[u]+w;hops[v]=hops[u]+1;order.append(v)
    assert len(parent)==647 and len(corridors)==646
    guard=read(ROOT/'ROOT_DISTANCE_GUARD_AUDIT.json')
    root_values=np.array([depth[b] for b in sorted(pool)])
    cut=float(np.quantile(root_values,.05,method='linear'))
    assert abs(cut-guard['root_distance_q05_ohm'])<1e-12
    max_root_delta=max(abs(depth[b]-pool[b]['primary_upstream_impedance_ohm']) for b in pool)
    assert max_root_delta<1e-12
    allowed={r['bus'] for r in read(ROOT/'GUARDED_CANDIDATE_POOL.json')}
    assert allowed=={b for b in pool if depth[b]>=guard['root_distance_q05_ohm']}
    assert len(allowed)==606 and all(b in allowed for b in selected.values())
    path_edges={};path_nodes={};mapping=[]
    for aidc,b in sorted(selected.items()):
        assert b in pool and buses[b]['selection_ready'] and buses[b]['electrically_eligible']
        assert not buses[b]['eligibility_exclusions'] and set(buses[b]['nodes'])=={1,2,3}
        assert abs(buses[b]['kv_base_sqrt3']-12.47)<=.01247
        nn=[];ee=[];u=b
        while u is not None:
            nn.append(u)
            if parent[u] is not None:ee.append(tuple(sorted([u,parent[u]])))
            u=parent[u]
        path_edges[b]=set(ee);path_nodes[b]=list(reversed(nn))
        mapping.append({'aidc_id':aidc,'ieee8500_bus':b,'x':pool[b]['x'],'y':pool[b]['y'],'coordinate_units':'original_Buscoords_unknown_CRS','nominal_kv_ll':buses[b]['kv_base_sqrt3'],'phases':'ABC','feeder_depth_corridor_hops':hops[b],'electrical_root_distance_ohm':depth[b],'major_lateral_group_id':pool[b]['lateral_group']})
    assert len({(r['x'],r['y']) for r in mapping})==12
    rows=[];X=[];Y=[]
    for r in mapping:
        a=anchors[r['aidc_id']];X.append([a['x_east_km'],a['y_north_km']]);Y.append([r['x'],r['y']])
    X=np.array(X);Y=np.array(Y)
    for i in range(12):
        for j in range(i+1,12):
            a=mapping[i];b=mapping[j];u=a['ieee8500_bus'];v=b['ieee8500_bus'];shared=path_edges[u]&path_edges[v]
            C=sum(adj[p][q] for p,q in sorted(shared));sym=path_edges[u]^path_edges[v]
            D=sum(adj[p][q] for p,q in sorted(sym));union=sum(adj[p][q] for p,q in sorted(path_edges[u]|path_edges[v]));ratio=C/union
            geo=math.dist(Y[i],Y[j]);mel=math.dist(X[i],X[j])
            lca=next(n for n in reversed(path_nodes[u]) if n in set(path_nodes[v]))
            rows.append({'aidc_i':a['aidc_id'],'aidc_j':b['aidc_id'],'bus_i':u,'bus_j':v,'lowest_common_ancestor_bus':lca,'shared_upstream_impedance_ohm':C,'upstream_union_impedance_ohm':union,'shared_path_ratio':ratio,'electrical_tree_distance_ohm':D,'geographic_distance_original_units':geo,'melbourne_distance_km':mel,'electrical_distance_hard_pass':D>=.9129072401559803,'geographic_distance_hard_pass':geo>=2221.532547954318})
    xc=X-X.mean(axis=0);yc=Y-Y.mean(axis=0);xn=xc/np.sqrt(np.mean(np.sum(xc*xc,axis=1)));yn=yc/np.sqrt(np.mean(np.sum(yc*yc,axis=1)))
    U,sv,Vt=np.linalg.svd(xn.T@yn);proper=U@np.diag([1,np.linalg.det(U@Vt)])@Vt
    ec=float(np.sqrt(np.mean(np.sum((xn@proper-yn)**2,axis=1))))
    md=np.array([r['melbourne_distance_km'] for r in rows]);gd=np.array([r['geographic_distance_original_units'] for r in rows]);mdn=md/np.sqrt(np.mean(md*md));gdn=gd/np.sqrt(np.mean(gd*gd));ep=float(np.sqrt(np.mean((mdn-gdn)**2)))
    neighbors=[]
    for i in range(12):
        mnear=sorted((j for j in range(12) if i!=j),key=lambda j:(math.dist(X[i],X[j]),mapping[j]['aidc_id']))[:2]
        gnear=sorted((j for j in range(12) if i!=j),key=lambda j:(math.dist(Y[i],Y[j]),mapping[j]['aidc_id']))[:2]
        neighbors.append({'aidc_id':mapping[i]['aidc_id'],'melbourne_two_nearest':[mapping[j]['aidc_id'] for j in mnear],'ieee8500_two_nearest':[mapping[j]['aidc_id'] for j in gnear],'retained_neighbors':len(set(mnear)&set(gnear)),'retention':len(set(mnear)&set(gnear))/2})
    retention=sum(r['retained_neighbors'] for r in neighbors)/24
    counts=Counter(r['major_lateral_group_id'] for r in mapping)
    metrics={'E_coord':ec,'E_pair':ep,'nearest_neighbor_retention':retention,'nearest_neighbor_preserved_directed_relations':sum(r['retained_neighbors'] for r in neighbors),'nearest_neighbor_total_directed_relations':24,'min_electrical_tree_distance_ohm':min(r['electrical_tree_distance_ohm'] for r in rows),'mean_electrical_tree_distance_ohm':float(np.mean([r['electrical_tree_distance_ohm'] for r in rows])),'max_shared_path_ratio':max(r['shared_path_ratio'] for r in rows),'mean_shared_path_ratio':float(np.mean([r['shared_path_ratio'] for r in rows])),'min_geographic_distance_original_units':float(gd.min()),'geographic_convex_hull_area_original_units_squared':float(ConvexHull(Y).volume),'represented_major_laterals':sum(k.startswith('MAJOR:') for k in counts),'represented_groups':len(counts),'group_occupancies':dict(sorted(counts.items())),'proper_rotation_determinant':float(np.linalg.det(proper)),'E_coord_margin_to_limit':.2-ec,'E_pair_margin_to_limit':.2-ep}
    checks={'exactly_12_unique_eligible_buses':len(mapping)==len(set(selected.values()))==12,'unchanged_638_pool_and_input_hashes':True,'all_selected_12_47_kv_ABC_and_exclusions_empty':True,'E_coord_le_0_20':ec<=.20,'E_pair_le_0_20':ep<=.20,'nearest_neighbor_retention_ge_0_50':retention>=.5,'all_66_electrical_distance_ge_frozen_threshold':all(r['electrical_distance_hard_pass'] for r in rows),'all_66_geographic_distance_ge_frozen_threshold':all(r['geographic_distance_hard_pass'] for r in rows),'proper_rotation_no_reflection':abs(np.linalg.det(proper)-1)<1e-12,'66_pairs':len(rows)==66}
    compare={'ec':ec,'ep':ep,'retention':retention,'min_d':metrics['min_electrical_tree_distance_ohm'],'mean_d':metrics['mean_electrical_tree_distance_ohm'],'max_r':metrics['max_shared_path_ratio'],'mean_r':metrics['mean_shared_path_ratio'],'min_g':metrics['min_geographic_distance_original_units']}
    deltas={k:abs(result['metrics'][k]-v) for k,v in compare.items()}
    assert max(deltas.values())<1e-9;assert all(checks.values())
    checks['root_distance_guard_all_selected']=all(depth[b]>=cut for b in selected.values())
    checks['606_guarded_pool_independently_verified']=True
    validation={'status':'TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION','hard_criteria_all_pass':True,'checks':checks,'metrics':metrics,'independent_vs_selector_absolute_deltas':deltas,'verification_implementation':'Scalar reconstructed path edge sets and proper-rotation SVD; selector metric functions not imported','global_optimality':'NOT_CLAIMED_NOT_CERTIFIED','loads_added':0,'scenario_runs':0,'original_freeze_unchanged':True,'procedure_freeze_sha256':sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')}
    if (ROOT/'DETERMINISM_VERIFICATION.json').exists():
        validation['deterministic_replay']=read(ROOT/'DETERMINISM_VERIFICATION.json')
        assert validation['deterministic_replay']['status']=='PASS'
    validation['source_proximity_guard']={'q05_ohm':cut,'original_count':638,'remaining_count':606,'excluded_count':32,'minimum_selected_root_distance_ohm':min(depth[b] for b in selected.values()),'root_distances_reconstruction_max_delta':max_root_delta}
    save('AIDC01_AIDC12_IEEE8500_MAPPING',mapping);save('ALL_66_PAIR_METRICS',rows);save('NEAREST_NEIGHBOR_RETENTION',neighbors);save('SELECTION_VALIDATION',validation);save('SELECTED_ROOT_PATHS',[{'aidc_id':a,'bus':b,'root_to_host_path':path_nodes[b]} for a,b in sorted(selected.items())]);save('GEOMETRY_ALIGNMENT',{'melbourne_normalized':xn.tolist(),'ieee8500_normalized':yn.tolist(),'proper_rotation':proper.tolist(),'melbourne_rotated':(xn@proper).tolist()})
