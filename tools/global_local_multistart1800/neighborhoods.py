"""Finite adaptive route families, center-containing closure and witness radius."""
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.dag import Graph

def priorities(case,point,context):
    # Original signed sensitivity and actual route reachability, not absolute
    # sensitivity alone. Ranking is heuristic and never alters source rows.
    ranks=n._signed_ranking(case,point,context)
    out={}
    for u in sorted(case.graph[1]):
        choices=[]
        for row in ranks:
            if row['unit']==u and row['site'] not in choices:choices.append(row['site'])
        out[u]=choices
    order=sorted((u for u in out if u!='MESS03'),key=lambda u:(-max((r['score'] for r in ranks if r['unit']==u),default=0.),u))
    return out,order,ranks[:64]

def descriptors(partners):
    primary=[dict(label='R1_FIRST_SMALL',stage='R1',units=['MESS03'],start=0,stop=24,size=3,slack=4,cap=120),
        dict(label='R2_LATE_SMALL',stage='R2',units=['MESS03'],start=60,stop=96,size=4,slack=8,cap=120),
        dict(label='R1_FIRST_EXPANDED',stage='R1',units=['MESS03'],start=0,stop=40,size=5,slack=8,cap=130),
        dict(label='R2_LATE_EXPANDED',stage='R2',units=['MESS03'],start=48,stop=96,size=6,slack=12,cap=130),
        dict(label='R3_WHOLE_MESS03_FOUR_SITES',stage='R3',units=['MESS03'],start=0,stop=96,size=4,slack=16,cap=180),
        dict(label='R3_WHOLE_MESS03_24_SITES',stage='R3',units=['MESS03'],start=0,stop=96,size=24,slack=32,cap=220)]
    primary.extend(dict(label='R4_MESS03_'+u,stage='R4',units=['MESS03',u],start=0,stop=96,size=6,partner_size=3,slack=24,cap=130) for u in partners)
    # These are different mathematical corridors/radii, never retries of a
    # large root-incomplete model. Beam is invoked only after R1..R4 stagnation.
    reserve=[dict(label=f'R5_BEAM_CORRIDOR_{i}',stage='R5',units=['MESS03',partners[i%len(partners)]],start=0,stop=96,
        size=6+i*2,partner_size=4+i,slack=32+i*8,cap=125 if i<2 else 150,beam_ordinal=i) for i in range(6)]
    return primary,reserve

def make(case,point,replay,descriptor,priority_sites,extra_paths=()):
    graph=Graph(case);base=paths_of(case,point);closures={};vertices={}
    for u in descriptor['units']:
        route_sites=[]
        for k in base[u]:
            for site in (graph.arcs[k][0],graph.arcs[k][2]):
                if site not in route_sites:route_sites.append(site)
        size=descriptor['size'];first=route_sites
        sites=list(dict.fromkeys(first+priority_sites[u]))[:size]
        added=[p[u] for p in extra_paths if u in p]
        closure=graph.closure(u,base[u],descriptor['start'],descriptor['stop'],sites,
            terminal_any=descriptor['stop']==96,extra_paths=added)
        closures[u]=closure
        vertices[u]={graph.arcs[k][:2] for k in closure['inner_arcs']}|{graph.arcs[k][2:4] for k in closure['inner_arcs']}
    modes=set(map(int,np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))))
    ids,vals=route_values(case,base);fixed=[];values=[];ham=[]
    for j,value in zip(ids,vals):
        name=str(case.d['names'][j]);family,fields=name.split('[',1);axis=fields[:-1].split(',');u=axis[0];c=closures.get(u)
        free=False
        if c is not None:
            if family=='route_flow':free=int(axis[1]) in set(c['inner_arcs'])
            elif family=='node_activity':free=(axis[1],int(axis[2])) in vertices[u] and c['start']<=int(axis[2])<=c['stop']
        if free and case.d['lower'][j]<case.d['upper'][j]:
            if family=='node_activity':ham.append(int(j))
        else:fixed.append(int(j));values.append(float(value))
    witness_list=[];joint={u:list(p) for u,p in base.items()}
    for u,c in closures.items():
        witness={w:list(p) for w,p in base.items()};witness[u]=c['witness'];witness_list.append(witness);joint[u]=c['witness']
    if len(closures)>1:witness_list.append(joint)
    witness_list.extend(p for p in extra_paths if all(set(p[u])<=set(closures[u]['allowed_arcs']) for u in closures))
    distances=[]
    for paths in witness_list:
        wi,wv=route_values(case,paths);trial=point.copy();trial[wi]=wv
        distances.append(int(np.count_nonzero(trial[ham]!=point[ham])))
    radius=max(distances)+descriptor['slack'];assert radius>0
    spec=dict(method='ROUTE_LOCAL_BRANCHING',candidate_id=descriptor['label'],stage=descriptor['stage'],descriptor=descriptor,
        center_paths=base,center_full_replay=record(replay),center_vector_sha256=v.vector_sha(point),closures=closures,
        fixed_route_columns=fixed,fixed_route_values=values,hamming_columns=ham,hamming_radius=radius,
        witness_paths=witness_list,witness_Hamming_distances=distances,warm_start_compatible=True,center_included=True,
        all384_modes_free=True,Modes_in_Hamming=0,restricted_ObjBound_is_Global_LB=False,
        heuristic_corridor_selection_not_exact_global_prescreen=True,source_matrix_and_all_physics_unchanged=True)
    lo,hi,hh,cc,rhs,_=restriction(case,point,spec)
    spec['mathematical_model_signature']=signature(lo,hi,hh,cc,rhs)
    spec['actual_free_binary']=int(np.count_nonzero((case.d['types']!='C')&(lo<hi)))
    spec['actual_fixed_binary']=9322-spec['actual_free_binary']
    return spec
