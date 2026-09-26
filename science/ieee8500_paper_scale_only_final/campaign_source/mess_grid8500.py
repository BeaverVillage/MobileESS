"""Full frozen electrical equations with certified MESS-domain presolve."""
from common8500 import *
import gurobipy as gp,scipy.sparse as sp,math
from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters
COS=math.cos(math.pi/16);COUNT=0
_POLYGON_CACHE_HITS=0
_POLYGON_CACHE_MISSES=0
def polygon_parameters(c):
    """Reuse immutable IEEE8500 polygon linearization across route candidates."""
    global _POLYGON_CACHE_HITS,_POLYGON_CACHE_MISSES
    if os.environ.get('PAPER_8500_POLYGON_CACHE','1')=='0':
        return anchored_polygon_parameters(c)
    from dayahead.v35r3 import algorithm as fixed_candidate
    if c.coefficient_sha256 in fixed_candidate._POLYGON_CACHE:
        _POLYGON_CACHE_HITS+=1
    else:
        _POLYGON_CACHE_MISSES+=1
    bias,corr=fixed_candidate._cached_polygon_parameters(c)
    return bias,corr,c.anchor
def rows(c):
    yield 'voltage_upper',c.voltage_matrix.T,c.voltage_constant,1.05**2
    yield 'voltage_lower',-c.voltage_matrix.T,-c.voltage_constant,-.95**2
    bias,corr,_=polygon_parameters(c)
    for f in range(16):
        co=math.cos(2*math.pi*f/16);si=math.sin(2*math.pi*f/16)
        w=(co*c.flow_p_matrix[:NL]+si*c.flow_q_matrix[:NL])/COS+corr[:,:NL].T
        const=(co*c.flow_p_constant[:NL]+si*c.flow_q_constant[:NL])/COS+bias[:NL]-corr[:,:NL].T@c.anchor
        yield 'line',w,const,0.
        sl=slice(NL,NL+NT)
        yield 'tx', (co*c.flow_p_matrix[sl]+si*c.flow_q_matrix[sl])/COS,(co*c.flow_p_constant[sl]+si*c.flow_q_constant[sl])/COS,1.
        sl=slice(NL+NT,None);rating=np.array(AX['winding_rating_kVA'])*COS
        yield 'kva',(co*c.flow_p_matrix[sl]+si*c.flow_q_matrix[sl])/rating[:,None],(co*c.flow_p_constant[sl]+si*c.flow_q_constant[sl])/rating,1.
def components(model,controls):
    model.update();variables={};terms=[];constant=[]
    for x in controls:
        if isinstance(x,(float,int,np.number)):constant.append(float(x));terms.append({})
        elif isinstance(x,gp.Var):constant.append(0.);variables[x.index]=x;terms.append({x.index:1.})
        else:
            constant.append(x.getConstant());d={}
            for i in range(x.size()):
                v=x.getVar(i);variables[v.index]=v;d[v.index]=d.get(v.index,0.)+x.getCoeff(i)
            terms.append(d)
    ids=sorted(variables);v=[variables[i] for i in ids];idx={j:i for i,j in enumerate(ids)};C=np.zeros((60,len(ids)))
    for j,tt in enumerate(terms):
        for k,a in tt.items():C[j,idx[k]]=a
    lo=np.array([x.LB for x in v]);hi=np.array([x.UB for x in v])
    return np.array(constant),C,v,lo,hi
def add(model,coefficients,controls,objective_cap=1.,eta=None,exclusive=None):
    global COUNT
    COUNT+=1;start=time.perf_counter();parts=[components(model,x) for x in controls]
    if eta is None:eta=model.addVar(lb=0,ub=objective_cap,name='rho_max')
    model.update()
    def projected(w,const,part):
        fixed,C,vs,lo,hi=part;B=w@C;base=const+w@fixed
        if exclusive is not None:
            # One movable MESS in the original sequential fleet full MILP:
            # at most one service is connected at a slot. Fixed predecessors
            # are in the numeric control constant, not in this domain bound.
            pp,qq=exclusive;radius=np.max(np.abs(w[:,12:36])*pp+np.abs(w[:,36:60])*qq,axis=1)
            upper=base+radius;lower=base-radius
        else:
            assert max(np.abs(np.r_[lo,hi]),default=0)<1e8
            upper=base+np.maximum(B,0)@hi+np.minimum(B,0)@lo
            lower=base+np.maximum(B,0)@lo+np.minimum(B,0)@hi
        return B,base,lower,upper
    # Any line face supplies a valid globally implied rho lower bound.
    anchors=np.array([p[0] for p in parts]);peak=evaluate_grid(coefficients,anchors,AX['nodes']);t=peak['critical_slot'];floor=0.
    for kind,w,cons,bound in rows(coefficients[t]):
        if kind=='line':floor=max(floor,float(projected(w,cons,parts[t])[2].max())-1e-8)
    model.addConstr(eta>=floor,name='IEEE8500_MESS_DERIVED_RHO_FLOOR');total=0;kept=0;cert=[]
    for t,c in enumerate(coefficients):
        kt=0;nt=0
        for kind,w,cons,bound in rows(c):
            B,base,lower,upper=projected(w,cons,parts[t]);keep=upper>(floor-1e-8 if kind=='line' else bound-1e-8)
            nt+=len(keep);kt+=int(keep.sum())
            if not keep.any():continue
            A=np.c_[B[keep],-np.ones(keep.sum()) if kind=='line' else np.zeros(keep.sum())]
            rhs=(0. if kind=='line' else bound)-base[keep]
            model.addMConstr(sp.csr_matrix(A),gp.MVar.fromlist(parts[t][2]+[eta]),'<',rhs,name=f'IEEE8500_{kind}_{t}')
        total+=nt;kept+=kt;cert.append(dict(slot=t,full_rows=nt,retained=kt))
    model.update();report=dict(status='PASS',full_rows=total,retained_rows=kept,rho_floor=floor,domain_changes=0,electrical_equivalence='All omitted rows are bounded redundant over unchanged MESS domain; no sensitivity threshold or candidate pruning',exclusive_one_vehicle=exclusive is not None,wall_seconds=time.perf_counter()-start,slots=cert,polygon_cache_hits=_POLYGON_CACHE_HITS,polygon_cache_misses=_POLYGON_CACHE_MISSES)
    save(P/'MESS_grid_certificates'/f'{COUNT:06}.json',report)
    return eta,report
def integrated_grid(model,coefficients,controls,eta,inputs):
    assert len(inputs.initial_service_by_mess)==1
    _,info=add(model,coefficients,controls,eta=eta,exclusive=(inputs.electrical_authority.active_power_limit_kw,inputs.electrical_authority.pcs_kva))
    return info['retained_rows']+1
