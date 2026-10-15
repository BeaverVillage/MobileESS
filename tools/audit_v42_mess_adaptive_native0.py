"""Actual May01 FULL matrix/Direct readback. Never optimizes or certifies UB."""
import os
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[_key]='1'
from pathlib import Path
import sys,json,gc
from types import SimpleNamespace
from time import perf_counter
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def audit(execution,output):
    from v42_integration.table_v_run import load_context,budget,current_build_admission
    from v42_integration.table_v_mess import TableVMessStages
    from v42_integration.m_engine import PathGraph,pin_pools,direct_joint,_native_joint,_write,file_record
    from v42_integration.m_candidates import generate
    from v42_integration.m_adaptive import pool_identity
    from v42_common_mess.fixed_pattern import values_for,stationary_paths
    from v42_integration.table_v_memory import memory_sample
    import gurobipy as gp
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    calls=[]
    def forbidden(*a,**k):calls.append('FORBIDDEN');raise AssertionError('MESS_NATIVE0_REAL_NATIVE_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS','feasRelax','feasRelaxS'):setattr(gp.Model,name,forbidden)
    before=memory_sample();began=perf_counter();context=load_context(execution)
    main=budget(execution,'PLANNING');factory=TableVMessStages(context,main)
    read=lambda name:json.loads((Path(execution)/name).read_text(encoding='utf8'))
    ref,accept=read('REFERENCE_RESULT.json'),read('REFERENCE_ACCEPTANCE.json')
    admission=current_build_admission(main,arm='B2',stage='M1',operation='CURRENT_M_NATIVE0_BUILD')
    case=factory.prepare('B2','M1',ref,accept,output/'CURRENT_M',build_admission=admission,
        progress=lambda value:print('M_NATIVE0',value,flush=True))
    graph=PathGraph(case);point=np.zeros(case.A.shape[1]);point[case.d['lower']==case.d['upper']]=case.d['lower'][case.d['lower']==case.d['upper']]
    ids,values=values_for(case,stationary_paths(case),lambda u,t:False);point[ids]=values
    for j,name in enumerate(map(str,case.d['names'])):
        if name.startswith('SOC['):point[j]=case.graph[3].initial
        if name=='rho_max':point[j]=10.
    # Structural center is not an admitted UB. Readback proves substitution,
    # axes and all original rows/modes; production must obtain a FULL seed.
    bank=SimpleNamespace(graph=graph,best=(point,{'Global_UB':10.}),best_moving=None)
    case.mess_search_state=dict(epoch=1,reservoir={},seen_pools=set(),feedback=[])
    rows=[]
    class NoNative:
        def remaining(self):return 1800.
        def record_external(self,*a,**k):pass
    for epoch in (1,2):
        case.mess_search_state['epoch']=epoch;case.mess_iteration_output=output/f'ITERATION_{epoch:02d}'
        pools=generate(case,point,bank,NoNative())
        if pools is None:raise ValueError('TWO_DIFFERENT_CURRENT_M_POOLS_REQUIRED')
        pools=pin_pools(case,point,bank,pools);signature=pool_identity(pools)
        if signature in case.mess_search_state['seen_pools']:raise ValueError('DUPLICATE_CURRENT_M_POOL')
        case.mess_search_state['seen_pools'].add(signature)
        packet=direct_joint(case,point,pools)
        native,_=_native_joint(case,NoNative(),packet,output/f'ITERATION_{epoch:02d}/JOINT',0.,native0=True)
        proof=packet[-1];_write(output/f'ITERATION_{epoch:02d}/DIRECT_PROOF.json',proof)
        if proof['original_charge_modes_retained']!=384:raise ValueError('ALL_384_CHARGE_MODES_REQUIRED')
        rows.append(dict(epoch=epoch,pool_sha=signature,pool_counts={u:len(p) for u,p in pools.items()},
            original_modes=384,original_rows=case.A.shape[0],direct_rows=packet[0].shape[0],
            direct_columns=packet[0].shape[1],native_readback=native,static_cache_hit=proof['static_cache_hit']))
        del packet;gc.collect()
    result=dict(status='PASS_NATIVE0_ACTUAL_MATRIX_READBACK',iterations=rows,
        source_identity=context['manifest']['identity'],source_sha=context['manifest']['source_sha'],case_sha=case.case_sha,
        actual_original_FULL_shape=list(case.original_A.shape),actual_original_FULL_NNZ=case.original_A.nnz,
        selected_shape=list(case.A.shape),selected_NNZ=case.A.nnz,
        Native_calls=0,blocked_real_native_attempts=calls,production_UB_certified=False,
        scope='STRUCTURAL_CENTER_NOT_A_FULL_FEASIBLE_RESULT_OR_PLANNING_SOLUTION',
        actual_M2_matrix_requires_current_optimized_A2=True,wall_seconds=perf_counter()-began,
        before_memory=before,after_build_memory=memory_sample())
    case=factory=context=bank=point=None;gc.collect();result['released_memory']=memory_sample()
    if calls:raise ValueError('NATIVE0_OPTIMIZE_ATTEMPT')
    _write(output/'RESULT.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.execution,a.output)
