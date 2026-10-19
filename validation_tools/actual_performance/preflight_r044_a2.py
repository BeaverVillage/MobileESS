"""Exercise the real restored A2 pipeline up to Native admission, without optimize."""
import v44_recovery_r044
from pathlib import Path
from unittest.mock import patch
from types import FunctionType
from fractions import Fraction
import json,numpy as np
from v44_recovery_r044 import operations as op,numerical
from v44_recovery_r029.integer_repair import install as integer
from v44_recovery_r029.voltage_policy import install as voltage
from v44_recovery_r038 import operations as inherited
from v44 import a2
from v44.common import read,atomic,record,digest,now
from v44.execution import case_scope
from v44.locks import process_identity
from v42_may_campaign_native90.budget import DateBudget
from v42_may_campaign_native90.preflight import native_zero

folder=op.OPS/'R044_NATIVE0_PIPELINE_CHECK';folder.mkdir(exist_ok=False)
request=read(op.PARENT/'A2/request.json');m1=read(op.PARENT/'M1/RESULT.json')
request.update(case_root=str(folder),root=str(folder/'A2'),output=str(folder/'A2/OUTPUT'),
    M1_result=record(op.PARENT/'M1/RESULT.json'))
request['sources']+=op.sources()+[record(op.PERMIT)];request['source_sha']=digest(request['sources'])
Path(request['root']).mkdir();budget=DateBudget(folder/'A2/NATIVE_RUNTIME_LEDGER.json')
seen=[];who=dict(**process_identity(),worker_slot=1,day=request['day'],arm=request['arm'])
with op.week.bindings(),inherited.previous.install(),integer(),voltage(),numerical.scope(),native_zero() as denied,case_scope(request,read(op.STATE)['lease'],who):
    with a2.scope(request,m1) as run:
        factory=run.__globals__['_native']
        def native(*args,**kwargs):
            instance=factory(*args,**kwargs)
            def solve(snapshot,output,component):
                lb=Fraction(read(op.PARENT/'A2/OUTPUT/P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'])
                j=next(iter(snapshot.objectives[0].coefficients()))
                assert all(snapshot.vtypes=='C') and snapshot.lower[j]==float(lb)
                assert budget.used()==12.59800386428833 and budget.remaining()==5400-budget.used()
                assert instance.incumbent_callback is None
                seen.append(dict(component=component,rows=snapshot.matrix.shape[0],columns=snapshot.matrix.shape[1],
                    repair_fingerprint=snapshot.fingerprint(),certified_objective_floor=float(lb),
                    inherited_Native_seconds=budget.used(),remaining_Native_seconds=budget.remaining(),
                    original_callback_disabled_for_continuous_LP=True))
                raise RuntimeError('R044_EXPECTED_NATIVE0_PREFLIGHT_BOUNDARY')
            instance.solve=solve;return instance
        ns=dict(run.__globals__,_native=native,_dump_state=lambda p,s:None)
        checked=FunctionType(run.__code__,ns,run.__name__,run.__defaults__,run.__closure__)
        result=checked(request,budget)
        assert result.get('error')=="RuntimeError('R044_EXPECTED_NATIVE0_PREFLIGHT_BOUNDARY')",result
        assert len(seen)==1 and not denied
        value=dict(PASS=True,UTC=now(),Native_calls=0,real_restored_A2_pipeline_reached_native_admission=True,
            original_native_factory_and_physical_model_built=True,expected_boundary=seen[0],
            authorization=record(op.PERMIT),original_result_files_modified=False)
        atomic(op.OPS/'R044_NATIVE0_PIPELINE_CHECK.json',value);print(json.dumps(value,indent=2))
