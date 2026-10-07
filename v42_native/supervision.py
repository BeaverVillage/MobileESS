"""External stage wall clock, Windows kill-on-close process tree, sealed incumbent.

Only the child writes validated incumbents. Output publication uses immutable
sequence files followed by atomic pointer replacement. Parent never trusts a
partial JSON file or a result written for another request/code/validator.
"""
from pathlib import Path
from time import monotonic,sleep
import ctypes,json,os,subprocess,sys,uuid,importlib
from .contracts import require,digest,file_sha,write_once

STAGE_SECONDS=dict.fromkeys(('A1','M1','A2','M2'),600.)

class ProcessTree:
    def __init__(self,process):
        self.process=process;self.handle=None
        if os.name!='nt':return
        from ctypes import wintypes as w
        class BASIC(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),('LimitFlags',w.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',w.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',w.DWORD),('SchedulingClass',w.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(n,ctypes.c_uint64) for n in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
        class EXTENDED(ctypes.Structure):
            _fields_=[('BasicLimitInformation',BASIC),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE
        k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];k.SetInformationJobObject.restype=w.BOOL
        k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.AssignProcessToJobObject.restype=w.BOOL
        k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
        self.kernel=k;h=k.CreateJobObjectW(None,None);require(h,'CREATE_JOB_OBJECT_FAILED');self.handle=h
        info=EXTENDED();info.BasicLimitInformation.LimitFlags=0x2000 # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(h,9,ctypes.byref(info),ctypes.sizeof(info)) or not k.AssignProcessToJobObject(h,w.HANDLE(int(process._handle))):
            self.close();process.kill();raise OSError(ctypes.get_last_error(),'HARD_WALL_PROCESS_TREE_UNAVAILABLE')
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
        elif os.name!='nt' and self.process.poll() is None:
            import signal
            os.killpg(self.process.pid,signal.SIGKILL)

def atomic(path,value):
    p=Path(path);temporary=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf8') as f:
        json.dump(value,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temporary,p)

class StageContext:
    def __init__(self,request,folder,validator):
        self.request=request;self.folder=Path(folder);self.validator=validator;self.sequence=0
    @property
    def remaining(self):return max(0.,self.request['deadline_monotonic']-monotonic())
    def check(self,estimated_atomic_seconds=0.):
        require(estimated_atomic_seconds>=0,'NEGATIVE_ATOMIC_ESTIMATE')
        if self.remaining<=estimated_atomic_seconds:raise TimeoutError('INSUFFICIENT_STAGE_BUDGET')
    def progress(self,value):
        """Atomic diagnostic journal; never an accepted physical incumbent."""
        from math import isfinite
        def clean(x):
            if isinstance(x,float) and (not isfinite(x) or abs(x)>=1e99):return None
            if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
            if isinstance(x,(tuple,list)):return [clean(v) for v in x]
            return x
        # Keep latest raw incumbent separately when a later node-only update
        # carries bounds but no solution. Both remain explicitly unvalidated.
        payload=dict(clean(value),request_sha256=digest(self.request),scientific_acceptance=False)
        atomic(self.folder/'solver_progress.json',payload)
        if 'raw_incumbent_values' in value:atomic(self.folder/'raw_incumbent_diagnostic.json',payload)
    def publish(self,candidate):
        self.check();cert=self.validator(candidate,self.request['payload']);self.check()
        require(cert.get('PASS') is True,'INDEPENDENT_INCUMBENT_VALIDATION_FAILED')
        self.sequence+=1;name=f'incumbent_{self.sequence:06}.json'
        value=dict(request_sha256=digest(self.request),candidate=candidate,certificate=cert,published_monotonic=monotonic())
        write_once(self.folder/name,value);self.check()
        atomic(self.folder/'incumbent_pointer.json',dict(path=name,sha256=file_sha(self.folder/name),request_sha256=digest(self.request)))
        self.check()

def resolve(name):
    module,attribute=name.split(':');return getattr(importlib.import_module(module),attribute)

def supervise(stage,worker,validator,payload,folder,seconds=600.):
    from v42_a_stage_domain_v2.execution import require_action_authorized
    require_action_authorized(payload,stage,require_day=False)
    require(stage in STAGE_SECONDS and 0<seconds<=STAGE_SECONDS[stage],'STAGE_HARD_BUDGET')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);start=monotonic()
    # Source import/hash setup is charged too. worker/validator are trusted repo entrypoints.
    # Never import arbitrary worker code in the supervising process: even an
    # import can block. Worker source must be in the canonical local namespace.
    sources={}
    for name in (worker,validator):
        module,attribute=name.split(':');require(module.startswith('v42_native.') and all(p.isidentifier() for p in module.split('.')) and attribute.isidentifier(),'STAGE_ENTRYPOINT')
        source=Path(__file__).resolve().parents[1].joinpath(*module.split('.')).with_suffix('.py')
        require(source.is_file(),'STAGE_SOURCE_MISSING');sources[name]=file_sha(source)
    request=dict(stage=stage,worker=worker,validator=validator,sources=sources,payload=payload,
                 started_monotonic=start,deadline_monotonic=start+seconds,budget_seconds=seconds)
    write_once(folder/'request.json',request)
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
    reason='COMPLETED';process=None;tree=None
    with (folder/'worker.log').open('x',encoding='utf8') as log:
        try:
            process=subprocess.Popen([sys.executable,'-B','-m','v42_native.stage_worker',str(folder)],stdout=log,stderr=subprocess.STDOUT,**kwargs)
            tree=ProcessTree(process)
            # Worker cannot enter an expensive task before tree supervision is active.
            write_once(folder/'start.json',dict(authorized=True))
            remaining=max(0.,start+seconds-monotonic())
            try:process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:reason='EXTERNAL_HARD_WALL_TIMEOUT';tree.close();process.wait(timeout=10)
            if reason=='COMPLETED' and process.returncode!=0:reason='WORKER_FAILURE'
        finally:
            if tree is not None:tree.close()
    execution_end=monotonic();candidate=None;pointer=folder/'incumbent_pointer.json'
    if pointer.exists():
        ref=json.loads(pointer.read_text());p=folder/ref['path'];require(p.resolve().parent==folder.resolve(),'INCUMBENT_PATH_ESCAPE')
        require(ref['request_sha256']==digest(request) and file_sha(p)==ref['sha256'],'INCUMBENT_SEAL')
        record=json.loads(p.read_text());require(record['request_sha256']==digest(request) and record['certificate']['PASS'],'INCUMBENT_CERTIFICATE')
        require(record['published_monotonic']<=request['deadline_monotonic'],'LATE_INCUMBENT')
        candidate=record['candidate']
    receipt=dict(stage=stage,budget_seconds=seconds,total_wall_seconds=execution_end-start,
                 cleanup_overhead_seconds=max(0.,execution_end-(start+seconds)) if reason=='EXTERNAL_HARD_WALL_TIMEOUT' else 0.,
                 timeout_reason=reason,validated_incumbent_exists=candidate is not None,
                 status='INCUMBENT_RETAINED' if candidate is not None else 'FAIL_CLOSED_NO_VALIDATED_INCUMBENT',
                 exit_code=process.returncode if process else None,request_sha256=digest(request),external_process_tree=True)
    write_once(folder/'stage_receipt.json',receipt)
    return candidate,receipt
