"""Complete local trajectory disjunction and exact homogeneous Balas lift.

No optimization here. Transit mode bits are independent binary cubes, factored
without deleting any integral state. Every native coefficient is exactly the
binary64 coefficient of the original physical row, with no summed travel cost.
"""
from common import *
from array import array
from collections import defaultdict,Counter
from fractions import Fraction as F
import itertools, time

def frac(v):return v if isinstance(v,F) else F.from_float(float(v))
def clipped_half(faces,mode,L,S):
    # Exact polygon clipping, independent verifier uses pairwise intersections.
    polygon=[(F(0),-S),(L,-S),(L,S),(F(0),S)]
    planes=[(a*(1 if mode==0 else -1),b,c) for a,b,c in faces]
    for a,b,c in planes:
        new=[]
        for v,w in zip(polygon,polygon[1:]+polygon[:1]):
            fv=a*v[0]+b*v[1]-c;fw=a*w[0]+b*w[1]-c
            if fv<=0:new.append(v)
            if (fv<0 and fw>0) or (fv>0 and fw<0):
                alpha=fv/(fv-fw);new.append((v[0]+alpha*(w[0]-v[0]),v[1]+alpha*(w[1]-v[1])))
        polygon=list(dict.fromkeys(new))
        assert polygon
    selected=[]
    for i,(a,b,c) in enumerate(planes):
        active=[v for v in polygon if a*v[0]+b*v[1]==c]
        if len(active)>=2:selected.append(i)
    return planes,selected,polygon

