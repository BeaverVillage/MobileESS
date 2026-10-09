"""Actual Windows sharing repro in an isolated synthetic request, never scientific work."""
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import ctypes,hashlib,json,sys
from ctypes import wintypes
import gurobipy as gp
REPO=Path('D:/MobileESS_v42_autonomous');OUT=Path(__file__).parent;sys.path.insert(0,str(REPO))
from v42_autonomous import recovery as r
def record(path):
    path=Path(path);data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
case=OUT/'windows_share_synthetic_case';case.mkdir(exist_ok=False)
attempt=case/'dates/B2/2025-05-05/attempts/synthetic_io_only'
request=dict(arm='B2',day='2025-05-05',attempt_id='synthetic_io_only',implementation_SHA='b'*64,
    result=str(attempt/'RESULT.json'),output=str(attempt/'output'))
path=attempt/'request.json';r.atomic(path,request)
heartbeat=attempt/'HEARTBEAT.json';r.atomic(heartbeat,dict(timestamp_UTC='2099-01-01T00:00:00+00:00',synthetic_IO_fixture=True))
row=dict(arm='B2',date=request['day'],retry_attempt_id=request['attempt_id'],repair_source_SHA='b'*64,
    retry_request_receipt=r.record(path))
worker=dict(r.identity(),request=str(path));raw_before=heartbeat.read_bytes();before=record(heartbeat)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=(wintypes.HANDLE,);kernel.CloseHandle.restype=wintypes.BOOL
calls=[]
def deny_model(*args,**kwargs):calls.append('model');raise AssertionError('REAL_NATIVE_MODEL_FORBIDDEN')
def deny_optimize(*args,**kwargs):calls.append('optimize');raise AssertionError('REAL_NATIVE_OPTIMIZE_FORBIDDEN')
handle=kernel.CreateFileW(str(heartbeat),0x80000000,0,None,3,0,None)
assert handle!=ctypes.c_void_p(-1).value
fault=None
with patch.object(gp.Model,'__init__',deny_model),patch.object(gp.Model,'optimize',deny_optimize):
    try:
        try:r._read_worker_heartbeat(case,worker,row,request,heartbeat)
        except r.HeartbeatObservationDeferred as error:
            fault=dict(error.observation);assert isinstance(error.__cause__,PermissionError)
        else:raise AssertionError('ACTUAL_EXCLUSIVE_SHARE_MUST_DENY_READ')
    finally:assert kernel.CloseHandle(handle)
    parsed,raw=r._read_worker_heartbeat(case,worker,row,request,heartbeat)
assert fault is not None and fault['errno']==13 and raw==raw_before and record(heartbeat)==before
assert parsed['synthetic_IO_fixture'] is True and not calls
doc=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_ACTUAL_WINDOWS_HEARTBEAT_SHARE_DENIAL_AND_CLEAN_READ_NATIVE0_PROOF',
    scope='Isolated synthetic operational I/O fixture; not a scientifically admitted request or production day evidence',
    actual_Win32_CreateFileW_share_mode_zero_denied_Path_read_bytes=True,actual_deferred_error=fault,
    handle_closed_before_clean_read=True,actual_clean_read_identical_bytes_and_JSON=True,
    expected_owned_heartbeat_before=before,owned_request=record(path),control_source_files=[record(REPO/'v42_autonomous/recovery.py'),record(REPO/'v42_autonomous/supervisor.py')],
    Native_optimize_calls=0,real_Native_model_constructions=0,denied_entry_attempts=calls,
    budget_ledgers_or_results_created=False,production_immutable_queue_manifest_changes=0,process_actions=0,
    historical_atomic_replace_race_cause_is_plausible_not_proven=True,
    historical_saved_error_scope='The original saved failure only preserves PermissionError13, without a serialized winerror. This reproduction proves a Windows sharing failure follows the scoped defer path; it does not prove the exact historical cause.',
    source_script=record(__file__))
target=OUT/'ACTUAL_WINDOWS_HEARTBEAT_SHARE_NATIVE_ZERO_PROOF.json'
with target.open('x',encoding='utf-8') as stream:json.dump(doc,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(PASS=True,receipt=record(target),error=fault),ensure_ascii=False))
