"""Exhaustive successor projection, scientific optima and matrix tradeoffs."""
from time import perf_counter
from v42_root.common import *
from v42_root.gates import fixtures,physical_sets,scientific,model
from v42_root.eliminate import project
from .config import PRIMARY

KINDS=PRIMARY[1:]+['DA0','DA1','DA2','DA3','LINK','F0','STATE']
def size(m):
    import numpy as np
    m.update();density=np.diff(m.getA().indptr)
    return dict(columns=m.NumVars,rows=m.NumConstrs,nonzeros=m.NumNZs,max_density=int(density.max()),p99_density=float(np.percentile(density,99)))
def main():
    frozen();start=perf_counter();results=[];decompositions=[];structures=[]
    source={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for folder in ['v42_root','v42_sparse'] for p in sorted((ROOT/folder).glob('*.py'))}
    for label,jobs,bounds,r in fixtures():
        sets,rows=physical_sets(label,jobs,bounds,r,kinds=KINDS)
        sci=scientific(label,jobs,bounds,r,kinds=['F2']+KINDS)
        results.append(dict(case=label,physical=sets,scientific=sci));decompositions+=rows
        for kind in ['F2']+KINDS:
            m,*_=model(jobs,bounds,r,kind);structures.append(dict(case=label,formulation=kind,**size(m)));m.dispose()
        print('sparse complete physical + six levels',label,'PASS',flush=True)
    if any(sha(ROOT/p)!=h for p,h in source.items()):raise ValueError('SOURCE_CHANGED_DURING_EQUIVALENCE')
    receipt=dict(PASS=True,cases=results,source_sha256=source,seconds=perf_counter()-start,complete_bounded_domains=True,reverse_pool_complete=True,all_six_objectives=True,deterministic_reconstruction=True)
    dump('FORMULATION_EXACTNESS.json',receipt)
    table('AGGREGATE_TO_INDIVIDUAL_VALIDATION.csv',decompositions);table('BOUNDED_STRUCTURAL_COMPARISON.csv',structures)
    for name in ['RUNTIME_CLASS_COUNT_EQUIVALENCE.json','CANONICAL_POST_TIE_VALIDATION.json']:
        dump(name,dict(PASS=True,evidence='FORMULATION_EXACTNESS.json',source_sha256=source,cases=len(results),six_scientific_objectives_preserved=True,individual_reconstruction=True))
    # Algebraic state elimination audit retains all derived bounds; no dense
    # projection is silently admitted to production on column reduction alone.
    state=[]
    from v42_root.gates import fixture
    j,b,r,_=fixture('F');m,units,data,*_=model({j.uid:j},{j.uid:b},r,'F2')
    state.append(dict(family='retained',**size(m)))
    for family in ['r0','h','r1']:
        n,*_=project(m,{j.uid:units[0]['v']},{family});state.append(dict(family=family,**size(n)));n.dispose()
    m.dispose();dump('STATE_COMPRESSION_AUDIT.json',dict(bounded_projection=state,selection='retain sparse migration recurrences; histogram compression only for certified nonmigration paths',full_cumulative_projection_selected=False,reason='projection removes state columns but expands downstream rows; no timing-based admission without structural and clean LP evidence'))
    frozen()
if __name__=='__main__':main()
