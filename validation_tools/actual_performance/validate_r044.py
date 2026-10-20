"""Read-only real checkpoint validation plus focused Native0 regressions."""
import v44_recovery_r044
import gzip,pickle,json,ast
from pathlib import Path
from fractions import Fraction
import numpy as np
import pytest
from v44.common import read,record,atomic,now
from v44_recovery_r044 import operations as op
from v44_recovery_r044.numerical import fixed_model,adapt_tree
from v42_a_stage_practical.integer_model import restore_types
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_lexfull.runner import objective_value
from v44.frozen.v43_a2 import adapter
from v42_may_campaign_native90 import a_stage

def main():
    with op.week.bindings():
        op.sequence.authority();old,m1,account=op.validate_parent()
        parent=op.PARENT/'A2/OUTPUT'
        with gzip.open(parent/'STATIC/P1_CLOSED_STATE.pkl.gz','rb') as stream:state=pickle.load(stream)
        typed,_=restore_types(state,state['global_types'])
        native=read(parent/'P1/INTEGER_CONTROL/NATIVE_RESULT.json')
        with np.load(native['raw_attributes']['path'],allow_pickle=False) as z:x=z['X'].copy()
        lb=Fraction(read(parent/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'])
        ub=objective_value(typed,x,'rho');before=primal_replay(typed,x)
        fixed,integer,residual,j=fixed_model(typed,x,lb)
        assert typed.fingerprint()==read(parent/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json')['original_snapshot_sha256']
        assert residual==0 and ub<lb and before['PASS'] and before['max_row_violation']>0
        assert np.array_equal(fixed.lower[integer],x[integer]) and np.array_equal(fixed.upper[integer],x[integer])
        tree=adapt_tree(adapter.source_tree(a_stage,'run'));compile(ast.fix_missing_locations(ast.Module(body=[tree],type_ignores=[])),'<r044-real-source>','exec')
        tests=['tests/test_v44_recovery_r044.py','tests/test_v44_week2_dispatch.py','tests/test_v44_week2_sequence.py',
               'tests/test_v44_recovery_r029_repairs.py']
        code=pytest.main(['-q','-p','no:cacheprovider',*tests,'--junitxml='+str(op.OPS/'R044_REGRESSION.xml')])
        if code:raise SystemExit(code)
        value=dict(PASS=True,UTC=now(),Native_calls=0,real_closed_checkpoint_validated=True,
            integer_model_sha=typed.fingerprint(),rows=typed.matrix.shape[0],columns=typed.matrix.shape[1],
            saved_integer_residual=residual,original_rows=before,UB=float(ub),LB=float(lb),UB_minus_LB=float(ub-lb),
            inherited_A2_Native_seconds=account['measured'],M1_Native_seconds=m1['Native_seconds'],
            fixed_M1_plan_sha=m1['MESS_plan']['plan_sha'],original_constraints_tolerances_unchanged=True,
            regression=record(op.OPS/'R044_REGRESSION.xml'),sources=op.sources())
        atomic(op.VALIDATION,value);print(json.dumps({k:v for k,v in value.items() if k!='sources'},indent=2))

if __name__=='__main__':main()
