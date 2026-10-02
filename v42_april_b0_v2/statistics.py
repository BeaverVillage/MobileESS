"""Predeclared directional residual statistics, including empty evidence.

Linear empirical quantiles (position (n-1)q) are descriptive. Correlated
node/time samples and at most 30 days do not establish tail safety.
"""
import math
from datetime import datetime, timezone, timedelta
from .contracts import april, require, QUANTILES

AXIS = ('day', 'node', 'phase', 'slot', 'timestamp')


def quantile(values, q):
    require(0 <= q <= 1, 'QUANTILE_RANGE')
    a = sorted(values)
    require(all(math.isfinite(x) for x in a), 'FINITE_SAMPLES')
    if not a:
        return None
    x = (len(a) - 1) * q
    lo = math.floor(x)
    hi = math.ceil(x)
    return a[lo] + (a[hi] - a[lo]) * (x - lo)


def residuals(plan, da, actual, frozen_dates):
    """Align supplied samples and check residual arithmetic only.

    This utility does not attest complete grid/day coverage. Scientific
    producers must use complete_calibration_residuals with their authoritative
    node/phase population before exporting calibration evidence.
    """
    dates = set(frozen_dates)
    require(len(dates) == len(frozen_dates), 'DUPLICATE_FROZEN_DATE')
    for d in dates:
        april(d)
    def keyed(rows):
        result = {}
        for row in rows:
            april(row['day'])
            require(row['day'] in dates, 'DATE_NOT_PREREGISTERED')
            key = tuple(row[k] for k in AXIS)
            require(key not in result, 'DUPLICATE_NODE_PHASE_TIME')
            require(type(row['slot']) is int and 0 <= row['slot'] < 96, 'DAY_SLOT_AXIS')
            stamp = datetime.fromisoformat(row['timestamp'])
            end = datetime.fromisoformat(row['day'] + 'T00:00:00+10:00') + timedelta(minutes=15*(row['slot']+1))
            require(stamp.tzinfo is not None and stamp == end, 'TIMESTAMP_SLOT_ALIGNMENT')
            require(row['phase'] in ('a', 'b', 'c') and bool(row['node']), 'NODE_PHASE_AXIS')
            require(math.isfinite(row['voltage_pu']) and row['voltage_pu'] > 0, 'FINITE_VOLTAGE')
            result[key] = row['voltage_pu']
        return result
    p, d, a = map(keyed, (plan, da, actual))
    require(p.keys() == d.keys() == a.keys(), 'THREE_CURVE_ALIGNMENT')
    require({k[0] for k in p} == dates, 'FROZEN_DATE_MISSING')
    out = []
    for key in sorted(p):
        model, forecast, total = d[key] - p[key], a[key] - d[key], a[key] - p[key]
        tolerance = 8 * math.ulp(max(p[key], d[key], a[key]))
        require(abs(total - model - forecast) <= tolerance, 'RESIDUAL_IDENTITY')
        out.append(dict(zip(AXIS, key), V_PLAN=p[key], V_DA_AC=d[key], V_DDAY_AC=a[key],
                        e_model=model, e_forecast=forecast, e_total=total,
                        r_up=max(0., total), r_down=max(0., -total)))
    return out


def complete_calibration_residuals(plan, da, actual, frozen_dates, *, expected_node_phases):
    """Require every grid node/phase and all 96 slots on every frozen day.

    The expected node/phase pairs must come from grid authority, independently
    of the supplied voltage curves. Matching truncation in all three curves
    cannot establish a complete calibration population.
    """
    require(isinstance(expected_node_phases, (set, frozenset, list, tuple))
            and bool(expected_node_phases), 'COMPLETE_GRID_AUTHORITY_REQUIRED')
    require(all(isinstance(pair, (list, tuple)) and len(pair) == 2
                and isinstance(pair[0], str) and bool(pair[0].strip())
                and pair[1] in ('a', 'b', 'c') for pair in expected_node_phases),
            'EXPECTED_NODE_PHASE_AXIS')
    pairs = {tuple(pair) for pair in expected_node_phases}
    require(len(pairs) == len(expected_node_phases), 'DUPLICATE_EXPECTED_NODE_PHASE')
    dates = list(frozen_dates)
    require(bool(dates), 'COMPLETE_FROZEN_DATES_REQUIRED')
    rows = residuals(plan, da, actual, dates)
    expected = {(day, node, phase, slot) for day in dates
                for node, phase in pairs for slot in range(96)}
    observed = {(r['day'], r['node'], r['phase'], r['slot']) for r in rows}
    require(observed == expected and len(rows) == len(expected), 'INCOMPLETE_GRID_AXIS')
    return rows


