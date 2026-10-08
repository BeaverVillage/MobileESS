import os,sys,json,csv,hashlib,subprocess,time,importlib.util,math
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parent
REPORTS=WORK/'reports'
P183=ROOT/'docs/v42_m1_route_mode_benders_20261008'
BASE='3100039d19a22ec407713f36a9e978b2e96533a8'
LB=.5687116104049206
UB=.6284141956452488
SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=0,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0,BarConvTol=1e-8,TimeLimit=900)
OLD_ZF=Path('D:/v42_m1_zf_recourse_pilot_20261008')
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(np.ndarray,list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(tmp,path)
def table(path,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader();writer.writerows(clean(rows))
def save(path,**arrays):
    with Path(path).open('wb') as f:np.savez_compressed(f,**arrays)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
prior=module('physics_readonly_scientific_authority',ROOT/'docs/v42_m1_joint_formulation_20261008/common.py')
hc=prior.hc
import v42_bootstrap.m1 as native_reader
original_native_inputs=native_reader.native_inputs
def d_native_inputs(bundle):
    path=WORK/'artifacts/source_authority/ROUTE_TABLE.json.gz'
    assert sha(path)==bundle['route_table']['sha256']=='3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9'
    copy=dict(bundle);copy['route_table']=dict(bundle['route_table'],path=str(path))
    return original_native_inputs(copy)
native_reader.native_inputs=d_native_inputs
def io_guard(event,args):
    if event!='open' or not args or not isinstance(args[0],(str,bytes,os.PathLike)):return
    try:path=Path(os.fsdecode(args[0])).resolve()
    except (TypeError,ValueError,OSError):return
    mode=args[1];flags=args[2]
    writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
    if writing and not path.is_relative_to(WORK):raise AssertionError('WRITE_OUTSIDE_NEW_D_WORKSPACE:'+str(path))
    if path.drive.upper()=='C:' and path.suffix.lower() in ('.npz','.pkl','.mps','.gz'):raise AssertionError('SCIENTIFIC_C_INPUT_FORBIDDEN:'+str(path))
sys.addaudithook(io_guard)
def paths_audit(label,model=None):
    keys=['TEMP','TMP','TMPDIR','GIT_TMPDIR','PIP_CACHE_DIR','PYTHONPYCACHEPREFIX','XDG_CACHE_HOME','MPLCONFIGDIR']
    paths={key:os.environ.get(key) for key in keys};paths.update(cwd=str(Path.cwd()),git_common=subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=ROOT,text=True).strip(),scientific_matrix=str(hc.PARENT/'C3A_A.npz'),scientific_data=str(hc.PARENT/'C3A_DATA.npz'),traffic=str(WORK/'artifacts/source_authority/ROUTE_TABLE.json.gz'),**{k:str(WORK/k) for k in ('repo','artifacts','logs','tmp','cache','reports','checkpoints')})
    if model is not None:paths.update(LogFile=model.Params.LogFile,NodefileDir=model.Params.NodefileDir)
    ok=all(v and Path(v).resolve().drive.upper()=='D:' for v in paths.values())
    file=REPORTS/'D_DRIVE_EXECUTION_AUDIT.json';ledger=read(file) if file.exists() else dict(checks=[])
    ledger['checks'].append(dict(label=label,paths=paths,PASS=ok));ledger['PASS']=all(x['PASS'] for x in ledger['checks']);ledger.update(executable_exception=sys.executable,all_new_writes_restricted_to_new_workspace=True,scientific_C_read_guard=True,old_inputs_read_only=True)
    ledger['all_new_writes_restricted_to_new_workspace']=False
    ledger['python_writes_restricted_to_new_workspace']=True
    ledger['all_new_scientific_writes_restricted_to_new_workspace']=True
    ledger['Git_metadata_exception']='D: shared Git common directory for explicitly requested separate worktree; original tracked files and old scientific evidence are not changed'
    write(file,ledger);assert ok
    return paths
def assignment(d):
    path=P183/'artifacts/candidate_000.npz'
    with np.load(path) as f:return {key:f[key].copy() for key in f.files}
