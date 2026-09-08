"""Restore retained pre-V4 temporal choices without expanding migration pairs."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from dayahead.v41r1 import terminal,migration
from dayahead.v40g.domain import Option
from dayahead.v41r3.authority import OUT,OLD,OLD_RUN,DAY
from dayahead.v41.preflight import ROOT,record
from dayahead.paper_analysis.storage import read,write_json,digest

CONTRACT='V41R3_RESTORED_PRE_V4_TEMPORAL_OPTIONS_PLUS_FROZEN_V4_MIGRATION'
BASE_COUNT=4772575
RESTORED_COUNT=117252
TOTAL_COUNT=BASE_COUNT+RESTORED_COUNT

def reference(row):
    return terminal.attach([row])[0]

def restored_options(row,capacity):
    # This is the exact retained predecessor implementation, applied to the
    # current frozen B0 reference. Carry-in, admission and migration remain as
    # in V4. Only previously authorized standalone temporal choices return.
    if not migration.pending_in_day(row):return ()
    ref=reference(row)
    return tuple(Option(s,t,t+row['safe_duration_slots']) for s,t in terminal.authorized_options(ref,capacity) if t!=row['start_slot'])

def validate(reference_row,candidate):
    if candidate['start_slot']==reference_row['r1_reference_start']:
        return
    if candidate.get('migration_selected'):raise ValueError('NEW_TEMPORAL_MIGRATION_COMBINATION_FORBIDDEN')
    if not migration.pending_in_day(reference_row):raise ValueError('TEMPORAL_ELIGIBILITY_CHANGED')
    old=reference(reference_row);new=dict(old)
    for key in ('AIDC_site','start_slot','end_slot','migration_selected'):new[key]=candidate.get(key,False)
    terminal.check(old,new)

@contextmanager
def activate():
    """Explicit scoped adapter; original migration source bytes stay archived."""
    old_check,old_boundary=migration.check,migration.model_boundary
    def check(ref,candidate):
        validate(ref,candidate)
        if candidate['start_slot']!=ref['r1_reference_start']:
            restored=dict(candidate,start_slot=ref['r1_reference_start'],end_slot=ref['r1_reference_end'])
            old_check(ref,restored)
        else:old_check(ref,candidate)
    def boundary(model,jobs,options_by_uid,slots):
        base={r['job_uid']:tuple(o for o in options_by_uid[r['job_uid']] if o.start==r['r1_reference_start']) for r in jobs}
        result=old_boundary(model,jobs,base,slots)
        count=0
        for row in jobs:
            for o in options_by_uid[row['job_uid']]:
                if o.start==row['r1_reference_start']:continue
                assert not o.migrated
                validate(row,dict(row,start_slot=o.start,end_slot=o.end,AIDC_site=o.site,migration_selected=False))
                count+=1
        result.update(restored_temporal_options=count,temporal_contract=CONTRACT,original_migration_candidates_retained=True,new_temporal_migration_products=0)
        assert count==RESTORED_COUNT
        return result
    migration.check=check;migration.model_boundary=boundary
    try:yield
    finally:migration.check=old_check;migration.model_boundary=old_boundary

def audit():
    from dayahead.v41r2.authority import capacity
    jobs=read(OLD_RUN/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json');cap=capacity()[0]
    assert record(ROOT/'dayahead/v41r1/terminal.py')['sha256']==record(OLD/'dayahead/v41r1/terminal.py')['sha256']
    rows=[];total=0;tests=[]
    for r in jobs:
        opts=restored_options(r,cap)
        if not opts:continue
        total+=len(opts);lo,hi=terminal.start_bounds(reference(r))
        for o in (opts[0],opts[-1]):
            c=dict(r,start_slot=o.start,end_slot=o.end,AIDC_site=o.site,migration_selected=False)
            with activate():migration.check(r,c)
        rows.append(dict(job_id=r['job_uid'],reference_start=r['start_slot'],lower=lo,upper=hi,restored_options=len(opts),duration=r['safe_duration_slots']))
    assert len(rows)==452 and total==RESTORED_COUNT
    # Focused rejection checks keep release/slack and carry-in constraints.
    r=next(r for r in jobs if r['job_uid']==rows[0]['job_id']);ref=reference(r);lo,hi=terminal.start_bounds(ref)
    for t in (lo-1,hi+1):
        try:validate(r,dict(r,start_slot=t,end_slot=t+r['safe_duration_slots'],migration_selected=False))
        except ValueError:tests.append('OUTSIDE_LEGACY_WINDOW_REJECTED')
    assert len(tests)==2
    authority=dict(status='FROZEN',contract=CONTRACT,user_authorization='Latest user correction: Timeshifting must exist; restore it if removed.',historical_time_source=record(ROOT/'dayahead/v41r1/terminal.py'),historical_function='terminal.attach/start_bounds/authorized_options/check, byte-identical retained pre-V4 implementation',base_candidates=BASE_COUNT,restored_temporal_candidates=RESTORED_COUNT,total_candidates=TOTAL_COUNT,eligible_jobs=len(rows),rows=rows,base_candidates_removed=0,migration_candidates_added=0,new_temporal_migration_cartesian_products=0,B0_reference_and_physical_trajectory_changed=False,P1_P5_definitions_changed=False,P5_ranks_recomputed_for_restored_domain=True,old_4772575_hash_role='Immutable migration/spatial subset only; no longer the complete active universe',source=record(__file__))
    write_json(OUT/'V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json',authority)
    value=dict(status='PASS',classification='TIMESHIFTING_RESTORED_FROM_PRE_V4_AUTHORITY',PRE_V41R3_TIMESHIFTING_EXISTED='YES',V41R3_TIMESHIFTING_CHANGED='YES_EXPLICIT_USER_AUTHORIZED_RESTORATION',RESTORATION_REQUIRED='YES',RESTORATION_COMPLETED='YES',TEMPORAL_ELIGIBILITY_UNCHANGED='YES_VERSUS_RESTORED_PRE_V4_SOURCE',TEMPORAL_CONSTRAINTS_UNCHANGED='YES_VERSUS_RESTORED_PRE_V4_SOURCE',TEMPORAL_CANDIDATE_DOMAIN_UNCHANGED='RESTORED_117252_OMITTED_OPTIONS; ORIGINAL_4772575_ALL_RETAINED',P4_TEMPORAL_ACCOUNTING_UNCHANGED='YES',D24_SEMANTICS_UNCHANGED='YES_EXISTING_PRE_V4_TEMPORAL_BOUNDS; V4_MIGRATION_BOUNDARY_RETAINED',ACTUAL_TEMPORAL_SEMANTICS_UNCHANGED='YES',PERSISTENCE_UNCHANGED='YES_ORIGINAL_FIELDS_PRESERVED; TEMPORAL_SUMMARY_ADDED',FOUR_NEW_RANKING_METHODS_CHANGE_SEARCH_ORDER_ONLY='YES',authority=record(OUT/'V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'),focused_window_tests=tests,known_boundary='Restored standalone spatial-temporal choices do not gain new shifted-start checkpoint-migration combinations. Every existing V4 migration option remains available.',earlier_audit=record(OUT/'V41R3_TIMESHIFTING_PRESERVATION_AUDIT.before_user_restore.json'))
    write_json(OUT/'V41R3_TIMESHIFTING_PRESERVATION_AUDIT.json',value)
    return authority
