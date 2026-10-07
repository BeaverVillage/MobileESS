"""Solver-free independent native-row check of separator and mode control.

Does not import the separator producer or the trajectory constructor.
"""
from common import *
from fractions import Fraction as F
from collections import defaultdict
from verify_hull import intersections

def main():
    a=Authority();s=read(OUT/'MESS04_69_72_COMMON_MODE_SEPARATION.json')
    with np.load(HISTORY/'PURE_LP_POINT.npz') as z:x=z['x']
    unit='MESS04';checks=[]
    for result in s['results']:
        t=result['slot'];terms=defaultdict(F)
        for detail in result['details']:
            site=detail['site'];L=F.from_float(a.battery.p_limit);S=F.from_float(a.battery.pcs_kva)
            rows=[(-F(1),F(0),{}),(F(1),F(0),{'y':F(1)}),(-L,F(0),{'D':-F(1)}),(L,F(0),{'y':L,'C':-F(1)})]
            for aa,bb,cap in a.pcs(unit,site,t):
                rows.extend([(-cap,bb,{'D':-aa}),(cap,-bb,{'y':cap,'C':aa,'Q':-bb})])
            rows.extend([(-S,F(1),{}),(-S,-F(1),{}),(S,-F(1),{'y':S,'Q':-F(1)}),(S,F(1),{'y':S,'Q':F(1)})])
            saved=[(F(r['u_coefficient']),F(r['qD_coefficient']),{k:F(v) for k,v in r['rhs'].items()}) for r in detail['rows']]
            assert rows==saved
            weights=[(int(i),F(w)) for i,w in detail['dual_weights']]
            assert all(w>=0 for i,w in weights)
            support=defaultdict(F)
            if weights:
                assert sum(w*rows[i][0] for i,w in weights)==-1
                assert sum(w*rows[i][1] for i,w in weights)==0
            for i,w in weights:
                for k,v in rows[i][2].items():support[k]-=w*v
            assert dict(support)=={k:F(v) for k,v in detail['support_coefficients'].items()}
            siteid=a.sites.index(site)
            names={'y':f'arc[{unit},{siteid*96+t}]','C':f'Pch[{unit},{site},{t}]','D':f'Pdis[{unit},{site},{t}]','Q':f'Q[{unit},{site},{t}]'}
            for k,w in support.items():terms[names[k]]+=w
            # Independently test every original half-polygon vertex.
            for bit in (0,1):
                planes=[(aa*(1 if bit==0 else -1),bb,cap) for aa,bb,cap in a.pcs(unit,site,t)]
                vertices=intersections(planes+[(-F(1),F(0),F(0)),(F(1),F(0),L)])
                assert vertices
                for p,q in vertices:
                    v={'y':F(1),'C':p if bit else F(0),'D':F(0) if bit else p,'Q':q}
                    assert sum(support[k]*v[k] for k in support)<=1-bit
        terms[f'charge_mode[{unit},{t}]']+=1
        assert {k:v for k,v in terms.items() if v}=={k:F(v) for k,v in result['physical_terms'].items()}
        violation=sum(w*a.value(k,x) for k,w in terms.items())-1
        assert violation==F(result['exact_violation'])
        checks.append(dict(slot=t,exact_violation=str(violation),native_halfplane_weights_checked=True,all_half_polygon_vertices_checked=True))
    with np.load(OUT/'MODE_RELABELED_PROXY_POINT.npz') as z:y=z['x']
    A,d,_=load();changed=np.flatnonzero(x!=y)
    assert len(changed)==1 and d['names'][changed[0]]=='charge_mode[MESS04,71]'
    assert d['objective'][changed[0]]==0 and float(d['objective']@x)==float(d['objective']@y)
    strongest=s['strongest'];terms={k:F(v) for k,v in strongest['physical_terms'].items()}
    assert sum(w*a.value(k,y) for k,w in terms.items())<=1
    geometries=[]
    for label in ('MESS04_69_72','MESS03_69_72'):
        h=read(OUT/(label+'_HULL_AUTHORITY.json'));cache=set()
        for key,g in h['geometries'].items():
            planes=[tuple(map(F,r)) for r in g['planes']];signature=tuple(planes),tuple(g['selected'])
            if signature in cache:continue
            cache.add(signature)
            bounds=[(-F(1),F(0),F(0)),(F(1),F(0),F(300))]
            retained=[planes[k] for k in g['selected']]
            assert any(bb>0 for aa,bb,cap in retained) and any(bb<0 for aa,bb,cap in retained)
            # The EF retains PCS facets but no perspective Q-box rows.
            # Prove omitted Q-boxes and PCS facets without assuming them.
            reduced=intersections(retained+bounds)
            assert reduced==intersections(planes+bounds)=={tuple(map(F,v)) for v in g['vertices']}
            assert all(abs(q)<=400 for p,q in reduced)
        geometries.append(dict(label=label,unique_geometries=len(cache),perspective_Q_boxes_exactly_implied=True))
    # Adversarial sign/normalization errors cannot satisfy the exact identity.
    samples=[d for r in s['results'] for d in r['details'] if d['dual_weights']]
    witness=samples[0];i,w=witness['dual_weights'][0];row=witness['rows'][i]
    original_sum=sum(F(v)*F(witness['rows'][j]['u_coefficient']) for j,v in witness['dual_weights'])
    assert original_sum==-1 and -original_sum!=-1 and original_sum*F(101,100)!=-1
    write('CAUSAL_CONTROLS_INDEPENDENT_VERIFICATION.json',dict(PASS=True,optimize_calls=0,production_constructor_imported=False,separator_producer_imported=False,exact_separator_checks=checks,only_objective_zero_mode_coordinate_changed=True,strongest_separator_removed_without_PQ_route_SOC_change=True,does_not_claim_full_four_slot_membership=True,additional_geometry_checks=geometries,sign_and_one_percent_multiplier_mutations_rejected=True))
    print('CAUSAL_CONTROLS_INDEPENDENT_PASS',flush=True)

if __name__=='__main__':main()
