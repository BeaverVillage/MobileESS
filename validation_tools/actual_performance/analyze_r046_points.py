import v44_recovery_r045
import gzip,pickle,json
from pathlib import Path
from fractions import Fraction
import numpy as np
from scipy.sparse import load_npz
from v44.common import read,atomic,record,now
from v44_recovery_r045 import operations as op
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_practical.integer_model import restore_types
from v42_a_stage_lexfull.runner import objective_value

p=op.CAMPAIGN/'2025-05-11/B1/attempt002/A1/OUTPUT'
result=read(p/'PHASE_I/S0/NATIVE_RESULT.json');static=Path(result['raw_attributes']['path']).parent
with np.load(static/'ATTRIBUTES.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
s=LinearSnapshot(load_npz(static/'MATRIX.npz'),a['lower'],a['upper'],a['senses'],a['rhs'],a['vtypes'],
    (Objective('Phi',tuple((int(j),Fraction(float(a['objective'][j]))) for j in np.flatnonzero(a['objective']))),))
with np.load(result['raw_attributes']['path'],allow_pickle=False) as z:r={k:z[k] for k in z.files}
phase=dict(original_primal=primal_replay(s,r['X']),original_dual_sign=verify_sign_convention(s,r['Pi'],r['RC']),
    native_result=record(p/'PHASE_I/S0/NATIVE_RESULT.json'),parameters=read(p/'PHASE_I/S0/SOLVER_PARAMETERS.json')['effective'])
print('MAY11',json.dumps(phase))
p=op.CAMPAIGN/'2025-05-12/B3/attempt002/A2/OUTPUT'
with gzip.open(p/'STATIC/P1_CLOSED_STATE.pkl.gz','rb') as stream:state=pickle.load(stream)
typed,_=restore_types(state,state['global_types']);rec=read(p/'P1/INTEGER_CONTROL/NATIVE_RESULT.json')
with np.load(rec['raw_attributes']['path'],allow_pickle=False) as z:x=z['X']
lb=Fraction(read(p/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB']);ub=objective_value(typed,x,'rho')
iv=typed.vtypes!='C'
bound=dict(UB=float(ub),LB=float(lb),UB_minus_LB=float(ub-lb),
    integer_residual=float(np.max(abs(x[iv]-np.rint(x[iv])),initial=0)),original_rows=primal_replay(typed,x),
    strict_voltage_parent=not read(p/'R029_CONDITIONAL_VOLTAGE_PROGRESS.json')['approved_rows'],
    model_identity_matches=typed.fingerprint()==read(p/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json')['original_snapshot_sha256'])
print('MAY12',json.dumps(bound))
atomic(op.OPS/'R046_NUMERICAL_DIAGNOSIS.json',dict(UTC=now(),Native_calls=0,May11_A1=phase,May12_A2=bound))
