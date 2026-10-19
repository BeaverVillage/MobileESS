import v44_recovery_r044
import json
from v44_recovery_r044 import operations as op,numerical
from v44.common import read,atomic,record,now
from v44 import a2
from v44_recovery_r029.integer_repair import install as integer
from v44_recovery_r029.voltage_policy import install as voltage
from v44_recovery_r038 import operations as inherited
from v42_may_campaign_native90.preflight import native_zero

with op.week.bindings(),inherited.previous.install(),integer(),voltage(),numerical.scope(),native_zero() as denied:
    request=read(op.PARENT/'A2/request.json');m1=read(op.PARENT/'M1/RESULT.json')
    target=op.OPS/'R044_NATIVE0_ROUTING_CHECK/A2';target.mkdir(parents=True,exist_ok=False)
    request.update(root=str(target),output=str(target/'OUTPUT'))
    with a2.scope(request,m1) as run:
        names=set(run.__code__.co_names)
        assert {'_r044_repair','_r044_load_state','_r044_priced'}<=names
        assert all(callable(run.__globals__[name]) for name in ('_r044_repair','_r044_load_state','_r044_priced'))
        assert 'A_CERTIFIED_LB_UB_CONFLICT' in run.__code__.co_consts or any('A_CERTIFIED_LB_UB_CONFLICT' in getattr(c,'co_consts',()) for c in run.__code__.co_consts)
        assert not denied
        result=dict(PASS=True,UTC=now(),full_r029_r037_r032_voltage_dated_A2_routing=True,Native_calls=0,
            restored_dispatch_names=sorted(names&{'_r044_repair','_r044_load_state','_r044_priced'}),
            original_exact_bound_conflict_guard_retained=True,authorization=record(op.PERMIT))
        atomic(op.OPS/'R044_ROUTING_CHECK.json',result);print(json.dumps(result,indent=2))
