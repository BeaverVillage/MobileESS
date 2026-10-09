import hashlib
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='52ef855a59144a7c561df44b81dc2ad265babdbd'
OUT=ROOT/'docs/v42_m1_degenmoves_zero_start_v1'
REF=ROOT/'docs/v42_single_worker_single_thread_a1_m1'
SOURCE=Path('C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
LOCAL=ROOT.parent/'DEGEN_START_LOCAL'
ENV=dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1')
os.environ.update(ENV)
POLICY=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,TimeLimit=1800,DegenMoves=0)
NORMALAMPS='0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(name,value):
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');temp.replace(path)
def finite(value):return float(value) if abs(float(value))<1e100 else None
