"""Scalar Native observations only; none of these fields are certificates."""
import math
from .common import now

UNKNOWN = 'UNKNOWN'


def empty():
    return {name: UNKNOWN for name in (
        'SolCount', 'Native_SolCount', 'Native_solution_count_callback', 'Native_incumbent',
        'Native_BestBd', 'Native_Gap', 'Native_NodeCount', 'Native_root_progress',
        'Native_subphase', 'Native_iteration_count', 'Native_observation_UTC',
        'Native_mip_phase', 'Native_open_nodes', 'Native_gap_source',
        'Native_first_incumbent_Runtime', 'Native_first_incumbent_UTC', 'Native_first_incumbent_source')}


def number(value, gp):
    try:
        value = float(value)
        return value if math.isfinite(value) and abs(value) < gp.GRB.INFINITY else UNKNOWN
    except (TypeError, ValueError):
        return UNKNOWN


def relative_gap(incumbent, bound):
    if UNKNOWN in (incumbent, bound):
        return UNKNOWN
    if incumbent == 0:
        return 0. if bound == 0 else 'INFINITY'
    return abs(incumbent - bound) / abs(incumbent)


def observe(model, where, gp):
    cb = gp.GRB.Callback
    def get(name):
        try:
            return number(model.cbGet(getattr(cb, name)), gp)
        except (gp.GurobiError, AttributeError):
            return UNKNOWN
    row = dict(Native_observation_UTC=now())
    for phase in ('MIP', 'MIPNODE', 'MIPSOL'):
        if where != getattr(cb, phase):
            continue
        incumbent, bound = get(phase + '_OBJBST'), get(phase + '_OBJBND')
        nodes = get(phase + '_NODCNT')
        row.update(Native_subphase=phase, Native_incumbent=incumbent,
            Native_BestBd=bound, Native_Gap=relative_gap(incumbent, bound),
            Native_NodeCount=nodes, Native_solution_count_callback=get(phase + '_SOLCNT'),
            Native_mip_phase=get(phase + '_PHASE'),
            Native_gap_source='CALLBACK_FLOAT_OBJECTIVE_BOUNDS_NOT_CERTIFIED')
        # MIPSOL_SOLCNT counts prior callback solutions, not Model.SolCount.
        # Do not infer no incumbent from a callback solution counter of zero.
        if where == cb.MIPNODE and nodes == 0:
            row['Native_root_progress'] = 'ROOT_NODE_CALLBACK_OBSERVED'
        if where == cb.MIP:
            row['Native_iteration_count'] = get('MIP_ITRCNT')
            row['Native_open_nodes'] = get('MIP_NODLFT')
        return row
    for phase, iteration in (('PRESOLVE', None), ('SIMPLEX', 'SPX_ITRCNT'),
                             ('BARRIER', 'BARRIER_ITRCNT')):
        if where == getattr(cb, phase):
            row['Native_subphase'] = phase
            if iteration:
                row['Native_iteration_count'] = get(iteration)
            return row
    return {}  # MESSAGE/POLLING are not evidence of a scientific subphase.


def finished(model, gp):
    def get(name):
        try:
            return number(getattr(model, name), gp)
        except (gp.GurobiError, AttributeError):
            return UNKNOWN
    count = get('SolCount')
    incumbent = get('ObjVal') if count != UNKNOWN and count > 0 else UNKNOWN
    return dict(SolCount=count, Native_SolCount=count, Native_incumbent=incumbent,
        Native_BestBd=get('ObjBound'), Native_Gap=get('MIPGap') if incumbent != UNKNOWN else UNKNOWN,
        Native_NodeCount=get('NodeCount'), Native_observation_UTC=now(),
        Native_gap_source='MODEL_MIPGAP_NOT_CERTIFIED')
