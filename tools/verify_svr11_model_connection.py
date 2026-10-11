"""One causal-prefix regeneration verifies the final generator's model wiring.

Development evidence only. No old coefficient is installed in campaign models.
"""
from pathlib import Path
import sys,ast,copy,shutil,time,json
import numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
from v42_svr11.authority import scope
from v42_svr11 import model
from v42_svr11.ldc_interval import project

DIAG=Path(r'D:\v42_svr11_planning_diagnostics_20261011')
OLD=Path(r'D:\v42_svr11_may_20261011_10')
DEV=DIAG/'FINAL_GENERATOR_CONNECTION'
DEV.mkdir(exist_ok=False)
sources=source_files();m=read(OLD/'CAMPAIGN_MANIFEST.json')
for key in ('predecessor_drain_contract','equipment_change_contract','model_checkpoint_reuse_contract'):m.pop(key,None)
h=read(m['hardware']['path']);h['source_SHA']=digest(sources);atomic(DEV/'HARDWARE.json',h)
m.update(execution_SHA=digest(sources),execution_sources=sources,root=str(DEV),code_root=str(SOURCE),
    development_diagnosis_only=True,production_campaign=False,hardware=record(DEV/'HARDWARE.json'))
atomic(DEV/'CAMPAIGN_MANIFEST.json',m)
day='2025-05-18';t=51
output=DEV/'SLOT_51';(output/'FORECAST_ANCHOR').mkdir(parents=True)
for name in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz'):
    shutil.copyfile(OLD/'models'/day/'FORECAST_ANCHOR'/name,output/'FORECAST_ANCHOR'/name)
# Retain the exact production setup and causal AUTO probe body. The isolated
# verifier stops before publication, after generating one full 121-probe slot.
fn=next(n for n in ast.parse((SOURCE/'v42_svr11/model.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='generate')
boundary=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='t')
fn.body=fn.body[:boundary]+ast.parse('''base=probe(51)
mat=[np.empty((60,len(x))) for x in base]
for j,control in enumerate(controls):
    plus=probe(51,j,1);minus=probe(51,j,-1);d=original._perturbation(control,anchor[51,j])
    for k in range(4):mat[k][j]=(plus[k]-minus[k])/(2*d)
row={}
for k,f in enumerate(('voltage','current','flow_p','flow_q')):
    row[f+'_constant']=base[k]-anchor[51]@mat[k]
    row[f+'_matrix']=mat[k] if k<2 else mat[k].T
row['branch_limits']=limits
return project(row,ldc),count,solves,ldc
''').body
namespace=dict(vars(model));exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(SOURCE/'v42_svr11/model.py'),'exec'),namespace)
start=time.perf_counter()
with scope(DEV/'CAMPAIGN_MANIFEST.json'):
    row,count,solves,ldc=namespace['generate'](day,OLD/'inputs/B2'/day,output,lambda v:None)
candidate=DIAG/(day+'_CAP_AWARE_LDC_INTERVAL_DIAGNOSTIC_COEFFICIENTS.npz')
with np.load(candidate) as z:
    checks={f:dict(bitwise_equal=np.array_equal(row[f],z[f][51]),max_absolute_difference=float(np.max(np.abs(row[f]-z[f][51])))) for f in model.FIELDS}
result=dict(PASS=all(x['bitwise_equal'] for x in checks.values()),synthetic_fixture_only=False,Actual_inputs_used_for_model=0,
    day=day,slot=51,Forecast_only=True,model_version=model.VERSION,source_SHA=digest(sources),
    model_source=record(SOURCE/'v42_svr11/model.py'),LDC_source=record(SOURCE/'v42_svr11/ldc_interval.py'),
    independent_compiles=count,physical_solves=solves,fields=checks,tap_optimization_variables=0,
    old_coefficients_promoted_to_campaign=0,development_candidate=record(candidate),
    LDC_contract_SHA=digest(ldc),wall_seconds=time.perf_counter()-start,UTC=now())
atomic(DEV/'GENERATOR_CONNECTION_VALIDATION.json',result)
print(json.dumps(result),flush=True)
