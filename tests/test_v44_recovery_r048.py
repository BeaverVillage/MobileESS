from pathlib import Path
from unittest.mock import patch
import pytest
from v44_recovery_r048 import operations as op
from v44_week4 import preparation as prep


def test_month_days_and_two_roots_are_exact():
    assert len(op.DAYS)==17
    assert op.campaign_for('2025-05-15')==op.CAMPAIGNS[0]
    assert op.campaign_for('2025-05-21')==op.CAMPAIGNS[0]
    assert op.campaign_for('2025-05-22')==op.CAMPAIGNS[1]
    assert op.campaign_for('2025-05-31')==op.CAMPAIGNS[1]
    for day in ('2025-05-14','2025-06-01'):
        with pytest.raises(PermissionError):op.campaign_for(day)


@pytest.mark.parametrize('arm',['B1','B3'])
def test_new_weeks_cannot_release_other_arms(arm):
    r=dict(day='2025-05-15',arm=arm,worker_slot=1,sources=[],R048_authorization={'path':'auth'})
    with patch.object(op,'authority',return_value={}),patch.object(op,'verify'),patch.object(op,'record',return_value={'path':'auth'}),pytest.raises(PermissionError):op.authorize_case(r)


def test_input_blocked_day_is_not_executable():
    r=dict(day='2025-05-23',arm='B0',worker_slot=1,sources=[],R048_authorization={})
    with patch.object(op,'authority',return_value={'plan':[dict(day=r['day'],eligible=False)]}),patch.object(op,'verify'),patch.object(op,'record',return_value={}),pytest.raises(PermissionError):op.authorize_case(r)


@pytest.mark.parametrize('arm,n,day',[('B0',2,'2025-05-15'),('B2',2,'2025-05-08'),('B3',1,'2025-05-22')])
def test_extra_slots_and_other_arms_rejected(arm,n,day):
    with patch.object(op,'alive',return_value=True),pytest.raises(PermissionError),op.slot(day,arm,n,root=op.MAIN,lease={}):pass


def test_week4_has_ten_days_and_exactly_40_held_cases():
    from tests.test_v44_week3_preparation import templates
    from v44_week3 import preparation as old
    with prep.bindings(),patch.object(old,'DAYS',prep.DAYS),patch.object(old,'DOC',prep.DOC),patch.object(old,'CAMPAIGN',prep.CAMPAIGN):
        rows=templates()
        with patch.dict(prep.validate_templates.__globals__,verify=lambda x:None):prep.validate_templates(rows)
    assert len(rows)==40 and all(r['execution_authorized'] is False for r in rows)
    assert prep.DAYS[0]=='2025-05-22' and prep.DAYS[-1]=='2025-05-31'


def test_historical_permit_date_scope_is_retained_under_new_week_binding():
    # The request adapter must route legacy permits through week2's original
    # historical-day wrapper, not the active future-week day axis.
    import inspect
    source=inspect.getsource(op.bindings.__wrapped__)
    assert 'return fallback(path,certification)' in source
    assert 'fallback=prepare.require_execution_permit' in source
