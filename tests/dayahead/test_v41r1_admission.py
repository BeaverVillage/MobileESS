from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from tests.dayahead.test_v41_scalar_interface import fixture
from dayahead.v41r1.migration import attach, target, checkpoints, check
from dayahead.v40g.domain import options, segments, audit
from dayahead.v40g_segments.canonical import import_frozen, occupancy, terminal, planning_power
from dayahead.v40h.feedback import candidates


def unadmitted_fixture():
    ctx,row,snapshot=fixture()
    row.update(start_slot=0,end_slot=40,safe_duration_slots=40,safe_duration_seconds=36000.,
        AIDC_site='UNASSIGNED',Rack_label=None)
    return ctx,attach([row])[0],snapshot


def test_q90_backlog_keeps_full_service_without_admission_or_migration():
    ctx,row,_=unadmitted_fixture()
    assert not target(row) and checkpoints(row)==()
    opts=options(row,ctx.capacity,None,{})
    assert len(opts)==1 and opts[0].site=='UNASSIGNED' and not opts[0].migrated
    assert opts[0].segments(row)==()
    assert sum(b-a for s,a,b in segments(row))==40
    canonical=import_frozen([row])
    assert sum(p['end']-p['start'] for p in canonical[0]['compute_segments'])==40
    assert occupancy(canonical,ctx.capacity.aidc_ids)[0].sum()==0
    assert candidates(canonical[0],ctx.capacity)==canonical
    assert audit([row],[row],ctx.capacity,None)['status']=='PASS'
    t=terminal(canonical[0])
    assert t['status']=='FROZEN_UNADMITTED_BACKLOG' and t['state_at_H']=='PENDING'
    assert t['remaining_compute_slots']==40 and t['remaining_compute_GPU_slots']==40*row['requested_GPU']
    changed=deepcopy(row);changed['AIDC_site']='AIDC01'
    with pytest.raises(ValueError,match='ADMISSION'):check(row,changed)


def test_legacy_unassigned_overlap_still_requires_explicit_current_authority():
    ctx,row,_=unadmitted_fixture();row.pop('v41r1_migration_contract')
    with pytest.raises(ValueError,match='UNASSIGNED_OPERATING_COMPUTE'):
        occupancy(import_frozen([row]),ctx.capacity.aidc_ids)


def test_actual_unadmitted_backlog_uses_realized_service_without_execution():
    from dayahead.v41.actual import replay_jobs
    from tests.dayahead.test_v41_actual import fixture as actual_fixture
    from datetime import timedelta
    ctx,row,_=unadmitted_fixture()
    base,obs,kwargs=actual_fixture();row['requested_walltime_seconds']=base['requested_walltime_seconds']
    obs['one']['end_time']=obs['one']['start_time']+timedelta(seconds=40000)
    actual=replay_jobs(import_frozen([row]),obs,**kwargs)
    out=actual['job_ledger'][0]
    assert out['status']=='FROZEN_UNADMITTED_BACKLOG' and out['actual_compute_segments']==[]
    assert not out['frozen_policy_admitted'] and out['backlog_GPU_hours']==40000*row['requested_GPU']/3600


def test_explicit_recurrence_and_feedback_keep_backlog_out_of_physical_model(tmp_path,monkeypatch):
    from dayahead.v40g.optimizer import solve
    from dayahead.v41.reserve import bind
    from dayahead.paper_analysis.storage import write_json,sha
    import dayahead.v40h.feedback as feedback
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from tests.dayahead.test_v40g_joint import Wan
    ctx,row,snapshot=unadmitted_fixture();ctx.wan=Wan();ctx.elapsed={}
    snapshot['PENDING_JOB_Q90_SECONDS']={row['job_uid']:36000.}
    snapshot['PENDING_JOB_DURATION_SLOTS']={row['job_uid']:40}
    path=tmp_path/'ML.json';write_json(path,snapshot);bind(ctx,path,sha(path))
    pcc=planning_power(import_frozen([row]),ctx)['pcc']
    explicit=solve([row],pcc,ctx,tmp_path/'explicit',factorize=False,event_load=False)
    recurrence=solve([row],pcc,ctx,tmp_path/'recurrence',factorize=True,event_load=True)
    assert explicit['jobs']==recurrence['jobs']==[row]
    np.testing.assert_allclose(explicit['OBJECTIVE_VECTOR'],recurrence['OBJECTIVE_VECTOR'],rtol=0,atol=1e-9)
    assert explicit['GPU'].sum()==recurrence['GPU'].sum()==0
    assert explicit['reserve_diagnostics']==recurrence['reserve_diagnostics']
    canonical=import_frozen([row])
    monkeypatch.setattr(feedback,'controls_from_trajectory',
        lambda coefficients,pcc,slots:np.column_stack([pcc,np.zeros(96)]))
    a1=feedback.solve_feedback(canonical,MessTrajectory(()),ctx)
    assert a1['jobs']==canonical
    assert planning_power(a1['jobs'],ctx)['gpu'].sum()==0
