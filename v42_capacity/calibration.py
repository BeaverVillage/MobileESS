"""Exact-axis Planning magnitude versus Actual AC magnitude; empirical higher."""
import numpy as np


def magnitude(values, representation):
    v=np.asarray(values,float)
    if not np.isfinite(v).all() or (v<=0).any(): raise ValueError('FINITE_POSITIVE_VOLTAGE')
    if representation=='squared_pu': return np.sqrt(v)
    if representation=='magnitude_pu': return v.copy()
    raise ValueError('VOLTAGE_REPRESENTATION_REQUIRED')


def aligned_residual(plan, actual, plan_axis, actual_axis, *, plan_representation):
    if tuple(plan_axis)!=tuple(actual_axis) or len(set(plan_axis))!=len(plan_axis):
        raise ValueError('EXACT_NODE_PHASE_SLOT_ALIGNMENT')
    p=magnitude(plan,plan_representation); a=magnitude(actual,'magnitude_pu')
    if p.shape!=a.shape or p.shape[-1]!=len(plan_axis): raise ValueError('EXACT_VOLTAGE_SHAPE')
    e=a-p
    return dict(V_PLAN=p,V_ACTUAL_AC=a,e_total=e,r_up=np.maximum(e,0),r_down=np.maximum(-e,0),abs_e=abs(e))


def statistics(residual, days, nodes):
    e=residual['e_total']; up=residual['r_up']; down=residual['r_down']; absolute=residual['abs_e']
    if e.shape!=(len(days),96,len(nodes)) or len(days)!=30: raise ValueError('FULL_APRIL_REQUIRED')
    location=np.unravel_index(np.argmax(absolute),e.shape)
    d,t,n=location
    metrics=dict(mean_signed_error=float(e.mean()),MAE=float(absolute.mean()),RMSE=float(np.sqrt((e**2).mean())),
        median_absolute_error=float(np.median(absolute)),maximum_absolute_error=float(absolute.max()),
        worst_location=dict(day=days[d],slot=int(t),node_phase=nodes[n],node=nodes[n].rsplit('.',1)[0],
                            phase='ABC'[int(nodes[n].rsplit('.',1)[1])-1],V_PLAN=float(residual['V_PLAN'][location]),
                            V_ACTUAL_AC=float(residual['V_ACTUAL_AC'][location]),e_total=float(e[location])))
    point=[]; dayworst=[]; bands=[]
    for q in [.9,.95,.975,.99]:
        for kind,ru,rd,target in [('pointwise',up,down,point),('day_worst',up.max((1,2)),down.max((1,2)),dayworst)]:
            du=float(np.quantile(ru,q,method='higher')); dd=float(np.quantile(rd,q,method='higher'))
            target.append(dict(q=q,delta_up=du,delta_down=dd,method='higher'))
            bands.append(dict(population=kind,q=q,lower_pu=.95+dd,upper_pu=1.05-du,delta_up=du,delta_down=dd,FINAL_MARGIN_ACCEPTED=False))
    exceed=np.maximum(absolute-.005,0)
    coverage=dict(upper_pointwise_coverage=float((up<=.005).mean()),lower_pointwise_coverage=float((down<=.005).mean()),
        joint_pointwise_coverage=float((absolute<=.005).mean()),joint_day_coverage=float((absolute.max((1,2))<=.005).mean()),
        exceedance_days=[days[i] for i in np.flatnonzero(absolute.max((1,2))>.005)],maximum_exceedance=float(exceed.max()),
        worst_location=metrics['worst_location'],margin_pu=.005)
    return metrics,point,dayworst,coverage,bands
