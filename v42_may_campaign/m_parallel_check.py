"""Three-process Native-zero M construction/isolation audit, never a solver.

Each spawned process owns an Env and keeps the unchanged original FULL model
alive until all current-day case proofs have finished.  Successful local Env
starts empirically admit three licensed sessions. Actual simultaneous optimize
execution, outcomes and performance remain unobserved in this Native-zero audit.
"""
from contextlib import contextmanager
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from unittest.mock import patch
import os
import sys
import time
import traceback
import psutil
from .common import ROOT,atomic,read,record,sha,d_path,environment,process,now

DATES=('2025-05-01','2025-05-02','2025-05-03')
OFFICIAL_SOURCES={
    'process_environment': 'https://support.gurobi.com/hc/en-us/articles/360043111231-How-do-I-use-multiprocessing-in-Python-with-Gurobi',
    'environment_license_session': 'https://docs.gurobi.com/projects/optimizer/en/current/concepts/environments/session.html',
    'model_copy': 'https://docs.gurobi.com/projects/optimizer/en/current/reference/python/model.html#Model.copy',
}


@contextmanager
def resident_models(gp,env):
    """Route constructors to this Env; delay only the captured copy's dispose."""
    original_model=gp.Model; original_copy=original_model.copy; original_dispose=original_model.dispose
    held=[]
    class OwnEnvModel(original_model):
        def __init__(self,*args,**kwargs):
            supplied=kwargs.pop('env',env)
            if supplied is not env:raise ValueError('PARALLEL_AUDIT_CROSS_ENV_MODEL')
            super().__init__(*args,env=env,**kwargs)
    def copy(model,*args,**kwargs):
        result=original_copy(model,*args,**kwargs)
        held.append(result)
        return result
    def dispose(model):
        # An original model's __del__ can re-enter dispose after its native
        # object is freed. Python identity avoids any Gurobi attribute lookup.
        if any(model is resident for resident in held):return
        original_dispose(model)
    try:
        with patch.object(original_model,'copy',copy),patch.object(original_model,'dispose',dispose),patch.object(gp,'Model',OwnEnvModel):
            yield held
    finally:
        for model in held:original_dispose(model)


def _child(root,day,folder,begin,release,messages):
    folder=d_path(folder);environment(folder);folder.mkdir(parents=True,exist_ok=True)
    os.chdir(folder)
    started=time.perf_counter();identity=process();stage='GUROBI_ENV_START'
    def emit(kind,**values):messages.put(dict(kind=kind,day=day,process=identity,UTC=now(),**values))
    try:
        import gurobipy as gp
        from .preflight import native_zero
        from .m_stage import prepare,verify_case
        from .m_model import _domain_sha
        from v42_m1_hybrid.blocks import matrix_sha
        from v42_integrated.matrix import arrays
        own_input=Path(root)/'inputs/B2'/day
        input_before={name:record(own_input/name) for name in
            ('NATIVE_INPUT.json','PLANNING_INPUT_BUNDLE.json','B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz')}
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag',0);env.setParam('LogFile',str(folder/'GUROBI_ENV.log'))
            env.setParam('Threads',1);env.start()
            emit('ENV_READY',gurobi_version=list(gp.gurobi.version()),environment_start_PASS=True)
            begin.wait()
            stage='CURRENT_DAY_M_PREPARE'
            opendss_receipts=[]
            from .operations import isolated_compile
            import v42_regcontrol.authority as authority
            authority.source()  # Verify the frozen source and install its import root.
            import dayahead.run_planning_ac_voltage_forensic_v1 as planning_engine
            original_compile=authority.compile_verified
            def compile_own():return isolated_compile(original_compile,folder,opendss_receipts)
            original_planning_compile=planning_engine._compile
            def planning_compile_own(*args,**kwargs):
                def compile_original():
                    engine,adapter=original_planning_compile(*args,**kwargs)
                    return engine,adapter,authority.source()['inventory'](engine)
                engine,adapter,_=isolated_compile(compile_original,folder/'OPENDSS_PLANNING',opendss_receipts)
                return engine,adapter
            def progress(value):
                atomic(folder/'PROGRESS.json',dict(value,process=identity,UTC=now()))
                emit('PROGRESS',phase=value.get('phase'))
            request=dict(root=str(root),arm='B2',day=day,input_folder=str(own_input),output=str(folder/'output'))
            with native_zero() as attempts,resident_models(gp,env) as held,patch.object(authority,'compile_verified',compile_own),patch.object(planning_engine,'_compile',planning_compile_own):
                state=prepare(request,progress);proof=verify_case(state)
                if attempts or not proof.get('PASS') or len(held)!=1:raise ValueError('PARALLEL_NATIVE_ZERO_CASE_NOT_PROVEN')
                full=held[0];A,d=arrays(full)
                if matrix_sha(A)!=state.identity['original_matrix_sha'] or _domain_sha(d)!=state.identity['original_domain_sha']:
                    raise ValueError('PARALLEL_RESIDENT_NATIVE_FULL_MODEL_BYTES_DRIFT')
                if full.Params.Threads!=1:raise ValueError('PARALLEL_MODEL_THREADS_ONE_REQUIRED')
                del A,d
                if any(sha(row['path'])!=row['sha256'] for row in input_before.values()):
                    raise ValueError('PARALLEL_ORIGINAL_INPUT_FILES_CHANGED')
                if len(opendss_receipts)!=2 or len({r['data_path'] for r in opendss_receipts})!=2:
                    raise ValueError('PARALLEL_ORIGINAL_ACTUAL_PLANNING_DSS_CONTEXT_ISOLATION')
                receipt=dict(PASS=True,day=day,arm='B2',process=identity,output=str(folder/'output'),
                    temporary_directory=os.environ['TEMP'],working_directory=str(folder),
                    environment_start_PASS=True,native_FULL_model_resident=True,
                    native_FULL_rows=full.NumConstrs,native_FULL_columns=full.NumVars,
                    native_FULL_Threads=int(full.Params.Threads),
                    resident_model_and_current_original_case_SHA_match=True,
                    case_sha=state.case_sha,case_proof=proof,input_files=input_before,
                    route_table=state.bundle['route_table'],electrical_certificate=state.bundle['electrical_certificate'],
                    opendss_contexts=opendss_receipts,
                    stationary_candidate_PASS=bool(state.point is not None),
                    Native_optimize_calls=0,Native_presolve_calls=0,denied_native_attempts=attempts,
                    simultaneous_optimization_license_status='NOT_TESTED_NATIVE_ZERO_REQUIRED',
                    construction_seconds=time.perf_counter()-started,UTC=now())
                atomic(folder/'PARALLEL_CHILD_RECEIPT.json',receipt);emit('MODEL_READY',receipt=record(folder/'PARALLEL_CHILD_RECEIPT.json'))
                release.wait()
            stage='ENV_DISPOSE'
        emit('DONE',PASS=True,elapsed_seconds=time.perf_counter()-started)
    except BaseException as error:
        receipt=dict(PASS=False,day=day,process=identity,stage=stage,error_type=type(error).__name__,
            error=str(error),traceback=traceback.format_exc(),Native_optimize_calls=0,Native_presolve_calls=0,UTC=now())
        atomic(folder/'PARALLEL_CHILD_ERROR.json',receipt)
        emit('FAILED',error_type=type(error).__name__,error_packet=record(folder/'PARALLEL_CHILD_ERROR.json'))
        raise


