"""Two-variable leased native smoke, separate from the fresh production clock."""
from pathlib import Path
import sys,numpy as np,scipy.sparse as sp
from fractions import Fraction
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,atomic,record,now
from v44_recovery_r021 import operations as ops
from v44_recovery_r021.phase_stability import StableNative,policy,observe
from v44.locks import coordinator,worker_slot,process_identity
from v44.execution import case_scope,native_stage
from v44 import q250_m4_v2 as q
from v42_may_campaign_native90.budget import DateBudget
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.stress_backend import materialize
from v42_a_stage_domain_v2.solver_policy import apply_policy
from v42_may_campaign_native90.a_stage import POLICY_PATH
import gurobipy as gp
permit=ops.validate();out=Path('D:/MobileESS_V44/development/r021_native_smoke_02');out.mkdir(exist_ok=False)
atomic(out/'PHASE.json',dict(lane='MAIN',UTC=now()))
request=read(ops.CAMPAIGN/'2025-05-02/B3/attempt001/A2/request.json')
request.update(case_root=str(out/'case'),campaign_root=str(out),root=str(out/'A2'),output=str(out/'A2/OUTPUT'),worker_slot=1,execution_permit=record(ops.PERMIT))
request=ops.decorate(request,permit)
s=LinearSnapshot(sp.csr_matrix([[1.,1.]]),np.zeros(2),np.ones(2),np.array(['>']),np.ones(1),np.full(2,'C'),(Objective('Phi',((1,Fraction(1)),),0),)).require()
with coordinator(out) as lease:
    request['lease']=lease;who=dict(**process_identity(),day=request['day'],arm='B3',worker_slot=1)
    with worker_slot(request['day'],'B3',1,root=out,lease=lease),case_scope(request,lease,who),q.install(ops.PERMIT),native_stage(request):
        budget=DateBudget(out/'NATIVE_LEDGER.json',native_limit=10.)
        class Native:
            def remaining(self):return budget.remaining()
            def solve(self,snapshot,folder,component):
                model,objs=materialize(snapshot,request['day']);model.setObjective(objs[0][1],gp.GRB.MINIMIZE)
                try:
                    policy(apply_policy)(model,read(POLICY_PATH),gp)
                    budget.optimize(model,track='A',label='R021_LEASED_STABILITY_SMOKE',requested_seconds=10.)
                    rec=dict(status=model.Status,objective=model.ObjVal,native_seconds=model.Runtime)
                    raw={k:np.asarray(model.getAttr(k)) for k in ('X','Pi','RC')}
                    atomic(Path(folder)/'NATIVE_RESULT.json',rec)
                    assert model.Params.Method==1 and model.Params.NumericFocus==3 and model.Params.Threads==1
                    return rec,raw
                finally:model.dispose()
        facade=StableNative(Native());facade.admit_prior(s,np.array([0.,1.]))
        result,raw=facade.solve(s,out/'SMOKE','PHASE_I')
        assert result['status']==2 and raw['X'][1]==0 and len(budget.calls)==1
        atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,lease_and_guard_verified=True,Native_seconds=budget.used(),Native_calls=len(budget.calls),
            actual_Method=1,actual_NumericFocus=3,actual_Threads=1,previous_primal_seed_admitted=True,original_raw_replay_PASS=True,
            production_A2_Native_consumed=0.,physical_simulation=False,small_synthetic_model=True,full_campaign_stability_not_yet_proven=True,
            permit=record(ops.PERMIT)))
        print(read(out/'RESULT.json'))
