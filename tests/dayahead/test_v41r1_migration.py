from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import inspect
import numpy as np
import pytest
from tests.dayahead.test_v40g_joint import Wan
from tests.dayahead.test_v40f_min_rho import setup
from tests.dayahead.test_v41_actual import fixture
from dayahead.v41r1.migration import attach,target,pending_in_day,state_at_d00,checkpoints,check
from dayahead.v40g.domain import options,materialize,audit
from dayahead.v40g_segments.canonical import import_frozen,wan_audit


def job(start=96,duration=44,state='PENDING'):
    ctx,row=setup()
    row.update(start_slot=start,end_slot=start+duration,safe_duration_slots=duration,
        safe_duration_seconds=duration*900.,state_at_issue=state)
    return ctx,attach([row])[0]


@pytest.mark.parametrize('start,duration,state,expected',[(0,200,'RUNNING','RUNNING'),(20,20,'PENDING','RUNNING'),
    (24,10,'PENDING','PENDING'),(0,24,'RUNNING','COMPLETE'),(120,10,'PENDING','PENDING')])
def test_d00_boundary(start,duration,state,expected):
    _,row=job(start,duration,state);assert state_at_d00(row)==expected


@pytest.mark.parametrize('start,duration,state',[(0,200,'RUNNING'),(20,140,'PENDING'),(96,44,'PENDING')])
def test_same_migration_state_machine_and_crossmidnight(start,duration,state):
    ctx,row=job(start,duration,state);cp=checkpoints(row,{'one':0.})
    opts=options(row,ctx.capacity,Wan(),{'one':0.})
    moves=[o for o in opts if o.migrated];assert moves
    for opt in (moves[0],moves[-1]):
        out=materialize(row,opt,ctx.capacity,Wan());check(row,out)
        canonical=import_frozen([out]);assert wan_audit(canonical,Wan())['status']=='PASS'
        assert opt.checkpoint==cp[0] and opt.transfer_end+1<120
        assert sum(b-a for s,a,b in opt.segments(row))==duration
        assert audit([row],[out],ctx.capacity,Wan())['status']=='PASS'


def test_placement_no_checkpoint_no_restart_no_migration_count_and_start_frozen():
    ctx,row=job();opts=options(row,ctx.capacity,Wan(),{})
    opt=next(o for o in opts if o.site!='AIDC01' and not o.migrated)
    out=import_frozen([materialize(row,opt,ctx.capacity,Wan())])[0]
    assert out['start_slot']==96 and out['safe_duration_slots']==44
    assert not out['migration_selected'] and out['migration_events']==[]
    assert out['AIDC_site']=='AIDC02' and checkpoints(row)==tuple(range(98,120,2))
    assert all(o.start==96 for o in opts)


def test_placement_then_migration_uses_selected_initial_site():
    ctx,row=job();opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC02')
    out=materialize(row,opt,ctx.capacity,Wan())
    assert out['initial_AIDC']=='AIDC02' and out['frozen_WAN_transfer']['source_AIDC']=='AIDC02'
    assert out['initial_Rack_label']=='AIDC02_LP01'
    assert out['compute_segments'][0]['site']=='AIDC02' and out['migration_destination']=='AIDC01'


def test_no_checkpoint_before_start_and_no_restart_at_boundary():
    ctx,row=job(118,20);opts=options(row,ctx.capacity,Wan(),{})
    assert checkpoints(row)==() and not any(o.migrated for o in opts)
    ctx,row=job(117,20);assert checkpoints(row)==(119,)
    assert not any(o.migrated for o in options(row,ctx.capacity,Wan(),{}))


def test_disabled_policy_keeps_reference_site_and_no_migration():
    ctx,row=job();opts=options(row,ctx.capacity,Wan(),{},temporal_only=True)
    assert len(opts)==1 and opts[0].site==row['AIDC_site'] and not opts[0].migrated


def test_a1_freezes_pending_migration_and_crossmidnight_placement():
    from dayahead.v40h.feedback import candidates
    ctx,row=job();opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated)
    out=import_frozen([materialize(row,opt,ctx.capacity,Wan())])[0]
    assert candidates(out,ctx.capacity)==[out]


def test_hard_gpu_rack_compatibility():
    ctx,row=job();row['requested_GPU']=3
    assert options(row,ctx.capacity,Wan(),{})==()


def test_wan_capacity_no_transfer_option():
    class Zero(Wan):
        def path_capacity_bytes(self,s,d,t):return 0
    ctx,row=job();assert not any(o.migrated for o in options(row,ctx.capacity,Zero(),{}))


def test_actual_pending_migration_frozen_full_realized_service_and_cancellation():
    from dayahead.v41.actual_dispatch import replay_jobs
    ctx,row=job();base,obs,kw=fixture();row.update(submit_time=base['submit_time'],requested_walltime_seconds=100000.)
    opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC02')
    frozen=import_frozen([materialize(row,opt,ctx.capacity,Wan())]);before=deepcopy(frozen)
    for seconds in (3600,901):
        obs['one']['end_time']=obs['one']['start_time']+timedelta(seconds=seconds)
        result=replay_jobs(frozen,obs,wan=Wan(),**kw);out=result['job_ledger'][0]
        assert result['exact_execution_feasibility']['status']=='PASS'
        assert out['actual_compute_segments'][0]['start']==96 and out['actual_compute_segments'][0]['site']=='AIDC02'
        assert out['migration_executed']==(seconds>1800)
        assert abs(sum(s['end']-s['start'] for s in out['actual_compute_segments'])*900-seconds)<1e-6
        assert frozen==before


