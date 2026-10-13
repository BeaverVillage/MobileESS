"""Execute literal frozen MESS commands; no redispatch or P/Q repair."""
import math
from .a_engine import digest


def consume_frozen_mess(plan, *, day_begin_seconds, evidence_kind='REAL_DATA',original_full_validated=False):
    if plan.get('plan_sha')!=digest({k:v for k,v in plan.items() if k!='plan_sha'}):
        raise ValueError('ACTUAL_FROZEN_MESS_SHA_DRIFT')
    units=sorted(plan['SOC'])
    if len(units)!=4 or set(plan['Mode'])!=set(units) or set(plan['routes'])!=set(units):
        raise ValueError('ACTUAL_FOUR_MESS_PLAN_REQUIRED')
    if any(len(plan['SOC'][u])!=97 or len(plan['Mode'][u])!=96 for u in units):
        raise ValueError('ACTUAL_MESS_SOC_MODE_AXIS')
    sites=sorted(plan['P_by_site'])
    if sites!=sorted(plan['Q_by_site']):raise ValueError('ACTUAL_MESS_SITE_AXIS')
    for family in ('P_by_site','Q_by_site'):
        if any(len(plan[family][s])!=96 or not all(math.isfinite(float(x)) for x in plan[family][s]) for s in sites):
            raise ValueError('ACTUAL_MESS_FINITE_POWER_AXIS')
    if any(x not in (0,1) for u in units for x in plan['Mode'][u]):
        raise ValueError('ACTUAL_MESS_LITERAL_CHARGE_MODE')
    off=all(abs(float(x))<=1e-12 for field in ('P_by_site','Q_by_site') for row in plan[field].values() for x in row)
    if not original_full_validated and not off:
        raise ValueError('ACTUAL_MESS_ORIGINAL_FULL_RECEIPT_REQUIRED')
    if not original_full_validated and any(any(abs(float(x)-float(plan['SOC'][u][0]))>1e-12 for x in plan['SOC'][u]) for u in units):
        raise ValueError('ACTUAL_MESS_OFF_SOC_MUST_REMAIN_CONSTANT')
    commands=[]
    for t in range(96):
        commands.append(dict(control_seconds=day_begin_seconds+t*900,
            P_by_site={s:plan['P_by_site'][s][t] for s in sites},
            Q_by_site={s:plan['Q_by_site'][s][t] for s in sites},
            SOC_begin={u:plan['SOC'][u][t] for u in units},
            SOC_end={u:plan['SOC'][u][t+1] for u in units},
            Mode={u:plan['Mode'][u][t] for u in units},
            connection_site={u:plan.get('connection_site',{}).get(u,[None]*96)[t] for u in units}))
    return dict(engine='LITERAL_FROZEN_MESS_EXECUTOR_V1',plan_sha=plan['plan_sha'],
        commands=commands,routes=plan['routes'],moves=plan.get('moves',[]),
        original_FULL_feasibility_precondition=True,evidence_kind=evidence_kind,
        frozen_execution_validated=True,original_FULL_reused=original_full_validated,
        validation_scope='FROZEN_SHA_AXES_AND_ORIGINAL_FULL_PRECONDITION',
        P_Q_repair_calls=0,global_optimize_calls=0,Actual_travel_uncertainty_simulated=False,
        electrical_consumer_status='AWAITING_FRESH_AC',fresh_AC_PASS=None)
