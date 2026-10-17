from contextlib import contextmanager
from pathlib import Path
import pytest
from v44.common import atomic,read,record
from v44_recovery_r024a.failure_continue import defer,deferred_dates,technical_hold,authorized_retry


def failed_case(tmp_path):
    case=tmp_path/'campaign/2025-05-03/B0/attempt001'
    atomic(case/'RESULT.json',dict(status='FAILED',PASS=False,error='fixture'))
    atomic(case/'M1/NATIVE_LEDGER.json',dict(measured_Native_Runtime=17.))
    return case


def test_failure_is_queued_without_rewriting_result_or_Native(tmp_path):
    case=failed_case(tmp_path);ops=tmp_path/'ops';ops.mkdir()
    result=record(case/'RESULT.json');ledger=record(case/'M1/NATIVE_LEDGER.json')
    queue=defer(ops,case,read(case/'RESULT.json'));original=record(queue)
    assert defer(ops,case,read(case/'RESULT.json'))==queue and record(queue)==original
    assert record(case/'RESULT.json')==result and record(case/'M1/NATIVE_LEDGER.json')==ledger
    assert deferred_dates(ops)=={'2025-05-03'}


def test_pass_can_never_enter_repair_queue(tmp_path):
    with pytest.raises(ValueError,match='CANNOT_DEFER_PASS'):defer(tmp_path,tmp_path,dict(PASS=True))


@pytest.mark.parametrize('user_stop,reason,case,expected',[
    (False,'R022_A2_CONTINUATION_TECHNICAL_ERROR_HOLD','target',True),
    (True,'R022_A2_CONTINUATION_TECHNICAL_ERROR_HOLD','target',False),
    (False,'SOURCE_DRIFT','target',False),
    (False,'R022_A2_CONTINUATION_TECHNICAL_ERROR_HOLD','other',False)])
def test_only_matching_current_case_technical_stop_can_advance(user_stop,reason,case,expected,tmp_path):
    guard=dict(protected_case_root=str(tmp_path/'target'))
    assert technical_hold(dict(user_stop=user_stop,reason=reason,failed_case=str(tmp_path/case)),guard)==expected


def test_retry_requires_separate_validated_release_and_current_permit(tmp_path):
    case=failed_case(tmp_path);ops=tmp_path/'ops';ops.mkdir();permit=tmp_path/'permit.json'
    atomic(permit,dict(revision='fixture'))
    queue=defer(ops,case,read(case/'RESULT.json'))
    assert not authorized_retry(ops,case,permit)
    proof=tmp_path/'repair.json';atomic(proof,dict(PASS=True))
    atomic(ops/'R024A_REPAIR_RELEASES'/queue.name,dict(repair_validation=record(proof),failed_queue_receipt=record(queue),
        execution_permit=record(permit),diagnosed_cause_fixed=True,allow_new_attempt=True))
    assert authorized_retry(ops,case,permit) and not deferred_dates(ops)
    atomic(proof,dict(PASS=False))
    with pytest.raises(Exception):authorized_retry(ops,case,permit)


@pytest.mark.parametrize('launcher_error',[False,True])
def test_coordinator_case_error_skips_same_date_and_runs_next_date(tmp_path,monkeypatch,launcher_error):
    from v44_recovery_r024a import operations as op,handover
    from v44 import config
    campaign=tmp_path/'campaign';ops=campaign/'AUTONOMOUS_RECOVERY';doc=tmp_path/'doc'
    atomic(doc/'SCIENTIFIC_FREEZE_MANIFEST.json',dict(unchanged_source_rows=[],unchanged_support_inputs=[],inherited_external_M_algorithms=[],adapters=[],source_sha='fixture'))
    atomic(doc/'SEVEN_DAY_INPUT_MANIFEST.json',dict(days=[dict(day=d,files={}) for d in ('2025-05-03','2025-05-04')]))
    order=(('2025-05-03','B0'),('2025-05-03','B1'),('2025-05-04','B0'))
    monkeypatch.setattr(op,'CAMPAIGN',campaign);monkeypatch.setattr(op,'OPS',ops);monkeypatch.setattr(op,'DOC',doc)
    monkeypatch.setattr(op,'validate',lambda:{})
    monkeypatch.setattr(op,'decorate',lambda case,permit:dict(case,sources=[]))
    monkeypatch.setattr(op,'workers',lambda:[])
    monkeypatch.setattr(op,'record',lambda p:{} if p==op.PERMIT else record(p))
    monkeypatch.setattr(config,'B2_ORDER',());monkeypatch.setattr(config,'MAIN_ORDER',order)
    monkeypatch.setattr(config,'axis',lambda day:{})
    monkeypatch.setattr(handover,'require_boundary',lambda:None);monkeypatch.setattr(handover,'activate',lambda lease:None)
    @contextmanager
    def lease(root):yield {}
    monkeypatch.setattr(op,'coordinator',lease)
    def states(root):
        return {key:read(op.latest(root,*key)/'RESULT.json')['status'] if op.latest(root,*key) else 'READY' for key in order}
    monkeypatch.setattr(op,'states',states)
    launched=[]
    class Child:
        pid=123
        def __init__(self,args,**kw):
            case=read(args[-1]);launched.append((case['day'],case['arm']))
            if launcher_error and len(launched)==1:raise OSError('fixture launcher failure')
            self.returncode=1 if len(launched)==1 else 0
            atomic(Path(case['case_root'])/'RESULT.json',dict(status='FAILED' if self.returncode else 'COMPLETE',PASS=not self.returncode,error='fixture' if self.returncode else None))
        def poll(self):return self.returncode
    monkeypatch.setattr(op.subprocess,'Popen',Child)
    class Done(Exception):pass
    def sleep(seconds):
        if len(launched)==2:raise Done
    monkeypatch.setattr(op.time,'sleep',sleep)
    with pytest.raises(Done):op.run()
    assert launched==[('2025-05-03','B0'),('2025-05-04','B0')]
    assert not (ops/'STOP_AUTONOMY.json').exists()
    assert len(list((ops/'R024A_REPAIR_QUEUE').glob('*.json')))==1
