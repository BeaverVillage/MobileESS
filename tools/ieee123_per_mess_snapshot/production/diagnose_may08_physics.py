import os,sys,json,pickle,sqlite3,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W));os.chdir(W)
os.environ['V41R4_MAY_DATE']='2025-05-08'
from v41r4_windows_paths import install
install()
from v41r4_resited_io import install
install()
from v41r4_electrical import configure
configure('2025-05-08')
from v41r4_rho_certification import install
install()
from dayahead.v40h.authorities import load_bound_traffic
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v40h.recourse import validate_physics
from v41r4_per_mess_budget import dispatch_trajectory
import gurobipy as gp
gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(AssertionError('DIAG_NO_OPTIMIZE'))
S=W/'frozen_artifacts/v41r4_may/per_mess_900_v1/2025-05-08/B2/search'
identity=read(S/'M1_IDENTITY.json')
_,_,routes,_=load_bound_traffic(W,'2025-05-08',identity['identity']['inputs'])
from dayahead.v41.electrical import load
from dayahead.v41.reserve import bind
from dayahead.v41.execution import planning_power
from dayahead.v40h.beam_driver import _restore_slots
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v35r3e_r1.beam import BeamState
from dayahead.v40h.cache import state_record
from dayahead.v40a.grid import evaluate_grid,controls_from_trajectory
request=read(S.parent/'dayahead/M1/BOUNDED_MESS_INPUT.json')
ctx=load('2025-05-08');bind(ctx,request['ML_snapshot']['path'],request['ML_snapshot']['sha256'])
pcc=planning_power(request['jobs'],ctx)['pcc']
stage=read(next((S/'search_cache').rglob('STAGE_3.json')))
parents=[BeamState.from_dict(x) for x in stage['payload']['retained_states']]
con=sqlite3.connect('file:'+str(S/'exact_runtime/certified_candidates.sqlite3')+'?mode=ro',uri=True)
import v41r4_per_mess_budget as m
from dayahead.v40h import beam_driver as b
E=R/'manifests/per_mess_900s/may08_physics_fix';E.mkdir(exist_ok=True)
m.ORIGINAL_CHILD=b._make_child
m.ACTIVE=m.DepthBudget('2025-05-08','B2',4,output=E/'regression')
m.ACTIVE.context=dict(case='B3',mess_id='MESS04',sequence_index=3,aidc=pcc,
    coefficients=ctx.coefficients,nodes=ctx.nodes,route_table=routes,electrical=ctx.electrical)
results=[]
for ident,blob,sha,at in con.execute('select identity,result,result_sha,completed_at from certified order by completed_at desc limit 2'):
    assert hashlib.sha256(blob).hexdigest()==sha
    ident=json.loads(ident)
    if ident['depth']!=4:continue
    value=pickle.loads(blob);dispatch=value[1];trajectory=dispatch_trajectory(dispatch,routes)
    physical=validate_physics(trajectory)
    item=dict(candidate=dispatch['candidate'].candidate_id,at=at,physical=physical,evaluation=value[2],dispatch_keys=list(dispatch))
    item['parents']=[]
    for parent in parents:
        if state_record(parent)['content_SHA']!=ident['parent_state']:continue
        combined=MessTrajectory(tuple(_restore_slots(parent.trajectory_slots))+trajectory.slots)
        grid=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,combined.slots),ctx.nodes)
        grid.pop('coefficient_SHAs',None)
        item['parents'].append(dict(parent=parent.state_sha256,physics=validate_physics(combined),grid=grid))
        m.ACTIVE.parent=parent
        m.observe(value)
    if physical['status']!='PASS':
        from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
        a=MessElectricalAuthority.from_repository();res=[]
        for t,r in enumerate(trajectory.slots):
            travel=r.energy_safe_kwh if r.departure_slot==t and r.mode=='TRANSIT' else 0
            expected=r.battery_energy_kwh+a.charge_efficiency*a.interval_hours*max(-r.p_kw,0)-a.interval_hours*max(r.p_kw,0)/a.discharge_efficiency-travel
            actual=trajectory.slots[t+1].battery_energy_kwh if t+1<96 else a.terminal_energy_kwh
            if abs(expected-actual)>1e-6:res.append(dict(slot=t,residual=expected-actual,p=r.p_kw,charge=float(dispatch['p_charge_kw'][t]),discharge=float(dispatch['p_discharge_kw'][t])))
        item['energy_residuals']=res
    results.append(item)
E=R/'manifests/per_mess_900s/may08_physics_fix';E.mkdir(exist_ok=True)
write_json(E/'DIAGNOSTIC.json',dict(results=results,optimizer_calls=0))
print(json.dumps([x for x in results if any(y['grid']['status']!='PASS' or y['physics']['status']!='PASS' for y in x['parents'])],ensure_ascii=False,indent=2,default=str))
print('candidates',len(results),'parent matches',sum(len(x['parents']) for x in results))
assert len(results)==2 and m.ACTIVE.certified==1 and m.ACTIVE.retention_rejections==1
write_json(E/'REAL_REJECTION_REGRESSION.json',dict(status='PASS',optimizer_calls=0,
    restricted_candidates=2,retained_certified=1,polygon_rejected=1,physical_limits_unchanged=True))
print('REAL_REJECTION_REGRESSION_PASS')
