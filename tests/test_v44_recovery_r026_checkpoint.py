from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import json,inspect
import numpy as np
import scipy.sparse as sp
import pytest
from v44_recovery_r026.a2_continue import FrozenWeights,resumed_budget,continued_phase
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_early.progress import capture,inclusion_witness


def snapshot(matrix,rhs=None):
    matrix=sp.csr_matrix(matrix,dtype=float);m,n=matrix.shape
    return LinearSnapshot(matrix,np.zeros(n),np.ones(n),np.full(m,'>'),
        np.ones(m) if rhs is None else np.asarray(rhs,dtype=float),np.full(n,'C'),
        (Objective('rho',((0,Fraction(1)),),Fraction(0)),)).require()


def test_new_support_weight_drift_reproduces_original_failure_then_exact_inclusion_passes():
    old=snapshot([[1.] ]);new=snapshot([[1.,1024.]])
    original=elastic_master(old,(0,));moving=elastic_master(new,(0,))
    previous=capture(old,dict(units=[]),original,dict(X=np.asarray([0.,1.])))
    descriptor=dict(units=[dict(id='new',v={'z':{0:('v',1)}})])
    with pytest.raises(ValueError,match='FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT'):
        inclusion_witness(previous,new,descriptor,moving,1)
    policy=FrozenWeights(old,(0,),{0:Fraction(1)})
    fixed=policy.elastic_master(new,(0,))
    proof,mapped=inclusion_witness(previous,new,descriptor,fixed,1)
    assert proof['PASS'] and mapped.tolist()==[0.,0.,1.]
    assert fixed.weights==original.weights and fixed.artificial_signs==original.artificial_signs
    assert proof['previous_Phi']==proof['mapped_Phi']=='1'


def test_frozen_weights_never_accept_changed_row_sense_or_rhs():
    old=snapshot([[1.] ]);policy=FrozenWeights(old,(0,),{0:Fraction(1)})
    for new in (replace(old,rhs=np.asarray([2.])),replace(old,senses=np.asarray(['<']))):
        with pytest.raises(ValueError,match='ROW_SENSE_OR_RHS_DRIFT'):policy.elastic_master(new,(0,))


def test_restricted_row_identity_preserves_original_global_weight():
    old=snapshot([[1.,0.],[0.,8.]])
    policy=FrozenWeights(old,(0,1),{0:Fraction(1),1:Fraction(1,8)})
    restricted=policy.restricted(old,[1])
    assert policy.elastic_master(restricted,(0,)).weights==(Fraction(1,8),)


def test_original_total_native_budget_is_carried_without_reset(tmp_path,monkeypatch):
    from v42_may_campaign_native90 import budget as module
    monkeypatch.setattr(module,'d_path',Path)
    parent=tmp_path/'parent';(parent/'A2').mkdir(parents=True)
    used=723.613000869751
    row=dict(status='FINISHED',Native_Runtime=used,runtime_unavailable=False)
    ledger=dict(Native_ceiling_seconds=5400.,measured_Native_Runtime=used,calls=[row],costs=[],
        inflight=None,wall_seconds=5592.94862879999)
    (parent/'A2/NATIVE_RUNTIME_LEDGER.json').write_text(json.dumps(ledger))
    cls=resumed_budget(parent,module.DateBudget)
    budget=cls(tmp_path/'new/NATIVE_RUNTIME_LEDGER.json',native_limit=5400.)
    assert budget.used()==used and budget.remaining()==5400.-used and budget.calls==[row]
    budget.calls.append(dict(row,Native_Runtime=1.5));budget.charge(1.5)
    current=json.loads(budget.path.read_text())
    assert current['measured_Native_Runtime']==used+1.5
    assert current['Native_ceiling_seconds']==5400. and current['Native_clock_reset'] is False
    assert json.loads((parent/'A2/NATIVE_RUNTIME_LEDGER.json').read_text())==ledger


def test_resume_phase_keeps_entire_existing_solve_pricing_acceptance_body():
    from v42_a_stage_canary import phase
    packet=dict(phase_traces=[{'solve':14}],stagnation=1,activation_round=10,bestPhi=Fraction(1,1000))
    namespace=dict(vars(phase));generated=continued_phase(phase.run,namespace,packet)
    old=inspect.getsource(phase.run);new=inspect.getsource(generated)
    boundary='    if certified_zero_point is not None:\n'
    assert old[old.index(boundary):]==new[new.index(boundary):]


def test_checkpoint_install_requires_live_authorized_case():
    from v44_recovery_r026.a2_continue import scope
    with pytest.raises(RuntimeError,match='LIVE_CASE_LEASE'):
        with scope({}):pass


def test_restored_phase_initializes_output_path_and_admits_saved_s15(tmp_path):
    from v42_a_stage_canary import phase
    packet=dict(phase_traces=[{'solve':i} for i in range(15)],stagnation=1,activation_round=10,bestPhi=Fraction(1,1000))
    namespace=dict(vars(phase),OUT=tmp_path)
    run=continued_phase(phase.run,namespace,packet)
    calls=[]
    class Native:
        def remaining(self):return 4676.386999130249
        def solve(self,master,folder,component):
            assert folder==tmp_path/'2025-05-02/PHASE_I/S15'
            assert folder.is_dir() and component=='PHASE_I' and master.objective('Phi')
            calls.append(True)
            raise RuntimeError('S15_ADMITTED_WITHOUT_RUNNING_NATIVE')
    state=dict(grows=(0,),compact=snapshot([[1.]]))
    with pytest.raises(RuntimeError,match='S15_ADMITTED_WITHOUT_RUNNING_NATIVE'):run(Native(),state,'2025-05-02')
    assert calls==[True]
