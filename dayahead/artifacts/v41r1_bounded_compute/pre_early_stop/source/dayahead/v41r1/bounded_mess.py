"""Bound the inherited MESS search with a complete feasible fleet checkpoint.

The AIDC F&O revision leaves MESS route/physics/candidate authority intact.
An unfinished route-search subprocess never holds the only feasible fleet.
"""
from pathlib import Path
from dataclasses import asdict
import os
import subprocess
import sys
import time
import uuid
import psutil
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.preflight import ROOT,record
from .feasible_seed import policy_reference


def validate(jobs,trajectory,context):
    from dayahead.v40g_segments.canonical import planning_power
    from dayahead.v40h.recourse import validate_physics
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    physics=validate_physics(trajectory)
    grid=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,
        planning_power(jobs,context)['pcc'],trajectory.slots),context.nodes)
    if physics['status']!='PASS' or grid['status']!='PASS':raise ValueError('MESS_CHECKPOINT_NOT_FEASIBLE')
    return physics,grid


def run(day,jobs,context,output):
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    policy=context.v41_policy
    neutral,seed=policy_reference(jobs,context,output/'seed',policy)
    physics,grid=validate(jobs,neutral,context)
    write_json(output/'BOUNDED_FLEET_INCUMBENT.json',dict(trajectory_slots=[asdict(r) for r in neutral.slots],
        rho=grid['rho_max'],physics=physics,grid=grid,source='VERIFIED_NEUTRAL_FULL_FLEET',accepted_at=time.time()))
    request=output/'BOUNDED_MESS_INPUT.json'
    # The inherited cache uses deep fingerprint paths. A short, unique physical
    # root avoids Windows MAX_PATH failures without changing any cache identity.
    search_output=Path('D:/MobileESS_FO_M1')/uuid.uuid4().hex[:12]
    search_output.mkdir(parents=True,exist_ok=False)
    write_json(request,dict(day=day,jobs=jobs,ML_snapshot=dict(path=context.v41_ml_snapshot_path,sha256=context.v41_ml_snapshot_sha256),
        source=record(__file__),policy=policy,search_output=str(search_output)))
    budget=context.v41_policy_budget
    allowance=max(0.,min(budget.remaining,min(900.,budget.total*.5) if policy=='B3' else budget.remaining)-5.)
    timed_out=False;code=None
    if allowance>.05:
        with (output/'BOUNDED_MESS_WORKER.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([sys.executable,'-u','-m','dayahead.v41r1.bounded_mess',str(request)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while process.poll() is None and time.perf_counter()-started<allowance:time.sleep(.2)
            if process.poll() is None:
                timed_out=True
                parent=psutil.Process(process.pid);children=parent.children(recursive=True)
                # The worker owns only this policy-day's MESS search pool.
                for p in [parent]+children:
                    try:p.terminate()
                    except psutil.NoSuchProcess:pass
                psutil.wait_procs([parent]+children,timeout=5)
            code=process.wait()
        if not timed_out and code:
            raise RuntimeError('BOUNDED_MESS_WORKER_CRASH:'+str(output/'BOUNDED_MESS_WORKER.log'))
    budget.charge(time.perf_counter()-started,'M1_BOUNDED_INHERITED_SEARCH')
    saved=read(output/'BOUNDED_FLEET_INCUMBENT.json')
    trajectory=MessTrajectory(tuple(_restore_slots(saved['trajectory_slots'])))
    physics,grid=validate(jobs,trajectory,context)
    value=dict(status='PASS',classification='BOUNDED_COMPUTE_FEASIBLE',
        algorithm='INHERITED_MESS_SEARCH_WITH_SHARED_POLICY_DAY_DEADLINE',
        trajectory_slots=saved['trajectory_slots'],planning=grid,global_bound=None,global_gap=None,
        termination='TIME_LIMIT_WITH_VERIFIED_FLEET' if timed_out else 'SEARCH_COMPLETED_OR_NO_REMAINING_BUDGET',
        optimization_seconds=time.perf_counter()-started,policy_day_seconds=budget.used,
        seed_audit=record(output/'seed/POLICY_FEASIBLE_SEED_AUDIT.json'),
        inherited_search_root=str(search_output),external_search_files=[record(p) for p in sorted(search_output.rglob('*')) if p.is_file()],
        fleet_checkpoint=record(output/'BOUNDED_FLEET_INCUMBENT.json'),
        V40A_route_search_campaign_calls=1,scientific_candidate_pruning=0,
        MESS_scientific_semantics='UNCHANGED',physics=physics)
    write_json(output/'M1_RESULT.json',value)
    return trajectory,value


def worker(request):
    from dayahead.v41.electrical import load
    from dayahead.v41.reserve import bind
    from dayahead.v41.execution import run_m1
    from dayahead.v40h import beam_driver as beam
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    data=read(request);output=Path(request).parent;ctx=load(data['day'])
    if data['source']!=record(__file__):raise ValueError('MESS_WORKER_SOURCE_DRIFT')
    bind(ctx,data['ML_snapshot']['path'],data['ML_snapshot']['sha256'])
    original=beam._make_child
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    original_guards=(r3.assert_apr01_only,r3e.assert_apr01_only)
    def selected_day(day):
        if str(day)!=data['day'] or not str(day).startswith('2025-05-'):
            raise ValueError('MESS_OUTSIDE_AUTHORIZED_INDEPENDENT_DAY')
    # Same selected-day adapter used by the inherited authorized May runner.
    r3.assert_apr01_only=r3e.assert_apr01_only=selected_day
    neutral=read(output/'BOUNDED_FLEET_INCUMBENT.json')['trajectory_slots']
    def checkpoint(trajectory,source):
        physics,grid=validate(data['jobs'],trajectory,ctx)
        before=read(output/'BOUNDED_FLEET_INCUMBENT.json')
        if grid['rho_max']<before['rho']-1e-10:
            value=dict(trajectory_slots=[asdict(r) for r in trajectory.slots],rho=grid['rho_max'],
                physics=physics,grid=grid,source=source,accepted_at=time.time())
            path=output/'MESS_ACCEPTED_HISTORY'/f'{time.time_ns()}.json';write_json(path,value)
            with_ledger={**value,'history_artifact':record(path)}
            write_json(output/'BOUNDED_FLEET_INCUMBENT.json',with_ledger)
    def make_child(**kwargs):
        child=original(**kwargs)
        # All processed fleet trajectories are fixed in the original child.
        # Unprocessed vehicles take the independently verified zero/STAY state.
        merged={(r['mess_id'],r['slot']):r for r in neutral}
        merged.update({(r['mess_id'],r['slot']):r for r in child.trajectory_slots})
        full=MessTrajectory(tuple(_restore_slots([merged[k] for k in sorted(merged)])))
        checkpoint(full,'COMPLETED_INHERITED_FULL_CHILD_PLUS_NEUTRAL_REMAINDER')
        return child
    beam._make_child=make_child
    try:
        trajectory,result=run_m1(data['day'],data['jobs'],ctx,Path(data['search_output']))
        checkpoint(trajectory,'COMPLETED_INHERITED_FULL_FLEET_SEARCH')
    finally:
        beam._make_child=original;r3.assert_apr01_only,r3e.assert_apr01_only=original_guards
        ctx.electrical.voltage.close();ctx.electrical.current.close()


if __name__=='__main__':worker(sys.argv[1])
