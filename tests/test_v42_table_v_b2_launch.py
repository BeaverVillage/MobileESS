"""B2 independent authority and physical ancestry negatives; Native0 only."""
import json
from pathlib import Path

import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record
from v42_integration import table_v_launch as launch
from v42_integration import table_v_campaign as campaign
from v42_integration.table_v_b2_gate import (B2_SCOPES, MAY_DATES, REPRESENTATIVES,
    validate_b2_scope, validate_b2_launch_evidence)
from v42_integration.table_v_launch_evidence import REFERENCE_POLICY
from test_v42_table_v_launch_evidence import fixture, write
from test_v42_table_v_launch_resources import launch_fixture


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    import gurobipy as gp
    monkeypatch.setattr(gp.Model, '__init__', lambda *a, **k: pytest.fail('Native0: model creation forbidden'))


def b2_launch_fixture(tmp_path, monkeypatch):
    plan, approve, root = launch_fixture(tmp_path, monkeypatch)
    _, expected, actual_policy, _, _ = fixture(root, 'B2')
    manifest = json.loads((root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text())
    policy = manifest['science_derivation']['policy']
    write(root/'INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json', {'spec': policy})
    day = expected['day']
    plan.update(execution_scope=B2_SCOPES[0], run_arms=['B2'])
    plan['case_bindings'][day] = expected
    plan['policy_bindings'][day] = digest(policy)
    plan['actual_policy_bindings'] = {day: {'B2': actual_policy}}
    for kind in ('PLANNING', 'K48'):
        path = root/(kind+'_AUTHORIZATION.json')
        authority = json.loads(path.read_text())
        authority.update(source_cases=[expected], authorized_arm_stages=[
            'B2:M1' if kind == 'PLANNING' else 'B2:K48_M1'])
        plan['budget_authorizations'][day][kind] = write(path, authority)
        write(root/(kind+'_NATIVE_LEDGER.json'), dict(authorization_document=authority,
            release_identity={'authorization_sha': digest(authority)}, inflight=None, active_stage_context=None))
    return plan, approve, root


def evidence_fixture(tmp_path, *, full_slots=96, full_arm='B2'):
    plan = dict(execution_scope=B2_SCOPES[2], run_arms=['B2'], dates=list(MAY_DATES), actual_slots=96,
        release_sha='CURRENT_SOURCE', release_git_sha='CURRENT_GIT', case_bindings={},
        policy_bindings={}, actual_policy_bindings={})
    gate = {'B2_representative_canary_approvals': {}}
    for day in ('2025-05-01',)+REPRESENTATIVES:
        arm = full_arm if day == '2025-05-01' else 'B2'
        slots = full_slots if day == '2025-05-01' else 16
        folder, expected, policy, _, _ = fixture(tmp_path/day, arm, day=day, slots=slots)
        plan['case_bindings'][day] = expected
        manifest = json.loads((tmp_path/day/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text())
        plan['policy_bindings'][day] = digest(manifest['science_derivation']['policy'])
        plan['actual_policy_bindings'][day] = {'B2': digest(REFERENCE_POLICY)}
        record = file_record(folder/'ARM_OUTCOME.json')
        approved = dict(day=day, arm='B2', approved=True, human_approval_reference='NAMED_NATIVE0',
            source_case=expected, release_sha=plan['release_sha'], release_git_sha=plan['release_git_sha'],
            policy_sha=plan['policy_bindings'][day], actual_policy_sha=policy, physical_evidence=record)
        sidecar = write(tmp_path/day/'CURRENT_RELEASE_APPROVAL.json', approved)
        if day == '2025-05-01':
            gate.update(B2_May01_Full96=record, B2_May01_release=sidecar)
        else:
            gate['B2_representative_canary_approvals'][day] = sidecar
    return plan, gate


def test_b2_may01_launch_needs_no_b1_result_and_replays_real_reference(tmp_path, monkeypatch):
    from v42_integration.table_v_run import require_arm_launch
    plan, approve, root = b2_launch_fixture(tmp_path, monkeypatch)
    gate = approve()
    readiness = campaign.preflight_table_v_plan(plan, gate)
    assert readiness['status'] == 'PASS_NATIVE0_WIRING' and readiness['case_count'] == 1
    assert not readiness['launch_blockers']
    campaign._launch_gate(plan, gate)
    assert require_arm_launch(root, {'plan':plan, 'gate':gate}, actual_slots=96, arm='B2') == '2025-05-01'
    with pytest.raises(PermissionError, match='ARM_NOT_IN_EXACT_APPROVED'):
        require_arm_launch(root, {'plan':plan, 'gate':gate}, actual_slots=96, arm='B1')
    reference = json.loads((root/'REFERENCE_RESULT.json').read_text())
    reference['AIDC_P_by_site']['AIDC01'][0] += 1.
    write(root/'REFERENCE_RESULT.json', reference)
    with pytest.raises(ValueError):
        campaign._launch_gate(plan, gate)


@pytest.mark.parametrize('mutation', ['source', 'policy', 'release', 'unrestricted-budget', 'inflight', 'prepared'])
def test_b2_current_launch_authority_cannot_be_weakened(tmp_path, monkeypatch, mutation):
    plan, approve, root = b2_launch_fixture(tmp_path, monkeypatch)
    if mutation == 'source': plan['case_bindings']['2025-05-01']['source_sha'] = 'OTHER'
    elif mutation == 'policy': plan['actual_policy_bindings']['2025-05-01']['B2'] = digest('OTHER')
    elif mutation == 'release': plan['release_sha'] = 'OTHER'
    elif mutation == 'prepared': plan['execution_scope'] = 'PREPARED_ONLY'
    elif mutation == 'unrestricted-budget':
        path = root/'PLANNING_AUTHORIZATION.json'
        authority = json.loads(path.read_text()); authority.pop('authorized_arm_stages')
        plan['budget_authorizations']['2025-05-01']['PLANNING'] = write(path, authority)
    elif mutation == 'inflight':
        path = root/'PLANNING_NATIVE_LEDGER.json'
        ledger = json.loads(path.read_text()); ledger['inflight'] = {'pid': 123}
        write(path, ledger)
    with pytest.raises((PermissionError, ValueError)):
        campaign._launch_gate(plan, approve())


def test_b2_month_evidence_uses_only_b2_complete_ancestry(tmp_path):
    plan, gate = evidence_fixture(tmp_path)
    validate_b2_launch_evidence(plan, gate)
    assert 'May01_four_arm_Full96' not in gate
    plan.update(execution_scope=B2_SCOPES[1], dates=['2025-05-10'], actual_slots=16)
    validate_b2_launch_evidence(plan, {k:v for k,v in gate.items() if k != 'B2_representative_canary_approvals'})


@pytest.mark.parametrize('mutation', ['wrong-arm', 'wrong-source', 'old-release', 'cross-day',
    'fake-full96', 'full96-as-canary', 'missing-m1', 'reference', 'actual-policy', 'header-only', 'science-policy'])
def test_b2_ancestry_release_and_exact_physical_scope_are_required(tmp_path, mutation):
    plan, gate = evidence_fixture(tmp_path, full_slots=16 if mutation == 'fake-full96' else 96,
        full_arm='B0' if mutation == 'wrong-arm' else 'B2')
    if mutation in ('wrong-source', 'old-release', 'cross-day', 'actual-policy', 'header-only', 'science-policy'):
        record = gate['B2_May01_release']; path = record['path']
        approval = json.loads(Path(path).read_text(encoding='utf8'))
        if mutation == 'wrong-source': approval['source_case'] = dict(approval['source_case'], source_sha='OTHER')
        elif mutation == 'old-release': approval['release_git_sha'] = 'OLD'
        elif mutation == 'cross-day': approval['day'] = '2025-05-02'
        elif mutation == 'actual-policy': approval['actual_policy_sha'] = digest('OTHER')
        elif mutation == 'science-policy':
            approval['policy_sha'] = digest('OTHER')
            plan['policy_bindings']['2025-05-01'] = approval['policy_sha']
        else: approval.pop('physical_evidence')
        gate['B2_May01_release'] = write(Path(path), approval)
    elif mutation == 'full96-as-canary':
        day = REPRESENTATIVES[0]
        folder, _, _, _, _ = fixture(tmp_path/day, 'B2', day=day, slots=96)
        path = tmp_path/day/'CURRENT_RELEASE_APPROVAL.json'; approval = json.loads(path.read_text())
        approval['physical_evidence'] = file_record(folder/'ARM_OUTCOME.json')
        gate['B2_representative_canary_approvals'][day] = write(path, approval)
    elif mutation == 'missing-m1':
        (tmp_path/'2025-05-01/B2/M1/TABLE_V_M_ACCEPTANCE.json').unlink()
    elif mutation == 'reference':
        path = tmp_path/'2025-05-01/REFERENCE_RESULT.json'
        reference = json.loads(path.read_text()); reference['reference_sources'] = []
        write(path, reference)
    with pytest.raises((ValueError, PermissionError, KeyError, OSError)):
        validate_b2_launch_evidence(plan, gate)


@pytest.mark.parametrize('scope,dates,slots,arms', [
    (B2_SCOPES[0], ['2025-05-02'], 96, ['B2']),
    (B2_SCOPES[0], ['2025-05-01'], 16, ['B2']),
    (B2_SCOPES[0], ['2025-05-01'], 96, ['B1','B2']),
    (B2_SCOPES[1], ['2025-05-03'], 16, ['B2']),
    (B2_SCOPES[1], ['2025-05-02'], 96, ['B2']),
    (B2_SCOPES[2], ['2025-05-01'], 96, ['B2']),
])
def test_b2_scope_cannot_expand_approved_day_arm_or_actual_axis(scope, dates, slots, arms):
    with pytest.raises(PermissionError):
        validate_b2_scope(dict(execution_scope=scope, dates=dates, actual_slots=slots, run_arms=arms))
