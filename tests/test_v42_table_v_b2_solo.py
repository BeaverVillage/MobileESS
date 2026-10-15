"""B2 supervisor control/evidence tests; no Native or large scientific data."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record
from v42_integration import table_v_b2_solo as solo
from v42_integration.table_v_b2_gate import B2_SCOPES
from v42_integration.table_v_control import CampaignStopped
from test_v42_table_v_b2_launch import b2_launch_fixture
from test_v42_table_v_launch_evidence import fixture, write


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    import gurobipy as gp
    monkeypatch.setattr(gp.Model, '__init__', lambda *a, **k: pytest.fail('Native0: model construction forbidden'))
    for method in ('optimize', 'presolve', 'computeIIS', 'feasRelax'):
        monkeypatch.setattr(gp.Model, method, lambda *a, **k: pytest.fail('Native0: solver method forbidden'))


def test_latest_native_descendant_is_exact_and_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(solo, 'ROOT', tmp_path)
    folder = tmp_path/'docs/v42_source18r_phase_20261015'
    ledger = write(folder/'NATIVE03/PLANNING_NATIVE_LEDGER.json', {'calls': [{'Native_Runtime': 83.953}]})
    head = write(folder/'DIAGNOSTIC_HEAD.json', {'state':'COMPLETE', 'ledger':ledger})
    k48 = write(tmp_path/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION08/K48_NATIVE_LEDGER.json', {'calls':[]})
    before = {r['path']: Path(r['path']).read_bytes() for r in (head, ledger, k48)}
    assert solo.initial_predecessors() == {'PLANNING':ledger, 'K48':k48}
    assert all(Path(path).read_bytes() == contents for path, contents in before.items())
    Path(ledger['path']).write_bytes(Path(ledger['path']).read_bytes()+b' ')
    with pytest.raises(RuntimeError, match='DESCENDANT'):
        solo.initial_predecessors()


def test_prepare_only_uses_original_date_reference_and_b2_scoped_carry(tmp_path, monkeypatch):
    import v42_integration.release_date_case as dates
    import v42_integration.table_v_flex_planning as flex
    import v42_integration.table_v_reference as reference
    calls = []; ledgers = []
    day = '2025-05-01'; root = tmp_path/'EXECUTION'
    identity = {'science_sha':'S', 'case_sha':'C', 'initial_state_sha':'I'}
    expected = {'day':day, 'source_sha':'SOURCE', 'source_identity':identity}
    manifest = {'day':day, 'source_sha':'SOURCE', 'identity':identity, 'science_derivation':{'policy':{'fixture':True}}}
    release = {'release_sha':'RELEASE', 'release_git_sha':'GIT', 'release_sources':[]}
    predecessors = {'PLANNING':write(tmp_path/'NATIVE03.json', {'calls':[{'arm':'B1'}]}),
                    'K48':write(tmp_path/'OLD_K48.json', {'calls':[]})}
    def basic(current, *, output, call_cap):
        calls.append(('basic', current, call_cap)); write(output/'ORIGINAL_INPUT.json', {'day':current})
        return {'day':current}
    def full(context, *, output, call_cap):
        calls.append(('flex', context, call_cap)); write(output/'TABLE_V_FLEX_CASE_MANIFEST.json', manifest)
        return {'manifest':manifest}
    def make(context, *, output):
        calls.append(('reference', context)); return {'original_reference':True}, {'validated':True}
    def validate(acceptance, *, identity, result):
        assert acceptance == {'validated':True} and result == {'original_reference':True}
        calls.append(('validate', identity))
    def stage_budget(path, *, authorization, historical_ledgers):
        ledgers.append(deepcopy(authorization)); write(Path(path), {'calls':[], 'authorization_document':authorization})
    monkeypatch.setattr(dates, 'compile_date_case', basic)
    monkeypatch.setattr(flex, 'compile_table_v_flex_context', full)
    monkeypatch.setattr(reference, 'make_reference', make)
    monkeypatch.setattr(reference, 'require_reference_acceptance', validate)
    monkeypatch.setattr(solo, 'initial_predecessors', lambda:predecessors)
    monkeypatch.setattr(solo, 'release_identity', lambda:deepcopy(release))
    monkeypatch.setattr(solo, 'TableVStageBudget', stage_budget)
    receipt = solo.prepare_date(day, root, 'NAMED_NATIVE0_DIRECT_REQUEST')
    assert [c[0] for c in calls] == ['basic','flex','reference','validate']
    assert receipt['Native_calls'] == receipt['Original_M_model_builds'] == 0
    assert receipt['source_case'] == expected and not receipt['prior_day_state_imported']
    assert [(a['authorized_arm_stages'],a['carry_forward_ledgers']) for a in ledgers] == [
        (['B2:M1'],[predecessors['PLANNING']]), (['B2:K48_M1'],[predecessors['K48']])]
    assert not any(root.glob('B[013]/*ACCEPTANCE*'))
    calls.clear(); assert solo.prepare_date(day, root, 'NAMED_NATIVE0_DIRECT_REQUEST') == receipt
    assert calls == [] and len(ledgers) == 2
    input_path = Path(receipt['inputs'][0]['path']); input_path.write_bytes(input_path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='INPUT_BYTES_DRIFT'):
        solo.prepare_date(day, root, 'NAMED_NATIVE0_DIRECT_REQUEST')


def test_make_launch_uses_real_b2_gate_and_current_reference(tmp_path, monkeypatch):
    plan, _, execution = b2_launch_fixture(tmp_path/'CASE', monkeypatch)
    identity = {k:plan[k] for k in ('release_sha','release_git_sha','release_sources')}
    monkeypatch.setattr(solo, 'release_identity', lambda:deepcopy(identity))
    chosen, gate = solo.make_launch(B2_SCOPES[0], ['2025-05-01'], {'2025-05-01':execution},
        'NAMED_NATIVE0_REQUEST', tmp_path/'LAUNCH')
    assert chosen['run_arms'] == ['B2'] and chosen['actual_slots'] == 96
    approved = solo.read(gate['launch_authorization']['path'])
    assert approved['approved_plan_sha'] == digest(chosen)
    assert solo.read(tmp_path/'LAUNCH/LAUNCH_VALIDATED.json')['Native_calls'] == 0
    assert 'May01_four_arm_Full96' not in gate


def test_completion_approval_verifies_actual_scope_and_preserves_raw(tmp_path):
    folder, expected, _, _, _ = fixture(tmp_path, 'B2', day='2025-05-10', slots=16)
    before = file_record(folder/'ARM_OUTCOME.json')
    approval = solo.approve_completed(tmp_path, folder, {'release_sha':'R', 'release_git_sha':'G'},
        'NAMED_NATIVE0_REQUEST', slots=16)
    value = solo.read(approval['path'])
    assert value['source_case'] == expected and value['physical_evidence'] == before
    assert value['arm'] == 'B2' and file_record(before['path']) == before
    with pytest.raises(ValueError):
        solo.approve_completed(tmp_path, folder, {'release_sha':'R', 'release_git_sha':'G'},
            'NAMED_NATIVE0_REQUEST', slots=96)


def integrity_fixture(tmp_path, monkeypatch):
    plan, _, execution = b2_launch_fixture(tmp_path, monkeypatch)
    source = write(tmp_path/'SMALL_SOURCE.json', {'source':'original'})
    write(execution/'EXECUTION_SOURCE_FREEZE.json', {'files':[source], 'source_sha':digest([source])})
    for name in ('PLANNING', 'K48'):
        path = execution/(name+'_NATIVE_LEDGER.json'); ledger = solo.read(path)
        ledger.update(calls=[], Gurobi_Native_seconds=0., active_stage_owner_pid=None,
            schema='TABLE_V_NATIVE_STAGE_LEDGER_V1', Worker=1, Threads=1, P2_calls=0)
        write(path, ledger)
    return execution, source


@pytest.mark.parametrize('reason', ['WORKER_OWNERSHIP_LOST','SOURCE_BYTES_DRIFT','NATIVE_UNRECONCILED',
    'ARM_STAGE_NOT_AUTHORIZED','UNBUDGETED_OPTIMIZE','FORGED_EVIDENCE','RELEASE_INTEGRITY_ERROR'])
def test_integrity_failure_is_not_an_independent_scientific_day_failure(tmp_path, monkeypatch, reason):
    execution, _ = integrity_fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError):
        solo.check_integrity(execution, {'status':'NOT_CERTIFIED','error':reason})


def test_scientific_failure_can_continue_but_source_or_user_stop_cannot(tmp_path, monkeypatch):
    execution, source = integrity_fixture(tmp_path, monkeypatch)
    solo.check_integrity(execution, {'status':'NOT_CERTIFIED','error':'NO_FULL_FEASIBLE_UB'})
    with pytest.raises(CampaignStopped):
        solo.check_integrity(execution, {'status':'INTERRUPTED_BY_USER'})
    Path(source['path']).write_bytes(b'CHANGED')
    with pytest.raises(ValueError, match='DRIFT'):
        solo.check_integrity(execution, {'status':'NOT_CERTIFIED'})


@pytest.mark.parametrize('mutation', ['inflight','active','unknown','nan','negative','total-mismatch',
    'authorization-drift','owner-not-cleared'])
def test_native_integrity_mismatch_stops_campaign(tmp_path, monkeypatch, mutation):
    execution, _ = integrity_fixture(tmp_path, monkeypatch)
    path = execution/'PLANNING_NATIVE_LEDGER.json'; ledger = solo.read(path)
    if mutation == 'inflight': ledger['inflight'] = {'pid':123}
    elif mutation == 'active': ledger['active_stage_context'] = {'day':'2025-05-01','arm':'B2','stage':'M1'}
    elif mutation == 'owner-not-cleared': ledger['active_stage_owner_pid'] = 123
    elif mutation == 'total-mismatch': ledger['Gurobi_Native_seconds'] = 1.
    elif mutation == 'authorization-drift': ledger['authorization_document']['authorized_arm_stages'] = ['B1:A1']
    else:
        ledger['calls'] = [{'solver':'GUROBI','Native_Runtime':{'unknown':None,'nan':float('nan'),'negative':-1.}[mutation]}]
    write(path, ledger)
    with pytest.raises((RuntimeError, ValueError, PermissionError)):
        solo.check_integrity(execution, {'status':'NOT_CERTIFIED','error':'NO_FULL_FEASIBLE_UB'})


def reuse_fixture(tmp_path, monkeypatch):
    import v42_integration.tablev_actual as actual
    import v42_integration.table_v_control as control
    folder, expected, _, _, _ = fixture(tmp_path, 'B2', day='2025-05-10', slots=16)
    calls = []
    monkeypatch.setattr(solo, 'require_arm_launch', lambda root, authority, **kw:calls.append(('launch',kw)))
    monkeypatch.setattr(solo, 'load_context', lambda root:{'day':expected['day']})
    monkeypatch.setattr(solo, 'check_integrity', lambda root, outcome:calls.append(('integrity',outcome['status'])))
    monkeypatch.setattr(control, 'require_running', lambda root:None)
    def evaluate(**kwargs):
        calls.append(('actual',kwargs)); return {'status':'FULL_PASS','new_actual_scope':96}
    def fresh(**kwargs):
        calls.append(('fresh',kwargs)); return {'status':'FULL_PASS','new_fresh_scope':96}
    monkeypatch.setattr(actual, 'run_tablev_actual', evaluate)
    monkeypatch.setattr(actual, 'run_tablev_fresh', fresh)
    write(tmp_path/'EXECUTION_SOURCE_FREEZE.json', {'files':[], 'source_sha':digest([])})
    return folder, calls


def test_reuses_only_original_full_m1_planning_and_executes_new_actual_fresh96(tmp_path, monkeypatch):
    folder, calls = reuse_fixture(tmp_path, monkeypatch)
    canary = file_record(folder/'ARM_OUTCOME.json')
    immutable = {p:file_record(p) for p in folder.rglob('*') if p.is_file()}
    ledger = write(tmp_path/'PLANNING_NATIVE_LEDGER.json', {'calls':[{'Native_Runtime':11.}]})
    outcome, full = solo.reuse_planning_actual96(tmp_path, folder, {'fixture':'approved'}, {})
    assert outcome['executed_actual_slots'] == outcome['executed_fresh_slots'] == 96
    assert [call[0] for call in calls] == ['launch','actual','fresh','integrity']
    assert calls[1][1]['slots'] == calls[2][1]['slots'] == 96
    assert calls[1][1]['output'] == full/'ACTUAL96' and calls[2][1]['output'] == full/'FRESH_AC96'
    assert outcome['actual']['new_actual_scope'] == outcome['fresh']['new_fresh_scope'] == 96
    reuse = solo.read(full/'PLANNING_REUSE.json')
    assert reuse['donor'] == canary and not reuse['prefix_Actual_promoted_to_Full96']
    assert reuse['new_Native_calls'] == reuse['new_M_model_builds'] == 0
    assert file_record(ledger['path']) == ledger
    assert all(file_record(path) == record for path,record in immutable.items())
    for name in ('TABLE_V_M_RESULT.json','TABLE_V_M_ACCEPTANCE.json','SCIENTIFIC_CASE_IDENTITY.json'):
        assert (full/'M1'/name).read_bytes() == (folder/'M1'/name).read_bytes()


def test_bad_canary_raw_never_starts_reused_actual96(tmp_path, monkeypatch):
    folder, calls = reuse_fixture(tmp_path, monkeypatch)
    stages = solo.read(folder/'PLANNING_STAGE_RESULTS.json')
    Path(stages['M1']['acceptance']['raw_point']['path']).write_bytes(b'CHANGED_POINT')
    with pytest.raises(ValueError):
        solo.reuse_planning_actual96(tmp_path, folder, {}, {})
    assert [call[0] for call in calls] == ['launch']
    assert not (tmp_path/'B2/ATTEMPT_FULL96').exists()


def test_user_stop_during_reused_actual_remains_campaign_stop(tmp_path, monkeypatch):
    import v42_integration.tablev_actual as actual
    folder, calls = reuse_fixture(tmp_path, monkeypatch)
    def stop(**kwargs): raise CampaignStopped('CAMPAIGN_STOP_REQUEST')
    monkeypatch.setattr(actual, 'run_tablev_actual', stop)
    def integrity(root, outcome):
        assert outcome['status'] == 'INTERRUPTED_BY_USER'
        raise CampaignStopped('STOP_PRESERVED')
    monkeypatch.setattr(solo, 'check_integrity', integrity)
    with pytest.raises(CampaignStopped):
        solo.reuse_planning_actual96(tmp_path, folder, {}, {})
    saved = solo.read(tmp_path/'B2/ATTEMPT_FULL96/ARM_OUTCOME.json')
    assert saved['status'] == 'INTERRUPTED_BY_USER'
    assert 'fresh' not in [c[0] for c in calls]
