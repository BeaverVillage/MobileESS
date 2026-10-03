import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='6795206a09e5f6ce1ad4de5c29a4c729bf79bd43'
OUT=ROOT/'docs/v42_m1_cutpass_loop_campaign'
REF=ROOT/'docs/v42_m1_degenmoves_zero_start_v1'
SCIENCE=ROOT/'docs/v42_single_worker_single_thread_a1_m1'
SOURCE=Path('C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
LOCAL=ROOT.parent/'CUTPASS_LOCAL'
ENV=dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1')
os.environ.update(ENV)
POLICY=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,TimeLimit=1800)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def finite(value):return float(value) if abs(float(value))<1e100 else None
