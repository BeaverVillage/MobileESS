"""Leased synthetic integration of repeated restricted LPs, full Phi, and P1."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
import numpy as np,scipy.sparse as sp
from fractions import Fraction
from v44.common import read,atomic,record,now,digest
from v44_recovery_r022 import operations as ops
from v44_recovery_r022.phase_stability import StableNative,policy,observe
from v44_recovery_r022.row_generation import compile_phase
from v44_recovery_r022.a2_continue import FrozenWeights
from v44.locks import coordinator,worker_slot,process_identity
from v44.execution import case_scope,native_stage
from v44 import q250_m4_v2 as q
from v42_may_campaign_native90.budget import DateBudget
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.stress_backend import materialize
from v42_a_stage_domain_v2.solver_policy import apply_policy
from v42_may_campaign_native90.a_stage import POLICY_PATH
from v42_a_stage_canary import phase
from unittest.mock import patch
import gurobipy as gp

permit=ops.validate();out=Path('D:/MobileESS_V44/development/r022/native_smoke');out.mkdir(exist_ok=False)
atomic(out/'PHASE.json',dict(lane='MAIN',UTC=now()))
request=read(ops.CAMPAIGN/'2025-05-02/B3/attempt001/A2/request.json')
request.update(case_root=str(out/'case'),campaign_root=str(out),root=str(out/'A2'),output=str(out/'A2/OUTPUT'),worker_slot=1,execution_permit=record(ops.PERMIT))
request=ops.decorate(request,permit);request['sources'].append(record(__file__));request['source_sha']=digest(request['sources'])
size=1000
s=LinearSnapshot(sp.eye(size,format='csr'),np.zeros(size),np.ones(size),np.full(size,'>'),np.ones(size),np.full(size,'C'),(Objective('rho',((0,Fraction(1)),),0),)).require()
state=dict(compact=s,reference=s,n=size,grows=tuple(range(size)),axes={},atlas=dict(rf=np.zeros(size,dtype=int),rf_names=np.array(['SYNTHETIC'])),prior_compact=np.zeros(size),metas={},data=None,domains=None,ledger=None)
frozen=FrozenWeights(s,state['grows'],None);namespace=dict(vars(phase),OUT=out,elastic_master=frozen.elastic_master,restricted=frozen.restricted)
namespace['expanded_point']=lambda state,point:np.asarray(point).copy()
namespace['partition']=lambda *args:({}, {})
def toy_full_pricing(*args):
    folder=args[-1];folder.mkdir(parents=True,exist_ok=True)
    result=dict(full_domain_phase1_lower_bound='1',no_negative_omitted_block_certified=True,synthetic_complete_domain_only=True)
    atomic(folder/'FULL_PRICING_RESULT.json',result);return result,[]
namespace['full_pricing']=toy_full_pricing
run=compile_phase(phase.run,namespace);calls=[]
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
                    budget.optimize(model,track='A',label='R022_LEASED_ROW_GENERATION_SMOKE',requested_seconds=10.)
                    rec=dict(status=model.Status,objective=model.ObjVal,native_seconds=model.Runtime,Work=model.Work)
                    raw={k:np.asarray(model.getAttr(k)) for k in ('X','Pi','RC')};calls.append(dict(component=component,rows=model.NumConstrs,cols=model.NumVars))
                    atomic(Path(folder)/'NATIVE_RESULT.json',rec)
                    return rec,raw
                finally:model.dispose()
        with patch.object(gp.Model,'optimize',observe(gp.Model.optimize)):
            run(StableNative(Native()),state,request['day'])
        trace=read(out/request['day']/'PHASE_I_TRACE.json')['trajectory']
        assert len(trace)>=3 and trace[0]['Phi']>0 and trace[-1]['Phi']<=1e-8
        assert read(out/request['day']/'PHASE_I_ZERO_CERTIFICATE.json')['PASS']
        assert read(out/request['day']/'P1_RESULT.json')['PASS']
        assert max(row['rows'] for row in trace)<=size and calls[-1]['component']=='ORIGINAL_P1'
        atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,lease_and_guard_verified=True,Native_seconds=budget.used(),Native_calls=len(budget.calls),
            production_A2_Native_consumed=0.,physical_simulation=False,synthetic_model=True,synthetic_P1_oracle=True,
            full_PhaseI_loop_executed=True,phase_trace=trace,model_sizes=calls,all_full_zero_and_raw_replays_PASS=True,
            full_campaign_success_not_claimed=True,permit=record(ops.PERMIT)))
        print(dict(PASS=True,Native_seconds=budget.used(),Native_calls=len(budget.calls),rowgen_solves=len(trace)))
