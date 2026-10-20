"""Observe existing stage calls once; no additional solve, probe or validation."""
from contextlib import contextmanager,ExitStack
from functools import wraps
from pathlib import Path
from unittest.mock import patch
import json,time,os

def ledger_totals(folder):
    result={}
    for name in ['NATIVE_RUNTIME_LEDGER.json','K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json']:
        path=Path(folder)/name
        if path.exists():
            try:
                value=json.loads(path.read_text(encoding='utf8'))
                if 'measured_Native_Runtime' in value:result[name]=value['measured_Native_Runtime']
                elif 'calls' in value:result[name]=sum(r.get('Native_Runtime',0.) or 0. for r in value['calls'])
            except (OSError,ValueError,TypeError):pass
    return result

@contextmanager
def install(case,source_io):
    from v44 import worker
    from v44.svr12 import SVR12CurrentAC
    from v44.common import now
    output=Path(case['case_root'])/'R018_STAGE_COST_PROFILE.jsonl'
    errors=[]
    def emit(row):
        if not output.parent.exists():return
        try:
            with output.open('a',encoding='utf8',newline='\n') as stream:
                stream.write(json.dumps(dict(UTC=now(),pid=os.getpid(),day=case['day'],arm=case['arm'],**row),ensure_ascii=False,allow_nan=False)+'\n')
        except OSError as error:errors.append(repr(error))
    def wrap(function,label):
        @wraps(function)
        def call(*args,**kwargs):
            request=args[0] if args and isinstance(args[0],dict) else {}
            stage=request.get('stage',label);folder=request.get('output',output.parent/stage)
            wall=time.perf_counter();cpu=time.process_time();before=source_io.report();error=None;result=None
            try:
                result=function(*args,**kwargs);return result
            except BaseException as exc:error=repr(exc);raise
            finally:
                after=source_io.report()
                emit(dict(stage=stage,stage_family=label,wall_seconds=time.perf_counter()-wall,
                    CPU_seconds=time.process_time()-cpu,Native_completed_by_ledger=ledger_totals(folder),
                    source_IO_delta={key:after[key]-before[key] for key in ['record_lookups','bytes_hashed','mapped_record_seconds','unknown_path_original_IO_calls']},
                    PASS=result.get('PASS') if isinstance(result,dict) else None,error=error,
                    includes_nested_independent_Fresh=label=='ACTUAL',Native_solve_calls_added=0,physical_probe_calls_added=0))
        return call
    original_fresh=SVR12CurrentAC.full_fresh_probe
    @wraps(original_fresh)
    def fresh(oracle,rows,*args,**kwargs):
        wall=time.perf_counter();cpu=time.process_time();error=None;value=None
        try:value=original_fresh(oracle,rows,*args,**kwargs);return value
        except BaseException as exc:error=repr(exc);raise
        finally:
            emit(dict(stage='FRESH',stage_family='INDEPENDENT_FRESH',wall_seconds=time.perf_counter()-wall,
                CPU_seconds=time.process_time()-cpu,slots=len(rows),PASS=value.get('PASS') if isinstance(value,dict) else None,
                error=error,included_in_parent_ACTUAL_wall=True,Native_solve_calls_added=0,physical_probe_calls_added=0))
    with ExitStack() as stack:
        for name,label in [('reference','REFERENCE'),('a_stage','A'),('m_stage','M'),('actual','ACTUAL')]:
            stack.enter_context(patch.object(worker,name,wrap(getattr(worker,name),label)))
        stack.enter_context(patch.object(SVR12CurrentAC,'full_fresh_probe',fresh))
        try:yield
        finally:
            if errors:emit(dict(stage='PROFILE_IO_WARNING',errors=errors))
