"""User-requested equal-budget Barrier / dual simplex Root LP comparison.

No integer search, candidate generation, production restart or bound promotion.
Presolve the unchanged saved first Joint MIP once, then relax the remaining
integrality and copy that identical LP into two cold, single-thread solves.
"""
from pathlib import Path
from time import perf_counter
import argparse
import numpy as np
from scipy import sparse

from . import barrier
from .common import RUNTIME,read,atomic,record,verify,digest,now

ROOT=RUNTIME/'v43_planning_svr12_actual_v1/MAY02_ROOT_LP_COMPARE002'
PERMIT=RUNTIME/'v43_planning_svr12_actual_v1/ROOT_LP_COMPARE_PERMIT002.json'


def authorization():
    return dict(policy='V44_MAY02_EQUAL_ROOT_LP_BARRIER_DUAL_V1',source=record(__file__),
        methods=[2,1],seconds_per_method=300.,Threads=1,production_setting_changed=False,
        day='2025-05-02',MIP_optimization=False,independent_cold_copies=True,
        common_MIP_presolve=True,per_method_Presolve=0,same_fixed_logical_processor=0)


def make_permit():
    value=barrier.validate()
    value.update(root_lp_comparison=authorization(),comparison_sha=digest(authorization()),
        direct_comparison_instruction='Barrier가 빠른지 Dual Simplex가 빠른지 5월 2일 Root LP 안풀린 모델로 검증')
    if PERMIT.exists():raise FileExistsError('ROOT_COMPARISON_NEW_PERMIT_REQUIRED')
    atomic(PERMIT,value)
    return value


def validate():
    value=barrier.validate(PERMIT)
    if value.get('root_lp_comparison')!=authorization() or value.get('comparison_sha')!=digest(authorization()):
        raise PermissionError('EXACT_USER_ROOT_COMPARISON_REQUIRED')
    return value


def primal_check(model):
    import gurobipy as gp
    if not model.SolCount:return dict(primal_point_available=False)
    x=np.asarray(model.X);A=model.getA().tocsr();rhs=np.asarray(model.RHS)
    residual=A@x-rhs;sense=np.asarray(model.Sense)
    violation=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
    bound=max(0.,float(np.max(np.asarray(model.LB)-x)),float(np.max(x-np.asarray(model.UB))))
    return dict(primal_point_available=True,row_violation=max(0.,float(np.max(violation))),
        bound_violation=bound,objective=float(np.asarray(model.Obj)@x+model.ObjCon),
        solver_status_OPTIMAL=model.Status==gp.GRB.OPTIMAL)


