"""Diagnostic-only storage and authority. No production-module mutations on disk."""
import os,sys,json,hashlib,math
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
RUN=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4'
sys.path.insert(0,str(ROOT))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def clean(x):
    import numpy as np
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x):return None
    return x
def save(p,x):
    p=Path(p);assert p.resolve().is_relative_to(OUT)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def arrays(p):
    import numpy as np
    with np.load(p,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def protect():
    protected=ROOT.parent.resolve()
    def pathcheck(p):
        if isinstance(p,(str,bytes,os.PathLike)):
            p=Path(os.path.abspath(os.fsdecode(p)))
            if (p.is_relative_to(protected) or p.is_relative_to(Path('C:/Users/kjw39/OneDrive')) or p.is_relative_to(Path('D:/ChatGPT'))) and not p.is_relative_to(OUT):
                raise PermissionError('DIAGNOSTIC_ONLY_WRITE:'+str(p))
    def hook(event,args):
        if event=='open':
            p,mode,flags=args
            if (mode and any(c in mode for c in 'wax+')) or (flags and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):pathcheck(p)
        elif event in ('os.remove','os.rmdir','os.mkdir'):pathcheck(args[0])
        elif event in ('os.rename','os.replace'):pathcheck(args[0]);pathcheck(args[1])
    sys.addaudithook(hook)
def authority():
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    a=read(OUT/'BATTERY_EFFICIENCY_AUTHORITY.json')
    da=MessElectricalAuthority.from_repository();da.validate()
    assert a['eta_charge']==da.charge_efficiency==.95
    assert a['eta_discharge']==da.discharge_efficiency==.95
    assert (da.active_power_limit_kw,da.pcs_kva,da.pcs_polygon_faces)==(300,400,16)
    return a,da
