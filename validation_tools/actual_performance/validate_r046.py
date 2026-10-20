import v44_recovery_r046
from v44_recovery_r046 import operations as op
from v44_recovery_r046.planning import a1_scope
from v44.common import read,record,verify,atomic,now
from v44.checkpoints import ledger_state
from v44.config import axis
from pathlib import Path
import pytest,json,uuid

with op.core.week.bindings():
    op.core.seq.authority();diagnosis=read(op.OPS/'R046_NUMERICAL_DIAGNOSIS.json')
    assert diagnosis['May11_A1']['original_primal']['PASS'] is False and diagnosis['May11_A1']['original_dual_sign']['PASS']
    assert diagnosis['May12_A2']['integer_residual']==0 and diagnosis['May12_A2']['UB_minus_LB']<0
    assert diagnosis['May12_A2']['strict_voltage_parent'] and diagnosis['May12_A2']['model_identity_matches']
    _,m1,a2_account=op.validate_parent()
    parent=op.CAMPAIGN/'2025-05-11/B1/attempt002/A1'
    old=ledger_state(parent/'NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    assert abs(old['measured']-.4100000858306885)<1e-8
    with a1_scope(parent):
        from v42_may_campaign_native90.budget import DateBudget
        from v44_recovery_r029 import phase_limit
        b=DateBudget(op.OPS/('R046_NATIVE0_BUDGET_CHECK_'+uuid.uuid4().hex+'.json'),native_limit=5400.)
        class Native:
            def remaining(self):return b.remaining()
        with phase_limit.phase_scope(Native(),op.OPS/'R046_NATIVE0_PHASE_CHECK') as limited:
            assert limited.context['used']==old['measured']
            assert abs(limited.remaining()-(1500-old['measured']))<1e-7
            phase_remaining=limited.remaining()
        assert b.used()==old['measured'] and len(b.calls)==1
    state=read(op.STATE);plans=[]
    for j in state['jobs']:
        r=read(j['prepare_request']);assert (r['day'],r['arm'])==op.core.seq.key(j) and r['axis']==axis(j['day'])
        root=Path(j['case_root'])
        if op.core.seq.key(j) in op.REPAIRS:
            attempts=list(root.parent.glob('attempt[0-9][0-9][0-9]'))
            root=root.parent/f"attempt{max(int(p.name[-3:]) for p in attempts)+1:03d}";assert not root.exists()
        plans.append(dict(day=j['day'],arm=j['arm'],case_root=str(root),original_request=j['prepare_request']))
    code=pytest.main(['-q','-p','no:cacheprovider','tests/test_v44_recovery_r046.py','tests/test_v44_recovery_r045.py',
        'tests/test_v44_recovery_r044.py','tests/test_v44_week2_sequence.py','--junitxml='+str(op.OPS/'R046_REGRESSION.xml')])
    if code:raise SystemExit(code)
    value=dict(PASS=True,UTC=now(),Native_calls=0,all_28_request_axes_verified=True,
        A1_inherited_Native_seconds=old['measured'],A1_remaining_PhaseI_Native_seconds=phase_remaining,
        A2_inherited_Native_seconds=a2_account['measured'],completed_M1_Native_seconds=m1['Native_seconds'],
        preserve_current_Actual=True,repair_Planning_workers=1,next_Actual_workers=7,
        regression=record(op.OPS/'R046_REGRESSION.xml'),sources=op.sources())
    atomic(op.VALIDATION,value);atomic(op.OPS/'R046_RESTART_PLAN.json',dict(UTC=now(),plan=plans))
    print(json.dumps(value,indent=2))
