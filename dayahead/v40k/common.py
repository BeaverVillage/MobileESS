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
OUT=ROOT/'dayahead/artifacts/v40k_central_runtime'
J=ROOT/'dayahead/artifacts/v40j_runtime_redesign'
START='a2a21c904535125c66668a294f91d73a66f5d4a7'
LEGACY=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v35r3d_kestrel_runtime_authority_closure')
CACHE=LEGACY/'dayahead/cache/v35r3d_kestrel_runtime_authority_closure/kestrel_preissue_normalized.parquet'
ARCHIVE=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
APRIL='esif.hpc.kestrel.job-anon/year=2025/month=4/kestrel_jobs_202504_0.parquet'
SEED=4011
FEATURES9=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account']
FEATURES=FEATURES9+['submit_hour','submit_dow','submit_week','hardware','standby']
CATS=['partition','qos','user','account','hardware']
Q=5576.44921875
CUTOFF='2025-05-01T00:00:00+00:00'

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def write(n,o,immutable=False):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    b=(json.dumps(o,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False,default=str)+'\n').encode('utf-8')
    if immutable and p.exists() and p.read_bytes()!=b:raise ValueError('IMMUTABLE:'+n)
    p.write_bytes(b);return p
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def event(kind,**kw):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'V40K_EVENTS.jsonl').open('a',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps({'timestamp':now(),'kind':kind,**kw},ensure_ascii=False,default=str)+'\n')
def require_prereg():
    r=read('V40K_PREREGISTRATION_COMMIT_RECEIPT.json')
    for n,h in r['frozen_artifact_sha256'].items():
        assert sha(OUT/n)==h,('CONTRACT_CHANGED',n)
        assert hashlib.sha256(git('show',r['commit']+':'+str((OUT/n).relative_to(ROOT)).replace('\\','/'))).hexdigest()==h
    return r['commit']

class Firewall:
    """Python audit plus explicit Parquet group/column gating; writes only V40K."""
    def __init__(self,stage,files=(),roots=()):
        self.stage=stage;self.active=False;self.busy=False;self.events=[];self.denied=[]
        self.files={str(Path(p).resolve()).casefold() for p in files}
        self.roots=[str(Path(p).resolve()).casefold()+os.sep for p in roots]
    def __enter__(self):
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'temporary').mkdir(exist_ok=True)
        tempfile.tempdir=str(OUT/'temporary')
        self.active=True;sys.addaudithook(self.audit);event('stage_start',stage=self.stage);return self
    def audit(self,name,args):
        if not self.active or self.busy or name!='open' or not isinstance(args[0],(str,bytes,Path)):return
        self.busy=True
        try:
            p=str(Path(os.fsdecode(args[0])).resolve()).casefold();mode=args[1]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(args[2],int) and bool(args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT)))
            out=str(OUT.resolve()).casefold()+os.sep
            source=str((ROOT/'dayahead/v40k').resolve()).casefold()+os.sep
            library=any(s in p for s in ['site-packages','\\python311\\lib\\','\\venvs\\','\\dependencies\\python\\']) or p.endswith('python311.zip') or Path(p).name=='nul'
            jsource=str((ROOT/'dayahead/v40j').resolve()).casefold()+os.sep
            jdata=str(J.resolve()).casefold()+os.sep
            allowed=(p.startswith((out,source,jsource,jdata)) or p in self.files or any(p.startswith(r) for r in self.roots) or library)
            if writing:allowed=p.startswith(out)
            if re.search(r'2025[-_]05(?:[-_\\/]|$)|year=2025[\\/]month=0?5[\\/]|[\\/]v40i[\\/]',p):allowed=False
            if not allowed:
                self.denied.append({'path':p,'mode':mode});event('read_denied',stage=self.stage,path=p,mode=mode)
                raise PermissionError('V40K_FIREWALL:'+p)
            if not library and not writing:self.events.append(p)
        finally:self.busy=False
    def __exit__(self,*args):
        self.active=False
        write('READS_'+self.stage+'.json',{'stage':self.stage,'allowlisted_reads':self.events,'denied':self.denied,'new_May_payload_reads':0})
        event('stage_end',stage=self.stage,error=None if args[0] is None else str(args[1]))