def generate(unit='MESS04',start=69,end=73,label='MESS04_69_72'):
    from prepare import enumerate_paths
    t0=time.perf_counter();a=Authority();paths=enumerate_paths(a,unit,start,end)
    H=end-start;assert H==4
    energy=[a.energy(unit,t) for t in range(start,end)]
    assert all(e['normalizer']==1 for e in energy)
    geometries={};cache={}
    for t in range(start,end):
        for site in a.sites:
            if f'Q[{unit},{site},{t}]' not in a.names:continue
            faces=a.pcs(unit,site,t)
            for mode in (0,1):
                key=tuple(faces),mode
                if key not in cache:cache[key]=clipped_half(faces,mode,frac(a.battery.p_limit),frac(a.battery.pcs_kva))
                planes,selected,vertices=cache[key]
                geometries[f'{t}:{site}:{mode}']=dict(planes=[[str(x) for x in p] for p in planes],selected=selected,vertices=[[str(x) for x in p] for p in vertices])
    # Reject non-binary64 transport rather than round an exact hull coefficient.
    for geom in geometries.values():
        for p in geom['planes']:
            assert all(frac(float(F(c)))==F(c) for c in p)
    for e in energy:assert all(frac(float(e[k]))==e[k] for k in ('charge','discharge'))
    A,d,_=load();n=A.shape[1]
    rr=array('i');cc=array('i');vv=array('d');senses=[];rhs=[]
    lower=array('d');upper=array('d');blocks=[]
    arc_link=defaultdict(list);power_link=defaultdict(list);mode_one=defaultdict(list);mode_off=defaultdict(list);E0_link=[];lambda_link=[];Et_link=defaultdict(list)
    def col(lo,hi):
        j=n+len(lower);lower.append(lo);upper.append(hi);return j
    def row(terms,sense='<',value=0):
        i=len(senses);senses.append(sense);rhs.append(float(value))
        for j,w in terms:
            if w:rr.append(i);cc.append(int(j));vv.append(float(w))
        return i
    for path_id,path in enumerate(paths):
        stays={a.arcs[k][1]:(a.arcs[k][0],k) for k in path if a.arcs[k][-1] is None}
        departures={a.arcs[k][1]:k for k in path if a.arcs[k][-1] is not None and start<=a.arcs[k][1]<end}
        events=sorted(set(stays)|set(departures))
        cost=sum((frac(a.arcs[k][-1].energy_kwh) for k in departures.values()),F(0))
        assert cost<=frac(a.battery.maximum-a.battery.minimum),'EMPTY_TRAJECTORY_REQUIRES_EXACT_CHECK'
        connected=sorted(stays)
        for bits in itertools.product((0,1),repeat=len(connected)):
            modes=dict(zip(connected,bits));first_col=n+len(lower);first_row=len(senses)
            lam=col(0,1);lambda_link.append(lam)
            for k in path:arc_link[k].append(lam)
            estate=[col(0,a.battery.maximum) for _ in range(len(events)+1)];E0_link.append(estate[0])
            for ej in estate:
                row([(ej,1),(lam,-a.battery.maximum)])
                row([(ej,-1),(lam,a.battery.minimum)])
            powers=[]
            for pos,t in enumerate(events):
                ej,after=estate[pos:pos+2]
                if t in stays:
                    site,k=stays[t];mode=modes[t];p=col(0,a.battery.p_limit);q=col(-a.battery.pcs_kva,a.battery.pcs_kva)
                    powers.append((t,site,mode,p,q));power_link['Pch' if mode else 'Pdis',site,t].append(p);power_link['Q',site,t].append(q)
                    row([(p,1),(lam,-a.battery.p_limit)])
                    geom=geometries[f'{t}:{site}:{mode}']
                    for facet in geom['selected']:
                        alpha,beta,gamma=map(F,geom['planes'][facet]);row([(p,alpha),(q,beta),(lam,-gamma)])
                    coefficient=energy[t-start]['charge' if mode else 'discharge']
                    row([(after,1),(ej,-1),(p,-coefficient)],'=')
                else:
                    k=departures[t];source_col=a.names[f'arc[{unit},{k}]']
                    # Actual stored energy row, not recomputed battery/route formula.
                    cost=energy[t-start]['raw'][source_col]
                    assert cost==frac(a.arcs[k][-1].energy_kwh)
                    row([(after,1),(ej,-1),(lam,cost)],'=')
            for t in range(start,end):
                if t not in stays:mode_off[t].append(lam)
                elif modes[t]:mode_one[t].append(lam)
                Et_link[t+1].append(estate[sum(event<=t for event in events)])
            blocks.append((path_id,sum(int(modes[t])<<(t-start) for t in modes),first_col,n+len(lower),first_row,len(senses)))
        if path_id and path_id%25000==0:print('HULL_BUILD',label,path_id,'of',len(paths),'rows',len(senses),'cols',len(lower),flush=True)
    block_end=len(senses)
    row([(j,1) for j in lambda_link],'=',1)
    def link(name,terms):
        expression,constant=a.expression(name)
        row(list(expression.items())+[(j,-w) for j,w in terms],'=',-constant)
    for k,lams in sorted(arc_link.items()):link(f'arc[{unit},{k}]',[(j,1) for j in lams])
    for t in range(start,end):
        for site in a.sites:
            for family in ('Pch','Pdis','Q'):link(f'{family}[{unit},{site},{t}]',[(j,1) for j in power_link[family,site,t]])
        u=col(0,1)
        link(f'charge_mode[{unit},{t}]',[(j,1) for j in mode_one[t]]+[(u,1)])
        row([(u,1)]+[(j,-1) for j in mode_off[t]])
    link(f'SOC[{unit},{start}]',[(j,1) for j in E0_link])
    for t in range(start+1,end+1):link(f'SOC[{unit},{t}]',[(j,1) for j in Et_link[t]])
    B=sparse.coo_matrix((np.frombuffer(vv,dtype=np.float64).copy(),(np.frombuffer(rr,dtype=np.int32).copy(),np.frombuffer(cc,dtype=np.int32).copy())),shape=(len(senses),n+len(lower))).tocsr();B.sum_duplicates();B.sort_indices()
    assert max(np.diff(B.indptr))<len(lower)+1
    sparse.save_npz(OUT/(label+'_EF_MATRIX.npz'),B)
    np.savez_compressed(OUT/(label+'_EF_DATA.npz'),lower=np.asarray(lower),upper=np.asarray(upper),rhs=np.asarray(rhs),sense=np.asarray(senses),blocks=np.asarray(blocks,dtype=np.int64))
    trajectories=[dict(id=i,arcs=list(path),connected_slots=[a.arcs[k][1] for k in path if a.arcs[k][-1] is None],all_mode_bits=list(range(16))) for i,path in enumerate(paths)]
    write(label+'_INTEGER_TRAJECTORIES.json',dict(unit=unit,start=start,end_exclusive=end,mobility_count=len(paths),integer_trajectory_count=len(paths)*16,disjuncts=len(blocks),mode_cube_factorization='Transit mode bits arbitrary binary, independent of zero P/Q/SOC; exact convexification [0,1], not omitted states',boundary_SOC='Original finite bounds, not observed LP value; horizon-global extension not assumed',trajectories=trajectories))
    authority=dict(unit=unit,start=start,end_exclusive=end,representation='Homogeneous Balas disjunction over every local time-DAG path and every connected-slot mode word; free transit mode cubes exactly factored',integer_feasible_set_preserved=True,exact_local_convex_hull=True,global_96_slot_hull_not_claimed=True,geometries=geometries,energy_coefficients=[{k:str(e[k]) for k in ('charge','discharge')} for e in energy],boundary_bounds=[a.battery.minimum,a.battery.maximum],rows=B.shape[0],columns_added=len(lower),nnz=B.nnz,original_columns=n,blocks=len(blocks),block_rows_end=block_end,all_coefficients_exactly_binary64_representable=True,all_EF_bounds_finite=True,nonempty_disjunct_proof='Zero power/Q, E69=maximum satisfies all movement decrements <=maximum-minimum; event SOC otherwise bounded by retained perspective rows',matrix_SHA256=sha(OUT/(label+'_EF_MATRIX.npz')),data_SHA256=sha(OUT/(label+'_EF_DATA.npz')),trajectories_SHA256=sha(OUT/(label+'_INTEGER_TRAJECTORIES.json')),build_seconds=time.perf_counter()-t0)
    write(label+'_HULL_AUTHORITY.json',authority)
    print('HULL_COMPLETE',label,len(paths),len(blocks),B.shape,B.nnz,'seconds',authority['build_seconds'],flush=True)
    return authority

if __name__=='__main__':generate(unit=sys.argv[1] if len(sys.argv)>1 else 'MESS04',label=sys.argv[2] if len(sys.argv)>2 else 'MESS04_69_72')
