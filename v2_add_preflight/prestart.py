"""V2_add prestart evidence; append-only relative to PR236 d3b9f38.

No campaign or optimizer entry point is imported here.
"""
from pathlib import Path
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone

from .audit import ROOT, DOC, read, sha
from .physical import RUNTIME

BASE = 'd3b9f38c473a9304a7cd1d652ba2bd51cf2f51c2'
SOURCE = 'affc7226a519adbe072d7debbc3ae25ea71c3487'
OUT = DOC / 'prestart'
RUN = RUNTIME / 'prestart'
INITIAL = {'MESS01':'STA01','MESS02':'STA12','MESS03':'STA08','MESS04':'STA06',
           'MESS05':'STA02','MESS06':'STA03','MESS07':'STA04','MESS08':'STA05'}

def digest(x):
    return sha(json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False).encode())

def put(name, value):
    p=OUT/name; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return value

def table(name, rows):
    assert rows
    p=OUT/name; p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader();w.writerows(rows)

def record(p):
    p=Path(p);return dict(path=str(p.resolve()),sha256=sha(p.read_bytes()),bytes=p.stat().st_size)

def initialise():
    OUT.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True)
    path=OUT/'BASELINE_PRESERVATION.json'
    if not path.exists():
        tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
        paths=[s for s in tracked if s.startswith(('docs/v2_add/','v2_add_preflight/'))]
        put(path.name,dict(commit=BASE,files={s:sha((ROOT/s).read_bytes()) for s in paths}))
    before=read(path)
    assert all(sha((ROOT/p).read_bytes())==h for p,h in before['files'].items()),'PR236 baseline changed'
    directive=Path('C:/Users/kjw39/.codex/attachments/78c0e75c-4d60-45f5-ac2d-c07889e53f7d/붙여넣은 텍스트.txt')
    (OUT/'TASK_DIRECTIVE_KO.md').write_bytes(directive.read_bytes())
    return before

def resources():
    import psutil
    p=psutil.Process();p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    if 12 in p.cpu_affinity():p.cpu_affinity([12])
    return dict(pid=p.pid,priority=p.nice(),affinity=p.cpu_affinity(),available_RAM_bytes=psutil.virtual_memory().available,
        other_python=[dict(pid=q.pid,command=q.info['cmdline']) for q in psutil.process_iter(['name','cmdline'])
                      if q.pid!=p.pid and 'python' in (q.info['name'] or '').lower()])

def input_manifest():
    initialise();days=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'];rows=[]
    for d in days:
        files={}
        for role,r in d['files'].items():
            p=Path(r['path'])
            files[role]=dict(r,exists=p.is_file(),verified_SHA=(sha(p.read_bytes())==r['sha256']) if p.is_file() else False)
        n=read(d['files']['native']['path']);w=read(d['files']['windows']['path'])
        import gzip
        rt=json.loads(gzip.decompress(Path(n['route_table']['path']).read_bytes()))
        rows.append(dict(day=d['day'],axis=d['axis'],files=files,
            source_original=SOURCE,source_baseline=BASE,role='DEVELOPMENT_ALREADY_EXPOSED' if d['day']=='2025-05-01' else 'GENERALIZATION_NOT_YET_8500_AC_CERTIFIED',
            installed_GPU=sum(n['capacities'].values()),AIDC=len(n['capacities']),known_jobs=len(n['known_population']),windows=len(w),
            route_records=len(rt['routes']),route_services=len(rt['service_ids']),initial_MESS8=INITIAL,battery=n['battery'],
            original_4_initial_authority=d['files']['initial_MESS_authority'],extra_4='PR236 preregistered research assumption',
            IEEE8500_Planning_coefficients='NOT_GENERATED',IEEE8500_Actual120_Fresh='MAY01_ARCHIVED_ONLY' if d['day']=='2025-05-01' else 'NOT_RUN',
            prior_IEEE8500_native_control_history='NOT_AVAILABLE_IN_V44_IEEE123_INPUTS',
            input_files_PASS=all(v['verified_SHA'] for v in files.values())))
    return put('MAY01_07_PRESTART_INPUT_MANIFEST.json',dict(days=rows,dates=[r['day'] for r in rows],
        candidate=dict(beta_BG=2.,Actual='S1_03',Planning='S0',frozen_final=False),
        official_campaign_started=False,May08_31='SEPARATE_EXTENSION_NOT_SELECTED',all_file_receipts_PASS=all(r['input_files_PASS'] for r in rows),
        all_dates_IEEE8500_electrically_certified=False))

if __name__=='__main__':
    import sys
    if sys.argv[1]=='inputs':input_manifest()
    elif sys.argv[1]=='init':initialise();put('RESOURCE_BASELINE.json',resources())
