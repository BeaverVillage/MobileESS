from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import pytest
import v44_recovery_r045
from v44_recovery_r045.reference import roster
from v44_recovery_r045.admission import authorized_peer
from v44_recovery_r045 import operations as op


def reference():
    return [dict(job_uid='keep'),dict(job_uid='outside',operating_day='2025-05-08',terminal_class='POST_H_ONLY',
        state_at_issue='PENDING',AIDC_site='UNASSIGNED',start_slot=20001,end_slot=20183,
        common_terminal_obligation=dict(must_complete_by_H=False),accepted_A0_assignment_and_WAN={},migration_selected=False)]


def test_only_proven_outside_native_unassigned_posth_reference_is_projected():
    native=dict(day='2025-05-08',known_population=[dict(job_uid='keep')]);rows=reference()
    kept,extra=roster(native,rows)
    assert kept==[rows[0]] and extra==[rows[1]] and len(rows)==2


@pytest.mark.parametrize('field,value',[('AIDC_site','AIDC1'),('start_slot',119),('operating_day','2025-05-09'),
    ('terminal_class','IN_H'),('state_at_issue','RUNNING'),('migration_selected',True)])
def test_effectful_or_cross_date_reference_extra_is_rejected(field,value):
    rows=reference();rows[1][field]=value
    with pytest.raises(ValueError,match='CURRENT_HORIZON'):roster(dict(day='2025-05-08',known_population=[dict(job_uid='keep')]),rows)


def test_reference_never_removes_or_duplicates_native_jobs():
    native=dict(day='2025-05-08',known_population=[dict(job_uid='missing')])
    with pytest.raises(ValueError,match='MISSING_OR_DUPLICATE'):roster(native,reference())


def test_admission_excludes_only_same_leased_own_worker_or_actual_peers(monkeypatch):
    request=dict(day='2025-05-08',arm='B3',case_root='same',lease=dict(pid=1),campaign_root='campaign',
        r038_phase='PREPARE_SERIAL',R045_authorization='sealed')
    monkeypatch.setattr('v44_recovery_r045.admission.read',lambda p:dict(request))
    own=dict(pid=os.getpid(),cmdline=['python',op.ENTRY,'--worker','request.json'])
    assert authorized_peer(own,request,op.ENTRY)
    own['pid']=123;assert not authorized_peer(own,request,op.ENTRY)
    request.update(r038_phase='ACTUAL_PARALLEL',sequence_mode='MAIN')
    assert authorized_peer(own,request,op.ENTRY)
    own['cmdline']=['python','v44_recovery_r044.operations','--worker','request.json']
    assert not authorized_peer(own,request,op.ENTRY)


def test_cross_lease_peer_is_foreign(monkeypatch):
    request=dict(lease='current',campaign_root='campaign')
    monkeypatch.setattr('v44_recovery_r045.admission.read',lambda p:dict(lease='other',campaign_root='campaign'))
    assert not authorized_peer(dict(pid=os.getpid(),cmdline=[op.ENTRY,'--worker','request.json']),request,op.ENTRY)


def test_infrastructure_failure_cannot_be_excluded_and_completed(tmp_path):
    j=dict(day='2025-05-08',arm='B3',case_root=str(tmp_path))
    with pytest.raises(RuntimeError,match='INFRASTRUCTURE_FAILURE'):op.collect(SimpleNamespace(returncode=1),j,planning=True)
    assert j['status']=='INFRASTRUCTURE_BLOCKED'


def test_reference_original_function_is_retained_outside_module_patch(monkeypatch):
    from v43_arms import reference as original
    from v44_recovery_r045 import reference as adapter
    captured=adapter._original_project
    monkeypatch.setattr(original,'project',adapter.project)
    assert adapter._original_project is captured and captured is not adapter.project
