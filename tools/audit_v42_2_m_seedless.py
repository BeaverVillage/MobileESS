"""Actual May01 seedless K16 and Joint Native0, plus same-pool Direct A/B."""
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[_name]='1'
from copy import copy
import gc
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from types import ModuleType
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def audit(execution,output):
    import gurobipy as gp
    from v42_integration.table_v_run import load_context,budget,current_build_admission
    from v42_integration.table_v_mess import TableVMessStages
    from v42_integration.m_engine import IncumbentBank,PathGraph,pin_pools,direct_joint,_native_joint,_write,file_record,matrix_sha,domain_sha
    from v42_integration.m_candidates import generate
    from v42_integration.table_v_k48 import prepare_k16
    from v42_integration.m_adaptive import pool_identity
    from v42_integration.table_v_memory import memory_sample
    from v42_common_mess.fixed_pattern import values_for,stationary_paths
    calls=[]
    def forbidden(*args,**kwargs):calls.append('FORBIDDEN');raise AssertionError('ACTUAL_NATIVE0_NATIVE_ENTRYPOINT_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS','feasRelax','feasRelaxS'):setattr(gp.Model,name,forbidden)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);began=perf_counter()
    before=memory_sample();context=load_context(execution);main=budget(execution,'PLANNING')
    factory=TableVMessStages(context,main)
    ref=json.loads((Path(execution)/'REFERENCE_RESULT.json').read_text(encoding='utf8'))
    accepted=json.loads((Path(execution)/'REFERENCE_ACCEPTANCE.json').read_text(encoding='utf8'))
    case=factory.prepare('B2','M1',ref,accepted,output/'CURRENT_M',
        build_admission=current_build_admission(main,arm='B2',stage='M1',operation='CURRENT_M_NATIVE0_BUILD'),
        progress=lambda row:print('M_NATIVE0',row,flush=True))
    packet,certificate=prepare_k16(case,None,output/'K16')
    K,e=packet['A'],packet['d']
    model=gp.Model('SEEDLESS_K16_NATIVE0')
    try:
        model.Params.Threads=1;model.Params.OutputFlag=0
        x=model.addMVar(K.shape[1],lb=e['lower'],ub=e['upper'],vtype=e['types'],obj=e['objective'])
        rows=model.addMConstr(K,x,e['sense'],e['rhs']);model.ObjCon=float(e['constant']);model.update()
        checks=dict(matrix=matrix_sha(model.getA().tocsr())==matrix_sha(K),
            lower=np.array_equal(x.LB,e['lower']),upper=np.array_equal(x.UB,e['upper']),types=np.array_equal(x.VType,e['types']),
            objective=np.array_equal(x.Obj,e['objective']),rhs=np.array_equal(rows.RHS,e['rhs']),
            sense=np.array_equal(rows.Sense,e['sense']),no_Start=np.all(np.asarray(x.Start)==gp.GRB.UNDEFINED))
        if not all(checks.values()):raise ValueError('SEEDLESS_K_NATIVE_READBACK_FAILED')
        _write(output/'K16_NATIVE_READBACK.json',dict(PASS=True,checks=checks,Native_calls=0,FULL_UB=None))
    finally:model.dispose()
    del packet;gc.collect()
    class NoNative:
        def remaining(self):return 1800.
        def record_external(self,*args,**kwargs):pass
    bank=IncumbentBank(case);case.mess_search_state=dict(epoch=1,reservoir={},seen_pools=set(),feedback=[])
    iterations=[];first_pools=None
    for epoch in (1,2):
        case.mess_search_state['epoch']=epoch;case.mess_iteration_output=output/f'ITERATION_{epoch:02d}'
        pools=generate(case,None,bank,NoNative())
        if pools is None:raise ValueError('TWO_DIVERSE_SEEDLESS_POOLS_REQUIRED')
        pools=pin_pools(case,None,bank,pools);signature=pool_identity(pools)
        if signature in case.mess_search_state['seen_pools']:raise ValueError('DUPLICATE_SEEDLESS_POOL')
        case.mess_search_state['seen_pools'].add(signature)
        packet=direct_joint(case,None,pools)
        if packet[3] is not None:raise ValueError('SEEDLESS_START_FABRICATED')
        native,_=_native_joint(case,NoNative(),packet,output/f'ITERATION_{epoch:02d}/JOINT',0.,native0=True)
        proof=packet[-1]
        if proof['original_charge_modes_retained']!=384:raise ValueError('ORIGINAL_384_MODES_LOST')
        _write(output/f'ITERATION_{epoch:02d}/DIRECT_PROOF.json',proof)
        iterations.append(dict(epoch=epoch,pool_sha=signature,pool_counts={u:len(p) for u,p in pools.items()},
            native_readback=native,rows=packet[0].shape[0],columns=packet[0].shape[1],charge_modes=384,
            MIP_Start_present=False,all_four_route_choices_independent=True))
        if first_pools is None:first_pools=pools
        del packet;gc.collect()
    # A structural STAY reference is only for equal-start/equal-pool Native0
    # formulation comparison. It is never solved, offered as UB or admitted.
    point=np.zeros(case.A.shape[1]);fixed=case.d['lower']==case.d['upper'];point[fixed]=case.d['lower'][fixed]
    ids,values=values_for(case,stationary_paths(case),lambda u,t:False);point[ids]=values
    for j,name in enumerate(map(str,case.d['names'])):
        if name.startswith('SOC['):point[j]=case.graph[3].initial
        if name=='rho_max':point[j]=10.
    old=subprocess.check_output(['git','show','v42.1-freeze-20261016:v42_integration/m_engine.py'],cwd=ROOT)
    snapshot=output/'V42_1_DIRECT_BASELINE_SOURCE.txt';snapshot.write_bytes(old)
    module=ModuleType('v42_integration._v42_1_direct_baseline');module.__file__=str(snapshot);module.__package__='v42_integration'
    sys.modules[module.__name__]=module;exec(compile(old,str(snapshot),'exec'),module.__dict__)
    baseline=copy(case);current=copy(case)
    for c in (baseline,current):c.__dict__.pop('_direct_static_cache',None)
    measurements=[]
    for repeat in (1,2):
        tick=perf_counter();left=module.direct_joint(baseline,point,first_pools);old_wall=perf_counter()-tick
        tick=perf_counter();right=direct_joint(current,point,first_pools);new_wall=perf_counter()-tick
        equal=(matrix_sha(left[0])==matrix_sha(right[0]) and domain_sha(left[1])==domain_sha(right[1])
            and matrix_sha(left[2])==matrix_sha(right[2]) and np.array_equal(left[3],right[3]))
        if not equal:raise ValueError('SAME_POOL_BASELINE_NEW_EXACT_MATRIX_OR_START_DRIFT')
        measurements.append(dict(repeat=repeat,baseline_wall_seconds=old_wall,current_wall_seconds=new_wall,
            exact_same_matrix_domain_lift_start=True,scope='DIRECT_CONSTRUCTION_ONLY_NOT_FULL_ARM_SPEEDUP'))
        del left,right;gc.collect()
    result=dict(status='PASS',Native_calls=0,blocked_Native_attempts=calls,K16=certificate,
        seedless_iterations=iterations,Direct_same_pool_AB=measurements,source_case=case.identity,
        case_sha=case.case_sha,source_sha=context['manifest']['source_sha'],before_memory=before,
        after_memory=memory_sample(),wall_seconds=perf_counter()-began,FULL_UB_certified=False,
        current_source_records=[file_record(ROOT/p) for p in ('v42_integration/m_engine.py','v42_integration/m_candidates.py',
            'v42_integration/table_v_k48.py','v42_integration/m_adaptive.py','v42_integration/table_v_mess.py')])
    if calls:raise ValueError('NATIVE0_NATIVE_CALL_ATTEMPTED')
    _write(output/'RESULT.json',result);print(json.dumps(dict(status='PASS',wall_seconds=result['wall_seconds'])),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();audit(args.execution,args.output)
