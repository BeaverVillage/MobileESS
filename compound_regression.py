"""Focused contract proof; no model creation or optimization."""
from fast_prepare import *
import ast,inspect
import numpy as np

def node(source,name,method=None):
    tree=ast.parse(source)
    found=next(n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
    if method:found=next(n for n in found.body if isinstance(n,ast.FunctionDef) and n.name==method)
    return ast.dump(found,include_attributes=False)

def run(ranking,preparation_seconds,output):
    from dayahead.v41.physics_ranking import INSTANCE,existing_anchor_search_units
    before=OUT/'development_only/source'
    old=(before/'dayahead/v41/physics_ranking.py').read_text(encoding='utf-8')
    new=(ROOT/'dayahead/v41/physics_ranking.py').read_text(encoding='utf-8')
    direct=['__init__','gains','add','delta_gpu','net_score','score_active','tier','describe','accepted']
    assert all(node(old,'Ranking',m)==node(new,'Ranking',m) for m in direct)
    a=(before/'dayahead/v41r1/bounded_solver.py').read_text(encoding='utf-8')
    b=(ROOT/'dayahead/v41r1/bounded_solver.py').read_text(encoding='utf-8')
    for method in ('__init__','_solve','_semantic','optimize','vector','_refresh_structure'):
        assert node(a,'BoundedLex',method)==node(b,'BoundedLex',method)
    prior=read(OUT/'V41R3_FO_PHYSICS_RANKING_AUDIT.json')
    for k in ('candidate_count','candidate_set_SHA','sensitivities','critical','active_constraints','initial_priority_tier_top_20','top_20_direct_by_leverage'):
        assert ranking[k]==prior[k],k
    with np.load(OUT/'V41R3_RANKING_PHYSICS.npz') as z:
        assert np.array_equal(z['S'],INSTANCE.S) and np.array_equal(z['weights'],INSTANCE.weight)
    # The exact pre-existing two and three prefixes, including their full
    # time/site effects, are supplied to the pure ordering function.
    uids=[]
    for r in prior['initial_priority_tier_top_20']+prior['top_20_direct_by_leverage']:
        if r['job_id'] not in [u for u,k in uids]:uids.append((r['job_id'],r['option_index']))
    for uid,d in INSTANCE.data.items():
        if len(uids)>=3:break
        if uid not in [u for u,k in uids] and d['g'] and len(d['opts'])>1:
            uids.append((uid,int(np.argmax(d['exposure']))))
    assert len(uids)>=3
    components=uids[:3];scores={};numeric=[]
    for width in (2,3):
        part=components[:width];s=INSTANCE.net_score(part)
        delta=sum((INSTANCE.delta_gpu(u,[k],np.arange(96))[0] for u,k in part),np.zeros((96,12),int))
        assert np.array_equal(delta,s['net_gpu_delta'])
        p=s['net_pcc_delta']
        expected=INSTANCE.Arho+np.sum(INSTANCE.AS*p[INSTANCE.at],axis=1)
        assert float(expected.max())==s['P1_hat_active']
        expected_exposure=float(np.sum(INSTANCE.weight*np.maximum(-np.sum(INSTANCE.ES*p,axis=1),0)))
        assert abs(expected_exposure-s['ExposureRelief'])<1e-13
        s['differential_sensitivity_relief']=float(sum(INSTANCE.data[u]['gamma'][k] for u,k in part))
        scores[str(width)]=s
        numeric.append(dict(width=width,all_components_used=True,P1_hat=s['P1_hat_active'],exposure=s['ExposureRelief'],capacity_feasible=s['net_capacity_feasible']))
    group={u:i for i,(u,k) in enumerate(components)};anchors=list(group.values())
    best={u:dict(rank=i+1,metrics=(.9+i*.001,.01,.001,.0001)) for i,(u,k) in enumerate(components)}
    units=existing_anchor_search_units(anchors,components,group,best,scores)
    assert all(units[i]['key']<=units[i+1]['key'] for i in range(len(units)-1))
    assert {g for r in units for g in r['groups']}==set(anchors)
    # Test-only score substitutions prove the consumed queue responds to
    # compound metrics, including every lexicographic tie-break level.
    checks=[]
    fields=('P1_hat_active','ExposureRelief','critical_leverage','differential_sensitivity_relief')
    for field in fields:
        test={str(w):dict(P1_hat_active=.8,ExposureRelief=.01,critical_leverage=.001,differential_sensitivity_relief=.0001) for w in (2,3)}
        test['3'][field]+=(-.01 if field=='P1_hat_active' else .01)
        first=existing_anchor_search_units(anchors,components,group,best,test)
        order=[r['kind'] for r in first if r['kind'].startswith('EXISTING_COMPOUND')]
        assert order==['EXISTING_COMPOUND_3','EXISTING_COMPOUND_2']
        checks.append(field)
    equal={str(w):dict(P1_hat_active=.8,ExposureRelief=.01,critical_leverage=.001,differential_sensitivity_relief=.0001) for w in (2,3)}
    assert [r['kind'] for r in existing_anchor_search_units(anchors,components,group,best,equal) if r['kind'].startswith('EXISTING_COMPOUND')]==['EXISTING_COMPOUND_2','EXISTING_COMPOUND_3']
    # Exact consumer linkage, as opposed to diagnostic-only persistence.
    choose=inspect.getsource(__import__('dayahead.v41r1.bounded_solver',fromlist=['BoundedLex']).BoundedLex._choose)
    assert "anchor_stream=[g for unit in units for g in unit['groups']]" in choose
    assert 'for g in anchor_stream+interleaved:' in choose
    report=dict(status='PASS',COMPOUND_NET_EFFECT_COMPUTED='YES',COMPOUND_NET_EFFECT_USED_IN_ORDERING='YES',CANDIDATE_UNIVERSE_CHANGED='NO',NEW_VARIABLES=0,NEW_CONSTRAINTS=0,OBJECTIVE_CHANGED='NO',candidate_count=ranking['candidate_count'],candidate_set_SHA=ranking['candidate_set_SHA'],direct_ranking_unchanged=True,physical_coefficients_exact=True,unchanged_direct_functions=direct,compound_net_numeric_tests=numeric,all_four_score_levels_consumed=checks,existing_deterministic_tie_PASS=True,actual_consumer='BoundedLex._choose iterates the ordered existing-anchor-unit stream before unchanged full-domain direct fallback',new_compound_candidates=0,Cartesian_products=0,compound_domain='Only the exact 2-/3-prefix bundles already computed by the development implementation',overlap_note='Existing bundles can overlap/nest; different bundle priorities can yield the same de-duplicated job order. This is reported, not treated as a reason to invent new bundles.',source_files=[record(ROOT/'dayahead/v41/physics_ranking.py'),record(ROOT/'dayahead/v41r1/bounded_solver.py')],development_ranking=record(OUT/'V41R3_FO_PHYSICS_RANKING_AUDIT.json'),preparation_seconds_before_regression=preparation_seconds)
    save(output/'V41R3_COMPOUND_RANKING_COMPLETION_AUDIT.json',report)
    return report
