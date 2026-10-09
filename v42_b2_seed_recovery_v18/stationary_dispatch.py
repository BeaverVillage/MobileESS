"""Current-day route witness generator; its point must pass the original FULL gate.

Fixing is confined to an auxiliary continuous model. The seed MILP retains the
entire original integer/route/P/Q/SOC domain and receives only a verified start.
"""
import numpy as np
from scipy import sparse
from v42_may_campaign_native90 import m_stage as original
from .common import atomic


def discrete_stationary(case):
    ids = np.flatnonzero(case.d['types'] != 'C')
    values = []
    for j in ids:
        name = str(case.d['names'][j])
        if name.startswith('arc['):
            unit,k = name[4:-1].split(','); arc=case.graph[2][int(k)]
            value = float(arc[-1] is None and arc[0] == case.graph[1][unit])
        elif name.startswith('charge_mode['):
            value = 0.
        elif name.startswith('node_activity['):
            unit,site,slot = name[14:-1].split(',')
            value = float(site == case.graph[1][unit])
        else:
            raise ValueError('STATIONARY_UNKNOWN_ORIGINAL_DISCRETE_FAMILY:'+name)
        values.append(value)
    return ids,np.asarray(values,dtype=np.float64)


def validated_start(case,budget,progress):
    ids, values = discrete_stationary(case)
    model, identity = original._model(case,continuous=True)
    try:
        fix = sparse.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),ids)),
            shape=(len(ids),case.A.shape[1]))
        model.addMConstr(fix,model.getVars(),'=',values,name='CURRENT_DAY_STATIONARY_INTEGER_WITNESS')
        model.Params.Method = 1
        model.update()
        atomic(case.output/'STATIONARY_DISPATCH_MODEL_IDENTITY.json',dict(identity,
            fixed_discrete_count=len(ids),candidate_generator_only=True,
            original_CSR_objective_physics_retained=True,unrestricted_seed_MILP_changed=False))
        if progress:
            progress(dict(phase='M_CURRENT_DAY_STATIONARY_DISPATCH_FEASIBILITY'))
        budget.native_optimize(model,component='FEASIBILITY_LP',track='M_START',
            label='CURRENT_DAY_STATIONARY_ROUTE_DISPATCH_WITNESS',requested_seconds=120.)
        if model.Status != 2 or not model.SolCount:
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(PASS=False,
                reason='NO_OPTIMAL_CONTINUOUS_WITNESS',Native_status=int(model.Status)))
            return None
        raw = np.asarray(model.getAttr('X'),dtype=np.float64)
        packet = case.output/'STATIONARY_DISPATCH_RAW_POINT.npz';np.savez_compressed(packet,point=raw)
        try:
            with budget.cost('integer_physical_validation','stationary_dispatch_original_FULL_replay'):
                receipt = original._strict_ub(case,packet,{})
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(receipt,case_sha=case.case_sha))
            return raw
        except ValueError as exc:
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(PASS=False,reason=str(exc),
                case_sha=case.case_sha,invalid_start_not_supplied=True))
            return None
    finally:
        model.dispose()
