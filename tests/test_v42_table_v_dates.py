"""Public date binding fixtures; no native model or physical solve."""
from datetime import datetime, timezone, timedelta

import pytest

from v42_integration.table_v_dates import context_day, require_day


@pytest.mark.parametrize('n', range(1, 32))
def test_each_may_day_binds_its_own_public_midnight(n):
    day = f'2025-05-{n:02d}'
    begin = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
    context = dict(day=day,manifest={'day':day},state={'day':day,'begin_epoch_seconds':begin},data=[{'day':day}])
    assert context_day(context) == day


@pytest.mark.parametrize('day', ['2025-04-30','2025-06-01','2025-05-32','2026-05-01',None])
def test_other_dates_never_acquire_a_may_authority(day):
    with pytest.raises(ValueError,match='INDEPENDENT_MAY_DATE'):
        require_day(day)


def test_saved_may01_manifest_without_day_uses_its_public_context_day():
    assert context_day(dict(manifest={},day='2025-05-01',state={'day':'2025-05-01'})) == '2025-05-01'


@pytest.mark.parametrize('change', ['state','data','clock'])
def test_different_d0_or_day_clock_cannot_be_relabelled(change):
    day = '2025-05-31'
    context = dict(manifest={'day':day},state={'day':day},data=[{'day':day}])
    if change=='state':context['state']['day']='2025-05-01'
    elif change=='data':context['data'][0]['day']='2025-05-01'
    else:context['state']['begin_epoch_seconds']=0
    with pytest.raises(ValueError,match='DATE_'):
        context_day(context)