def verify_isolation(receipts,snapshot):
    if len(receipts)!=3 or {r['day'] for r in receipts}!=set(DATES):raise ValueError('THREE_DISTINCT_CURRENT_DATES_REQUIRED')
    for key in ('output','temporary_directory','working_directory','case_sha'):
        if len({r[key] for r in receipts})!=3:raise ValueError('PARALLEL_SHARED_'+key.upper())
    pids={r['process']['PID'] for r in receipts}
    if len(pids)!=3 or {r['pid'] for r in snapshot}!=pids or not all(r['alive'] for r in snapshot):
        raise ValueError('THREE_SIMULTANEOUS_RESIDENT_PROCESSES_REQUIRED')
    for r in receipts:
        if (not r['PASS'] or not r['native_FULL_model_resident'] or not r['environment_start_PASS']
            or not r['resident_model_and_current_original_case_SHA_match'] or not r['case_proof']['PASS']
            or r['native_FULL_Threads']!=1
            or r['Native_optimize_calls'] or r['Native_presolve_calls'] or r['denied_native_attempts']):
            raise ValueError('PARALLEL_NATIVE_ZERO_PROOF_REQUIRED')
        observed=next(s for s in snapshot if s['pid']==r['process']['PID'])
        if observed.get('creation_time')!=r['process'].get('created'):
            raise ValueError('PARALLEL_PROCESS_CREATION_IDENTITY_DRIFT')
        contexts=r['opendss_contexts'];own=d_path(r['working_directory'])
        if len(contexts)!=2 or any(c['PID']!=r['process']['PID']
            or not d_path(c['data_path']).is_relative_to(own)
            or c['scientific_control_settings_changed'] for c in contexts):
            raise ValueError('PARALLEL_OPENDSS_PROCESS_AND_DATA_PATH_ISOLATION')
    return dict(PASS=True,processes=3,distinct_dates=True,distinct_PIDs=True,distinct_case_SHA=True,
        distinct_output_tmp_cwd=True,three_Env_and_FULL_models_simultaneously_resident=True,
        scientific_algorithms_changed=False,Native_optimize_calls=0,Native_presolve_calls=0,
        simultaneous_optimization_license_status='NOT_TESTED_NATIVE_ZERO_REQUIRED')