def day_worst(rows):
    days = sorted({r['day'] for r in rows})
    out = []
    for d in days:
        group = [r for r in rows if r['day'] == d]
        row = dict(day=d, samples=len(group))
        for direction in ('up', 'down'):
            winner = max(group, key=lambda r: r['r_' + direction])
            row['r_' + direction] = winner['r_' + direction]
            row[direction + '_event'] = {k: winner[k] for k in AXIS}
        out.append(row)
    return out


def quantiles(rows, aggregation):
    require(aggregation in ('pointwise', 'day_worst'), 'AGGREGATION')
    data = rows if aggregation == 'pointwise' else day_worst(rows)
    out = []
    for q in QUANTILES:
        up = quantile([r['r_up'] for r in data], q)
        down = quantile([r['r_down'] for r in data], q)
        lower, upper = (None, None) if up is None else (.95 + down, 1.05 - up)
        out.append(dict(aggregation=aggregation, q=q, n=len(data), delta_up=up, delta_down=down,
                        lower_candidate=lower, upper_candidate=upper,
                        nonempty_band=None if up is None else lower <= upper,
                        FINAL_MARGIN_ACCEPTED=False))
    return out


def coverage(rows, margin=.005):
    require(math.isfinite(margin) and margin >= 0, 'MARGIN')
    days = day_worst(rows)
    def measure(data):
        n = len(data)
        return {direction: dict(n=n, covered=sum(r['r_' + direction] <= margin for r in data),
                                fraction=None if not n else sum(r['r_' + direction] <= margin for r in data) / n)
                for direction in ('up', 'down')}
    return dict(margin=margin, pointwise=measure(rows), day_worst=measure(days),
                exceedances=[{**{k: r[k] for k in AXIS}, 'direction': direction, 'residual': r['r_' + direction]}
                             for r in rows for direction in ('up', 'down') if r['r_' + direction] > margin],
                exceedance_days={direction: [r['day'] for r in days if r['r_' + direction] > margin]
                                 for direction in ('up', 'down')})


def error_stats(rows, field):
    values = [abs(r[field]) for r in rows]
    daily = [max(abs(r[field]) for r in rows if r['day'] == day) for day in sorted({r['day'] for r in rows})]
    n = len(values)
    return dict(n=n, days=len(daily), MAE=None if not n else sum(values)/n,
                RMSE=None if not n else math.sqrt(sum(x*x for x in values)/n),
                P95_absolute=quantile(values, .95), day_worst=daily,
                day_worst_P95=quantile(daily, .95), maximum=None if not n else max(values))


def dominance(model, forecast):
    fields = ('RMSE', 'MAE', 'P95_absolute', 'day_worst_P95')
    if any(model[k] is None or forecast[k] is None for k in fields):
        return 'INCONCLUSIVE'
    if all(model[k] > forecast[k] for k in fields):
        return 'MODEL'
    if all(model[k] < forecast[k] for k in fields):
        return 'FORECAST'
    return 'MIXED'


def sensitivity(plan):
    values = [r['voltage_pu'] for r in plan]
    return [dict(band=name, lower=lo, upper=hi, samples=len(values),
                 satisfies=None if not values else all(lo <= v <= hi for v in values),
                 label='B0_PHYSICAL_PLANNING_FEASIBLE' if name == 'S0' else
                       ('B0_ROBUST_MARGIN_005_FEASIBLE' if name == 'S2' else 'B0_MARGIN_0025_FEASIBLE'),
                 reoptimization_calls=0)
            for name, lo, hi in (('S0', .95, 1.05), ('S1', .9525, 1.0475), ('S2', .955, 1.045))]
