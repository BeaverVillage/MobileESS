"""One finite diagnostic solve of May11's unchanged rejected Phase I matrix."""
from pathlib import Path
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import read, record, atomic, now, ROOT
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_phase1.core import primal_replay, verify_sign_convention
from v42_may_recovery_v5.numerical import apply_precision


def main():
    output=ROOT/'docs/v42_may_recovery_v5_20261009'
    output.mkdir(exist_ok=True)
    source=ROOT/'runtime/v42_may_campaign/native90_build_reuse_20261009_01/dates/B1/2025-05-11/output/PHASE_I/S0/MODEL_IDENTITY.json'
    identity=read(source)
    for name in ('matrix','attributes'):
        assert record(identity[name]['path'])==identity[name]
    A=sp.load_npz(identity['matrix']['path'])
    with np.load(identity['attributes']['path']) as z:
        attrs={k:z[k].copy() for k in z.files}
    c=attrs['objective']
    snapshot=LinearSnapshot(A,attrs['lower'],attrs['upper'],attrs['senses'],attrs['rhs'],attrs['vtypes'],
        (Objective('Phi',tuple((int(j),Fraction(float(c[j]))) for j in np.flatnonzero(c))),)).require()
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag',0);env.start()
        with gp.Model(env=env) as model:
            x=model.addMVar(A.shape[1],lb=attrs['lower'],ub=attrs['upper'],vtype=attrs['vtypes'],obj=c)
            model.addMConstr(A,x,attrs['senses'],attrs['rhs']);model.update()
            policy=read(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json')
            effective=apply_precision(model,policy,gp,day='2025-05-11',component='PHASE_I')
            model.Params.TimeLimit=60;model.Params.LogFile=str(output/'MAY11_PRECISION_NATIVE.log')
            compiled=model.getA().tocsr();delta=compiled-A;delta.eliminate_zeros()
            assert delta.nnz==0 and np.array_equal(model.getAttr('RHS'),attrs['rhs'])
            assert np.array_equal(model.getAttr('Sense'),attrs['senses'])
            assert np.array_equal(model.getAttr('VType'),attrs['vtypes'])
            assert np.array_equal(model.getAttr('Obj'),c)
            model.optimize()
            raw={k:np.asarray(model.getAttr(k),dtype=float) for k in ('X','Pi','RC')}
            np.savez_compressed(output/'MAY11_PRECISION_RAW.npz',**raw)
            primal=primal_replay(snapshot,raw['X']);dual=verify_sign_convention(snapshot,raw['Pi'],raw['RC'])
            proof=dict(PASS=model.Status==gp.GRB.OPTIMAL and primal['PASS'] and dual['PASS'],UTC=now(),
                original_model=record(source),unchanged_matrix=identity['matrix'],unchanged_attributes=identity['attributes'],
                raw=record(output/'MAY11_PRECISION_RAW.npz'),compiled_original_model_identical=True,
                scientific_tolerance=1e-6,primal=primal,dual=dual,Native_calls=1,P2_calls=0,
                Native_Runtime=model.Runtime,finite_diagnostic_TimeLimit=60,
                original_campaign_ledger_modified=False,production_point_or_clock_transferred=False,
                solver_parameters=effective,status=model.Status,production_date_completed=False)
            atomic(output/'MAY11_PRECISION_VERIFICATION.json',proof)
            print({k:proof[k] for k in ('PASS','Native_Runtime','primal','dual')})
            if not proof['PASS']:raise RuntimeError('MAY11_UNCHANGED_MODEL_NUMERICAL_VERIFICATION_FAILED')


if __name__=='__main__':main()