def test_actual_checkpoint_follows_delayed_progress_without_new_decision():
    from dayahead.v41.actual_dispatch import replay_jobs
    ctx,row=job(24,20);base,obs,kw=fixture();row.update(submit_time=base['submit_time'],requested_walltime_seconds=100000.)
    opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC01')
    selected=materialize(row,opt,ctx.capacity,Wan())
    block={**row,'job_uid':'aaa','requested_GPU':2}
    obs['one']['end_time']=obs['one']['start_time']+timedelta(hours=1)
    obs['aaa']={**obs['one'],'gpus_requested':2}
    frozen=import_frozen([block,selected]);result=replay_jobs(frozen,obs,wan=Wan(),**kw)
    e=result['migration_execution_replay']['evidence']['one']
    assert e['START_DELAY_SECONDS']==3600
    assert e['ACTUAL_CHECKPOINT_NS']-e['DA_CHECKPOINT_NS']==3600*10**9
    assert e['destination']==selected['AIDC_site'] and e['payload_bytes']==10
    assert result['exact_execution_feasibility']['status']=='PASS'


def test_abandoned_terminal_and_actual_inputs_unreachable():
    import dayahead.v41r1.migration as module
    from dayahead.v40g import domain,optimizer
    from dayahead.v41 import common
    for source in (module,domain,optimizer,common):
        code=inspect.getsource(source)
        assert 'from dayahead.v41r1.terminal' not in code
        assert 'realized_runtime' not in code and 'actual_voltage' not in code
        assert 'terminal_residual_cap' not in code and 'spill_budget' not in code
    assert module.END-module.BEGIN==96 and 96-module.BEGIN==72


def test_late_checkpoint_serial_max_and_96_slot_model(tmp_path):
    from dayahead.v40g.optimizer import solve
    ctx,row=job(96,44);c=ctx.coefficients[0]
    ctx.coefficients=tuple(replace(c,slot=t) for t in range(96))
    ctx.tables={s:np.tile([[0.,1.,2.]],(96,1)) for s in ctx.capacity.aidc_ids}
    ctx.wan=Wan();ctx.elapsed={}
    pcc=np.zeros((96,2));pcc[72:,0]=1
    result=solve([row],pcc,ctx,tmp_path,inject_reference=True)
    assert result['jobs'][0]['start_slot']==96 and result['secondary_migration_optimum']==0
    assert (tmp_path/'DAY_BOUNDARY_AUDIT.json').exists()


def test_candidate_persistence_exact_reopen_and_hash(tmp_path):
    from dayahead.v41r1.migration_audit import persist
    from dayahead.v41.persistence import verify_table
    from dayahead.v41.preflight import record
    ctx,row=job();c=ctx.coefficients[0]
    ctx.coefficients=tuple(replace(c,slot=t) for t in range(96))
    ctx.tables={s:np.tile([[0.,1.,2.]],(96,1)) for s in ctx.capacity.aidc_ids}
    ctx.wan=Wan();ctx.elapsed={}
    value=persist(tmp_path,'2025-05-01','B1',[row],import_frozen([row]),ctx)
    assert value['N_PENDING_PRESTART_RELOCATION_ELIGIBLE']==1
    for ref in value['files'].values():
        assert len(verify_table(ref))==1 and ref['sha256']==record(ref['path'])['sha256']


def test_actual_migration_carry_out_is_recorded_not_policy_failure(tmp_path):
    from dayahead.v41.actual_dispatch import replay_jobs,persist
    from dayahead.v41.persistence import verify_table
    ctx,row=job(115,10);base,obs,kw=fixture();row.update(submit_time=base['submit_time'],requested_walltime_seconds=100000.)
    opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC01')
    selected=materialize(row,opt,ctx.capacity,Wan());block={**row,'job_uid':'aaa','requested_GPU':2}
    obs['one']['end_time']=obs['one']['start_time']+timedelta(hours=2)
    obs['aaa']={**obs['one'],'gpus_requested':2}
    result=replay_jobs(import_frozen([block,selected]),obs,wan=Wan(),**kw)
    e=result['migration_execution_replay']['evidence']['one']
    assert e['MIGRATION_CARRY_OUT'] and not e['MIGRATION_COMPLETED_WITHIN_HORIZON']
    assert not e['state_propagated_to_next_day'] and result['exact_execution_feasibility']['status']=='PASS'
    persist(tmp_path,result,obs,kw['issue_time'],ctx.capacity.site_capacity,kw['racks'])
    assert (tmp_path/'aidc/ACTUAL_MIGRATION_CLOCKS.parquet').exists()


def test_actual_shifted_wan_queues_same_path_and_frozen_uid_order():
    from dayahead.v41.actual_dispatch import replay_jobs
    ctx,row=job(96,30);base,obs,kw=fixture();row.update(submit_time=base['submit_time'],requested_walltime_seconds=100000.)
    first=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC01')
    second=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC01' and o.transfer_start==first.transfer_end)
    a=materialize(row,first,ctx.capacity,Wan());b=materialize({**row,'job_uid':'two'},second,ctx.capacity,Wan())
    obs['one']['end_time']=obs['one']['start_time']+timedelta(hours=3);obs['two']=dict(obs['one'])
    result=replay_jobs(import_frozen([a,b]),obs,wan=Wan(),**kw);e=result['migration_execution_replay']['evidence']
    assert e['two']['ACTUAL_WAN_START_NS']==e['one']['ACTUAL_WAN_END_NS']
    assert e['two']['WAN_QUEUE_DELAY_SECONDS']==900
    assert e['one']['WAN_path']==e['two']['WAN_path']==['fixed']
    assert result['exact_execution_feasibility']['status']=='PASS'
