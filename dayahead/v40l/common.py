import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40l_conditional_tail'
K=ROOT/'dayahead/artifacts/v40k_central_runtime'
J=ROOT/'dayahead/artifacts/v40j_runtime_redesign'
START='2434a0e8a870ad7c52c34fdc0e270c6e164aebd8'
XGB_PY=Path('C:/Users/kjw39/AppData/Local/MobileESS/venvs/v35r3d-runtime/Scripts/python.exe')
LGB_PY=Path('C:/Users/kjw39/AppData/Local/Programs/Python/Python311/python.exe')
LEGACY=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v35r3d_kestrel_runtime_authority_closure')
ARCHIVE=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
APRIL='esif.hpc.kestrel.job-anon/year=2025/month=4/kestrel_jobs_202504_0.parquet'
CUTOFF='2025-05-01T00:00:00+00:00'
Q=5576.44921875
SEED=4012
F9=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account']
CATS=['partition','qos','user','account','hardware','support_class']
FEATURES=F9+['submit_hour','submit_dow','submit_week','hardware','standby','wall_bucket','exact_count','near_count','support_class']

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def read(n):return load(OUT/n)
def write(n,obj,immutable=False):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    b=(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False,default=str)+'\n').encode('utf-8')
    if immutable and p.exists():assert p.read_bytes()==b,('IMMUTABLE',n)
    p.write_bytes(b);return p
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def event(kind,**kw):
    with (OUT/'V40L_EVENTS.jsonl').open('a',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps({'timestamp':now(),'kind':kind,**kw},default=str)+'\n')
def require_prereg():
    r=read('V40L_PREREGISTRATION_COMMIT_RECEIPT.json')
    for n,h in r['frozen_SHA'].items():
        assert sha(OUT/n)==h,('PREREG_CHANGED',n)
        assert hashlib.sha256(git('show',r['commit']+':'+(OUT/n).relative_to(ROOT).as_posix())).hexdigest()==h
    return r['commit']
def verify_k0():
    r=load(K/'V40K_FINAL_COMMIT_RECEIPT.json')
    assert r['final_research_commit']==START
    names=['models/K0_FINAL.pkl','POINT_HOLDOUT_PREDICTIONS.parquet','RESIDUAL_OOF_ROWS.parquet']
    for n in names:assert sha(K/n)==r['committed_V40K_file_SHA256'][(K/n).relative_to(ROOT).as_posix()],n
    return {n:sha(K/n) for n in names}

class Firewall:
    """Python file audit, paired with pre-decode raw row-group authorization."""
    def __init__(self,stage,raw=False):
        self.stage=stage;self.raw=raw;self.active=False;self.busy=False;self.reads=set();self.denied=[]
    def __enter__(self):
        (OUT/'temporary').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'temporary')
        sys.addaudithook(self.audit);self.active=True;event('stage_start',stage=self.stage);return self
    def audit(self,kind,args):
        if not self.active or self.busy or kind!='open' or not isinstance(args[0],(str,bytes,Path)):return
        self.busy=True
        try:
            p=str(Path(os.fsdecode(args[0])).resolve()).casefold();mode=args[1]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(args[2],int) and bool(args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT)))
            within=lambda r:p.startswith(str(r.resolve()).casefold()+os.sep)
            library=any(x in p for x in ['site-packages','\\python311\\lib\\','\\venvs\\','\\dependencies\\python\\']) or p.endswith('python311.zip') or Path(p).name=='nul'
            allowed=library or any(within(r) for r in [OUT,K,J,ROOT/'dayahead/v40l',ROOT/'dayahead/v40k',ROOT/'dayahead/v40j',LEGACY/'dayahead'])
            if self.raw and p==str(ARCHIVE.resolve()).casefold():allowed=True
            if writing:allowed=within(OUT)
            if re.search(r'2025[-_]05(?:[-_\\/]|$)|year=2025[\\/]month=0?5[\\/]|[\\/]v40i[\\/]',p):allowed=False
            if not allowed:
                self.denied.append({'path':p,'mode':mode});raise PermissionError('V40L_FIREWALL:'+p)
            if not writing and not library:self.reads.add(p)
        finally:self.busy=False
    def __exit__(self,*exc):
        self.active=False
        write('READS_'+self.stage+'.json',{'stage':self.stage,'allowlisted_reads':sorted(self.reads),'denied':self.denied,'raw_access_permitted':self.raw,'May_row_payload_reads':0})
        event('stage_end',stage=self.stage,error=None if exc[0] is None else str(exc[1]))
