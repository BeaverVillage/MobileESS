"""Coefficient-exact Runtime count keys, shared by native and bounded gates."""
from collections import defaultdict
import gurobipy as gp
from v42_compact.native import completion_risk

def coefficient_vector(j,raw,site,end,bundle):
    if bundle is None:
        from v42_final.reserve import risk_exposure
        return tuple(sorted(risk_exposure(j.gpu,end,site,[1,.5,.25],range(120)).items()))
    return tuple(sorted(completion_risk(j,raw,site,end,bundle).items()))

def factor_finishes(m,finishes,jobs,raw,bundle,classes):
    """Return equivalent synthetic completion events for the inherited binder."""
    class_for={u:g for g,us in classes.items() for u in us};groups=defaultdict(list);vectors={};representatives={}
    for u,k,t,x in finishes:
        key=class_for[u],k,t;vector=coefficient_vector(jobs[u],raw[u] if raw else None,k,t,bundle)
        if key in vectors and vectors[key]!=vector:raise ValueError('UNEQUAL_RUNTIME_COEFFICIENT_VECTOR')
        vectors[key]=vector;representatives[key]=u;groups[key].append(x)
    result=[]
    for (g,k,t),xs in sorted(groups.items()):
        C=m.addVar(lb=0,ub=len(classes[g]),name=f'finish_count[{g[:12]},{k},{t}]')
        m.addConstr(C==gp.quicksum(xs),name='exact_Runtime_finish_count')
        result.append((representatives[g,k,t],k,t,C))
    return result