def audit(root):
    root=d_path(root);base=root/'parallel_preflight';base.mkdir(parents=True,exist_ok=True)
    run=base/datetime.now().strftime('%Y%m%dT%H%M%S_%f');run.mkdir()
    source_at_start={name:record(ROOT/name) for name in ('v42_may_campaign/m_parallel_check.py',
        'v42_may_campaign/m_stage.py','v42_may_campaign/m_model.py','v42_may_campaign/inputs.py',
        'v42_may_campaign/operations.py')}
    ctx=get_context('spawn');begin=ctx.Event();release=ctx.Event();messages=ctx.Queue()
    children=[ctx.Process(target=_child,args=(str(root),day,str(run/day),begin,release,messages),name='Native0_M_'+day) for day in DATES]
    before=psutil.virtual_memory();started=time.perf_counter();samples=[];env_ready=set();ready={};done=set();errors=[]
    for child in children:child.start()
    try:
        while len(done)<3:
            try:message=messages.get(timeout=1.)
            except Empty:message=None
            observed=[]
            for child in children:
                try:
                    p=psutil.Process(child.pid);memory=p.memory_info()
                    observed.append(dict(pid=p.pid,alive=p.is_running(),RSS_bytes=memory.rss,
                        creation_time=p.create_time(),CPU_seconds=sum(p.cpu_times()[:2])))
                except psutil.Error:observed.append(dict(pid=child.pid,alive=False,RSS_bytes=0))
            system=psutil.virtual_memory()
            samples.append(dict(elapsed_seconds=time.perf_counter()-started,available_RAM_bytes=system.available,
                used_RAM_bytes=system.used,processes=observed,total_child_RSS_bytes=sum(p['RSS_bytes'] for p in observed)))
            if message:
                kind=message['kind'];day=message['day']
                if kind=='ENV_READY':env_ready.add(day)
                elif kind=='MODEL_READY':ready[day]=message['receipt']
                elif kind=='FAILED':errors.append(message);release.set();begin.set()
                elif kind=='DONE':done.add(day)
                if kind!='PROGRESS':print('PARALLEL_M_NATIVE0',day,kind,flush=True)
            if len(env_ready)==3:begin.set()
            if len(ready)==3 and not release.is_set():
                receipts=[read(ready[day]['path']) for day in DATES]
                try:
                    verification=verify_isolation(receipts,observed);resident_snapshot=samples[-1]
                except Exception as error:
                    errors.append(dict(error_type=type(error).__name__,error=str(error)))
                release.set()
            for child in children:
                if child.exitcode is not None and child.exitcode!=0 and child.name.split('Native0_M_',1)[1] not in done:
                    day=child.name.split('Native0_M_',1)[1];done.add(day);errors.append(dict(day=day,exitcode=child.exitcode));begin.set();release.set()
        for child in children:child.join()
    finally:
        begin.set();release.set()
    source_unchanged=all(sha(row['path'])==row['sha256'] for row in source_at_start.values())
    result=dict(PASS=not errors and len(ready)==3 and source_unchanged,
        status='PASS_NATIVE0_ENV_FULL_MODEL_ISOLATION' if not errors and len(ready)==3 and source_unchanged else 'FAIL',
        run_directory=str(run),dates=list(DATES),Native_optimize_calls=0,Native_presolve_calls=0,
        environment_admission='PASS' if len(env_ready)==3 else 'FAIL',actual_three_optimization_license='NOT_TESTED_NATIVE_ZERO_REQUIRED',
        actual_concurrent_optimization_performance='NOT_TESTED_NATIVE_ZERO_REQUIRED',
        total_RAM_bytes=before.total,available_RAM_before_bytes=before.available,
        minimum_available_RAM_bytes=min(s['available_RAM_bytes'] for s in samples),
        peak_total_child_RSS_bytes=max(s['total_child_RSS_bytes'] for s in samples),
        resource_limits_applied=False,CPU_throttle_applied=False,scientific_workers_artificially_delayed=False,
        start_and_ready_barriers='AUDIT_SYNCHRONIZATION_ONLY',
        source_unchanged=source_unchanged,sources=source_at_start,official_sources=OFFICIAL_SOURCES,
        ready_receipts=ready,exitcodes={child.name:child.exitcode for child in children},errors=errors,
        model_resident_overlap=locals().get('resident_snapshot'),isolation=locals().get('verification'),
        elapsed_seconds=time.perf_counter()-started,UTC=now())
    atomic(run/'RESOURCE_SAMPLES.json',samples);result['resource_samples']=record(run/'RESOURCE_SAMPLES.json')
    target=root/'B2_PARALLEL_PROCESS_ISOLATION_AUDIT.json'
    if target.exists():
        previous=read(target)
        atomic(d_path(previous['run_directory'])/'B2_PARALLEL_PROCESS_ISOLATION_AUDIT.json',previous)
    atomic(run/'B2_PARALLEL_PROCESS_ISOLATION_AUDIT.json',result)
    atomic(target,result)
    print('B2 PARALLEL PROCESS ISOLATION',result['PASS'],flush=True)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    args=parser.parse_args();raise SystemExit(0 if audit(args.root)['PASS'] else 1)
