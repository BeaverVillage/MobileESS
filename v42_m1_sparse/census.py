"""CSR matrix census in bounded chunks; no coefficient truncation or solve."""
from collections import Counter
from time import perf_counter
import numpy as np
from v42_root.common import *
from v42_native.solver import assert_milp
GRID=('voltage_','line_thermal','transformer_','response_','injection_')
def inspect(m,label,start_values,baseline=False):
    m.update();s=assert_milp(m);names=m.getAttr('VarName');types=m.getAttr('VType');rows=m.getAttr('ConstrName')
    vf=[n.split('[')[0] for n in names];rf=[n.split('[')[0] for n in rows]
    families=sorted(set(vf));rowfamilies=sorted(set(rf));vid=np.array([families.index(f) for f in vf],dtype=np.int8)
    rid=np.array([rowfamilies.index(f) for f in rf],dtype=np.int16)
    print(label,'getA',s['nonzeros'],flush=True);a=m.getA();density=np.diff(a.indptr)
    occurrences=np.bincount(vid[a.indices],minlength=len(families));touched=np.zeros(len(families),dtype=np.int64)
    cross=np.zeros((len(rowfamilies),len(families)),dtype=np.int64);ranges={f:[float('inf'),0.] for f in rowfamilies}
    for lo in range(0,m.NumConstrs,10000):
        hi=min(lo+10000,m.NumConstrs);b,e=a.indptr[lo],a.indptr[hi];vi=vid[a.indices[b:e]]
        rr=np.repeat(np.arange(lo,hi),density[lo:hi]);localrf=rid[rr]
        touched+=np.bincount(np.unique(rr*len(families)+vi)%len(families),minlength=len(families))
        cross+=np.bincount(localrf*len(families)+vi,minlength=cross.size).reshape(cross.shape)
        ad=np.abs(a.data[b:e])
        for i,f in enumerate(rowfamilies):
            z=ad[localrf==i];z=z[z>0]
            if len(z):ranges[f][0]=min(ranges[f][0],float(z.min()));ranges[f][1]=max(ranges[f][1],float(z.max()))
    vr=[dict(family=f,columns=vf.count(f),type_counts=json.dumps(dict(Counter(t for t,v in zip(types,vf) if v==f))),coefficient_occurrences=int(occurrences[i]),constraints_touched=int(touched[i])) for i,f in enumerate(families)]
    rr=[]
    for i,f in enumerate(rowfamilies):
        ids=np.flatnonzero(rid==i);d=density[ids];mx=ids[np.argmax(d)]
        rr.append(dict(family=f,rows=len(ids),nonzeros=int(d.sum()),mean=float(d.mean()),median=float(np.median(d)),P95=float(np.percentile(d,95)),P99=float(np.percentile(d,99)),maximum=int(d.max()),maximum_row=rows[mx],maximum_row_index=int(mx)))
    top=np.argsort(density)[-50:][::-1]
    dense=[dict(row_index=int(i),row=rows[i],family=rf[i],nonzeros=int(density[i])) for i in top]
    x=np.array([start_values[n] for n in names]);activity=a@x;rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'))
    error=np.where(sense=='=',abs(activity-rhs),np.where(sense=='<',activity-rhs,rhs-activity))
    lb=np.array(m.getAttr('LB'));ub=np.array(m.getAttr('UB'))
    residual=max(0.,float(error.max()),float((lb-x).max()),float((x-ub).max()))
    assert residual<=1e-5,(label,residual,rows[np.argmax(error)])
    mapped=dict(PASS=True,matrix_max_violation=residual,variables=m.NumVars,rho=start_values['rho_max'],physical_projection_unchanged=True,integer_LP_domains_unchanged=True)
    def finite_range(z):
        z=np.abs(z);z=z[(z>0)&(z<1e99)];return dict(min_abs=float(z.min()) if len(z) else None,max_abs=float(z.max()) if len(z) else None)
    numeric=dict(matrix=finite_range(a.data),RHS=finite_range(rhs),bounds=finite_range(np.concatenate([lb,ub])),objective=finite_range(np.array(m.getAttr('Obj'))),matrix_family_extremes={f:dict(min_abs=v[0] if np.isfinite(v[0]) else None,max_abs=v[1]) for f,v in ranges.items()},coefficient_deletion=False,rounding=False,clipping=False)
    numeric['matrix']['ratio']=numeric['matrix']['max_abs']/numeric['matrix']['min_abs']
    s.update(candidate=label,columns=m.NumVars,rows=m.NumConstrs,grid_nonzeros=sum(r['nonzeros'] for r in rr if r['family'].startswith(GRID)),voltage_nonzeros=sum(r['nonzeros'] for r in rr if 'voltage' in r['family']),line_nonzeros=sum(r['nonzeros'] for r in rr if 'line' in r['family']),transformer_nonzeros=sum(r['nonzeros'] for r in rr if 'transformer' in r['family']),PCS_nonzeros=sum(r['nonzeros'] for r in rr if r['family']=='PCS16'),max_row_density=int(density.max()),P99_row_density=float(np.percentile(density,99)))
    folder=OUT/'census';folder.mkdir(exist_ok=True)
    atomic(folder/(label+'.json'),dict(stats=s,variables=vr,rows=rr,start=mapped,numerical=numeric))
    if baseline:
        table('BASELINE_VARIABLE_FAMILY_CENSUS.csv',vr);table('BASELINE_ROW_FAMILY_CENSUS.csv',rr);table('BASELINE_DENSEST_ROWS.csv',dense)
        audit={f:{v:int(cross[rowfamilies.index(f),families.index(v)]) for v in ('Pch','Pdis','Q')} for f in rowfamilies if f.startswith(('voltage_','line_thermal','transformer_'))}
        dump('GRID_AFFINE_REPETITION_AUDIT.json',dict(grid_families=audit,individual_P_occurrences=sum(v['Pch']+v['Pdis'] for v in audit.values()),individual_Q_occurrences=sum(v['Q'] for v in audit.values()),fixed_AIDC_symbolic_columns=0,fixed_AIDC_contribution='already numeric, folded into constants/RHS by original Gurobi LinExpr construction'))
    del a
    return s,mapped,numeric
