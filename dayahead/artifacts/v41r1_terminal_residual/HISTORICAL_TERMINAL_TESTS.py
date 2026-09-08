from copy import deepcopy
from types import SimpleNamespace
import ast
from pathlib import Path
import pytest

from dayahead.v41r1.terminal import H, ISSUE_BEGIN, ISSUE_END, accounting, attach, check, start_bounds, authorized_options, residual_coordinates, CARRY_IN


def job(start=96, duration=44, **kw):
    row = dict(job_uid='one', state_at_issue='PENDING', AIDC_site='A', Rack_label='rA',
        start_slot=start, end_slot=start+duration, safe_duration_slots=duration, safe_duration_seconds=duration*900.,
        requested_GPU=1, eligible_standby=True, RSP_start_slot=88, RW_completion_slot=160,
        migration_selected=False, qos='standby', duration_authority='Q90',
        common_terminal_obligation={'must_complete_by_H':start+duration<=120}, source_snapshot_sha256='s',
        post_H_site='A' if start+duration>120 else None)
    row.update(kw)
    return attach([row])[0]


CAP = SimpleNamespace(aidc_ids=('A','B'),site_capacity={'A':64,'B':64},
    eligible_racks=lambda site,gpu:[SimpleNamespace(rack_pool_id='r'+site)])


def candidate(row, start, site='A'):
    result=deepcopy(row);result.update(start_slot=start,end_slot=start+row['safe_duration_slots'],AIDC_site=site,
        post_H_site=site if start+row['safe_duration_slots']>120 else None)
    return result


@pytest.mark.parametrize('start,expected',[(64,(0,32,12)),(68,(0,28,16)),(72,(0,24,20)),(80,(0,16,28))])
def test_full_duration_and_exact_terminal_examples(start,expected):
    assert accounting(start,44)==expected
    assert sum(expected)==44
    assert H==96 and ISSUE_END-ISSUE_BEGIN==96


@pytest.mark.parametrize('start',[88,92,96])
def test_cross_midnight_pending_can_shift_earlier_and_site(start):
    row=job()
    assert ('B',start) in authorized_options(row,CAP)
    check(row,candidate(row,start,'B'))
    assert start_bounds(row)==(88,96)


def test_late_terminal_increase_is_not_offset_by_another_job():
    row=job(); check(row,candidate(row,88))
    with pytest.raises(ValueError):check(row,candidate(row,100))


def test_existing_earliest_latest_window_not_widened():
    row=job(RSP_start_slot=92,RW_completion_slot=138)
    with pytest.raises(ValueError,match='COMMON_REFERENCE'):start_bounds(row)
    row=job(RSP_start_slot=92,RW_completion_slot=141)
    assert start_bounds(row)==(92,96)
    with pytest.raises(ValueError):check(row,candidate(row,91))


def test_non_crossing_job_cannot_dump_beyond_day():
    row=job(start=80,duration=32,RSP_start_slot=70,RW_completion_slot=150)
    assert start_bounds(row)==(70,88)
    with pytest.raises(ValueError):check(row,candidate(row,89))


def test_common_reference_remains_common_after_a0_then_a1():
    row=job(); a0=candidate(row,88,'B')
    assert start_bounds(a0)==(88,96)
    check(a0,candidate(a0,92,'A'))
    corrupt=candidate(a0,92);corrupt['terminal_reference_start_issue_slot']=88
    with pytest.raises(ValueError,match='REFERENCE_CHANGED'):check(row,corrupt)


def test_unselected_post_day_and_pre_day_execution_are_fixed_constants():
    for row in [job(start=140,AIDC_site='UNASSIGNED'),job(start=12,RSP_start_slot=0)]:
        assert authorized_options(row,CAP)==[(row['AIDC_site'],row['start_slot'])]
        with pytest.raises(ValueError):check(row,candidate(row,row['start_slot']+1))
    assert accounting(-12,44)==(12,32,0)


def test_running_domain_and_pending_migration_not_reopened():
    row=job(state_at_issue='RUNNING')
    assert authorized_options(row,CAP)==[('A',96)]
    row=job(); changed=candidate(row,92,'B'); changed['migration_selected']=True
    with pytest.raises(ValueError,match='MIGRATION'):check(row,changed)


def test_a1_owns_same_terminal_domain_and_canonical_audit():
    from dayahead.v40g_segments.canonical import import_frozen,terminal_audit
    from dayahead.v40h.feedback import candidates
    before=import_frozen([job()])[0]
    choices=candidates(before,CAP)
    moved=next(x for x in choices if x['start_slot']==88 and x['AIDC_site']=='B')
    assert terminal_audit([before],[moved])['status']=='PASS'
    assert terminal_audit([before],[moved])['POST_H_SITE_STATE_CHANGED_JOBS']==1


def test_terminal_module_has_no_optimizer_actual_grid_or_next_day_read():
    import dayahead.v41r1.terminal as terminal
    source=Path(terminal.__file__).read_text(encoding='utf-8')
    assert 'import gurobipy' not in source and 'read_parquet' not in source and 'run_fresh_opendss' not in source
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='optimize'
                   for n in ast.walk(ast.parse(source)))


