"""One exact date attempt; physical/solver/data failures terminate only this date."""
from pathlib import Path
import sys,time,threading,traceback,os
from v42_pr134_b1.common import read,atomic,record,now
from v42_common_campaign.authority import singleton
from .authority import scope,verify_request
from .processes import identity,assert_peers

def global_error(error):
    return any(k in str(error) for k in ('SVR11_GLOBAL_','SVR11_MINIMUM_IMPLEMENTATION_PREFLIGHT','SVR11_B3_EPOCH_PERMIT_DRIFT'))

def run(path):
    path=Path(path).resolve();request=read(path);attempt=Path(request['result']).parent;start=time.perf_counter()
    with singleton(attempt/'WORKER.lock'):
        if Path(request['result']).exists():raise PermissionError('SVR11_COMPLETED_ATTEMPT_NEVER_REEXECUTED')
        from v42_may_campaign_native90.common import environment
        environment(attempt);me=identity();stop=threading.Event();mutex=threading.RLock()
        state=dict(phase='ADMISSION',arm=request['arm'],day=request['day'],source_SHA=request['source_SHA'],worker=me,Native_Runtime=0)
        def progress(value):
            with mutex:
                state.update(value,UTC=now(),wall_seconds=time.perf_counter()-start)
                atomic(request['progress'],state)
                atomic(attempt/'HEARTBEAT.json',dict(worker=me,phase=state['phase'],UTC=now(),source_SHA=request['source_SHA']))
        def ticker():
            while not stop.wait(10):progress({})
        thread=threading.Thread(target=ticker,daemon=True);thread.start();progress({})
        result=dict(arm=request['arm'],day=request['day'],identity={k:request[k] for k in ('run_id','arm','day','source_SHA','attempt_id')},
            worker=me,source_SHA=request['source_SHA'],PASS=False,status='FAIL',started_UTC=now(),Native_Runtime=0,
            FULL_feasible_certified=False,global_gap_certified=False,metrics={'environments':{}},request=record(path))
        try:
            with scope(request['manifest']) as manifest:
                verify_request(request);assert_peers(request)
                from .stages import inputs,b1,b3
                progress(dict(phase='FRESH_INPUT_AND_SVR11_MODEL_PREPARATION'));inputs(request,progress)
                if request['arm']=='B0':
                    atomic(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(schema='V42_B0_NATIVE_ZERO_LEDGER_V1',measured_Native_Runtime=0,calls=[],inflight=None,Native_ceiling_seconds=0,source_SHA=manifest['execution_SHA'],UTC=now()))
                    from v42_voltage_control.b0_new import run_day
                    science=run_day(request['day'],request['input_folder'],request['output'],scenario=read(manifest['scenario']['path']),
                        source_SHA=manifest['execution_SHA'],progress=progress,design_receipt=manifest['hardware'])
                elif request['arm']=='B2':
                    from v42_common_campaign.b2 import run as execute
                    from .operations import scope as ops_scope
                    with ops_scope():science=execute(request,manifest,progress)
                else:science=(b1 if request['arm']=='B1' else b3)(request,manifest,progress)
                result.update(science,scientific_status=science.get('status'),status='PASS' if science.get('PASS') is True else 'FAIL')
                if not result['PASS']:result['reason']=science.get('status','DATE_FAILED')
                from .report import metrics
                result['metrics']=metrics(request['output'])
                failures=[]
                for ns,physical in result['metrics']['environments'].items():
                    for key,label in (('voltage_violations','VOLTAGE_VIOLATION'),('line_current_violations','LINE_CURRENT_VIOLATION'),
                        ('transformer_current_violations','TRANSFORMER_CURRENT_VIOLATION'),('transformer_nameplate_current_violations','TRANSFORMER_NAMEPLATE_CURRENT_VIOLATION'),
                        ('transformer_kVA_violations','TRANSFORMER_KVA_VIOLATION')):
                        if physical[key]:failures.append(dict(environment=ns,reason=label,violation_cells=physical[key]))
                    if not physical['AC_converged']:failures.append(dict(environment=ns,reason='AC_NONCONVERGENCE'))
                    if not physical['control_complete']:failures.append(dict(environment=ns,reason='SVR_CONTROL_FAIL'))
                result['physical_failures']=failures
                if failures:result.update(PASS=False,status='FAIL',reason='; '.join(f["environment"]+':'+f['reason'] for f in failures))
                scientific=science.get('scientific',science)
                result['Planning_objective']=scientific.get('verified_UB',scientific.get('UB'))
                result['FULL_feasible_certified']=scientific.get('feasible_accepted',result.get('FULL_feasible_certified',False))
                result['global_gap_certified']=scientific.get('global_gap_certified',result.get('global_gap_certified',False))
                result['certified_LB']=scientific.get('Certified_Global_LB',scientific.get('LB')) if result['global_gap_certified'] else None
                result['certified_Gap']=scientific.get('Certified_Gap',scientific.get('certified_gap')) if result['global_gap_certified'] else None
        except Exception as error:
            result.update(PASS=False,status='FAIL',reason=repr(error),traceback=traceback.format_exc(),source_global_integrity_block=global_error(error))
            result['retryable_pre_native_technical_error']=isinstance(error,OSError) and getattr(error,'winerror',None) in (32,33)
            atomic(attempt/'error.json',result)
            try:
                from .report import metrics
                result['metrics']=metrics(request['output'])
            except Exception as metric_error:result['metrics_error']=repr(metric_error)
        finally:
            # A crash after Native entry is never retried from zero. Retain
            # inflight Runtime uncertainty alongside every completed call.
            ledgers=[]
            for ledger in attempt.rglob('NATIVE_RUNTIME_LEDGER.json'):
                value=read(ledger);ledgers.append(dict(receipt=record(ledger),Native_Runtime=value.get('measured_Native_Runtime',0),inflight=value.get('inflight')))
            result['native_ledgers']=ledgers
            result['Native_Runtime']=sum(l['Native_Runtime'] for l in ledgers)
            result.update(finished_UTC=now(),wall_seconds=time.perf_counter()-start,
                Actual_PQ_repair=0,Actual_reoptimization=0,next_date_blocked_by_FAIL=False)
            atomic(request['result'],result);stop.set();thread.join(timeout=2);progress(dict(phase='TERMINAL',status=result['status']))
        return result

if __name__=='__main__':
    r=run(sys.argv[1]);raise SystemExit(0 if r['PASS'] else 1)
