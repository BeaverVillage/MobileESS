"""Verify real archived certified MOVE/STAY conversion with zero optimizer calls."""
import os,sys,pickle,json,time
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W));os.chdir(W)
os.environ['V41R4_MAY_DATE']='2025-05-03'
from v41r4_windows_paths import install
install()
from v41r4_resited_io import install
install()
from v41r4_electrical import configure
configure('2025-05-03')
from v41r4_rho_certification import install
install()
from dayahead.v40h.authorities import load_bound_traffic
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h import beam_driver as b
from v41r4_per_mess_budget import dispatch_trajectory,certified_child
import v41r4_per_mess_budget as m
import v41r4_exact_cache as cache
import gurobipy as gp
gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(AssertionError('REGRESSION_MUST_NOT_OPTIMIZE'))
z=pickle.load((R/'manifests/numerical_certification_fix/DIAGNOSTIC_INPUTS.pkl').open('rb'))
_,_,routes,_=load_bound_traffic(W,'2025-05-03',z['identity']['identity']['inputs'])
m.ORIGINAL_CHILD=b._make_child
from types import SimpleNamespace
context=dict(case='B3',mess_id='MESS02',sequence_index=1,aidc=z['aidc'],coefficients=z['coefficients'],nodes=[],
    route_table=routes,electrical=SimpleNamespace(legacy_context=None,voltage={},current={}))
found={};out=[]
for key,value in z['cache'].items():
    if not cache.certified(value):continue
    dispatch=value[1];kind='STAY' if dispatch['candidate'].is_stay else 'MOVE'
    if kind in found:continue
    trajectory=dispatch_trajectory(dispatch,routes)
    child=certified_child(trajectory,z['parent'],context,float(dispatch['objective']),dispatch['candidate'].candidate_id,'FIXED_ROUTE_EXACT_CERTIFIED')
    assert child.vehicles[-1]['physical']['status']=='PASS' and child.vehicles[-1]['grid']['status']=='PASS'
    found[kind]=True
    out.append(dict(kind=kind,candidate=dispatch['candidate'].candidate_id,objective=child.current_planning_objective,
        physical=child.vehicles[-1]['physical'],grid=child.vehicles[-1]['grid'],signature=child.state_sha256))
    if len(found)==2:break
assert set(found)=={'MOVE','STAY'}
write_json(R/'manifests/per_mess_900s/REAL_CERTIFICATE_CONVERSION.json',dict(status='PASS',records=out,optimizer_calls=0))
print('REAL_MOVE_STAY_CERTIFICATE_CONVERSION_PASS',flush=True)
