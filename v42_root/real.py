"""Complete native per-job domains and full electrical rows, all six levels."""
import gc
import gurobipy as gp,numpy as np
from .common import *
from .data import prepare
from .native import build,reconstruct
from v42_compact.equivalence import solve_levels
def main(kinds=('F2','F2A','F2B','F2C')):
    source={'v42_root/'+name:sha(ROOT/'v42_root'/name) for name in ('common.py','data.py','factor.py','native.py','real.py')}
    source.update({'v42_sparse/'+name:sha(ROOT/'v42_sparse'/name) for name in ('config.py','runtime.py','canonical.py','real.py')})
    full=prepare();bundle,jobs,bounds,r,raw,graphs,old,prep=full;results=[]
    cases=[('native_identical_short_jobs',['8632483','8632484']),('native_TS_migration',['8665305']),('native_RUNNING_carryout',['8683269'])]
    for name,us in cases:
        classes={key:[u for u in members if u in us] for key,members in prep['classes'].items() if any(u in us for u in members)}
        data=(bundle,{u:jobs[u] for u in us},{u:bounds[u] for u in us},r,{u:x for u,x in raw.items() if u not in jobs or u in us},{u:graphs[u] for u in us},{u:old[u] for u in us},dict(prep,classes=classes))
        rows=[]
        for kind in kinds:
            m,units,levels,controls,bindings=build(Context(),data,kind);m.Params.Threads=1;m.Params.Seed=20260929
            m.Params.OptimalityTol=1e-9;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
            row=solve_levels(m,levels[:6]);row['formulation']=kind
            if row['status']=='OPTIMAL':
                selected=reconstruct(units,data)
                if selected!=reconstruct(units,data):raise ValueError('NONDETERMINISTIC_REAL_RECONSTRUCTION')
                known=max(abs(x.X-(r.fixed_gpu.get((k,t),0)+sum(jobs[u].gpu for u,o in selected.items() for site,a,b in o['segments'] if site==k and a<=t<b))) for (k,t),x in bindings['known'].items())
                if known>1e-5:raise ValueError('REAL_KNOWN_GPU_BINDING')
                row['independent_known_GPU_violation']=known
                if kind not in ('F2','F2-BASE'):
                    from .certify import certificate
                    cert,*_=certificate(m,units,data,controls,bindings,levels,np.asarray(m.getAttr('X')),m.MaxVio)
                    if not cert['PASS']:raise ValueError('REAL_INDEPENDENT_CERTIFICATE:'+str(cert))
                    row['independent_native_certificate']=cert
            rows.append(row);m.dispose();del m,units,controls,bindings;gc.collect();print('real',name,kind,row['status'],flush=True)
        if len({x['status'] for x in rows})!=1 or any(not np.allclose(rows[0]['objectives'],x['objectives'],atol=3e-6,rtol=1e-7) for x in rows[1:]):raise ValueError('NATIVE_SCIENTIFIC_EQUIVALENCE:'+name+str(rows))
        results.append(dict(case=name,jobs=us,domain_scope='complete original sites/starts/checkpoints/service/WAN/restart/boundaries/carryout',native_electrical_slots=96,all_native_rows=True,rows=rows,PASS=True))
    if any(sha(ROOT/p)!=h for p,h in source.items()):raise ValueError('SOURCE_CHANGED_DURING_NATIVE_EQUIVALENCE')
    dump('NATIVE_REAL_EQUIVALENCE.json',dict(PASS=True,cases=results,source_sha256=source,limitation='Other explicit jobs are omitted consistently from every formulation; this certifies equivalence, not the full May optimum. No per-job authority is truncated.'))
if __name__=='__main__':main()
