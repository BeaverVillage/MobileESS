"""Independent finished native receipts, original replay and bound authority.

ZERO optimize and ZERO model-build calls. Live runs are reported pending.
"""
from practical_support import *
import argparse
def audit(folder):
    import gurobipy as gp
    def forbidden(*a,**kw):raise AssertionError('AUDIT_OPTIMIZE_AND_PRESOLVE_FORBIDDEN')
    gp.Model.optimize=forbidden;gp.Model.presolve=forbidden
    receipt=read(folder/'RESULT.json');once=read(folder/'OPTIMIZE_ONCE.json');params=read(folder/'SOLVER_PARAMETERS.json');model=read(folder/'MODEL_AUTHORITY.json');obj=read(folder/'OBJECTIVE_IDENTITY.json')
    A,d,_=hc.load();assert verifier.verify(ROOT,d)['PASS'] and model['PASS'] and obj['PASS'] and receipt['objective_identity_after_PASS']
    assert sha(OUT/'IMMUTABLE_DEADLINE.json')==once['deadline_SHA256']==params['immutable_deadline_SHA256']
    assert once['optimize_calls']==receipt['optimize_calls']==1 and once['settings']==params['settings']
    assert all(params['effective'][k]==v for k,v in params['settings'].items())
    assert {k:params['settings'][k] for k in SETTINGS}==SETTINGS
    source='native_production_runner.py' if receipt['kind']=='production' else 'native_runner.py'
    blob=subprocess.check_output(['git','show',once['source_commit']+':'+(OUT/source).relative_to(ROOT).as_posix()],cwd=ROOT)
    assert hashlib.sha256(blob).hexdigest()==once['source_SHA256']==sha(OUT/source),'RUNNER_SOURCE_CHANGED'
    for helper in ['practical_support.py']:
        blob=subprocess.check_output(['git','show',once['source_commit']+':'+(OUT/helper).relative_to(ROOT).as_posix()],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==sha(OUT/helper),'RUN_HELPER_SOURCE_CHANGED'
    restricted=receipt['kind']=='primal'
    if restricted:assert model['added_rows']==1 and not model['full_original_domain'] and receipt['radius'] in (64,96)
    else:assert model['added_rows']==0 and model['full_original_domain'] and params['settings']['Cuts']==0 and params['settings']['Heuristics']==0
    assert (model['rows'],model['cols'],model['binaries'])==(A.shape[0]+int(restricted),A.shape[1],int((d['types']=='B').sum()))
    log=(folder/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace');assert log.count('Optimize a model with')==1
    center_validation=read(folder/'CENTER_VALIDATION.json');assert center_validation['PASS']
    with np.load(folder/'CENTER.npz') as z:center=z['x']
    reader=hc.physical_reader();assert full_replay(A,d,center,reader)['PASS']
    if restricted:
        neighborhood=read(folder/'NEIGHBORHOOD.json');free=np.asarray(neighborhood['free']);fixed=np.asarray(neighborhood['fixed'])
        with np.load(ROOT/'docs/v42_m1_hamming48_600s_20261007/NEIGHBORHOOD_RESTRICTION.npz') as z:assert np.array_equal(free,z['free']) and np.array_equal(fixed,z['fixed'])
        assert neighborhood['free_names']==d['names'][free].tolist() and len(free)==2100
    import csv
    with (folder/'INCUMBENT_TRACE.csv').open(encoding='utf-8',newline='') as f:events=list(csv.DictReader(f))
    assert len(events)==receipt['all_incumbent_events_saved'];unique={};results=[];best=float(center[239826])
    for event in events:
        p=folder/event['point'];assert sha(p)==event['SHA256']
        with np.load(p) as z:x=z['x']
        h=hashlib.sha256(x.tobytes()).hexdigest()
        if h not in unique:
            check=full_replay(A,d,x,reader)
            if restricted:
                distance=int(np.count_nonzero((x[free]>.5)!=(center[free]>.5)))
                domain_PASS=bool(distance<=receipt['radius'] and np.max(abs(x[fixed]-center[fixed]),initial=0)<=1e-8)
                check['PASS']=bool(check['PASS'] and domain_PASS)
            unique[h]=check
        check=unique[h]
        results.append(dict(event=int(event['event']),point=event['point'],rho=float(x[239826]),PASS=check['PASS']))
        if check['PASS']:best=min(best,float(x[239826]))
    if (folder/'FINAL_POINT.npz').exists():
        with np.load(folder/'FINAL_POINT.npz') as z:x=z['x']
        check=full_replay(A,d,x,reader)
        if restricted:check['PASS']=bool(check['PASS'] and int(np.count_nonzero((x[free]>.5)!=(center[free]>.5)))<=receipt['radius'] and np.max(abs(x[fixed]-center[fixed]),initial=0)<=1e-8)
        if check['PASS']:best=min(best,float(x[239826]))
    with np.load(folder/'BEST_VALID_POINT.npz') as z:best_point=z['x']
    assert full_replay(A,d,best_point,reader)['PASS'] and float(best_point[239826])==receipt['valid_UB']==best
    assert sha(folder/'BEST_VALID_POINT.npz')==read(folder/'BEST_FULL_REPLAY.json')['point_SHA256']
    bound=native_bound_valid(receipt,True,restricted,best,log);assert bound==receipt['bound_authority']
    if restricted:assert bound['global_LB_candidate'] is None and 'RESTRICTED_PRIMAL_BOUND_NOT_GLOBAL' in bound['reasons']
    atomic(folder/'INDEPENDENT_AUDIT.json',dict(PASS=True,UTC=stamp(),audit_optimize_calls=0,model_build_calls=0,source_commit_and_SHA_PASS=True,objective_identity_PASS=True,deadline_identity_PASS=True,full_original_replay_PASS=True,valid_UB=best,bound_authority=bound,all_incumbent_events=results,every_unique_integer_vector_independently_replayed=True,restricted_bound_never_global=restricted,original_physics_A1_authority_PASS=True))
    print('INDEPENDENT_NATIVE_AUDIT_PASS',folder.name,len(events),best)
def run():
    finished=[];pending=[]
    for folder in sorted((OUT/'runs').glob('*')):
        if not folder.is_dir():continue
        if (folder/'RESULT.json').exists():audit(folder);finished.append(folder.name)
        else:pending.append(folder.name)
    atomic(OUT/'NATIVE_AUDIT_STATUS.json',dict(UTC=stamp(),finished=finished,pending=pending,optimize_calls=0))
if __name__=='__main__':run()
