"""Local read-only dashboard. No optimizer imports, writes, or process control."""
import argparse,ctypes,json,msvcrt,os,threading,time,mimetypes,hashlib
from ctypes import wintypes
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import psutil
HOME=Path(__file__).absolute().parent
RUN=HOME.parent/'IEEE8500_B3_production_20260912'
OLD_B1=HOME.parent/'IEEE8500_v41r4_production_20260911_r2/B1'
K=ctypes.WinDLL('kernel32',use_last_error=True)
K.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
K.CreateFileW.restype=wintypes.HANDLE
def shared_bytes(path):
    h=K.CreateFileW(str(path),0x80000000,7,None,3,0x80,None)
    if h==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    with os.fdopen(msvcrt.open_osfhandle(h,os.O_RDONLY|os.O_BINARY),'rb') as f:return f.read()
READ_CACHE={}
def read(path,default=None):
    path=Path(path)
    if not any(path.absolute().is_relative_to(root) for root in (RUN,OLD_B1)):raise ValueError('READ_OUTSIDE_RUN')
    try:
        st=path.stat();stamp=(st.st_mtime_ns,st.st_size);key=str(path)
        if key not in READ_CACHE or READ_CACHE[key][0]!=stamp:READ_CACHE[key]=(stamp,json.loads(shared_bytes(path)))
        return READ_CACHE[key][1]
    except (OSError,ValueError):return default
def role_for(stage):
    for role in ('B3_A1','B3_M1','B3_MF','B2','B1','B0'):
        if stage.startswith(role):return role
    return None
