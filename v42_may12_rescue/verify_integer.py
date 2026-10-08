"""Independent saved-integer-point verification, with optimize forbidden."""
import gzip,pickle
from fractions import Fraction
from time import perf_counter
import numpy as np
import gurobipy as gp
from .policy import OUT
from .prepare import route
from .exact import replay
from v42_pr134_b1.common import read,record,atomic,clean
from v42_a_stage_lexfull.runner import objective_value


def saved_schedule_equal(actual,saved):
    # The native receipt uses common.clean: JSON keys are strings and tuples
    # become arrays. This changes representation only, never numerical values.
    return len({str(k) for k in actual})==len(actual) and clean(actual)==saved


def run():
    started=perf_counter()
    def forbidden(*args,**kwargs):raise PermissionError('INDEPENDENT_REPLAY_MUST_NOT_OPTIMIZE')
    gp.Model.optimize=forbidden
    freeze=read(OUT/'P1_ONLY_FREEZE.json');integer=read(OUT/'P1_INTEGER_RESULT.json')
    for receipt in (freeze['integer_model_checkpoint'],integer['point']):
        if record(receipt['path'])!=receipt:raise ValueError('SAVED_INTEGER_MODEL_OR_POINT_BYTES_DRIFT')
    with gzip.open(freeze['integer_model_checkpoint']['path'],'rb') as f:stored=pickle.load(f)
    state,typed=stored['state']['state'],stored['state']['typed']
    native=read(integer['native_result']['path']);identity=read(native['model_identity']['path'])
    if typed.fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('SAVED_TYPED_NATIVE_MATRIX_DRIFT')
    x=np.load(integer['point']['path'])['X'];original_x=x.copy()
    exact=replay(typed,x)  # Original 1e-6 native scientific feasibility tolerance.
    iv=typed.vtypes!='C';integral=float(np.max(abs(x[iv]-np.rint(x[iv])),initial=0))
    route()
    from v42_a_stage_acceptance.physical import Physical
    physical=Physical(state,typed).verify(x)
    U=objective_value(typed,x,'rho');L=Fraction(read(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'])
    gap=(U-L)/abs(U) if U else Fraction(0) if L==0 else Fraction(1)
    saved=read(OUT/'ORIGINAL_PHYSICAL_REPLAY.json')
    unchanged=np.array_equal(original_x,x)
    passed=bool(exact['PASS'] and integral<=1e-5 and physical['PASS'] and unchanged
        and U==Fraction(integer['exact_UB']) and 0<=gap<=Fraction(1,200)
        and saved_schedule_equal(physical['selected_jobs'],saved['selected_jobs'])
        and read(OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json')['PASS'])
    proof=dict(PASS=passed,actual_full_scale_original_integer_model=True,native_optimize_calls=0,
        typed_matrix_identity=identity['original_snapshot_sha256'],original_rows_exact_dyadic_replay=exact,
        original_integer_columns=int(np.count_nonzero(iv)),max_integrality_residual=integral,
        independent_original_physical=physical['physical'],original_population=len(state['data'][1]),
        selected_jobs_match_saved_schedule=saved_schedule_equal(physical['selected_jobs'],saved['selected_jobs']),
        raw_point_not_rounded_clipped_or_modified=unchanged,exact_LB=str(L),exact_UB=str(U),
        exact_gap=str(gap),gap=float(gap),criterion='global integer relative gap <= 1/200',
        model=freeze['integer_model_checkpoint'],point=integer['point'],
        input_identity=record(OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json'),wall_seconds=perf_counter()-started)
    atomic(OUT/'INDEPENDENT_INTEGER_VERIFICATION.json',proof)
    print('INDEPENDENT_INTEGER_REPLAY',passed,float(gap),proof['wall_seconds'],flush=True)
    if not passed:raise ValueError('INDEPENDENT_SAVED_INTEGER_POINT_NOT_ACCEPTED')

if __name__=='__main__':run()
