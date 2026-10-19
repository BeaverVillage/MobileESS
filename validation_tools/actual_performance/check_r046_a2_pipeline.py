import v44_recovery_r046
from pathlib import Path
from types import FunctionType
from fractions import Fraction
import json
from v44_recovery_r046 import operations as op,numerical
from v44_recovery_r029.integer_repair import install as integer
from v44_recovery_r029.voltage_policy import install as voltage
from v44_recovery_r038 import operations as inherited
from v44 import a2
from v44.common import read,record,atomic,now
from v44.execution import case_scope
from v44.locks import process_identity
from v42_may_campaign_native90.budget import DateBudget
from v42_may_campaign_native90.preflight import native_zero

folder=op.OPS/'R046_NATIVE0_A2_PIPELINE';folder.mkdir(exist_ok=False)
request=read(op.PARENT/'A2/request.json');m1=read(op.PARENT/'M1/RESULT.json')
request.update(root=str(folder/'A2'),output=str(folder/'A2/OUTPUT'),case_root=str(folder),M1_result=record(op.PARENT/'M1/RESULT.json'))
Path(request['root']).mkdir();b=DateBudget(folder/'A2/NATIVE_RUNTIME_LEDGER.json');seen=[]
who=dict(**process_identity(),worker_slot=1,day=request['day'],arm=request['arm'])
with op.core.week.bindings(),inherited.previous.install(),integer(),voltage(),numerical.scope(),native_zero() as denied,case_scope(request,read(op.STATE)['lease'],who):
    with a2.scope(request,m1) as run:
        factory=run.__globals__['_native']
        def native(*args,**kwargs):
            instance=factory(*args,**kwargs)
            def solve(snapshot,output,component):
                lb=Fraction(read(op.PARENT/'A2/OUTPUT/P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'])
                j=next(iter(snapshot.objectives[0].coefficients()))
                assert all(snapshot.vtypes=='C') and snapshot.lower[j]==float(lb)
                assert b.used()==15.969001770019531 and instance.incumbent_callback is None
                seen.append(dict(day=request['day'],rows=snapshot.matrix.shape[0],columns=snapshot.matrix.shape[1],
                    objective_floor=float(lb),inherited_Native_seconds=b.used(),repair_snapshot_sha=snapshot.fingerprint()))
                raise RuntimeError('R046_EXPECTED_NATIVE0_BOUNDARY')
            instance.solve=solve;return instance
        fn=FunctionType(run.__code__,dict(run.__globals__,_native=native,_dump_state=lambda p,s:None),run.__name__,run.__defaults__,run.__closure__)
        result=fn(request,b)
        assert result.get('error')=="RuntimeError('R046_EXPECTED_NATIVE0_BOUNDARY')",result
        assert len(seen)==1 and not denied
        value=dict(PASS=True,UTC=now(),Native_calls=0,actual_May12_A2_restoration_and_physical_model_verified=True,
            stopped_before_any_optimize=True,expected_boundary=seen[0])
        atomic(op.OPS/'R046_A2_PIPELINE_VERIFIED.json',value);print(json.dumps(value,indent=2))
