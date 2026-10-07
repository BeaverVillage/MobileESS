from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic,record,digest
from v42_a_stage_phase1.oracle import corrected_certificate,true_objective
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_phase1.producer import price_snapshot
from v42_a_stage_phase1.runner import serial
from .policy import OUT,STATIC,ROOT

def solve_fixture(task):
    snapshot,B,pi,folder=task;folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    priced=price_snapshot(snapshot,B,pi)
    m=gp.Model('EXPLICIT_TINY_PARALLEL_EQUIVALENCE');m.Params.OutputFlag=0
    m.Params.Threads=1;m.Params.Method=2;m.Params.Seed=20260929;m.Params.TimeLimit=10
    x=m.addMVar(priced.matrix.shape[1],lb=priced.lower,ub=priced.upper)
    m.addMConstr(priced.matrix,x,priced.senses,priced.rhs)
    c=np.zeros(priced.matrix.shape[1])
    for j,v in priced.objectives[0].coefficients().items():c[j]=float(v)
    m.setObjective(c@x);m.optimize()
    raw={n:np.asarray(m.getAttr(n),dtype=float) for n in ('X','Pi','RC','Slack')}
    np.savez_compressed(folder/'RAW.npz',**raw) # first
    meta=dict(status=m.Status,Runtime=m.Runtime,Threads=m.Params.Threads,raw=record(folder/'RAW.npz'))
    atomic(folder/'NATIVE.json',meta)
    replay=primal_replay(priced,raw['X']);sign=verify_sign_convention(priced,raw['Pi'],raw['RC'])
    cert=corrected_certificate(snapshot,B,pi,raw['Pi'])
    if m.Status!=gp.GRB.OPTIMAL or not replay['PASS'] or not sign['PASS'] or not cert['PASS']:raise ValueError('TINY_PARALLEL_FIXTURE_FAIL')
    canonical=serial(dict(snapshot=priced.fingerprint(),raw={k:v.tolist() for k,v in raw.items()},certificate=cert,true_price=str(true_objective(B,pi,raw['X']))))
    atomic(folder/'CANONICAL.json',canonical);m.dispose()
    return canonical

def run():
    # Reuse the independently tested original native fixture, not a mock LP.
    import sys
    sys.path.insert(0,str(ROOT/'tests'))
    from test_v42_a_stage_phase1 import block_fixture
    from v42_a_stage_phase1.producer import native_block
    fixtures=[]
    for n in (1,2,3,2):
        data,graph,axes=block_fixture(n);snap,B,_,units=native_block(data,'c',graph,axes)
        pi=np.asarray([((i*17+n)%11-5)/8 for i in range(len(axes))]);fixtures.append((snap,B,pi))
    t=perf_counter()
    serial_results=[solve_fixture((*f,STATIC/'EQ1V2'/str(i))) for i,f in enumerate(fixtures)];serial_wall=perf_counter()-t
    t=perf_counter()
    with ProcessPoolExecutor(max_workers=4) as executor:
        parallel=list(executor.map(solve_fixture,[(*f,STATIC/'EQ4V2'/str(i)) for i,f in enumerate(fixtures)]))
    parallel_wall=perf_counter()-t
    equal=serial_results==parallel
    atomic(OUT/'PARALLEL_PRICING_EQUIVALENCE.json',dict(PASS=True,exact_equal=equal,selected_workers=4 if equal else 1,
        canonical_serial_sha256=digest(serial_results),canonical_parallel_sha256=digest(parallel),
        raw_X_Pi_RC_Slack_exact_equal=equal,exact_rational_certificates_equal=equal,fixtures=4,Threads_per_worker=1,
        maximum_simultaneous_native_solves=4,serial_wall=serial_wall,parallel_wall=parallel_wall,
        fixture_speed_ratio=serial_wall/parallel_wall,May19_speedup_measured=False,
        timing_scope='tiny fixture includes worker startup; not a valid full May19 speedup estimate'))
    print('EARLY_PARALLEL_EQUIVALENCE',equal,serial_wall,parallel_wall,flush=True)

if __name__=='__main__':run()
