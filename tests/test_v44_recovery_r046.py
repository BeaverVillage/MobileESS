from pathlib import Path
from unittest.mock import patch
from types import FunctionType
import inspect
import pytest
import v44_recovery_r046
from v44_recovery_r046 import operations as op
from v44_recovery_r046.planning import live_compiler


def test_a1_repair_body_uses_the_live_stage_group_not_stale_globals():
    from v42_may_campaign_native90 import a_stage
    from v44_recovery_r029 import integer_repair
    compiler=live_compiler(integer_repair.compile_run)
    fn=compiler(a_stage.run)
    assert fn.__globals__ is a_stage.__dict__
    marker=object()
    with patch.object(a_stage,'group',marker):assert fn.__globals__['group'] is marker
    assert '_r029_restore' in fn.__code__.co_names
    assert "A_CERTIFIED_LB_UB_CONFLICT" in inspect.getsource(fn)


def barrier():
    completed=[];ready=[]
    for i,(day,arm) in enumerate(op.core.seq.MAIN):
        root=Path('D:/test')/day/arm/'attempt001'
        if i<7:completed.append(dict(day=day,arm=arm,status='PASS',case_root=str(root),result=dict(path=str(root/'RESULT.json'))))
        else:ready.append(dict(day=day,arm=arm,handoff={'sha256':'sealed'}))
    return dict(completed=completed,ready=ready,excluded=[],all_preparations_resolved=True,
        Actual_started_before_barrier=False,cpu_placement=dict(slots=list(range(7))))


def setup_read(monkeypatch,b):
    records={j['result']['path']:dict(day=j['day'],arm=j['arm'],PASS=True,finished_UTC='complete') for j in b['completed']}
    monkeypatch.setattr(op,'verify',lambda r:None)
    monkeypatch.setattr(op,'read',lambda p:records[str(p)])
    return records


def test_completed_actuals_count_toward_barrier_but_are_not_relaunched(monkeypatch):
    b=barrier();setup_read(monkeypatch,b)
    assert len(op.validate_barrier(b)['ready'])==7
    fn=op.actual_function();assert callable(fn)


def test_completed_actual_cross_date_evidence_is_rejected(monkeypatch):
    b=barrier();records=setup_read(monkeypatch,b)
    records[b['completed'][0]['result']['path']]['day']='2025-05-30'
    with pytest.raises(PermissionError,match='TERMINAL_EVIDENCE'):op.validate_barrier(b)


def test_seven_worker_wave_cannot_omit_failed_or_completed_members(monkeypatch):
    b=barrier();setup_read(monkeypatch,b);b['completed'].pop()
    with pytest.raises(PermissionError,match='ALL_MAIN'):op.validate_barrier(b)


def test_may12_helpers_resolve_the_may12_parent_package():
    from v44_recovery_r046.numerical import relocated
    from v44_recovery_r044 import numerical
    fn=relocated(numerical.repair)
    assert fn.__globals__['__package__']=='v44_recovery_r046'
    assert op.PARENT.as_posix().endswith('/2025-05-12/B3/attempt002')