def run(output=ROOT):
    import gurobipy as gp
    from .locks import coordinator,worker_slot,process_identity
    from .execution import case_scope,native_stage
    from .planning import scope as planning_scope
    from .daily import load_aidc
    from .frozen.v43_mess.library import load
    from .frozen.v43_mess.performance import install as caches
    from .m_restore import restore
    from v42_may_campaign_native90.budget import DateBudget
    from v42_may_campaign_native90.execution import native_scope
    import psutil
    permit=validate();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    process=psutil.Process();old_affinity=process.cpu_affinity();process.cpu_affinity([0])
    atomic(output/'CPU_AFFINITY_CONTROL.json',dict(UTC=now(),**process_identity(),
        previous_affinity=old_affinity,comparison_affinity=process.cpu_affinity(),
        both_methods_same_logical_processor=True,set_before_first_Native_call=True,production_affinity_changed=False))
    old=RUNTIME/'v43_planning_svr12_actual_v1/campaign001'
    parent=old/'2025-05-02/B2/attempt001/M1'
    request=read(parent/'request.json')
    request.update(scientific_case_root=read(parent/'BINARY_STAGE_CHECKPOINT.json')['key']['case_root'],
        case_root=str(output/'case'),campaign_root=str(output),root=str(output/'case/M1'),output=str(output/'case/M1'),
        execution_permit=record(PERMIT),execution_policy_sha=permit['execution_policy_sha'],
        numerical_policy_sha=permit['numerical_policy_sha'],comparison_sha=permit['comparison_sha'])
    Path(request['output']).mkdir(parents=True)
    atomic(output/'PHASE.json',dict(lane='B2',UTC=now()))
    with coordinator(output) as lease:
        request['lease']=lease;who=dict(**process_identity(),day=request['day'],arm='B2',worker_slot=request['worker_slot'])
        atomic(output/'START.json',dict(who,UTC=now(),authorization=authorization(),lease=lease))
        with worker_slot(request['day'],'B2',request['worker_slot'],root=output,lease=lease),case_scope(request,lease,who),barrier.install(PERMIT),native_stage(request),planning_scope(request['day']):
            modules=load();engine=modules['m_engine']
            aidc,_=load_aidc(old/'references/2025-05-02','2025-05-02')
            # cap300.install has already repaired only the original-grid restore binding.
            from .m_restore import restore as original_grid_restore
            case=original_grid_restore(parent,Path(request['output']),request,aidc,modules)
            caches(case,modules)
            pool=old/'2025-05-02/B2/attempt003/M1/COMMON_M_PR222/ITERATION_0001/POOL.json'
            packet=engine.direct_joint(case,None,read(pool)['pools'])
            A,d,_,start,proof=packet
            if start is not None:raise ValueError('COMPARISON_MUST_BE_COLD')
            source=gp.Model('MAY02_ORIGINAL_FIRST_JOINT')
            frozen=root=None
            try:
                for key,value in engine.APPROVED_JOINT_PARAMETERS.items():setattr(source.Params,key,value)
                source.Params.OutputFlag=0
                x=source.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective'])
                x.VarName=d['names'].tolist();source.ObjCon=float(d['constant'])
                rows=source.addMConstr(A,x,d['sense'],d['rhs']);rows.ConstrName=d['row_names'].tolist();source.update()
                source_proof=dict(matrix=engine.matrix_sha(source.getA())==engine.matrix_sha(A),
                    rhs=np.array_equal(source.RHS,d['rhs']),bounds=np.array_equal(source.LB,d['lower']) and np.array_equal(source.UB,d['upper']),
                    objective=np.array_equal(source.Obj,d['objective']) and source.ObjCon==float(d['constant']),
                    types=np.array_equal(source.VType,d['types']),fingerprint=hex(source.Fingerprint))
                if not all(v for k,v in source_proof.items() if k!='fingerprint'):raise ValueError('ORIGINAL_FIRST_POOL_MODEL_DRIFT')
                began=perf_counter()
                with native_scope(source,component='UB',track='M'):
                    frozen=source.presolve()
                presolve_seconds=perf_counter()-began
                root=frozen.relax();root.update()
                if any(t!='C' for t in root.VType):raise ValueError('ROOT_LP_INTEGRALITY_NOT_RELAXED')
                root_A=root.getA().tocsr();sparse.save_npz(output/'ROOT_LP_A.npz',root_A)
                arrays={k:np.asarray(root.getAttr(v)) for k,v in [('lower','LB'),('upper','UB'),('objective','Obj'),('rhs','RHS'),('sense','Sense'),('names','VarName')]}
                np.savez_compressed(output/'ROOT_LP_DATA.npz',**arrays,constant=root.ObjCon)
                root_sha=engine.matrix_sha(root_A)
                manifest=dict(original_case_sha=case.case_sha,original_pool=record(pool),original_joint=source_proof,
                    common_MIP_presolve_seconds=presolve_seconds,rows=root.NumConstrs,columns=root.NumVars,nonzeros=root.NumNZs,
                    matrix_sha=root_sha,files=[record(output/'ROOT_LP_A.npz'),record(output/'ROOT_LP_DATA.npz')],
                    same_presolved_root_for_both_methods=True,per_method_Presolve=0,production_bound_or_incumbent=False)
                atomic(output/'ROOT_LP_IDENTITY.json',manifest)
                results=[]
                for method,label in ((2,'BARRIER'),(1,'DUAL_SIMPLEX')):
                    validate();folder=output/label;folder.mkdir()
                    model=root.copy()
                    try:
                        for key,value in engine.APPROVED_JOINT_PARAMETERS.items():setattr(model.Params,key,value)
                        model.Params.Method=method;model.Params.Presolve=0;model.Params.MIPGap=.03
                        model.Params.OutputFlag=1;model.Params.LogFile=str(folder/'SOLVER.log')
                        checks=dict(matrix=engine.matrix_sha(model.getA())==root_sha,
                            rhs=np.array_equal(model.RHS,arrays['rhs']),lower=np.array_equal(model.LB,arrays['lower']),
                            upper=np.array_equal(model.UB,arrays['upper']),objective=np.array_equal(model.Obj,arrays['objective']),
                            types=all(t=='C' for t in model.VType),constant=model.ObjCon==root.ObjCon,
                            cold=model.SolCount==0)
                        if not all(checks.values()):raise ValueError('UNEQUAL_ROOT_LP_COMPARISON')
                        budget=DateBudget(folder/'NATIVE_LEDGER.json',native_limit=300.,
                            progress=lambda value,f=folder:atomic(f/'progress.json',dict(value,UTC=now())))
                        budget.optimize(model,track='M',label='ROOT_LP_COMPARE_'+label,requested_seconds=300.)
                        result=dict(method=method,label=label,Native_Runtime=model.Runtime,Work=model.Work,
                            status=model.Status,OPTIMAL=model.Status==gp.GRB.OPTIMAL,Simplex_iterations=model.IterCount,
                            Barrier_iterations=model.BarIterCount,SolCount=model.SolCount,parameters=dict(Method=method,
                                Threads=1,Presolve=0,TimeLimit=300.,FeasibilityTol=1e-9,OptimalityTol=1e-9,NumericFocus=3,ScaleFlag=2),
                            original_data_readback=checks,primal_check=primal_check(model),
                            root_matrix_sha=root_sha,production_policy_changed=False)
                        if model.SolCount:np.savez_compressed(folder/'RELAXED_ROOT_POINT.npz',point=np.asarray(model.X))
                        atomic(folder/'RESULT.json',result);results.append(result)
                    finally:model.dispose()
                completed=[r for r in results if r['OPTIMAL']]
                winner=min(completed,key=lambda r:r['Native_Runtime'])['label'] if completed else None
                result=dict(UTC=now(),authorization=authorization(),identity=manifest,methods=results,
                    winner_among_OPTIMAL=winner,completed_methods=len(completed),
                    production_policy_changed=False,FULL_integer_incumbent_or_Global_LB=False,
                    limitation='Exact common MIP-presolved continuous root, without subsequent MIP cuts, heuristics or integer search.')
                atomic(output/'RESULT.json',result);return result
            finally:
                if root is not None:root.dispose()
                if frozen is not None:frozen.dispose()
                source.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    if not args.execute:raise PermissionError('EXPLICIT_ROOT_COMPARISON_REQUIRED')
    run(args.root)


if __name__=='__main__':main()
