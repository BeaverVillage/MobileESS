"""Isolated real Native replay of the unchanged failed integer model."""
from contextlib import ExitStack
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import ROOT, read, record, atomic, now
from v42_may_campaign_native90.common import exclusive_lock, RUNTIME
from v42_may31_recovery_v10.worker import assert_no_other_native_worker
from v42_may31_recovery_v10.numerical import apply_precision
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_lexfull.runner import objective_value


def main():
    out=ROOT/'docs/v42_may31_recovery_v10_20261009'
    out.mkdir(exist_ok=True)
    proof=out/'MAY31_INTEGER_PRECISION_VERIFICATION.json'
    if proof.exists():
        raise PermissionError('DIAGNOSTIC_RECEIPT_NEVER_OVERWRITTEN')
    run=ROOT/'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
    assert (run/'HOLD_V9.json').is_file()
    old=run/'dates/B1/2025-05-31/attempts/recovery_v9_01/output'
    source=old/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json'
    identity=read(source)
    for name in ('matrix','attributes'):
        assert record(identity[name]['path'])==identity[name]
    A=sp.load_npz(identity['matrix']['path'])
    with np.load(identity['attributes']['path']) as z:
        attrs={k:z[k].copy() for k in z.files}
    c=attrs['objective']
    snapshot=LinearSnapshot(A,attrs['lower'],attrs['upper'],attrs['senses'],attrs['rhs'],attrs['vtypes'],
        (Objective('rho',tuple((int(j),Fraction(float(c[j]))) for j in np.flatnonzero(c))),)).require()
    exact_lb=Fraction(read(old/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'])
    with ExitStack() as owned:
        owned.enter_context(exclusive_lock(RUNTIME/'NATIVE_WORKER.lock'))
        for slot in (1,2,3):
            owned.enter_context(exclusive_lock(RUNTIME/'native_slots'/f'SLOT_{slot}.lock'))
        assert_no_other_native_worker()
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag',0);env.start()
            with gp.Model(env=env) as model:
                x=model.addMVar(A.shape[1],lb=attrs['lower'],ub=attrs['upper'],vtype=attrs['vtypes'],obj=c)
                model.addMConstr(A,x,attrs['senses'],attrs['rhs']);model.update()
                policy=read(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json')
                effective=apply_precision(model,policy,gp,day='2025-05-31',component='INTEGER_CONTROL')
                model.Params.TimeLimit=60
                model.Params.LogFile=str(out/'MAY31_INTEGER_PRECISION_NATIVE.log')
                delta=model.getA().tocsr()-A;delta.eliminate_zeros();assert delta.nnz==0
                for name,field in (('RHS','rhs'),('Sense','senses'),('VType','vtypes'),('Obj','objective'),('LB','lower'),('UB','upper')):
                    assert np.array_equal(model.getAttr(name),attrs[field])
                model.optimize()
                ledger=out/'MAY31_INTEGER_PRECISION_DIAGNOSTIC_NATIVE_LEDGER.json'
                atomic(ledger,dict(Native_calls=1,Native_Runtime=model.Runtime,status=model.Status,
                    diagnostic_only=True,production_clock_transfer=False,P2_calls=0,UTC=now()))
                point=np.asarray(model.getAttr('X'),dtype=float) if model.SolCount else None
                rows=primal_replay(snapshot,point) if point is not None else dict(PASS=False)
                integer=attrs['vtypes']!='C'
                integral=float(np.max(abs(point[integer]-np.rint(point[integer])),initial=0)) if point is not None else None
                upper=objective_value(snapshot,point,'rho') if point is not None else None
                if point is not None:
                    np.savez_compressed(out/'MAY31_INTEGER_PRECISION_RAW.npz',X=point)
                packet=dict(PASS=bool(model.Status==gp.GRB.OPTIMAL and rows['PASS'] and integral<=1e-5 and upper>=exact_lb),
                    UTC=now(),original_model=record(source),compiled_original_model_identical=True,
                    unchanged_matrix=identity['matrix'],unchanged_attributes=identity['attributes'],
                    original_failure=record(old/'A_RESULT.json'),diagnostic_ledger=record(ledger),
                    raw=record(out/'MAY31_INTEGER_PRECISION_RAW.npz') if point is not None else None,
                    exact_LB=str(exact_lb),exact_UB=str(upper),LB=float(exact_lb),UB=float(upper) if upper is not None else None,
                    LB_UB_conflict=upper<exact_lb if upper is not None else None,primal=rows,integral_max_residual=integral,
                    solver_parameters=effective,status=model.Status,Native_Runtime=model.Runtime,Native_calls=1,
                    finite_diagnostic_TimeLimit=60,raw_point_rounded_or_clipped=False,acceptance_tolerance_changed=False,
                    production_point_or_bound_transferred=False,production_date_completed=False,scientific_full_PASS=False,P2_calls=0)
                atomic(proof,packet)
                print({k:packet[k] for k in ('PASS','Native_Runtime','LB','UB','LB_UB_conflict','primal')},flush=True)
                if not packet['PASS']:
                    raise RuntimeError('MAY31_INTEGER_PRECISION_DIAGNOSTIC_FAILED')


if __name__=='__main__':
    main()
