"""Release/dispatch contract fixtures; they are not physical validation."""
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from v42_pr134_b1.common import atomic,record
from v42_svr11 import batch,resources,milp_release
from svr11_monitor_ui import gap_display


@pytest.mark.parametrize('stage,capacity',[('M1',2),('A2',1),('M2',2)])
def test_epoch15_manifest_capacity_overrides_old_batch_default(tmp_path,stage,capacity):
    state=batch.initial();state['stage']=stage
    for prior in batch.ORDER[:batch.ORDER.index(stage)]:
        for row in state['stages'][prior].values():row['status']='PASS'
    ledger=dict(B3_batch=state,dates={'B3/'+d:dict(status='NOT_EXECUTED',attempts=[]) for d in batch.DAYS})
    manifest=dict(run_id='FIXTURE',execution_SHA='fixture',B3_memory_admission={},
        B3_stage_worker_counts=dict(M1=2,A2=1,M2=2,ACTUAL=1))
    atomic(tmp_path/'CAMPAIGN_MANIFEST.json',manifest)
    def spawn(path,request):
        return dict(PID=request['worker_slot'],b3_stage=stage,arm='B3',day=request['day'],worker_slot=request['worker_slot'])
    memory=dict(RAM_available=1,Commit_available=1,Commit_total=1)
    with patch.object(resources,'admits',return_value=True):
        peers=batch.tick(tmp_path,manifest,ledger,[],memory=memory,spawn=spawn)
        batch.tick(tmp_path,manifest,ledger,peers,memory=memory,spawn=spawn)
    assert len(peers)==capacity and state['effective_stage_worker_capacity']==capacity
    assert not state['barriers']


def test_gap_display_keeps_available_certificate_when_three_percent_unmet():
    view=gap_display(dict(independent_global_gap_available=True,global_gap_certified=False,
        certified_Global_LB=.5,certified_gap=.25,Solver_MIPGap=.2,solver_global_gap=.22))
    assert view['certified_LB']==.5 and view['certified_Gap']==.25
    assert view['Solver_MIPGap']==.2 and view['solver_global_gap']==.22
    assert not view['global_gap_certified']


def test_solver_zero_gap_does_not_create_independent_certificate():
    view=gap_display(dict(Solver_MIPGap=0,solver_global_gap=0,solver_global_gap_valid=True,
        certified_Global_LB=.5,certified_gap=0,global_gap_certified=False))
    assert view['Solver_MIPGap']==0 and view['solver_global_gap']==0
    assert view['certified_Gap'] is None and not view['independent_global_gap_available']


def test_independent_bound_alone_does_not_claim_gap_available():
    view=gap_display(dict(independent_global_bound_verified=True,certified_Global_LB=.5))
    assert view['certified_LB']==.5 and view['certified_Gap'] is None
    assert view['independent_global_bound_verified'] and not view['independent_global_gap_available']


def test_current_release_refuses_historical_proof_instead_of_fresh_reduction(tmp_path):
    proof=tmp_path/'proof.json';atomic(proof,dict(PASS=True,historical_row_indices_read=71540))
    validation=tmp_path/'validation.json';atomic(validation,dict(PASS=True,source_SHA='new',
        Native_M_limit_seconds=1800,A1_A2_algorithms_changed=False,
        physical_and_forecast_science_bitwise_unchanged=True,production_results_promoted=0,
        exact_reduction_proof=record(proof)))
    with pytest.raises(PermissionError,match='CURRENT_EXACT_C3A_PROOF_REQUIRED'):
        milp_release._validate_exact_c3a(dict(source_SHA='new',minimal_current_validation=record(validation)))
