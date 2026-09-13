"""Read-only production observer; independent timed incumbent receipts.

Never imports the optimizer, changes its process, writes its status, or restarts it.
Windows reads allow FILE_SHARE_DELETE so monitoring cannot block atomic replacement.
"""
import os,json,time,hashlib,threading,ctypes,msvcrt,sys,io
from pathlib import Path
from ctypes import wintypes
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import numpy as np
import psutil
HERE=Path(__file__).absolute().parent
P=HERE.parent
sys.path.insert(0,str(P))
from monitor import HTML
K=ctypes.WinDLL('kernel32',use_last_error=True)
K.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
K.CreateFileW.restype=wintypes.HANDLE
INVALID=ctypes.c_void_p(-1).value
def shared_bytes(path):
    h=K.CreateFileW(str(path),0x80000000,7,None,3,0x80,None)
    if h==INVALID:raise ctypes.WinError(ctypes.get_last_error())
    fd=msvcrt.open_osfhandle(h,os.O_RDONLY|os.O_BINARY)
    with os.fdopen(fd,'rb') as f:return f.read()
def read(path):return json.loads(shared_bytes(path))
def digest(b):return hashlib.sha256(b).hexdigest()
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    body=json.dumps(data,indent=2,ensure_ascii=False).encode('utf-8')
    temp=path.with_suffix(path.suffix+'.tmp')
    for retry in range(20):
        try:temp.write_bytes(body);os.replace(temp,path);return
        except PermissionError:time.sleep(.1)
    raise RuntimeError('TELEMETRY_OUTPUT_WRITE_FAILED '+str(path))
def ref(path,body=None):
    if body is None:body=shared_bytes(path)
    return dict(path=str(path),sha256=digest(body),bytes=len(body))
def seed(role):
    folder=P/role
    audit=read(folder/'POLICY_FEASIBLE_SEED_AUDIT.json')
    assert audit['status']=='PASS'
    f=folder/'bounded_checkpoints/0_0_SEED.npz';body=shared_bytes(f)
    return dict(checkpoint=ref(f,body),P1=audit['seed_objective_vector'][0],objective_vector=audit['seed_objective_vector'],iteration=0,validation=ref(folder/'POLICY_FEASIBLE_SEED_AUDIT.json'),validation_basis='Approved exact B0 seed for B1; original fixed-MESS seed audit for A1'),body
def incumbent(role):
    folder=P/role/'bounded_checkpoints'
    proofs=sorted(folder.glob('ITERATION_*.json'),key=lambda p:int(p.stem.split('_')[1]),reverse=True)
    for f in proofs:
        try:
            proof=read(f);a=proof['artifact'];body=shared_bytes(a['path'])
            assert digest(body)==a['sha256']
            with np.load(io.BytesIO(body),allow_pickle=False) as z:assert np.all(np.isfinite(z['values']))
            return dict(checkpoint=a,P1=proof['incumbent_after'][0],objective_vector=proof['incumbent_after'],iteration=proof['iteration'],validation=ref(f),validation_basis='Original accepted/retained incumbent after original model and exact AC validator'),body
        except (OSError,ValueError,KeyError,AssertionError):continue
    return seed(role)
CACHE={};LOCK=threading.Lock();SEEN={};ERRORS=[]
def collect():
    s=read(P/'STATUS.json');now=time.time();worker=int(s['pid'])
    alive=psutil.pid_exists(worker)
    s.update(worker_alive=alive,monitor_observed_unix=now,telemetry_recovery='Independent observer; production code and search unchanged')
    if not alive:s['search_stopped']=True
    role='B3_A1' if s.get('stage','').startswith('B3_A1:') else 'B1' if s.get('stage','').startswith('B1:') else None
    if role and (P/role/'F_AND_O_LIVE.json').exists():
        live=read(P/role/'F_AND_O_LIVE.json');s['original_search_live']=live
        start=live.get('search_loop_started_at_unix')
        if start:
            elapsed=min(14400,max(0,now-start));s['search_started_unix']=start;s['search_elapsed_seconds']=elapsed
            if not alive:s['status']='WORKER_EXITED' if s['status']=='RUNNING' else s['status']
            receipts=SEEN.setdefault(role,{})
            for seconds,label in [(1800,'30min'),(3600,'1h'),(7200,'2h'),(14400,'4h')]:
                path=HERE/role/'timed_checkpoints'/f'{label}.json'
                if path.exists():receipts[label]=read(path);continue
                if elapsed<seconds or not alive:continue
                r,body=incumbent(role)
                snapshot=path.with_suffix('.npz');snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(body)
                r.update(target_seconds=seconds,observed_seconds=now-start,recorded_unix=now,policy=role,continuous_search_origin_unix=start,snapshot=ref(snapshot,body),recorder='INDEPENDENT_SHARED_READ_OBSERVER',source_optimization_unchanged=True)
                save(path,r);receipts[label]=r
            s['checkpoints']=receipts
    for role in ['B1','B3_A1']:
        f=P/role/'SCALABILITY_METRICS.json'
        out=HERE/role/'SCALABILITY_METRICS_TIMED_RECEIPTS.json'
        receipts=SEEN.get(role,{})
        if f.exists() and len(receipts)==4 and not out.exists():
            original=read(f)
            original.update(P1_checkpoints={k:v['P1'] for k,v in receipts.items()},raw_original_metrics=ref(f),timing_authority='Independent on-time receipt files; raw original metrics preserved',timed_receipts={k:ref(HERE/role/'timed_checkpoints'/f'{k}.json') for k in receipts})
            save(out,original)
    s['independent_timed_receipts']={k:{n:r['P1'] for n,r in v.items()} for k,v in SEEN.items()}
    s['telemetry_errors']=ERRORS[-3:]
    with LOCK:CACHE.clear();CACHE.update(s)
def loop():
    while True:
        try:collect()
        except Exception as e:ERRORS.append(dict(at=time.time(),error=repr(e)))
        time.sleep(.5)
HTML=HTML.replace('status.textContent','document.getElementById("status").textContent')
HTML=HTML.replace("(p==='B0'&&s.B0?'PASS':'Pending')","(p==='B0'&&s.B0?'PASS':s.stage?.startsWith(p+':')&&s.worker_alive?'RUNNING':'Pending')")
HTML=HTML.replace("s.policy_results?.[p]?.P1??(p==='B0'?s.B0?.max_phase_line_loading_pu:'')","s.policy_results?.[p]?.P1??(s.stage?.startsWith(p+':')?s.P1:p==='B0'?s.B0?.max_phase_line_loading_pu:'')")
HTML=HTML.replace('Only independently validated feasible incumbents are retained.','Only independently validated feasible incumbents are retained. Timed checkpoint receipts are recorded by an independent read-only observer; optimizer code remains frozen.')
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with LOCK:body=json.dumps(CACHE,ensure_ascii=False).encode('utf-8') if self.path=='/api/status' else HTML.encode('utf-8')
        self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/api/status' else 'text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*a):pass
if __name__=='__main__':
    collect();threading.Thread(target=loop,daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1',8510),Handler).serve_forever()
