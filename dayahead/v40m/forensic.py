"""Reproducible, bounded local authority census and fail-closed case closure.

Run with python -B -m dayahead.v40m.forensic PHASE. All writes stay in V40M.
The original case domain is counterfactual AIDC, not historical Kestrel.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt')
OUT = REPO / 'dayahead/artifacts/v40m_authority72_closure'
OLD = SOURCE / 'dayahead/artifacts/v40i_authority_electrical_closure'
START = '2434a0e8a870ad7c52c34fdc0e270c6e164aebd8'
PRE = 'LEGITIMATE_PRE_DAY_COMPLETE'
AUTH = 'ACTUAL_EXECUTION_AUTHORIZED'
MISS = 'AUTHORITY_MISSING'
CONFLICT = 'AUTHORITY_CONFLICT'
HOLDS = {'31_DAY_ELECTRICAL_REGENERATION':'HOLD', 'B0_B1_B2_B3':'NO', 'FULL_MAY':'NO',
         'MODEL_RETRAINING':'NO', 'q_change':'NO', 'K0_change':'NO', 'tail_model_change':'NO',
         'PF_change':'NO', 'Q_control_change':'NO', 'optimization':'NO', 'certified_electrical_outputs_created':0}
FAMILIES = {'A':'Original scheduler/job raw records', 'B':'Execution/start/end raw records',
 'C':'Actual site/partition/node allocation records', 'D':'Authoritative adapter inputs',
 'E':'Archived raw source files', 'F':'Historical handoff/freeze references', 'G':'Execution logs/manifests'}
UID_KEYS = {'id','uid','UID','job_uid','job_id','original_job_uid','JobID','JobId'}
SKIP_DIRS = {'.git','__pycache__','.pytest_cache','node_modules','site-packages','.venv','venv'}

def guard(path):
    p = Path(path)
    if 'v40l' in str(p).lower():
        raise ValueError('V40L namespace access forbidden')
    return p

def read(path):
    return json.loads(guard(path).read_text(encoding='utf-8-sig'))

def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), default=str, allow_nan=False)

def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()

def write(name, value):
    OUT.mkdir(parents=True,exist_ok=True)
    p = OUT/name
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')
    return p

def sha(path):
    with guard(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def record(path):
    p=guard(path)
    return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}

def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args],text=True,encoding='utf-8').strip()

def norm(path):
    return str(Path(path)).lower()

def now():
    return datetime.now(timezone.utc).isoformat()

def protected():
    result={}
    for base in [SOURCE,REPO]:
        for rel in ['dayahead/v40i','dayahead/v40j','dayahead/v40k',
                    'dayahead/artifacts/v40i_authority_electrical_closure',
                    'dayahead/artifacts/v40j_runtime_redesign','dayahead/artifacts/v40k_central_runtime']:
            p=base/rel
            if p.exists():
                for f in p.rglob('*'):
                    if f.is_file():result[str(f)]=sha(f)
    return result

def init():
    assert git('rev-parse','HEAD')==START
    assert git('branch','--show-current')=='codex/v40m-actual-authority72-closure'
    p=OLD/'V40I_122_CASE_AUTHORITY_CLOSURE.parquet'
    frame=pd.read_parquet(p)
    summary=read(OLD/'V40I_122_CASE_AUTHORITY_CLOSURE.json')
    h=SOURCE/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.parquet'
    prior=pd.read_parquet(h)
    keys=sorted((r.case_id,str(r.uid)) for r in frame.itertuples())
    prior_keys=sorted((r.day+'/'+r.case,str(r.job_uid)) for r in prior.itertuples())
    assert keys==prior_keys and len(keys)==len(set(keys))==8786
    missing=frame[~frame.blocker_released]
    cases=[]
    for cid,g in frame.groupby('case_id',sort=True):
        unresolved=sorted(g.loc[~g.blocker_released,'uid'].astype(str))
        cases.append({'case_id':cid,'date':cid[:10],'baseline':cid[11:],
          'all_UIDs':sorted(g.uid.astype(str)),'missing_UIDs':unresolved,
          'old_status':MISS if unresolved else PRE,
          'case_key_sha256':digest([cid,sorted(g.uid.astype(str))])})
    assert len(cases)==122 and sum(c['old_status']==MISS for c in cases)==72
    sm={x['case_id']:x['classification'] for x in summary['cases']}
    assert all(sm[c['case_id']]==('ACTUAL_EXECUTION_AUTHORITY_MISSING' if c['old_status']==MISS else PRE) for c in cases)
    receipt=SOURCE/'dayahead/artifacts/v40k_central_runtime/V40K_FINAL_COMMIT_RECEIPT.json'
    kr=read(receipt)
    assert kr['final_research_commit']==START and kr['authority_missing']==72
    # V40K has a scalar hold, not a new UID cohort. Bind the cohort via V40I's
    # committed closure blob and the V40H exact UID/case-key join.
    rel=str(p.relative_to(SOURCE)).replace('\\','/')
    blob=subprocess.check_output(['git','-C',str(REPO),'show',START+':'+rel])
    assert hashlib.sha256(blob).hexdigest()==sha(p)
    identity={'created_at':now(),'identity_unit':'date/baseline case; UID is a child identity',
      'original_case_count':122,'original_UID_case_rows':8786,'original_UID_count':frame.uid.nunique(),
      'missing_case_count':72,'missing_UID_case_rows':len(missing),'missing_unique_UID_count':missing.uid.nunique(),
      'original_122_case_key_sha256':digest([c['case_id'] for c in cases]),
      'original_8786_UID_case_key_sha256':digest(keys),
      'blocker_72_case_key_sha256':digest([c['case_id'] for c in cases if c['old_status']==MISS]),
      'blocker_5126_UID_case_key_sha256':digest(sorted((r.case_id,str(r.uid)) for r in missing.itertuples())),
      'sources':[record(p),record(OLD/'V40I_122_CASE_AUTHORITY_CLOSURE.json'),record(h),record(receipt)],
      'V40K_receipt_semantics':'Scalar count only; exact identity restored from committed V40I and V40H, not inferred from 72.',
      'cases':cases,'historical_44_join':read(OLD/'V40I_44_JOB_VS_44_CASE_JOIN.json')}
    write('V40M_72_BLOCKER_IDENTITY.json',identity)
    write('V40M_START_STATE.json',{'created_at':now(),'starting_commit':START,'branch':git('branch','--show-current'),
      'worktree':str(REPO),'source_worktree_read_only':str(SOURCE),'old_counts':{PRE:50,AUTH:0,CONFLICT:0,MISS:72},
      'V40L_access_policy':'No enumeration inside, no content read, no mutation; path substring pruned before descent.',
      'identity':record(OUT/'V40M_72_BLOCKER_IDENTITY.json'),'protected_file_sha256':protected(),**HOLDS})
    print('Identity frozen: 122 cases, 72 missing cases,',len(missing),'UID/case rows',flush=True)

def root_discovery():
    oldroots=read(OLD/'CENSUS_SEARCH_ROOTS.json')
    raw=Path(oldroots[0]).parent
    roots=[]; discovery=[]
    def add(p,reason):
        if 'v40l' in str(p).lower() or norm(p)==norm(REPO):return
        roots.append({'path':str(p),'selection_reason':reason})
    for p in raw.iterdir():
        if 'v40l' in p.name.lower():continue
        selected=any(k in p.name.lower() for k in ('kestrel','scheduler'))
        discovery.append({'path':str(p),'selected':selected,'reason':'Kestrel/scheduler lineage' if selected else 'Different workload, weather or power domain; no current case allocation authority'})
        if selected:add(p,'Original raw scheduler roots and duplicate archive location')
    for p in oldroots[1:]:add(Path(p),'Prior V40I search root, freshly inventoried')
    for p in Path('C:/codex_mobileess_workspace').iterdir():
        if 'v40l' in p.name.lower() or norm(p)==norm(REPO):continue
        if p.is_dir() and p.name.startswith(('MobileESS_','_v39d_','V40A_reports')):
            add(p,'Historical workspace/archive/reference expansion')
    workspace=Path(oldroots[1]).parent
    for p in workspace.iterdir():
        if 'v40l' in p.name.lower():continue
        if p.is_dir() and any(k in p.name.lower() for k in ('handoff','overlay','authority','kestrel','raddit')):
            add(p,'Historical handoff, authority archive or scheduler forensic directory')
    wsl=Path('//wsl.localhost/Ubuntu-MobileESS-D/home/jaewon/mobile_ess_work')
    for name in ['kestrel','external_sources','handoff_results','exact_plot_source_handoff','GPT_TROUBLESHOOTING_HANDOFFS']:
        add(wsl/name,'WSL original scheduler / archive / handoff reference root')
    # Do not enumerate live run trees wholesale: add Kestrel-related frozen inputs
    # surfaced by their root names, and record other roots as out of domain.
    frozen=wsl/'frozen_artifacts'
    if frozen.exists():
        for p in frozen.iterdir():
            if 'v40l' in p.name.lower():continue
            selected=any(k in p.name.lower() for k in ('kestrel','aidc','v40','v39','v37'))
            discovery.append({'path':str(p),'selected':selected,'reason':'Named relevant authority archive' if selected else 'Earlier non-current-case electrical/campaign outputs; outside lineage search'})
            if selected:add(p,'WSL frozen authority input name census')
    unique={norm(r['path']):r for r in roots}
    return sorted(unique.values(),key=lambda x:x['path']),discovery

def family(path):
    low=str(path).lower()
    if 'job-anon.zip' in low:return 'A'
    if any(k in low for k in ('scheduler','kestrel')):return 'C' if any(k in low for k in ('node','allocation','partition')) else 'A'
    if any(k in low for k in ('frozen_job_observations','raw_blocked_uid','actual_timing')):return 'B'
    if any(k in low for k in ('adapter','materializ','snapshot','observation')):return 'D'
    if any(k in low for k in ('archive','external_sources')):return 'E'
    if any(k in low for k in ('handoff','freeze','reference')):return 'F'
    return 'G'

def census():
    roots,discovery=root_discovery();inventory={}; exclusions=[];errors=[]
    for n,r in enumerate(roots):
        p=guard(r['path']); before=len(inventory)
        if not p.exists():errors.append({'path':str(p),'reason':'ROOT_UNAVAILABLE'});continue
        if str(p).startswith('\\\\wsl.localhost'):
            linux='/'+'/'.join(p.parts[1:])
            code='''import os,json,sys
root=sys.argv[1];rows=[];errors=[]
walk=[(os.path.dirname(root),[],[os.path.basename(root)])] if os.path.isfile(root) else os.walk(root,followlinks=False)
for base,dirs,files in walk:
 dirs[:]=[d for d in dirs if 'v40l' not in d.lower() and d not in ['.git','__pycache__','node_modules','site-packages'] and not d.startswith(('.venv','venv'))]
 for name in files:
  if 'v40l' in name.lower():continue
  f=os.path.join(base,name)
  try:
   st=os.stat(f);rows.append([f,st.st_size,st.st_mtime_ns])
  except OSError as e:errors.append({'path':f,'reason':str(e)})
print(json.dumps({'rows':rows,'errors':errors}))
'''
            data=json.loads(subprocess.check_output(['wsl.exe','-d','Ubuntu-MobileESS-D','--','python3','-c',code,linux],encoding='utf-8'))
            for path,size,mtime in data['rows']:
                f=Path('//wsl.localhost/Ubuntu-MobileESS-D'+path)
                inventory[norm(f)]={'path':str(f),'bytes':size,'mtime_ns':mtime,'root':str(p),'family':family(f),'suffix':f.suffix.lower()}
            errors.extend(data['errors'])
            r['unique_file_count_added']=len(inventory)-before
            print('census root',n+1,'/',len(roots),'files',len(inventory),flush=True)
            continue
        if p.is_file():
            st=p.stat();inventory[norm(p)]={'path':str(p),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'root':str(p),'family':family(p),'suffix':p.suffix.lower()}
            r['unique_file_count_added']=len(inventory)-before
            continue
        def onerror(e):errors.append({'path':str(e.filename),'reason':str(e)})
        for base,dirs,files in os.walk(p,onerror=onerror,followlinks=False):
            keep=[]
            for d in dirs:
                low=d.lower()
                if 'v40l' in low:continue
                if low in SKIP_DIRS or low.startswith(('.venv','venv-')):
                    exclusions.append({'path':str(Path(base)/d),'reason':'Dependency/VCS/cache; not authority data'});continue
                keep.append(d)
            dirs[:]=keep
            for name in files:
                if 'v40l' in name.lower():continue
                f=Path(base)/name
                if norm(f) in inventory:continue
                try:
                    st=f.stat()
                    inventory[norm(f)]={'path':str(f),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,
                      'root':str(p),'family':family(f),'suffix':f.suffix.lower()}
                except OSError as e:errors.append({'path':str(f),'reason':str(e)})
        r['unique_file_count_added']=len(inventory)-before
        print('census root',n+1,'/',len(roots),'files',len(inventory),flush=True)
    rows=sorted(inventory.values(),key=lambda x:x['path'])
    inv=OUT/'V40M_SOURCE_INVENTORY.parquet'
    pd.DataFrame(rows).to_parquet(inv,index=False)
    manifest={'created_at':now(),'frozen_before_search':True,'roots':roots,'root_discovery':discovery,
       'directory_exclusions':exclusions,'inventory_errors':errors,'V40L_policy':'Pruned before descent; no path/content inventory of V40L',
       'families':FAMILIES,'file_count':len(rows),'total_bytes':sum(x['bytes'] for x in rows),'inventory':record(inv),
       'search_order':list(FAMILIES),'hash_policy':'SHA256 every parsed source; full inventory has SHA256; excluded files retain size/mtime and explicit reason',
       'interpretation':'Bounded local source census, not a claim of exhaustive external or inaccessible storage search'}
    write('V40M_AUTHORITY_SEARCH_MANIFEST.json',manifest)
    print('CENSUS',len(rows),'files',sum(x['bytes'] for x in rows),'bytes',len(errors),'inventory errors',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['init','census'])
    args=parser.parse_args();globals()[args.phase]()
