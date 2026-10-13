"""Native build/readback before source freeze, never Optimize."""
import gc
from tools.global_local_multistart1800.adapter import *
from tools.u4_primal_alns.pilot import PARAMS

def verify_build(case,point,spec,lower,upper,A,rhs,out):
    import gurobipy as gp
    from v42_common_mess.model import build
    out.mkdir(parents=True,exist_ok=True);before=r.memory();case.point=None
    model,x,identity=build(case,out,lower=lower,upper=upper,start=point,spec=None,numeric_parameters=dict(PARAMS,Method=2))
    try:
        lam=model.addMVar(spec['lambda_count'],lb=0,ub=1,vtype='B',obj=0);lam.Start=np.asarray(spec['lambda_Start'])
        combined=gp.MVar.fromlist(list(x.tolist())+list(lam.tolist()));model.addMConstr(A,combined,'=',rhs);model.update()
        actual=model.getA().tocsr();r0,c0=case.A.shape
        checks=dict(source_prefix=v.matrix_sha(actual[:r0,:c0].tocsr())==v.matrix_sha(case.A) and actual[:r0,c0:].nnz==0,
            link_matrix=v.matrix_sha(actual[r0:].tocsr())==v.matrix_sha(A),lambda_binary=model.NumBinVars==9322+spec['lambda_count'],
            raw_Start=np.array_equal(x.Start,point),lambda_Start=np.array_equal(lam.Start,spec['lambda_Start']),
            center_links=np.array_equal(A@np.r_[x.Start,lam.Start],rhs),source_common_readback=all(identity['checks'].values()),
            all_four_selectable=len(spec['pools'])==4,one_Start=model.NumStart==1)
        assert all(checks.values());del actual;gc.collect()
        gate=r.admit(before,r.memory());assert gate['PASS'];write(out/'POST_BUILD_NATIVE0_RESOURCE_GATE.json',gate)
        write(out/'JOINT_NATIVE0_READBACK.json',dict(PASS=True,checks=checks,Optimize_calls=0,source_Start_SHA=v.vector_sha(np.asarray(x.Start)),lambda_Start=spec['lambda_Start']))
    finally:model.dispose()
