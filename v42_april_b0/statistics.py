"""Pure offline arithmetic. Unit fixtures are not scientific April observations."""
from math import floor, isfinite, sqrt, isclose

from v42_native.contracts import require
from .contracts import QUANTILES, require_april

KEY = ('date', 'node', 'phase', 'time')


def quantile(values, q):
    require(q in QUANTILES and bool(values) and all(isfinite(v) for v in values), 'QUANTILE_INPUT')
    x = sorted(values)
    p = (len(x)-1)*q
    i = floor(p)
    return x[i] + (x[min(i+1, len(x)-1)]-x[i])*(p-i)


def residuals(plan, da_ac, dday_ac, *, frozen_dates, tolerance=1e-12):
    require(isfinite(tolerance) and 0 < tolerance <= 1e-9, 'IDENTITY_TOLERANCE')
    def index(rows):
        out = {}
        for row in rows:
            key = tuple(row[k] for k in KEY)
            require_april(row['date'], frozen_dates)
            require(key not in out and isfinite(row['voltage_pu']), 'DUPLICATE_OR_NONFINITE_VOLTAGE')
            out[key] = row['voltage_pu']
        require(bool(out), 'EMPTY_VOLTAGE_SERIES')
        return out
    p, a, d = map(index, (plan, da_ac, dday_ac))
    require(p.keys() == a.keys() == d.keys(), 'NODE_PHASE_TIME_ALIGNMENT')
    result = []
    for key in sorted(p):
        model, forecast, total = a[key]-p[key], d[key]-a[key], d[key]-p[key]
        require(isclose(total, model+forecast, rel_tol=0, abs_tol=tolerance), 'RESIDUAL_IDENTITY')
        result.append(dict(zip(KEY, key), V_PLAN=p[key], V_DA_AC=a[key], V_DDAY_AC=d[key],
                           e_model=model, e_forecast=forecast, e_total=total,
                           r_up=max(0., total), r_down=max(0., -total)))
    return result


def day_worst(rows):
    days = sorted({r['date'] for r in rows})
    require(bool(days), 'NO_DAYS')
    return [dict(date=d, R_up_day=max(r['r_up'] for r in rows if r['date'] == d),
                 R_down_day=max(r['r_down'] for r in rows if r['date'] == d)) for d in days]


def margin_summary(rows):
    daily = day_worst(rows)
    output = []
    for aggregation, up, down in (
        ('pointwise', [r['r_up'] for r in rows], [r['r_down'] for r in rows]),
        ('day_worst', [r['R_up_day'] for r in daily], [r['R_down_day'] for r in daily])):
        for q in QUANTILES:
            u, d = quantile(up, q), quantile(down, q)
            output.append(dict(aggregation=aggregation, q=q, delta_up=u, delta_down=d,
                               V_lower=.95+d, V_upper=1.05-u, nonempty_band=.95+d <= 1.05-u,
                               delta_up_minus_current=u-.005, delta_down_minus_current=d-.005,
                               current_up_empirical_percentile=sum(v <= .005 for v in up)/len(up),
                               current_down_empirical_percentile=sum(v <= .005 for v in down)/len(down),
                               IID_claim=False, CALIBRATED_CANDIDATE_ONLY=True, FINAL_MARGIN_ACCEPTED=False))
    return output


def component_summary(rows):
    require(bool(rows), 'NO_RESIDUALS')
    rmse = {k: sqrt(sum(r[k]**2 for r in rows)/len(rows)) for k in ('e_model', 'e_forecast', 'e_total')}
    dominant = 'equal' if rmse['e_model'] == rmse['e_forecast'] else max(('e_model', 'e_forecast'), key=rmse.get)
    return dict(RMSE=rmse, dominance_metric='RMSE', dominant=dominant)
