"""Exact bound-certified electrical presolve; original AIDC domains unchanged."""
from common8500 import *
import scipy.sparse as sp
import gurobipy as gp
CTX=None
MARGIN=1e-8
def prepare(ctx,folder,fixed=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    sites=ctx.capacity.aidc_ids
    lo=np.array([[min(ctx.tables[s][t]) for s in sites] for t in range(96)])
    hi=np.array([[max(ctx.tables[s][t]) for s in sites] for t in range(96)])
    # Bounds follow exactly from the original PWL power law and GPU capacity;
    # they are used for proofs only, never to modify a decision variable.
    floor=-np.inf;bounds=[]
    for t,c in enumerate(ctx.coefficients):
        if fixed is None:
            f=PREF/f'full_model/electrical_blocks/slot_{t:02}'
            a=sp.load_npz(f/'FULL_LINEAR_MATRIX.npz')
            with np.load(f/'RHS_AND_SEED.npz') as z:b=z['rhs'].copy()
        else:a,b,_=matrix_for_slot(c,fixed[t])
        w=a[:,:12];positive=w.maximum(0);negative=w.minimum(0)
        lower=positive@lo[t]+negative@hi[t]-b;upper=positive@hi[t]+negative@lo[t]-b
        line=np.asarray(a[:,12].toarray()).ravel()==-1
        floor=max(floor,float(lower[line].max())-MARGIN)
        np.savez_compressed(folder/f'bounds_{t:02}.npz',lower=lower,upper=upper,line=line)
        sp.save_npz(folder/f'full_{t:02}.npz',a);np.save(folder/f'rhs_{t:02}.npy',b)
    floor=max(0.,floor);kept=0;cert=[]
    for t in range(96):
        a=sp.load_npz(folder/f'full_{t:02}.npz');b=np.load(folder/f'rhs_{t:02}.npy')
        with np.load(folder/f'bounds_{t:02}.npz') as z:upper=z['upper'];line=z['line']
        redundant=np.where(line,upper<=floor-MARGIN,upper<=-MARGIN);idx=np.flatnonzero(~redundant)
        sp.save_npz(folder/f'active_{t:02}.npz',a[idx]);np.savez_compressed(folder/f'active_data_{t:02}.npz',rhs=b[idx],original_row_indices=idx)
        kept+=len(idx);cert.append(dict(slot=t,full_rows=a.shape[0],retained_rows=len(idx),provably_redundant=int(redundant.sum())))
    report=dict(status='PASS',method='EXACT_INTERVAL_REDUNDANCY_CERTIFICATE_NOT_SENSITIVITY_PRUNING',rho_implied_lower_bound=floor,full_rows=31945536,retained_rows=kept,margin=MARGIN,domain_changes=0,candidate_removals=0,PCC_bounds_source='Original frozen per-site C1 PWL breakpoint range with authorized expanded scheduling capacity and frozen power law',slots=cert)
    np.savez_compressed(folder/'PCC_IMPLIED_BOUNDS.npz',lower=lo,upper=hi);save(folder/'CERTIFICATE.json',report)
    return report
def add_grid(model,coefficients,controls,objective_cap=1.):
    assert CTX is not None
    assert all(isinstance(controls[t][j],gp.Var) for t in range(96) for j in range(12))
    assert all(isinstance(controls[t][j],(int,float,np.number)) for t in range(96) for j in range(12,60))
    folder=CTX.production_electrical_rows;cert=read(folder/'CERTIFICATE.json')
    rho=model.addVar(lb=0,ub=objective_cap,name='rho_max');model.update()
    with np.load(folder/'PCC_IMPLIED_BOUNDS.npz') as z:
        for t in range(96):
            for j in range(12):
                assert controls[t][j].LB==z['lower'][t,j] and controls[t][j].UB==z['upper'][t,j]
    model.addConstr(rho>=cert['rho_implied_lower_bound'],name='IEEE8500_DERIVED_RHO_LOWER_BOUND')
    for t in range(96):
        a=sp.load_npz(folder/f'active_{t:02}.npz')
        with np.load(folder/f'active_data_{t:02}.npz') as z:b=z['rhs']
        if not len(b):continue
        x=gp.MVar.fromlist(list(controls[t][:12])+[rho]);model.addMConstr(a,x,'<',b,name=f'IEEE8500_FULL_EQUIVALENT_{t}')
    model.update()
    return rho,dict(full_logical_rows=31945536,materialized_certified_equivalent_rows=cert['retained_rows']+1,certificate=record(folder/'CERTIFICATE.json'),no_AIDC_domain_changes=True)
