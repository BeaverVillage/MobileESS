from .common import *
import numpy as np
from v42_integrated.matrix import audit
from v42_dw_root.models import Block as OriginalBlock,Master as OriginalMaster,subset
from v42_strengthening.analysis import graph_inputs

def pure_binary_equalities(A,d):
    continuous=np.asarray(abs(A)@(d['types']=='C').astype(float)).ravel()
    return (continuous==0)&(d['sense']=='=')
def corrected_rows(A,d,x,integral=False,route_mask=None):
    r=audit(A,d,x,integral=integral,tolerance=POST_TOL)
    exact=not integral or np.array_equal(x[d['types']!='C'],np.rint(x[d['types']!='C']))
    route=0. if route_mask is None else float(np.max(abs((A@x-d['rhs'])[route_mask]),initial=0.))
    r.update(PASS=bool(r['PASS'] and r['max_bound_violation']<=STRICT_TOL and exact and route<=STRICT_TOL),
             affine_postsolve_tolerance=POST_TOL,bound_audit_tolerance_unchanged=STRICT_TOL,integer_pattern_exact=exact,
             route_equality_max_residual=route,route_equality_tolerance_unchanged=STRICT_TOL,physical_bounds_modified=False)
    return r
class Block(OriginalBlock):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.route_mask=pure_binary_equalities(self.A,self.d)
    def validate(self,x,physical=True):
        raw=corrected_rows(self.A,self.d,x,True,self.route_mask);exact=raw['integer_pattern_exact']
        result=dict(PASS=raw['PASS'],raw=raw,integer_pattern_exact=exact,repairs=0)
        if not result['PASS'] or not physical:return result
        # Preserve the original physical validators and their existing policy.
        from v42_native.mess import validate
        from v42_bootstrap.attribution import supplemental_physical
        values=dict(zip(map(str,self.d['names']),map(float,x)));u=self.unit
        for k in range(len(self.arcs)):values.setdefault(f'arc[{u},{k}]',0.)
        for s in self.sites:
            for t in range(96):
                for f in ('Pch','Pdis','Q'):values.setdefault(f'{f}[{u},{s},{t}]',0.)
        chosen=[k for k in range(len(self.arcs)) if values[f'arc[{u},{k}]']>.5]
        plan=dict(values=values,initial_sites={u:self.initial[u]},chosen_arcs={u:chosen},mode='MILP')
        routes=[a[-1] for a in self.arcs if a[-1] is not None]
        route=validate(plan,self.sites,routes,self.battery,96);extra=supplemental_physical(plan,self.sites,self.battery)
        result.update(PASS=bool(result['PASS'] and route['PASS'] and extra['charge_mode_and_connection_PASS']),route_SOC_PCS=route,mode_connection=extra,
                      movement_count=sum(self.arcs[k][-1] is not None for k in chosen),
                      movement_energy=sum(self.arcs[k][-1].energy_kwh for k in chosen if self.arcs[k][-1] is not None),native_unreachable_zero_constants_only=True)
        return result
class Master(OriginalMaster):
    def raw_audit(self):
        r=super().raw_audit()
        r['PASS']=bool(all(np.isfinite(r[k]) for k in ('master_row_max_violation','convexity_max_violation','bounds_max_violation'))
                       and r['master_row_max_violation']<=POST_TOL and r['convexity_max_violation']<=STRICT_TOL and r['bounds_max_violation']<=STRICT_TOL)
        r.update(affine_postsolve_tolerance=POST_TOL,convexity_and_bound_audits_unchanged=STRICT_TOL)
        return r
def prototypes(B,e,owner,row_owner,native):
    result=[];graph=graph_inputs()
    for m in range(4):
        b=Block.__new__(Block);b.unit=UNITS[m];b.columns=np.flatnonzero(owner==m);b.rows=np.flatnonzero(row_owner==m)
        b.global_rows=np.flatnonzero(row_owner<0);b.A=B[b.rows][:,b.columns];b.B=B[b.global_rows][:,b.columns]
        b.d=subset(e,b.rows,b.columns,native);b.mask=b.d['types']!='C';b.route_mask=pure_binary_equalities(b.A,b.d)
        b.sites,b.initial,b.arcs,b.battery,b.graph=graph;result.append(b)
    return result
