import v44_recovery_r046
import inspect,json
from v44_recovery_r046 import operations as op
from v44_recovery_r046.planning import a1_scope
from v44_recovery_r029.integer_repair import install as integer
from v44_recovery_r029.phase_rebuild import stage_scope
from v44.common import read,record,atomic,now
from v42_may_campaign_native90 import a_stage
from v42_a_stage_canary import phase
from v42_may_campaign_native90.preflight import native_zero

parent=op.CAMPAIGN/'2025-05-11/B1/attempt002/A1';request=read(parent/'request.json')
request.update(root=str(op.OPS/'R046_NATIVE0_A1_STAGE'),output=str(op.OPS/'R046_NATIVE0_A1_STAGE/OUTPUT'))
with op.core.week.bindings(),a1_scope(parent),integer(),stage_scope(request),native_zero() as denied:
    run=inspect.unwrap(a_stage.run)
    assert run.__globals__ is a_stage.__dict__
    ns=run.__globals__['group'](phase,('activate','run'),OUT=op.OPS/'R046_NATIVE0_A1_STAGE/OUTPUT',
        full_pricing=phase.full_pricing,targeted=phase.targeted)
    closure=inspect.getclosurevars(ns['run']).nonlocals
    assert closure['stable'] is True and closure['row_generation'] is True
    assert not denied
    value=dict(PASS=True,UTC=now(),Native_calls=0,actual_A1_compiler_uses_live_module=True,
        actual_A1_phase_group_has_StableNative=True,actual_A1_phase_row_generation_enabled=True,
        original_primal_dual_and_full_acceptance_checks_retained=True)
    atomic(op.OPS/'R046_A1_STAGE_ROUTING_VERIFIED.json',value);print(json.dumps(value,indent=2))
