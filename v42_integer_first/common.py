import os, sys, json, csv, hashlib, importlib.util, subprocess, time
from pathlib import Path
import numpy as np
from scipy import sparse
WORK = Path('D:/v42_m1_route_mode_benders_20261008')
ROOT = WORK/'repo'
REPORTS = WORK/'reports'
BASE = 'd541a9d15a03c4a6f8dbc1906a57c7486e9700e3'
LB = .5687116104049206
UB = .6306505800203936
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
prior=module('integer_first_readonly',ROOT/'docs/v42_m1_joint_formulation_20261008/common.py')
hc=prior.hc
# Historical bundles retain the C provenance path. Relocate only the reader's
# in-memory path; immutable bundle bytes and original C inputs stay unchanged.
import v42_bootstrap.m1 as _native_inputs_module
_original_native_inputs=_native_inputs_module.native_inputs
def _d_drive_native_inputs(bundle):
    local=WORK/'artifacts/source_authority/ROUTE_TABLE.json.gz'
    with local.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    assert actual==bundle['route_table']['sha256'],'D_ROUTE_COPY_SHA_FAILURE'
    copied=dict(bundle);copied['route_table']=dict(bundle['route_table'],path=str(local))
    return _original_native_inputs(copied)
_native_inputs_module.native_inputs=_d_drive_native_inputs
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(np.ndarray,list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v):return None
    return v
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(tmp,path)
def table(path,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r));path=Path(path)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(clean(rows))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,**arrays):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as f:np.savez_compressed(f,**arrays)
def paths_audit(label,model=None):
    keys=['TEMP','TMP','TMPDIR','GIT_TMPDIR','PIP_CACHE_DIR','PYTHONPYCACHEPREFIX','XDG_CACHE_HOME','MPLCONFIGDIR']
    paths={k:os.environ.get(k) for k in keys};paths.update(cwd=str(Path.cwd()),git_common=subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=ROOT,text=True).strip(),**{k:str(WORK/k) for k in ('repo','artifacts','logs','tmp','cache','checkpoints','reports')})
    if model is not None:paths.update(LogFile=model.Params.LogFile,NodefileDir=model.Params.NodefileDir)
    ok=all(v and Path(v).resolve().drive.upper()=='D:' for v in paths.values())
    p=REPORTS/'D_DRIVE_EXECUTION_AUDIT.json';history=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {'checks':[]}
    history['checks'].append(dict(label=label,paths=paths,PASS=ok));history['PASS']=all(x['PASS'] for x in history['checks']);history['executable_exception']=sys.executable
    write(p,history);assert ok,'D_DRIVE_PATH_FAILURE'
    return paths
