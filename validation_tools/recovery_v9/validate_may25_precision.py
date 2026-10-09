"""One isolated Native diagnostic of the exact rejected May25 Phase I matrix."""
from pathlib import Path
from fractions import Fraction
from contextlib import ExitStack
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import read, record, atomic, now, ROOT
from v42_may_campaign_native90.common import exclusive_lock, RUNTIME
from v42_may_mess_build_v7.worker import assert_no_other_native_worker
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_phase1.core import primal_replay, verify_sign_convention
from v42_may25_recovery_v9.numerical import apply_precision


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--method', type=int, choices=(1, 2), default=2)
    parser.add_argument('--presolve', type=int, choices=(-1, 0), default=-1)
    arguments = parser.parse_args()
    method = arguments.method
    prefix = 'MAY25_PRECISION' if method == 2 else 'MAY25_PRECISION_DUAL_SIMPLEX'
    if arguments.presolve == 0:
        prefix += '_ORIGINAL_ROWS'
    output = ROOT / 'docs/v42_may25_recovery_v9_20261009'
    output.mkdir(exist_ok=True)
    proof_path = output / (prefix + '_VERIFICATION.json')
    if proof_path.exists():
        raise PermissionError('DIAGNOSTIC_RECEIPT_NEVER_OVERWRITTEN')
    run = ROOT / 'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
    assert (run / 'HOLD_V7R2.json').is_file()
    source = run / 'dates/B1/2025-05-25/attempts/mess_build_v7r2_01/output/PHASE_I/S0/MODEL_IDENTITY.json'
    identity = read(source)
    for name in ('matrix', 'attributes'):
        assert record(identity[name]['path']) == identity[name]
    old = read(source.with_name('ORIGINAL_NUMERICAL_REPLAY.json'))
    A = sp.load_npz(identity['matrix']['path'])
    with np.load(identity['attributes']['path']) as z:
        attrs = {k: z[k].copy() for k in z.files}
    c = attrs['objective']
    snapshot = LinearSnapshot(A, attrs['lower'], attrs['upper'], attrs['senses'], attrs['rhs'], attrs['vtypes'],
        (Objective('Phi', tuple((int(j), Fraction(float(c[j]))) for j in np.flatnonzero(c))),)).require()
    with ExitStack() as locks:
        locks.enter_context(exclusive_lock(RUNTIME / 'NATIVE_WORKER.lock'))
        for slot in (1, 2, 3):
            locks.enter_context(exclusive_lock(RUNTIME / 'native_slots' / f'SLOT_{slot}.lock'))
        assert_no_other_native_worker()
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag', 0)
            env.start()
            with gp.Model(env=env) as model:
                x = model.addMVar(A.shape[1], lb=attrs['lower'], ub=attrs['upper'], vtype=attrs['vtypes'], obj=c)
                model.addMConstr(A, x, attrs['senses'], attrs['rhs'])
                model.update()
                policy = read(ROOT / 'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json')
                effective = apply_precision(model, policy, gp, day='2025-05-25', component='PHASE_I')
                model.Params.Method = method
                effective['Method'] = method
                model.Params.Presolve = arguments.presolve
                effective['Presolve'] = arguments.presolve
                model.Params.TimeLimit = 60
                model.Params.LogFile = str(output / (prefix + '_NATIVE.log'))
                delta = model.getA().tocsr() - A
                delta.eliminate_zeros()
                assert delta.nnz == 0
                for name, field in (('RHS', 'rhs'), ('Sense', 'senses'), ('VType', 'vtypes'), ('Obj', 'objective'), ('LB', 'lower'), ('UB', 'upper')):
                    assert np.array_equal(model.getAttr(name), attrs[field])
                model.optimize()
                raw = {k: np.asarray(model.getAttr(k), dtype=float) for k in ('X', 'Pi', 'RC')}
                np.savez_compressed(output / (prefix + '_RAW.npz'), **raw)
                primal = primal_replay(snapshot, raw['X'])
                dual = verify_sign_convention(snapshot, raw['Pi'], raw['RC'])
                proof = dict(PASS=model.Status == gp.GRB.OPTIMAL and primal['PASS'] and dual['PASS'], UTC=now(),
                    original_model=record(source), unchanged_matrix=identity['matrix'], unchanged_attributes=identity['attributes'],
                    old_rejection=record(source.with_name('ORIGINAL_NUMERICAL_REPLAY.json')), old_primal=old['primal'],
                    raw=record(output / (prefix + '_RAW.npz')), compiled_original_model_identical=True,
                    scientific_tolerance=1e-6, primal=primal, dual=dual, Native_calls=1, P2_calls=0,
                    Native_Runtime=model.Runtime, finite_diagnostic_TimeLimit=60,
                    original_campaign_ledger_modified=False, production_point_or_clock_transferred=False,
                    solver_parameters=effective, status=model.Status, production_date_completed=False)
                ledger = output / (prefix + '_DIAGNOSTIC_NATIVE_LEDGER.json')
                atomic(ledger, dict(Native_calls=1, Native_Runtime=model.Runtime,
                    status=model.Status, P2_calls=0, diagnostic_only=True, production_clock_transfer=False, UTC=now()))
                proof['diagnostic_ledger'] = record(ledger)
                atomic(proof_path, proof)
                print({k: proof[k] for k in ('PASS', 'Native_Runtime', 'primal', 'dual')})
                if not proof['PASS']:
                    raise RuntimeError('MAY25_UNCHANGED_MODEL_PRECISION_DIAGNOSTIC_FAILED')


if __name__ == '__main__':
    main()
