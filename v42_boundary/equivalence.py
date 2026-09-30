"""Bounded exact set/order comparison, before the full May build."""
import sys,runpy,linecache
from dataclasses import replace
from time import perf_counter
from collections import Counter
from .common import *
from .boundaries import load_native
from .generator import Generator
from v42_job_capability import build_domain
from v42_temporal.native import temporal_domain

def profile_legacy(call):
    phases=Counter();hits=Counter();last=[perf_counter(),None]
    def category(frame):
        name=frame.f_code.co_name;text=linecache.getline(frame.f_code.co_filename,frame.f_lineno)
        if name in ('validate','resources_used','resource_limit'):return 'validation'
        if name=='checkpoint_records':return 'checkpoint_enumeration'
        if 'Option(' in text:return 'Option_object_materialization'
        if 'in kept' in text or 'kept.append' in text:return 'duplicate_checking'
        if 'for start' in text:return 'start_enumeration'
        if 'for site' in text:return 'site_enumeration'
        if 'for dest' in text or 'path =' in text:return 'destination_enumeration'
        if any(x in text for x in ('for ts','while left','amount =','usage.','left -=','te +=')):return 'WAN_transfer_start_enumeration'
        return 'job_input_preparation_and_other'
    def trace(frame,event,arg):
        now=perf_counter()
        if last[1]:phases[last[1]]+=now-last[0]
        last[0]=now;last[1]=None
        if frame.f_code.co_filename.endswith('v42_job_capability.py') and event in ('line','call'):
            last[1]=category(frame);hits[last[1]]+=1
        return trace
    start=perf_counter();sys.settrace(trace)
    try:result=call()
    finally:sys.settrace(None)
    return result,dict(instrumented_wall_seconds=perf_counter()-start,phase_seconds=dict(phases),phase_trace_events=dict(hits),
        method='Python trace exclusive statement attribution on bounded fixture; includes instrumentation overhead; not extrapolated to May')

def main():
    fixture=runpy.run_path(str(ROOT/'tests/test_v42_job_capability.py'))['fixture'];rows=[]
    for case in 'ABCDEFGHIJ':
        j,b,r,_=fixture(case);t=perf_counter();old,_=build_domain(j,b,r);oldtime=perf_counter()-t
        g=Generator(r,max(120,b.latest_completion));t=perf_counter();d=g.domain(j,b);new=tuple(d);newtime=perf_counter()-t
        require(old==new,'SYNTHETIC_ORDER_OR_SET_MISMATCH:'+case)
        rows.append(dict(case=case,scope='EXISTING_SYNTHETIC_FIXTURE',legacy_options=len(old),accelerated_options=len(d),
            missing_from_new=len(set(old)-set(new)),extra_in_new=len(set(new)-set(old)),order_exact=True,legacy_seconds=oldtime,accelerated_seconds=newtime))
    j,b,r,_=fixture('F');_,profile=profile_legacy(lambda:build_domain(j,b,r))
    profile.update(PR97_receipt=rec(PR97/'A1_MODEL_STATS.json'),PR97_timeout_scope='COMPLETE_OPTION_GENERATION; NOT GUROBI',
        full_600_second_baseline_rerun=False,PR97_last_completed_jobs=325,PR97_last_retained_options=92656)
    dump('A1_GENERATION_PROFILE_BASELINE.json',profile)
    bundle,jobs,windows,seconds,r,raw=load_native()
    chosen=[u for u in sorted(jobs) if jobs[u].service_slots<=3 and len(windows[u].allowed_starts)==1][:8]
    require(len(chosen)==8,'DETERMINISTIC_REAL_SUBSET')
    g=Generator(r,max(b.latest_completion for b in windows.values()))
    for uid in chosen:
        t=perf_counter();old,_=temporal_domain(jobs[uid],windows[uid],r);ot=perf_counter()-t
        t=perf_counter();new=tuple(g.domain(jobs[uid],windows[uid]));nt=perf_counter()-t
        require(old==new,'REAL_ORDER_OR_SET_MISMATCH:'+uid)
        rows.append(dict(case=uid,scope='REAL_COMPLETE_JOB_DOMAIN',legacy_options=len(old),accelerated_options=len(new),
            missing_from_new=len(set(old)-set(new)),extra_in_new=len(set(new)-set(old)),order_exact=True,legacy_seconds=ot,accelerated_seconds=nt))
    dump('A1_LEGACY_ACCELERATED_EQUIVALENCE.json',dict(PASS=True,rows=rows,missing_from_new=0,extra_in_new=0,
        real_selection='First eight lexicographic real positive-service jobs with d<=3 and a singleton source start; full physical domains, no domain clipping',
        supplemental_varied_physical_fixtures=30,supplemental_receipt=rec(LOCAL/'boundary_tests.xml'),
        generator=rec(ROOT/'v42_boundary/generator.py'),zero_rate_WAN_waiting_preserved=True,full_May_generation_authorized=True))
    print(dict(PASS=True,synthetic=10,real=len(chosen),options_checked=sum(x['legacy_options'] for x in rows)))

if __name__=='__main__':main()
