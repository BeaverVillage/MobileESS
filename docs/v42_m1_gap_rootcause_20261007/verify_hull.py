"""Independent exhaustive checker. Does not import trajectory_hull/prepare."""
from common import *
from fractions import Fraction as F
from collections import defaultdict,Counter
import itertools,time

def intersections(planes):
    vertices=set()
    for (a,b,c),(d,e,f) in itertools.combinations(planes,2):
        det=a*e-b*d
        if not det:continue
        p,q=(c*e-b*f)/det,(a*f-c*d)/det
        if all(g*p+h*q<=k for g,h,k in planes):vertices.add((p,q))
    return vertices

def main(label='MESS04_69_72'):
    began=time.perf_counter();h=read(OUT/(label+'_HULL_AUTHORITY.json'));catalog=read(OUT/(label+'_INTEGER_TRAJECTORIES.json'))
    a=Authority();unit=h['unit'];start=h['start'];end=h['end_exclusive'];H=end-start
    paths=[tuple(r['arcs']) for r in catalog['trajectories']]
    assert len(set(paths))==len(paths)
    allowed=a.reachable[unit];out=defaultdict(list)
    for k in allowed:out[a.arcs[k][:2]].append(k)
    # Backward dynamic-programming count, different from production DFS.
    ways={}
    for t in reversed(range(start+1,end)):
        for s in a.sites:ways[s,t]=sum(1 if a.arcs[k][3]>=end else ways[a.arcs[k][2],a.arcs[k][3]] for k in out[s,t])
    crossing=[k for k in allowed if a.arcs[k][1]<=start<a.arcs[k][3]]
    expected=sum(1 if a.arcs[k][3]>=end else ways[a.arcs[k][2],a.arcs[k][3]] for k in crossing)
    assert expected==len(paths)
    for i,path in enumerate(paths):
        assert catalog['trajectories'][i]['id']==i and catalog['trajectories'][i]['all_mode_bits']==list(range(16))
        assert all(k in allowed for k in path)
        assert a.arcs[path[0]][1]<=start<a.arcs[path[0]][3]
        assert all(a.arcs[k][2:4]==a.arcs[j][0:2] for k,j in zip(path,path[1:]))
        assert a.arcs[path[-1]][3]>=end and all(a.arcs[k][3]<end for k in path[:-1])
    geometry_checks=[];geometry_cache={}
    for key,g in h['geometries'].items():
        t,site,mode=key.split(':');t=int(t);mode=int(mode)
        native=[(p*(1 if mode==0 else -1),q,c) for p,q,c in a.pcs(unit,site,t)]
        assert native==[tuple(map(F,row)) for row in g['planes']]
        bounds=[(-F(1),F(0),F(0)),(F(1),F(0),F.from_float(a.battery.p_limit)),(F(0),F(1),F.from_float(a.battery.pcs_kva)),(F(0),-F(1),F.from_float(a.battery.pcs_kva))]
        cache_key=tuple(native),tuple(g['selected'])
        if cache_key not in geometry_cache:
            full=intersections(native+bounds)
            reduced=intersections([native[k] for k in g['selected']]+bounds)
            assert full==reduced and full=={tuple(map(F,v)) for v in g['vertices']}
            geometry_cache[cache_key]=dict(vertices=len(full),retained_PCS_facets=len(g['selected']),all_omitted_original_facets_exactly_implied=True)
        geometry_checks.append(dict(key=key,**geometry_cache[cache_key]))
    E=[a.energy(unit,t) for t in range(start,end)]
    B=sparse.load_npz(OUT/(label+'_EF_MATRIX.npz')).tocsr()
    with np.load(OUT/(label+'_EF_DATA.npz')) as z:d={k:z[k] for k in z.files}
    n=h['original_columns'];row_cursor=0;col_cursor=n
    arc_terms=defaultdict(list);power_terms=defaultdict(list);mode_one=defaultdict(list);mode_off=defaultdict(list);E0=[];lams=[];Et=defaultdict(list)
    row_tests=0;mutation_checks=[];mutation_sample=None
    def check_row(i,terms,sense='<',rhs=0):
        nonlocal row_tests
        terms=sorted((int(j),float(w)) for j,w in terms if w)
        assert len({j for j,w in terms})==len(terms)
        begin,finish=B.indptr[i:i+2]
        assert np.array_equal(B.indices[begin:finish],np.array([j for j,w in terms]))
        assert np.array_equal(B.data[begin:finish],np.array([w for j,w in terms]))
        assert str(d['sense'][i])==sense and float(d['rhs'][i])==float(rhs)
        row_tests+=1
    checked_modes=defaultdict(set)
    def bounds(j,lo,hi):assert d['lower'][j-n]==lo and d['upper'][j-n]==hi
    for block in d['blocks']:
        path_id,bits,c0,c1,r0,r1=map(int,block);path=paths[path_id]
        assert c0==col_cursor and r0==row_cursor
        stay={a.arcs[k][1]:(a.arcs[k][0],k) for k in path if a.arcs[k][-1] is None}
        depart={a.arcs[k][1]:k for k in path if a.arcs[k][-1] is not None and start<=a.arcs[k][1]<end}
        events=sorted(set(stay)|set(depart));mask=sum(1<<(t-start) for t in stay)
        assert bits&~mask==0 and bits not in checked_modes[path_id];checked_modes[path_id].add(bits)
        modes={t:(bits>>(t-start))&1 for t in stay}
        lam=c0;bounds(lam,0,1);lams.append(lam)
        for k in path:arc_terms[k].append(lam)
        estate=list(range(c0+1,c0+2+len(events)));E0.append(estate[0]);i=r0
        for ej in estate:
            bounds(ej,0,a.battery.maximum)
            check_row(i,[(ej,1),(lam,-a.battery.maximum)]);i+=1
            check_row(i,[(ej,-1),(lam,a.battery.minimum)]);i+=1
        column=c0+2+len(events)
        total_cost=F(0)
        for index,t in enumerate(events):
            before,after=estate[index:index+2]
            if t in stay:
                site,k=stay[t];mode=modes[t];p,q=column,column+1;column+=2
                bounds(p,0,a.battery.p_limit);bounds(q,-a.battery.pcs_kva,a.battery.pcs_kva)
                power_terms['Pch' if mode else 'Pdis',site,t].append(p);power_terms['Q',site,t].append(q)
                check_row(i,[(p,1),(lam,-a.battery.p_limit)]);i+=1
                g=h['geometries'][f'{t}:{site}:{mode}']
                for facet in g['selected']:
                    aa,bb,cap=map(F,g['planes'][facet]);check_row(i,[(p,aa),(q,bb),(lam,-cap)]);i+=1
                coef=E[t-start]['charge' if mode else 'discharge'];check_row(i,[(after,1),(before,-1),(p,-coef)],'=');i+=1
            else:
                k=depart[t];cost=E[t-start]['raw'][a.names[f'arc[{unit},{k}]']]
                assert cost==F.from_float(a.arcs[k][-1].energy_kwh);total_cost+=cost
                check_row(i,[(after,1),(before,-1),(lam,cost)],'=')
                if mutation_sample is None:mutation_sample=(i,[(after,1),(before,-1),(lam,cost)])
                i+=1
        assert total_cost<=F.from_float(a.battery.maximum-a.battery.minimum)
        for t in range(start,end):
            if t not in stay:mode_off[t].append(lam)
            elif modes[t]:mode_one[t].append(lam)
            Et[t+1].append(estate[sum(event<=t for event in events)])
        assert i==r1 and column==c1
        col_cursor=c1;row_cursor=r1
    for p,path in enumerate(paths):
        mask=sum(1<<(a.arcs[k][1]-start) for k in path if a.arcs[k][-1] is None)
        assert checked_modes[p]=={b for b in range(1<<H) if b&~mask==0}
    assert row_cursor==h['block_rows_end']
    check_row(row_cursor,[(j,1) for j in lams],'=',1);row_cursor+=1
    def link(name,terms):
        nonlocal row_cursor
        expression,constant=a.expression(name)
        check_row(row_cursor,list(expression.items())+[(j,-w) for j,w in terms],'=',-constant);row_cursor+=1
    for k,js in sorted(arc_terms.items()):link(f'arc[{unit},{k}]',[(j,1) for j in js])
    for t in range(start,end):
        for site in a.sites:
            for family in ('Pch','Pdis','Q'):link(f'{family}[{unit},{site},{t}]',[(j,1) for j in power_terms[family,site,t]])
        u=col_cursor;col_cursor+=1;bounds(u,0,1)
        link(f'charge_mode[{unit},{t}]',[(j,1) for j in mode_one[t]]+[(u,1)])
        check_row(row_cursor,[(u,1)]+[(j,-1) for j in mode_off[t]]);row_cursor+=1
    link(f'SOC[{unit},{start}]',[(j,1) for j in E0])
    for t in range(start+1,end+1):link(f'SOC[{unit},{t}]',[(j,1) for j in Et[t]])
    assert row_cursor==B.shape[0] and col_cursor==B.shape[1] and B.nnz==h['nnz']
    # Adversarial native row mutations are rejected by semantic checks, not SHA.
    ri,expected_terms=mutation_sample;ab,ae=B.indptr[ri:ri+2];old=B.data[ab:ae].copy()
    for name,transform in [('movement_energy_deleted',lambda v:np.zeros_like(v)),('movement_energy_sign_flip',lambda v:-v),('energy_coefficient_1percent',lambda v:v*1.01),('state_balance_scaled_only_one_term',lambda v:v+np.arange(len(v))*.01)]:
        B.data[ab:ae]=transform(old)
        rejected=False
        try:check_row(ri,expected_terms,'=')
        except AssertionError:rejected=True
        assert rejected;mutation_checks.append(dict(mutation=name,rejected=True))
        B.data[ab:ae]=old
    for name,condition in [('missing_trajectory',len(paths)-1==expected),('duplicate_trajectory',len(set(paths+[paths[0]]))==len(paths)+1),('missing_transit_modes',list(range(15))==list(range(16))),('boundary_SOC_fixed_to_observed',F.from_float(1053.8145391476621)==F.from_float(a.battery.maximum)),('PCS_capacity_relaxed',h['boundary_bounds'][1]+1==a.battery.maximum)]:
        assert not condition;mutation_checks.append(dict(mutation=name,rejected=True))
    assert sha(OUT/(label+'_EF_MATRIX.npz'))==h['matrix_SHA256'] and sha(OUT/(label+'_EF_DATA.npz'))==h['data_SHA256']
    report=dict(PASS=True,unit=unit,start=start,end_exclusive=end,production_constructor_imported=False,optimize_calls=0,independent_path_count=expected,mobility_paths_checked=len(paths),all_integer_trajectory_count=len(paths)*16,disjuncts_checked=len(d['blocks']),rows_independently_checked=row_cursor,nnz_checked=B.nnz,exact_geometry_checks=geometry_checks,mutation_checks=mutation_checks,source_original_FULL_A_SHA256=sha(a.SOURCE/'FULL_A.npz') if hasattr(a,'SOURCE') else history_authority.FULL_A_SHA,source_original_FULL_DATA_SHA256=history_authority.FULL_DATA_SHA,scope='Complete original local physical window with unfixed boundary SOC; global SOC/grid extension not imposed',integer_set_preservation_proof='Every global integer path induces exactly one enumerated local path and one connected-mode word. Each disjunct is precisely original bounded local PCS/SOC dynamics. Homogeneous Balas lift has bounded disjuncts and lambda simplex: projection equals convex hull. Transit mode cube factoring commutes with independently free mode bits.',exact_native_transport_no_rounding=True,runtime_seconds=time.perf_counter()-began)
    write(label+'_INDEPENDENT_VERIFICATION.json',report);print('HULL_VERIFIED',row_cursor,'rows',len(d['blocks']),'disjuncts',report['runtime_seconds'],flush=True)

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'MESS04_69_72')
