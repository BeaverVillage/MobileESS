"""Independent readiness partition and concurrency acceptance tests."""
from copy import deepcopy
import pytest
from v44_week2 import operations as op

def manifest(failures=()):
    ready=[];excluded=[]
    for day in op.DAYS:
        for arm in op.ARMS:
            item=dict(day=day,arm=arm)
            if (day,arm) in failures:excluded.append(dict(item,exclusion_reason='Native budget exhausted'))
            else:ready.append(dict(item,handoff={'sha256':'verified'}))
    count=min(7,len(ready))
    return dict(ready=ready,excluded=excluded,all_preparations_resolved=True,Actual_started_before_barrier=False,
        cpu_placement=dict(slots=list(range(count))) if count else None)

def test_seven_workers_accept_28_prepared_cases():
    assert len(op.validate_barrier(manifest())['ready'])==28

def test_one_failed_preparation_does_not_block_healthy_cases():
    value=op.validate_barrier(manifest({('2025-05-09','B1'),('2025-05-09','B3')}))
    assert len(value['ready'])==26 and len(value['cpu_placement']['slots'])==7

def test_pending_case_prevents_any_actual_even_if_marked_ready():
    value=manifest();value['ready'].pop()
    with pytest.raises(PermissionError,match='ALL_28'):op.validate_barrier(value)

def test_duplicate_case_cannot_replace_unresolved_case():
    value=manifest();value['ready'][-1]=deepcopy(value['ready'][0])
    with pytest.raises(PermissionError,match='ALL_28'):op.validate_barrier(value)

def test_all_failed_is_terminal_with_no_cpu_pool():
    value=manifest({(d,a) for d in op.DAYS for a in op.ARMS})
    assert op.validate_barrier(value)['cpu_placement'] is None

def test_worker_count_is_seven_or_number_of_survivors():
    keys=[(d,a) for d in op.DAYS for a in op.ARMS]
    value=manifest(set(keys[3:]));assert len(op.validate_barrier(value)['cpu_placement']['slots'])==3
    value['cpu_placement']['slots']=list(range(7))
    with pytest.raises(PermissionError,match='SLOT'):op.validate_barrier(value)

def test_dates_remain_scoped_to_second_week_and_legacy_permit_scope_restores():
    from v44.config import axis
    with op.bindings():
        assert axis('2025-05-08')['prefix_slots']==24
        assert axis('2025-05-14')['evaluation_slots']==96
        with pytest.raises(ValueError):axis('2025-05-07')
        with op.period(op.OLD_DAYS):assert axis('2025-05-07')['evaluation_slots']==96
        assert axis('2025-05-14')['execution_slots']==120
