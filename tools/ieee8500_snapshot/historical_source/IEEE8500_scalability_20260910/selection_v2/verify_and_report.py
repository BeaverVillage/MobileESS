"""Independent scalar tree/geometry verification; never imports selector metrics."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
os.environ['MPLCONFIGDIR']=str(ROOT/'plot_cache')
sys.path.insert(0,str(ROOT/'plot_packages'))
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
    validation={'status':'TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION','hard_criteria_all_pass':True,'checks':checks,'metrics':metrics,'independent_vs_selector_absolute_deltas':deltas,'verification_implementation':'Scalar reconstructed path edge sets and proper-rotation SVD; selector metric functions not imported','global_optimality':'NOT_CLAIMED_NOT_CERTIFIED','loads_added':0,'scenario_runs':0,'original_freeze_unchanged':True,'procedure_freeze_sha256':sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')}
    if (ROOT/'DETERMINISM_VERIFICATION.json').exists():
        validation['deterministic_replay']=read(ROOT/'DETERMINISM_VERIFICATION.json')
        assert validation['deterministic_replay']['status']=='PASS'
    save('AIDC01_AIDC12_IEEE8500_MAPPING',mapping);save('ALL_66_PAIR_METRICS',rows);save('NEAREST_NEIGHBOR_RETENTION',neighbors);save('SELECTION_VALIDATION',validation);save('SELECTED_ROOT_PATHS',[{'aidc_id':a,'bus':b,'root_to_host_path':path_nodes[b]} for a,b in sorted(selected.items())]);save('GEOMETRY_ALIGNMENT',{'melbourne_normalized':xn.tolist(),'ieee8500_normalized':yn.tolist(),'proper_rotation':proper.tolist(),'melbourne_rotated':(xn@proper).tolist()})
    make_plots(mapping,corridors,buses,path_nodes,root,metrics,xn@proper,yn)
    table='\n'.join(f"| {r['aidc_id']} | `{r['ieee8500_bus']}` | {r['x']:.6f} | {r['y']:.6f} | {r['feeder_depth_corridor_hops']} | {r['electrical_root_distance_ohm']:.9f} | {r['major_lateral_group_id']} |" for r in mapping)
    metric_table='\n'.join(f'| {k} | {v} |' for k,v in metrics.items() if not isinstance(v,dict))
    text=f'''# IEEE8500 topology-only 12-site deterministic selection

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION** — 모든 기존 hard criteria를 독립 검증에서 통과했다. AIDC 수는 정확히 12개다. 전역 최적성이나 optimal AIDC siting을 주장하지 않는다. Source/topology 감사와 기존 후보 pool은 수정하지 않았다. V41R4/May 결과를 읽지 않았으며 OpenDSS compile, AIDC load 추가, B0–B3 실행은 모두 0회다.

## 최종 mapping

좌표는 원본 Buscoords의 값이다. 알려진 CRS/거리 단위가 없으므로 m/km로 해석하지 않는다. Feeder depth는 root `_hvmv_sub_lsb`에서의 상별 bank 집계 corridor hop 수이며, electrical root distance는 frozen static impedance metric의 합이다.

| AIDC | IEEE8500 bus | X | Y | Depth (hops) | Root distance (ohm) | Group |
|---|---|---:|---:|---:|---:|---|
{table}

D5710794-3_INT를 포함한 모든 host는 기존 638개 pool에 있던 bus이다. Pool의 source/substation/regulator 제외 판정을 변경하거나 후보를 추가하지 않았다. 명칭의 `_INT`만으로 기존 자격 판정을 새로 변경하지 않았다.

## 검증 결과

| 지표 | 값 |
|---|---:|
{metric_table}

E_coord는 0.20 제한에 가깝지만 hard threshold를 완화하지 않고 통과했다. E_coord 여유는 {metrics['E_coord_margin_to_limit']:.9f}이다. Retention은 24개의 directed two-neighbor 관계 중 {metrics['nearest_neighbor_preserved_directed_relations']}개 보존이며 완전 일치라는 뜻은 아니다. 3개 major lateral 및 trunk/minor의 4개 그룹이 모두 대표된다. Group occupancy: `{json.dumps(dict(sorted(counts.items())))}`.

66쌍 모두 electrical distance ≥0.9129072401559803 ohm 및 geographic distance ≥2221.532547954318 original units를 만족한다. 전체 ratio, 공통 경로 impedance, LCA와 거리 값은 `ALL_66_PAIR_METRICS.csv`에 저장했다. Site별 이웃 집합은 `NEAREST_NEIGHBOR_RETENTION.csv`에 있다. Mapping의 root 경로는 `SELECTED_ROOT_PATHS.json`에 있다.

독립 검증기는 frozen primary corridors에서 root 경로를 재구축하여 교집합/대칭차집합을 합산했다. Geometry는 selector의 닫힌 형태 공식을 사용하지 않고 proper-rotation SVD와 직접 좌표 residual로 다시 계산했다. Selector와 독립 검증 지표의 최대 절대 차이는 {max(deltas.values()):.3g}이다.

## 결정적 절차와 한계

선정 전 v2 문서와 selector code를 `PROCEDURE_FREEZE_MANIFEST.json`으로 고정했다. 12,600개 geometric transforms에서 {result['unique_mappings']:,}개 distinct mappings를 만들었다. 초기 geometric feasible mapping은 {result['geometric_feasible_count']}개였다. 정해진 64개 repair start에서 {result['feasible_after_repair']}개 feasible mapping을 얻고, 우선순위 상위 {result['local_starts']}개를 finite local improvement 절차로 평가했다.

핵심 우선순위는 maximum shared ratio → mean shared ratio → minimum electrical distance → major-lateral/group diversity → geographic dispersion → Melbourne relative-shape error였다. Hard criteria는 v1과 동일하다. 모든 설정은 `12_SITE_CANDIDATE_SELECTION_METHODOLOGY_V2.md`, 실행 로그는 `selection_run.log`, 개별 repair/descent 이력은 JSON에 있다.

동일한 frozen procedure를 2회 실행해 wall time을 제외한 search summary와 최종 mapping이 동일함을 확인했다. Repair 및 local improvement 결정 로그도 SHA256이 일치했다. 증거는 `DETERMINISM_VERIFICATION.json`과 첫 실행 기록에 있다.

이 결과는 동결 절차에서 얻은 feasible selection이다. 모든 12-bus 조합에 대한 탐색이나 전역 최적성 증명은 수행하지 않았다. Operational hosting capacity, AIDC 부하 수용 가능성, voltage/thermal 성능 및 B0–B3 개선 여부는 평가하지 않았다.

## 그림과 동결

![Selected sites on canonical feeder](FEEDER_TOPOLOGY_12_SITES.png)

그림은 원본 ABC primary topology의 646 corridors를 회색으로 표시하고 root→host 경로와 AIDC01–AIDC12를 강조한다. SVG도 함께 저장했다. 별도 `MELBOURNE_RELATIVE_GEOMETRY.png`는 proper rotation 후의 상대 구조 비교다.

원본 동결 manifest SHA256: `{proc['original_freeze_sha256']}`

사전 procedure freeze SHA256: `{sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')}`

최종 산출물과 code/input hash는 `SELECTION_FREEZE_MANIFEST.json`에 기록한다. 모든 새 파일은 selection_v2 아래에만 썼다.
'''
    (ROOT/'IEEE8500_12_SITE_SELECTION_REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps(validation,indent=2,default=lambda x:x.item()))

def make_plots(mapping,corridors,buses,path_nodes,root,metrics,xx,yy):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    colors={'MAJOR:l3081380':'#167d9a','MAJOR:m1047526':'#d77827','MAJOR:l2820531':'#825aa8','TRUNK_OR_MINOR_LATERAL':'#2b8760'}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
    fig=plt.figure(figsize=(17,10),facecolor='white');ax=fig.add_axes([.06,.10,.59,.80]);info=fig.add_axes([.68,.12,.30,.78]);info.axis('off')
    xy=lambda b:(buses[b]['x'],buses[b]['y'])
    ax.add_collection(LineCollection([[xy(e['u']),xy(e['v'])] for e in corridors],colors='#c5cdd3',linewidths=.7,zorder=1))
    for r in mapping:
        path=path_nodes[r['ieee8500_bus']];col=colors[r['major_lateral_group_id']]
        ax.add_collection(LineCollection([[xy(a),xy(b)] for a,b in zip(path[:-1],path[1:])],colors=col,linewidths=1.3,alpha=.65,zorder=2))
    offsets={1:(-22,13),2:(12,10),3:(13,-15),4:(14,15),5:(-25,12),6:(-25,-20),7:(10,14),8:(10,-22),9:(12,15),10:(-25,-22),11:(12,14),12:(-22,-24)}
    for i,r in enumerate(mapping,1):
        col=colors[r['major_lateral_group_id']];x,y=r['x'],r['y'];ax.scatter([x],[y],s=58,c=col,edgecolors='white',linewidths=1,zorder=4)
        ax.annotate(f'{i:02}',(x,y),xytext=offsets[i],textcoords='offset points',color=col,fontweight='bold',fontsize=11,bbox={'boxstyle':'round,pad=0.18','fc':'white','ec':col,'lw':.7},arrowprops={'arrowstyle':'-','color':col,'lw':.8},zorder=5)
    xr,yr=xy(root);ax.scatter([xr],[yr],marker='*',s=160,c='#182938',edgecolors='white',zorder=6);ax.annotate('ROOT',(xr,yr),xytext=(-48,20),textcoords='offset points',fontsize=9,fontweight='bold',arrowprops={'arrowstyle':'-','color':'#182938'})
    ax.autoscale();ax.margins(.08);ax.set_aspect('equal');ax.set_xlabel('Canonical Buscoords X (original units)');ax.set_ylabel('Canonical Buscoords Y (original units)');ax.ticklabel_format(style='plain',useOffset=False);ax.grid(alpha=.15)
    info.text(0,1,'AIDC electrical hosts',fontsize=15,fontweight='bold',va='top')
    info.text(0,.946,'ID    IEEE8500 bus                       Depth / root ohm',fontsize=10,color='#4a5560',va='top')
    for i,r in enumerate(mapping):
        y=.899-i*.052;info.text(0,y,r['aidc_id'],color=colors[r['major_lateral_group_id']],fontsize=10,fontweight='bold',va='top');info.text(.22,y,r['ieee8500_bus'],fontsize=10,va='top');info.text(.75,y,f"{r['feeder_depth_corridor_hops']:3} / {r['electrical_root_distance_ohm']:.3f}",fontsize=10,va='top')
    yy0=.22
    for k,col in colors.items():
        info.text(0,yy0,'\u25cf '+k.replace('MAJOR:','Major '),color=col,fontsize=10);yy0-=.034
    info.text(0,.02,f"Max / mean shared ratio: {metrics['max_shared_path_ratio']:.6f} / {metrics['mean_shared_path_ratio']:.6f}\nMin / mean tree distance: {metrics['min_electrical_tree_distance_ohm']:.3f} / {metrics['mean_electrical_tree_distance_ohm']:.3f} ohm",fontsize=10,linespacing=1.7)
    fig.text(.06,.96,'IEEE8500 | 12 topology-only AIDC hosts',fontsize=22,fontweight='bold',color='#182938');fig.text(.06,.925,'647 ABC-primary buses / 646 corridors  •  Colored lines: root-to-host paths  •  Global optimality not claimed',fontsize=11,color='#53616d')
    fig.text(.06,.035,'Source topology unchanged. No AIDC load added. No B0–B3 run. Coordinate CRS/units are not established.',fontsize=10,color='#53616d')
    fig.savefig(ROOT/'FEEDER_TOPOLOGY_12_SITES.png',dpi=180);fig.savefig(ROOT/'FEEDER_TOPOLOGY_12_SITES.svg');plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,7.5));ax.scatter(xx[:,0],xx[:,1],marker='o',facecolors='none',edgecolors='#2b6f93',s=90,label='Melbourne anchors (proper rotation)');ax.scatter(yy[:,0],yy[:,1],marker='x',color='#d77827',s=65,label='IEEE8500 selected sites')
    for i,(a,b) in enumerate(zip(xx,yy),1):
        ax.plot([a[0],b[0]],[a[1],b[1]],color='#9da9af',lw=.8);ax.annotate(f'{i:02}',b,xytext=(6,6),textcoords='offset points',fontsize=10)
    ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(loc='lower left');ax.set_xlabel('Centered / RMS-normalized X');ax.set_ylabel('Centered / RMS-normalized Y');ax.set_title(f"Melbourne relative structure | E_coord={metrics['E_coord']:.6f}, E_pair={metrics['E_pair']:.6f}\nTwo-neighbor retention: {metrics['nearest_neighbor_retention']:.2%}",pad=15);fig.tight_layout();fig.savefig(ROOT/'MELBOURNE_RELATIVE_GEOMETRY.png',dpi=180);fig.savefig(ROOT/'MELBOURNE_RELATIVE_GEOMETRY.svg');plt.close(fig)

if __name__=='__main__':run()