def test_off_by_24_issue_and_day_coordinates():
    assert 96-ISSUE_BEGIN == 72
    assert 72*15 == 18*60
    assert residual_coordinates(96,44) == max(0,72+44-96) == 20
    assert max(0,96+44-96) == 44  # Explicitly demonstrate the rejected mixed axis.
    for issue_start in range(24,120):
        for duration in (1,40,41,44,150):
            assert residual_coordinates(issue_start,duration) == accounting(issue_start-24,duration)[2]


def test_admission_full_duration_and_authority_cannot_change():
    row=job()
    for field,value in [('end_slot',101),('AIDC_site','UNASSIGNED'),('requested_GPU',2),('RSP_start_slot',0)]:
        changed=candidate(row,92);changed[field]=value
        with pytest.raises(ValueError):check(row,changed)


def test_real_96_slot_optimizer_and_fixed_outside_day_constants(tmp_path):
    from tests.dayahead.test_v40f_min_rho import setup
    from dayahead.v40g.optimizer import solve
    from dayahead.paper_analysis.storage import read
    from dataclasses import replace
    import numpy as np
    ctx,row=setup()
    ctx.coefficients=tuple(replace(ctx.coefficients[0],slot=t) for t in range(96))
    ctx.tables={s:np.tile(a,(96,1)) for s,a in ctx.tables.items()}
    row.update(start_slot=116,end_slot=124,safe_duration_slots=8,safe_duration_seconds=7200.,
        RSP_start_slot=110,RW_completion_slot=130,eligible_standby=True,post_H_site='AIDC01')
    unselected={**row,'job_uid':'unadmitted','AIDC_site':'UNASSIGNED','Rack_label':None,
        'start_slot':140,'end_slot':148,'post_H_site':None}
    rows=attach([row,unselected]);pcc=np.zeros((96,2));pcc[92:96,0]=1
    result=solve(rows,pcc,ctx,tmp_path)
    assert result['status']=='PASS' and result['GPU'].shape==(96,2)
    chosen={r['job_uid']:r for r in result['jobs']}
    for old in rows:check(old,chosen[old['job_uid']])
    assert chosen['one']['AIDC_site']=='AIDC02'
    boundary=read(tmp_path/'HORIZON_MODEL_AUDIT.json')
    assert boundary['post_H_timed_model_variables']==0
    assert boundary['maximum_day_index']==95 and boundary['fixed_PENDING_jobs']==1


def test_terminal_persistence_roundtrip_and_independent_snapshot(tmp_path):
    from dayahead.v41r1.terminal import persist
    from dayahead.v41.persistence import verify_table
    from dayahead.paper_analysis.storage import read
    row=job();carry=job(start=12,RSP_start_slot=0,job_uid='carry')
    common={'snapshot':{'sha256':'day-own-snapshot'},'files':{'COMMON_B0_REFERENCE_JOBS.json':{'sha256':'own-reference'}}}
    summary=persist(tmp_path,'2025-05-01','B1',[row,carry],[candidate(row,88,'B'),carry],common)
    frame=verify_table(summary['table'])
    assert summary['status']=='PASS' and summary['MAX_POSITIVE_TERMINAL_VIOLATION']==0
    assert len(frame)==2 and summary['N_FIXED_PRE_DAY_PENDING']==1
    assert frame.loc[frame.job_id=='carry','ACCOUNTING_SCOPE'].item()==CARRY_IN
    independent=read(tmp_path/'INDEPENDENT_DAY_TERMINAL_BOUNDARY_AUDIT.json')
    assert independent['initial_snapshot']==common['snapshot']
    assert not independent['previous_policy_day_terminal_state_used']


def test_causal_bin_index_strict_parquet_roundtrip_preserves_all_values(tmp_path):
    import pandas as pd
    from dayahead.v41.data import parquet_index
    original=pd.DataFrame({'count':[3,0,4]},index=pd.date_range('2025-04-30',periods=3,freq='30min',tz='UTC',name='arrival_bin'))
    frame=parquet_index(original)
    assert original.index.freq is not None and frame.index.freq is None
    assert frame.index.equals(original.index) and frame.equals(original)
    path=tmp_path/'bins.parquet';frame.to_parquet(path,index=True)
    pd.testing.assert_frame_equal(frame,pd.read_parquet(path),check_exact=True)


def test_mixed_raw_timestamp_units_preserve_instants_in_strict_bin_readback(tmp_path):
    import pandas as pd
    from dayahead.v41.data import parquet_bins
    index=pd.date_range('2025-04-30',periods=3,freq='30min',tz='UTC',name='arrival_bin')
    times=[pd.Timestamp('2025-04-30T00:01:00.123456Z').as_unit('us'),None,
        pd.Timestamp('2025-04-30T01:00:00.123456789Z')]
    original=pd.DataFrame({'max_observed_end':pd.Series(times,index=index,dtype=object),
        'modeled_end_max':pd.Series(times,index=index,dtype=object),'submit_count':[1,0,2]},index=index)
    frame=parquet_bins(original)
    assert original.max_observed_end.dtype==object and original.index.freq is not None
    assert frame.max_observed_end.iloc[0]==times[0] and frame.max_observed_end.iloc[2]==times[2]
    path=tmp_path/'bins.parquet';frame.to_parquet(path)
    pd.testing.assert_frame_equal(frame,pd.read_parquet(path),check_exact=True)
