from pathlib import Path
from types import SimpleNamespace
import pytest
from v44.common import read
from v44.daily import ActualBinding,day_inputs
from v44_recovery_r006.initial_running import install


@pytest.mark.parametrize('day',['2025-05-03','2025-05-07'])
def test_real_date_initial_running_roster_and_original_guards(day,tmp_path):
    row=day_inputs(day);native=read(row['files']['native']['path']);windows=read(row['files']['windows']['path'])
    folder=Path(r'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/references')/day
    with install():args,case=ActualBinding('B0',folder,None,day).prepare(tmp_path/day)
    qos=args['qos_window_provider'];w={r['job_id'] for r in windows}
    expected={r['job_uid'] for r in native['known_population'] if r['state']=='RUNNING' and r['job_uid'] not in w}
    positive={r['job_uid'] for r in native['known_population'] if r['state']=='RUNNING' and r['job_uid'] not in w and r['service_slots']>0}
    assert qos.external_running==expected and len(positive)==(2 if day=='2025-05-03' else 5)
    assert qos.windows=={r['job_id']:r for r in windows}
    initial_uids={r[0].uid for r in args['running']}
    assert positive<=initial_uids and not qos.external_running.intersection(qos.windows)
    uid=next(iter(positive))
    with pytest.raises(ValueError,match='EXTERNAL_RUNNING_CANNOT_CREATE_PENDING_COMMAND'):
        qos.issue(SimpleNamespace(uid=uid,origin_unknown=False,state='PENDING'))
    with pytest.raises(ValueError,match='ORIGINAL_KNOWN_PROVIDER_DRIFT'):
        qos.issue(SimpleNamespace(uid=uid,origin_unknown=False,state='RUNNING',provider_sha='wrong'))
    with pytest.raises(ValueError,match='ORIGINAL_KNOWN_WINDOW_REQUIRED'):
        qos.issue(SimpleNamespace(uid='UNREGISTERED_PENDING_JOB',origin_unknown=False,state='PENDING'))
