"""Exact necessary-certificate selection. Does not claim feasibility minimality."""
import itertools,sys
from fractions import Fraction
from .common import *
def select(day):
    rows=read(CASE/day/'BREAKING_STAYS.json');data=load(day);jobs=data[1];classes=data[7]['classes']
    margin=Fraction(read(OUT/(label(day)+'_S0_CERTIFICATE.json'))['exact_positive_contradiction_margin'])
    ranks=sorted(set(int(r['rank_same_site']) for r in rows if r['site']==jobs[classes[r['class_id']][0]].reference_site))
    trace=[]
    for rank in ranks:
        pool=[r for r in rows if r['site']==jobs[classes[r['class_id']][0]].reference_site and int(r['rank_same_site'])<=rank]
        by={}
        for r in pool:
            key=r['class_id'];prior=by.get(key)
            # One option per class, best relaxation; deterministic exact tie.
            score=(Fraction(r['class_delta_exact']),int(r['abs_delta_start']),int(r['delta_start'])>0,r['site'],int(r['start']),r['option_id'])
            if prior is None or score<prior[0]:by[key]=(score,r)
        candidates=[v[1] for v in by.values()]
        effects=sorted([-Fraction(r['class_delta_exact']) for r in candidates],reverse=True)
        minimum=next((k for k in range(1,len(effects)+1) if sum(effects[:k],Fraction(0))>=margin),None)
        trace.append(dict(rank=rank,classes_available=len(candidates),maximum_certificate_reduction=str(sum(effects,Fraction(0))),minimum_classes_necessary=minimum,
            solve_executed=False,reason='EXACT_NECESSARY_CERTIFICATE_BOUND'))
        if minimum is None:continue
        choices=[]
        for subset in itertools.combinations(candidates,minimum):
            if -sum((Fraction(r['class_delta_exact']) for r in subset),Fraction(0))<margin:continue
            deltas=[int(r['abs_delta_start']) for r in subset]
            score=(len(subset),len(subset),max(deltas),sum(deltas),0,0,0,tuple(sorted((int(r['delta_start'])>0,r['site'],int(r['start']),r['option_id']) for r in subset)))
            choices.append((score,subset))
        if not choices:continue
        score,subset=min(choices,key=lambda x:x[0]);selection=list(subset)
        atomic(CASE/day/'SELECTION.json',selection)
        write(label(day)+'_NECESSARY_SELECTION.json',dict(PASS=True,rank=rank,shell='S1' if rank==1 else 'S2',selected=selection,
            lex_score=score,necessary_classes_lower_bound=minimum,necessary_option_count_lower_bound=minimum,
            original_certificate_margin=str(margin),strict_minimal_full_feasible_domain_proven=False,selection_scope='SAME_SITE_CERTIFICATE_NECESSITY; full LP/MIP gate still required'))
        write(label(day)+'_SELECTION_TRACE.json',trace)
        print(day,'rank',rank,'selected',len(selection),'classes','delta',[-Fraction(r['class_delta_exact']) for r in selection],flush=True)
        return selection
    write(label(day)+'_SELECTION_TRACE.json',trace)
    print(day,'NO_SAME_SITE_CERTIFICATE_COVER',flush=True)
if __name__=='__main__':select(sys.argv[1])
