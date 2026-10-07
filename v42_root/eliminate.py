"""Exact bounded matrix projection oracle for rejected dense substitutions.

Not used by production; measures the density tradeoff without materializing
full-May cumulative expressions. Retains all transformed rows and bounds.
"""
from collections import defaultdict
import gurobipy as gp

def project(m,v,families):
    m.update();oldvars=m.getVars();derived={}
    for vv in v.values():
        for family in families:
            if family=='f0':
                if vv['q'] or vv.get('pair') or vv['w']:raise ValueError('F0_DIRECT_SUBSTITUTION_REQUIRES_NONMIGRATION')
                # Match each finish to the same site/start with the fixed D.
                starts=sorted(vv['y']);ends=sorted(vv['f0'])
                differences={t-s for (k,s),(d,t) in zip(starts,ends) if k==d}
                if len(differences)!=1:raise ValueError('FIXED_DURATION_MAPPING')
                D=next(iter(differences))
                for (k,t),x in vv['f0'].items():derived[x.index]=gp.LinExpr(vv['y'].get((k,t-D),0))
                continue
            if family=='r0':enter=vv['y'];leave=defaultdict(gp.LinExpr)
            elif family=='h':enter=vv['q'];leave=defaultdict(gp.LinExpr)
            elif family=='r1':enter=vv['arrive'];leave=defaultdict(gp.LinExpr)
            else:raise ValueError('UNSUPPORTED_STATE')
            if family=='r0':
                for n in ('q','f0'):
                    for key,x in vv[n].items():leave[key]+=x
            elif family=='h':
                for key,x in vv['depart'].items():leave[key]+=x
            else:
                for key,x in vv['f1'].items():leave[key]+=x
            for (k,t),x in vv[family].items():
                expr=gp.quicksum(z for (s,a),z in enter.items() if s==k and a<=t)-gp.quicksum(z for (s,a),z in leave.items() if s==k and a<=t)
                derived[x.index]=expr
    n=gp.Model('bounded_exact_projection');n.Params.OutputFlag=0
    source_day=getattr(m,'_v42_a_stage_day',None)
    if source_day is not None:
        from v42_a_stage_domain_v2.execution import tag_model_for_day
        tag_model_for_day(n,source_day)
    retained={x.index:n.addVar(lb=x.LB,ub=x.UB,vtype=x.VType,name=x.VarName) for x in oldvars if x.index not in derived}
    def convert(expr):
        e=gp.LinExpr(expr);result=gp.LinExpr(e.getConstant())
        for i in range(e.size()):
            x=e.getVar(i);a=e.getCoeff(i)
            if x.index in derived:result+=a*convert(derived[x.index])
            else:result+=a*retained[x.index]
        return result
    for idx,e in derived.items():
        x=oldvars[idx];ee=convert(e)
        if x.LB>-gp.GRB.INFINITY:n.addConstr(ee>=x.LB)
        if x.UB<gp.GRB.INFINITY:n.addConstr(ee<=x.UB)
    for c in m.getConstrs():
        e=convert(m.getRow(c));n.addConstr(e<=c.RHS if c.Sense=='<' else e>=c.RHS if c.Sense=='>' else e==c.RHS)
    newv={u:{name:{key:convert(x) for key,x in items.items()} for name,items in vv.items()} for u,vv in v.items()}
    n.update();return n,newv,convert
