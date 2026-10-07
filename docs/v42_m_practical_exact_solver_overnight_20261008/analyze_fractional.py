"""Read-only original-axis fractional-family evidence; no model/solve/cuts."""
from practical_support import *
from collections import defaultdict
def analyze():
    A,d,_=hc.load();binary=np.flatnonzero(d['types']=='B');CSC=A.tocsc();rows=[];points={}
    for p in [OLD/'NATIVE_ROOT_POINT.npz',OUT/'runs/cuts0_control/ROOT_POINT.npz']:
        if not p.exists():continue
        with np.load(p) as z:x=z['x'].copy()
        family=defaultdict(list);by_window=defaultdict(list)
        for j in binary:
            name=str(d['names'][j]);f=name.split('[',1)[0];distance=min(abs(float(x[j])),abs(1-float(x[j])))
            fields=name.split('[',1)[1][:-1].split(',');unit=fields[0];slot=int(fields[-1]);fractional=distance>1e-8
            family[f].append((j,fractional,distance));by_window[(f,unit,slot)].append((j,fractional,distance))
        source=p.relative_to(ROOT).as_posix()
        for f,values in family.items():
            rows.append(dict(source=source,family=f,count=len(values),fractional_count=sum(v[1] for v in values),fractional_fraction=sum(v[1] for v in values)/len(values),mean_distance=float(np.mean([v[2] for v in values])),max_distance=max(v[2] for v in values),objective_zero_columns=sum(d['objective'][v[0]]==0 for v in values)))
        candidates=[int(j) for j in binary if min(abs(float(x[j])),abs(1-float(x[j])))>1e-8]
        candidates=sorted(candidates,key=lambda j:(-min(abs(float(x[j])),abs(1-float(x[j]))),j))
        relaxed=hc.replay(A,dict(d,types=np.full(len(x),'C')),x,False)
        family_slots=[dict(family=f,MESS=u,slot=t,count=len(v),fractional=sum(a[1] for a in v),fractionality_mass=sum(a[2] for a in v)) for (f,u,t),v in sorted(by_window.items())]
        points[source]=dict(point_SHA256=sha(p),rho=float(x[239826]),relaxed_matrix_replay=relaxed,binaries=len(binary),fractional_count=len(candidates),family_by_MESS_slot=family_slots,top_fractional_candidates=[dict(column=j,name=str(d['names'][j]),X=float(x[j]),distance=min(abs(float(x[j])),abs(1-float(x[j]))),connected_rows=int(CSC.indptr[j+1]-CSC.indptr[j]),objective_coefficient=float(d['objective'][j])) for j in candidates[:40]],interpretation='Root observations only; no measured child uplift assigned and no heuristic score used for pruning')
    table(OUT/'FRACTIONAL_FAMILY_CENSUS.csv',rows)
    atomic(OUT/'FRACTIONAL_BRANCH_EVIDENCE.json',dict(UTC=stamp(),optimize_calls=0,points=points,no_cut_or_formulation_change=True,adaptive_pseudocost_requires_actual_child_certificates=True))
    print('READ_ONLY_FRACTIONAL_CENSUS',[(k,v['fractional_count']) for k,v in points.items()])
if __name__=='__main__':analyze()
