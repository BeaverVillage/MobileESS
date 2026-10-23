"""Append-only FULL integration evidence on a4dabafb; never a new experiment."""
from pathlib import Path
import json,csv,subprocess,time
from .prestart import ROOT,DOC,RUNTIME,read,sha,record,digest,INITIAL,SOURCE,resources
BASE='a4dabafb52e9ee12a95858438b7d65b6b751d34f'
OUT=DOC/'integration';RUN=RUNTIME/'integration'
def put(name,x):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return x
def table(name,rows):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def init():
    OUT.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True)
    p=OUT/'PRESERVATION_BASELINE.json'
    if not p.exists():
        files=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
        put(p.name,dict(commit=BASE,files={n:sha((ROOT/n).read_bytes()) for n in files if n.startswith(('docs/v2_add/','v2_add_preflight/'))}))
    b=read(p);assert all(sha((ROOT/n).read_bytes())==h for n,h in b['files'].items())
    return b
def day_input(day):return next(r for r in read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'] if r['day']==day)
def guard(start,rss_limit=4*1024**3,reserve=5*1024**3,wall=3600):
    import psutil
    if psutil.Process().memory_info().rss>rss_limit or psutil.virtual_memory().available<reserve:raise MemoryError('PROTECTED_WORKER_RESOURCE_RESERVE')
    if time.perf_counter()-start>wall:raise TimeoutError('ISOLATED_BUILD_WALL_GUARD')
if __name__=='__main__':init();put('RESOURCE_BASELINE.json',resources())
