"""Independent replay and OPEN proof audit; native optimize is forbidden."""
from practical_support import *
import cold_barrier_external_controller as controller
from owned_solver_guard_v3 import owned_controller_alive
import argparse

def run(output=None):
    assert owned_controller_alive() is None,'WAIT_FOR_OWNED_CONTROLLER_BOUNDARY_BEFORE_PACKAGE_AUDIT'
    assert not controller.existing_m0_alive(),'REGISTERED_M0_STILL_RUNNING'
    checkpoint=controller.RUN/'OPEN_CHECKPOINT.json'
    before=sha(checkpoint);started=time.perf_counter()
    A,d,_=hc.load();objective=verifier.verify(ROOT,d,1)
    assert objective['PASS']
    binary=np.flatnonzero(d['types']=='B')
    identity=dict(scientific=authority.SCIENTIFIC,A_SHA256=sha(hc.PARENT/'C3A_A.npz'),DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),objective=objective['source_objective_SHA256'],binary_columns_SHA256=hashlib.sha256(binary.tobytes()).hexdigest(),rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,root_relaxation='Only original B types relaxed to C',node_changes='Only inherited original B LB=UB=0/1',pruning_tolerance='0')
    bb=controller.ExactBB.load(checkpoint,identity)
    assert bb.state['in_flight'] is None,'IN_FLIGHT_RECEIPT_MUST_BE_CONSUMED_BEFORE_FINAL_AUDIT'
    # The production audit writes a restart report. Capture it in memory here
    # so this entry point leaves all existing run receipts and hashes intact.
    captured=[];prior_atomic=controller.atomic
    controller.atomic=lambda p,v:captured.append((p,v))
    import gurobipy as gp
    prior_optimize=gp.Model.optimize
    def forbidden(*args,**kwargs):raise AssertionError('PACKAGE_AUDIT_OPTIMIZE_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:controller.audit_checkpoint(bb,A,d)
    finally:controller.atomic=prior_atomic;gp.Model.optimize=prior_optimize
    assert len(captured)==1 and captured[0][1]['PASS']
    assert before==sha(checkpoint),'CHECKPOINT_CHANGED_DURING_INDEPENDENT_AUDIT'
    result=dict(PASS=True,UTC=stamp(),optimize_calls=0,wall_seconds=time.perf_counter()-started,source_commit=git('rev-parse','HEAD'),original_objective_bit_identity=objective,checkpoint_SHA256=before,checkpoint_unchanged=True,native_tree_resume_claimed=False,external_OPEN_queue_restart_verified=True,full_original_incumbent_replay_and_all_node_certificates=captured[0][1],identity=identity)
    atomic(output or OUT/'PACKAGE_AUDIT.json',result)
    print(json.dumps(dict(PASS=True,optimize_calls=0,wall_seconds=result['wall_seconds'],coverage=bb.audit())))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Audit saved original-C3A proofs without a solve')
    p.add_argument('--output',type=Path);a=p.parse_args();run(a.output)
