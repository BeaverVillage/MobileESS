"""Original explicit-variable full-row and physical audits, no D-W imports."""
import numpy as np
from v42_integrated.matrix import audit
from v42_rowgen.core import security_axis
from v42_strengthening.analysis import graph_inputs
from v42_native.mess import validate as mess_validate
from v42_bootstrap.attribution import supplemental_physical
from .core import Separator

class Validator:
    def __init__(self,A,d):
        self.A,self.d=A,d
        self.grid=Separator(A,d)
        continuous=np.asarray(abs(A)@(d['types']=='C').astype(float)).ravel()
        self.route_mask=(continuous==0)&(d['sense']=='=')
        self.sites,self.initial,self.arcs,self.battery,self.graph=graph_inputs()
        self.routes=[a[-1] for a in self.arcs if a[-1] is not None]
    def __call__(self,x):
        # Preserve PR158 postsolve affine authority; no clipping or rounding.
        raw=audit(self.A,self.d,x,integral=True,tolerance=1e-6)
        exact=np.array_equal(x[self.d['types']!='C'],np.rint(x[self.d['types']!='C']))
        residual=self.A@x-self.d['rhs']
        route=float(np.max(abs(residual[self.route_mask]),initial=0.))
        raw.update(integer_pattern_exact=exact,route_equality_max_residual=route,
            affine_postsolve_tolerance=1e-6,bound_and_route_tolerance=1e-8)
        raw['PASS']=bool(raw['PASS'] and exact and route<=1e-8 and raw['max_bound_violation']<=1e-8)
        grid=self.grid.evaluate(x)
        result=dict(PASS=bool(raw['PASS'] and grid['PASS']),raw=raw,
            exhaustive_grid=dict(PASS=grid['PASS'],checked_rows=grid['checked_rows'],
                ambiguous_exact_checks=grid['ambiguous_exact_checks'],
                maximum_upper=grid['maximum_upper'],tolerance=1e-8),
            objective=float(self.d['objective']@x+float(self.d['constant'])))
        if not result['PASS']:return result
        values=dict(zip(map(str,self.d['names']),map(float,x)))
        for u in self.initial:
            for k in range(len(self.arcs)):values.setdefault(f'arc[{u},{k}]',0.)
            for s in self.sites:
                for t in range(96):
                    for f in ('Pch','Pdis','Q'):values.setdefault(f'{f}[{u},{s},{t}]',0.)
        chosen={u:[k for k in range(len(self.arcs)) if values[f'arc[{u},{k}]']>.5] for u in self.initial}
        plan=dict(values=values,initial_sites=self.initial,chosen_arcs=chosen,mode='MILP')
        physics=mess_validate(plan,self.sites,self.routes,self.battery,96)
        supplemental=supplemental_physical(plan,self.sites,self.battery)
        result.update(PASS=bool(result['PASS'] and physics['PASS'] and supplemental['charge_mode_and_connection_PASS']),
            route_SOC_PCS=physics,mode_connection=supplemental,
            original_grid_physics='All original voltage/line-current/NormalAmps/transformer-kVA affine rows exhaustively checked.',
            repairs=0)
        return result
