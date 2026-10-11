"""Scoped zero-margin authority; inherited historical experiments stay intact."""
from contextlib import contextmanager
import re
import numpy as np
import gurobipy as gp
from .governance import NORMALAMPS, write

PLANNING_BAND = (0.95, 1.05)
MARGIN_PU = 0.0
P1 = 'MIN MAX_LINE_LOADING'
M_P2 = ('movement_energy', 'movement_count')
ACTUAL = dict(full_reoptimization=False, P_repair=False, Q_repair=False,
              MESS_AIDC_schedule_repair=False, Planning_tap_replay=False,
              Actual_tap_replay=False, capacitor_replay=False)
LP_POLICY = dict(Threads=4, Method=2, Crossover=0, TimeLimit=300,
                 FeasibilityTol=1e-8, OptimalityTol=1e-8,
                 BarConvTol=1e-11, PreDual=0, Seed=20260929)
MIP_POLICY = dict(Threads=4, Method=2, NodeMethod=1, Crossover=2,
                  MIPFocus=3, TimeLimit=1800, MIPGap=0.005,
                  FeasibilityTol=1e-8, OptimalityTol=1e-8,
                  IntFeasTol=1e-8, Seed=20260929)
DEFAULTS = ('Presolve', 'Cuts', 'Heuristics', 'NumericFocus', 'PreSparsify')

@contextmanager
def physical_authority():
    import v42_native.voltage as voltage
    previous = dict(voltage._MAPPING)
    planning = voltage.Voltage('INTEGRATED_ZERO_MARGIN', 0.95, 1.05,
                               0.95**2, 1.05**2)
    for stage in (voltage.Stage.A1, voltage.Stage.M1, voltage.Stage.A2, voltage.Stage.M2):
        voltage._MAPPING[stage] = planning
    try:
        from v42_thermal.authority import current_authority
        a = current_authority()
        from v42_svr11.authority import active
        epoch=active()
        expected_sha = __import__('v42_pr134_b1.common',fromlist=['read']).read(epoch['thermal']['path'])['transformer_current_authority_sha256'] if epoch else NORMALAMPS
        assert a['transformer_current_authority_sha256'] == expected_sha
        assert len(a['rows']) == (153 if epoch else 120) and len({r['transformer'] for r in a['rows']}) == (77 if epoch else 44)
        assert a['Planning'] == a['Actual']
        assert a['controls']['RegControl_count'] == (40 if epoch else 7) and a['controls']['CapControl_count'] == 0
        assert len(a['controls']['capacitors']) == 4
        yield a
    finally:
        voltage._MAPPING.clear(); voltage._MAPPING.update(previous)

def all_transformer_rows(builder, binding_rows=None):
    """Retain source line/kVA/voltage rows, explicitly bind all 120 current rows."""
    def wrapped(m, coefficients, controls, authority):
        from v42_thermal.authority import current_authority
        a = current_authority()
        ratings = {r['branch_phase'].lower(): r for r in a['rows']}
        m.update(); before = m.NumConstrs
        rho = builder(m, coefficients, controls, authority)
        m.update()
        old_rows = iter(r for r in m.getConstrs()[before:] if r.ConstrName == 'transformer_current')
        for t, (c, x) in enumerate(zip(coefficients, controls)):
            observed = set()
            for k, name in enumerate(c.branch_names):
                name = name.lower()
                if not name.startswith('transformer.'):
                    continue
                rating = ratings[name]; observed.add(name)
                assert float(c.current_denominators_A[k]) == rating['NormalAmps']
                label = f'NormalAmps[{t},{name}]'
                omitted = re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]', name)
                if omitted:
                    expression = float(c.current_constant[k]) + gp.quicksum(float(c.current_matrix[i,k])*x[i] for i in np.flatnonzero(c.current_matrix[:,k]))
                    m.addConstr(expression <= 1, name=label)
                else:
                    row = next(old_rows); row.ConstrName = label
                if binding_rows is not None:
                    binding_rows.append(dict(time=t, transformer=rating['transformer'], phase=rating['phase'], NormalAmps=rating['NormalAmps'], authority_SHA=a['transformer_current_authority_sha256'], constraint_name=label))
            assert observed == set(ratings), 'ALL_120_PHASES_REQUIRED'
        assert next(old_rows, None) is None
        return rho
    return wrapped

def evaluate(expr, point):
    if isinstance(expr, gp.Var): return float(point[expr.index])
    if isinstance(expr, gp.LinExpr):
        return float(expr.getConstant() + sum(expr.getCoeff(i)*point[expr.getVar(i).index] for i in range(expr.size())))
    return float(expr)

def grid_audit(coefficients, controls, rho, tolerance=1e-5):
    import math
    vmax = vmin = None
    errors = dict(voltage=0., line_current=0., transformer_current=0., transformer_kVA=0.)
    angles=2*np.pi*np.arange(16)/16; co=np.cos(angles); si=np.sin(angles)
    for c,x in zip(coefficients,controls):
        x=np.asarray(x,float); v=c.voltage_constant+c.voltage_matrix.T@x
        vmin=float(v.min()) if vmin is None else min(vmin,float(v.min()))
        vmax=float(v.max()) if vmax is None else max(vmax,float(v.max()))
        errors['voltage']=max(errors['voltage'],float((0.95**2-v).max()),float((v-1.05**2).max()))
        p=c.flow_p_constant+c.flow_p_matrix@x; q=c.flow_q_constant+c.flow_q_matrix@x
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*co+qa[:,None]*si)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(co[active,None]*c.flow_p_matrix+si[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad
        bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        for k,n in enumerate(c.branch_names):
            faces=co*p[k]+si*q[k]
            if n.lower().startswith('transformer.'):
                errors['transformer_current']=max(errors['transformer_current'],float(c.current_constant[k]+c.current_matrix[:,k]@x-1))
            else:
                errors['line_current']=max(errors['line_current'],float(np.max(faces/ap[k]+correction[k]@(x-c.anchor)+bias[k])-rho))
            if c.transformer_ratings[k] is not None:
                errors['transformer_kVA']=max(errors['transformer_kVA'],float(np.max(faces)-c.transformer_ratings[k]*math.cos(math.pi/16)))
    from v42_thermal.authority import current_authority
    return dict(PASS=max(errors.values())<=tolerance,maximum_violations=errors,min_voltage_pu=math.sqrt(max(0,vmin)),max_voltage_pu=math.sqrt(max(0,vmax)),transformer_current_authority_sha256=current_authority()['transformer_current_authority_sha256'],voltage_band=list(PLANNING_BAND),margin_pu=MARGIN_PU,all_transformer_phases_audited=True)
