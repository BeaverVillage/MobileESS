"""Admit complete finite weather observations under the original as-of contract.

No values are invented. Invalid observations stay in the immutable source and
are explicitly rejected; the unchanged CausalSeries chooses the last complete
past observation and retains its original 7200-second maximum age.
"""
from contextlib import contextmanager
from types import FunctionType
from unittest.mock import patch
import math
from v44.common import atomic,now


def finite(value):
    try:return math.isfinite(float(value))
    except (TypeError,ValueError):return False


def admit(rows):
    accepted=[];rejected=[]
    for row in rows:
        if not all(finite(row[k]) for k in ('observed_seconds','available_seconds')):
            raise ValueError('CAUSAL_NONFINITE_OBSERVATION_CLOCK')
        bad=[k for k,v in row['values'].items() if not finite(v)]
        if bad:
            rejected.append(dict(observed_seconds=row['observed_seconds'],available_seconds=row['available_seconds'],
                invalid_fields=bad,original_values={k:repr(v) for k,v in row['values'].items()},
                source=row.get('source'),source_row=row.get('source_row'),reason='INCOMPLETE_NONFINITE_OBSERVATION_NOT_ADMITTED'))
        else:accepted.append(row)
    if not accepted:raise ValueError('NO_COMPLETE_FINITE_WEATHER_OBSERVATION')
    return accepted,rejected


def loader(output=None):
    import v43_actual.observations as original
    from v43_actual.vendor.current_ac_admission import CausalSeries
    def series(rows,*,name):
        if name!='weather':raise PermissionError('ONLY_WEATHER_OBSERVATION_ADMISSION_ADAPTER')
        accepted,rejected=admit(rows)
        result=CausalSeries(accepted,name=name)
        if result.max_staleness_seconds!=7200:raise PermissionError('ORIGINAL_WEATHER_STALENESS_MUST_REMAIN_7200')
        if output is not None:
            atomic(output,dict(UTC=now(),policy='REJECT_INCOMPLETE_OBSERVATIONS_THEN_ORIGINAL_ASOF',
                accepted_rows=len(accepted),rejected_rows=rejected,values_imputed=False,
                interpolation='NONE_ASOF_FORWARD_HOLD',max_staleness_seconds=7200,
                availability_timestamps_modified=False,raw_weather_modified=False,
                receipt_sha=result.receipt_sha))
        return result
    fn=original.load_observations
    routed=FunctionType(fn.__code__,dict(fn.__globals__,CausalSeries=series),fn.__name__,fn.__defaults__,fn.__closure__)
    routed.__kwdefaults__=fn.__kwdefaults__
    return routed


@contextmanager
def install(output=None):
    import v43_actual.observations as original
    with patch.object(original,'load_observations',loader(output)):yield