def view():
    s=read(RUN/'STATUS.json',{});stage=s.get('stage','');role=role_for(stage);now=time.time()
    proc=None
    try:
        p=psutil.Process(int(s.get('pid',0)))
        if 'campaign.py' in ' '.join(p.cmdline()):proc=dict(pid=p.pid,rss=p.memory_info().rss,cpu_seconds=sum(p.cpu_times()[:2]))
    except (psutil.Error,ValueError):pass
    base=read(RUN/'B0/FINAL.json',{})
    seed_vector=read(RUN/'B1/POLICY_FEASIBLE_SEED_AUDIT.json',{}).get('seed_objective_vector',[])
    b0=seed_vector[0] if seed_vector else None
    policies={}
    for r in ('B0','B1','B2','B3_M1','B3_A1','B3'):
        policies[r]=read(RUN/r/('FINAL.json' if r=='B0' else 'FINAL_AUTHORITY.json'),{})
    series={};checkpoints={};lives={};exact={};seeds={}
    for r in ('B1','B3_A1'):
        folder=OLD_B1 if r=='B1' else RUN/r
        live=read(folder/'F_AND_O_LIVE.json',{});lives[r]=live
        seed=read(RUN/r/'POLICY_FEASIBLE_SEED_AUDIT.json',{}).get('seed_objective_vector',[]);seeds[r]=seed
        origin=live.get('search_loop_started_at_unix');points=[]
        if seed:points.append(dict(seconds=0,P1=seed[0],iteration=0))
        accepted=[x for x in read(folder/'IMPROVEMENT_TRACE.json',[]) if x.get('accepted')]
        for row in accepted:
            try:sec=max(0,Path(row['artifact']['path']).stat().st_mtime-origin) if origin else 0
            except OSError:continue
            points.append(dict(seconds=sec,P1=row['incumbent_after'][0],iteration=row['iteration']))
        series[r]=points
        checkpoints[r]={label:read(folder/'timed_checkpoints'/f'{label}.json') for label in ('30min','1h','2h','4h')}
        if accepted:
            n=accepted[-1]['iteration'];proof=read(folder/'bounded_checkpoints'/f'ITERATION_{n}.json',{})
            ref=proof.get('semantic_validation',{}).get('exact_IEEE8500_AC',{})
            if ref:
                ac=read(Path(ref['path']),{})
                exact[r]=dict(status=ac.get('status'),metrics=ac.get('metrics'),iteration=n,model_P1=accepted[-1]['incumbent_after'][0])
        if policies[r].get('status')=='PASS':exact[r]=dict(status='PASS',metrics=policies[r].get('AC'),iteration='final',model_P1=policies[r].get('P1'))
    for r in ('B0','B2','B3_M1','B3'):
        p=policies[r]
        if p.get('status')=='PASS':exact[r]=dict(status='PASS',metrics=p.get('AC',p.get('metrics')),iteration='final',model_P1=p.get('P1'))
    final=policies.get(role,{}) if role else {}
    # A MESS stage must never inherit a stale B1 objective from shared status.
    live=lives.get(role,{})
    vector=live.get('incumbent',seeds.get(role,[])) if role in lives else []
    if role in lives and s.get('stage','').startswith(role+':') and s.get('search_started'):vector=s.get('objective_vector',vector)
    current=vector[0] if vector else final.get('P1')
    # Display retained-beam progress only. Never write back or select a decision.
    beam=[]
    for path in (RUN/'B3_M1/beam/2025-05-21').glob('B3/B*/STAGE_*.json'):
        stage_data=read(path,{}) or {};states=stage_data.get('retained_states',[])
        values=[r.get('current_planning_objective') for r in states if isinstance(r.get('current_planning_objective'),(int,float))]
        if values:beam.append(dict(stage=int(path.stem.split('_')[-1]),P1=min(values),retained=len(values),mtime=path.stat().st_mtime,source=str(path)))
    beam.sort(key=lambda r:(r['mtime'],r['stage']));latest=beam[-1] if beam else None
    b1vec=read(RUN/'B1/ACCEPTED_AIDC.json',{}).get('OBJECTIVE_VECTOR',[])
    current_kind='validated_incumbent' if current is not None else 'awaiting'
    if role=='B3_M1' and not final:
        current=latest['P1'] if latest else policies['B1'].get('P1')
        current_kind='partial_beam' if latest else 'A0_reference'
        vector=[current]+b1vec[1:] if b1vec else []
    if current is None and role in ('B3_A1','B3_MF'):
        parent='B3_M1' if role=='B3_A1' else 'B3_A1'
        current=policies[parent].get('P1');current_kind=parent+'_reference' if current is not None else 'awaiting'
    comparison=[]
    for r,desc in [('B0','기준 AIDC · MESS OFF'),('B1','AIDC 최적화 · MESS OFF'),('B2','기준 AIDC + MESS · 복구 승인'),('B3','A0 → M1 → A1 → MF')]:
        p=policies[r];vec=(seed_vector if r in ('B0','B2') else b1vec if r=='B1' else read(RUN/'B3_A1/ACCEPTED_AIDC.json',{}).get('OBJECTIVE_VECTOR',[]))
        value=b0 if r=='B0' else p.get('P1');metric=p.get('AC',p.get('metrics',{}));isfinal=p.get('status')=='PASS'
        comparison.append(dict(policy=r,description=desc,status='FINAL' if isfinal else 'FAILED' if s.get('status')=='FAIL_CLOSE' else 'RUNNING' if proc and r=='B3' else 'PENDING',
            P1=value if isfinal else None,live_P1=current if r=='B3' and not isfinal else None,
            live_kind=current_kind if r=='B3' else None,AC=metric if isfinal else None,
            vector=([value]+vec[1:]) if isfinal and vec else None,
            AC_change_percent=((base['metrics']['max_phase_line_loading_pu']-metric['max_phase_line_loading_pu'])/base['metrics']['max_phase_line_loading_pu']*100) if isfinal and metric else None))
    if policies['B3'].get('status')=='PASS':
        current=policies['B3']['P1'];current_kind='final';role='B3';vector=comparison[-1]['vector'] or []
    started=read(RUN/'CAMPAIGN_STARTED.json',{}).get('started_unix')
    return dict(version=2,observed_unix=now,run_name=RUN.name,status=s,worker=proc,role=role,baseline_P1=b0,current_P1=current,current_kind=current_kind,vector=vector,live=live,lives=lives,series=series,checkpoints=checkpoints,exact=exact,comparison=comparison,beam_history=beam,latest_beam=latest,campaign_started_unix=started,policies={r:{k:v[k] for k in ('status','P1','AC','metrics') if k in v} for r,v in policies.items()},source='B3 production; final B1 reused; B2 physical-closure PASS; read-only',failure=read(RUN/'CAMPAIGN_FAILURE.json'))
CACHE={};LOCK=threading.Lock()
def collect():
    while True:
        try:
            data=view()
            with LOCK:CACHE.clear();CACHE.update(data)
        except Exception as e:
            with LOCK:CACHE['monitor_error']=str(e)
        time.sleep(3)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/api/dashboard':
            with LOCK:body=json.dumps(CACHE,ensure_ascii=False,allow_nan=False).encode('utf-8')
            kind='application/json; charset=utf-8'
        elif path in ('/','/index.html','/app.js','/style.css'):
            f=HOME/'dist'/('index.html' if path=='/' else path[1:]);body=f.read_bytes();kind=(mimetypes.guess_type(f)[0] or 'application/octet-stream')+'; charset=utf-8'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8510);args=parser.parse_args()
    CACHE.update(view());threading.Thread(target=collect,daemon=True).start()
    print(f'http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
