from pathlib import Path
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40a.invariants import digest
from dayahead.v40g_segments.canonical import import_frozen, identities, occupancy, planning_power
from dayahead.v40h.identity import *
from dayahead.v40h import electrical, b1, cache
from dayahead.v40h.certification import certify_case, certified_day, validate_completed_case, recovery_state
from tests.dayahead.test_v40g_segments import context96, migrant


def campaign():
    return campaign_identity({k: digest(k) for k in CAMPAIGN_ROLES})


def m1_identity(**changes):
    inputs = {k: digest(k) for k in cache.ROLES}; inputs.update(changes)
    return cache.execution_identity(inputs)


def test_initial_matrix_all_124_new():
    x = initialize_matrix(campaign()); validate_matrix(x, campaign())
    assert len(x['rows']) == 124 and all(r['status'] == 'RUN_REQUIRED' for r in x['rows'])
    assert all(sum(r['case'] == c for r in x['rows']) == 31 for c in CASES)
    x['rows'][0]['status'] = 'REUSE_CERTIFIED'
    with pytest.raises(IntegrityError, match='LEGACY_REUSE'): validate_matrix(x, campaign())


def case_fixture(root, case='B0', day='2025-05-01', identity=None):
    identity = identity or campaign(); dst = root / 'days' / day / case; dst.mkdir(parents=True)
    _, job = context96(); jobs = [job]; seg = identities(jobs); aidc_sha = digest(jobs); mess = []
    da = {'AIDC_decision_SHA': aidc_sha, 'MESS_trajectory_SHA': digest(mess)}
    bindings = {'DA_decision_SHA': digest(da), 'AIDC_decision_SHA': aidc_sha, 'AIDC_segment_SHA': seg['segment_and_event_SHA'],
                'MESS_trajectory_SHA': digest(mess), 'execution_identity_SHA': identity['identity_SHA']}
    physical = dict(status='PASS', voltage_violation_count=0, current_violation_count=0, transformer_violation_count=0)
    docs = {k: {'day': day, 'case': case, 'status': 'PASS', 'physical_violation': False, 'convergence_count': 96,
        'rho_max': .25, 'execution_identity_SHA': identity['identity_SHA'], 'final_executed_joint_SHA': digest(bindings)} for k in ('Planning', 'Fresh', 'Actual')}
    docs.update(physical_gates={k: physical for k in ('Planning', 'Fresh', 'Actual')},
        objective={'day': day, 'case': case, 'primary': 'MIN_RHO_MAX', 'rho_max': .25},
        DA_decision={'decision': da, 'decision_SHA': digest(da)},
        AIDC_decision={'jobs': jobs, 'decision_SHA': aidc_sha, 'segment_identity': seg},
        MESS_trajectory={'trajectory': mess, 'trajectory_SHA': digest(mess)},
        input_authority={'execution_identity': identity, 'files': []},
        final_executed_joint={'payload': bindings, 'final_executed_joint_SHA': digest(bindings)})
    roles = {}; files = []
    for role, doc in docs.items():
        path = dst / (role + '.json'); write_json(path, doc); record = file_record(path, root=root)
        files.append(record); roles[role] = record['relative_path']
    trajectory = dst / 'physical_trajectory.bin'; trajectory.write_bytes(b'full physical leaf')
    files.append(file_record(trajectory, root=root))
    checkpoint = dst / 'CHECKPOINT.json'
    write_json(checkpoint, {'schema': SCHEMA, 'status': 'COMPLETE_CURRENT_IDENTITY', 'execution_identity': identity,
        'day': day, 'case': case, 'files': files, 'roles': roles,
        'bindings': {**bindings, 'final_executed_joint_SHA': digest(bindings)}})
    return certify_case(checkpoint, identity, day=day, case=case, campaign_root=root)


@pytest.mark.parametrize('case', ['B0', 'B2'])
def test_old_v40b_certificate_rejected(tmp_path, case):
    path = tmp_path / ('OLD_' + case + '.json')
    write_json(path, {'status': 'PASS', 'day': '2025-05-01', 'case': case, 'CURRENT_LOADER_ACCEPTS_OLD_RESULT': 'YES'})
    with pytest.raises(IntegrityError, match='OLD_OR_INCOMPLETE'):
        validate_completed_case(file_record(path, root=tmp_path), campaign(), day='2025-05-01', case=case, campaign_root=tmp_path)


@pytest.mark.parametrize('damage', ['mutated', 'missing'])
def test_day_certificate_recursively_revalidates_leaves(tmp_path, damage):
    refs = {c: case_fixture(tmp_path, c) for c in CASES}
    day = tmp_path / 'DAY_CERTIFICATE.json'
    write_json(day, {'schema': SCHEMA, 'day': '2025-05-01', 'execution_identity': campaign(), 'cases': refs})
    ref = file_record(day, root=tmp_path)
    assert certified_day(ref, campaign(), day='2025-05-01', campaign_root=tmp_path)['ALL_4_CASE_LEAF_ARTIFACTS_VALID_NOW']
    leaf = tmp_path / 'days/2025-05-01/B1/physical_trajectory.bin'
    if damage == 'mutated': leaf.write_bytes(b'changed physical leaf')
    else: leaf.unlink()
    with pytest.raises(IntegrityError): certified_day(ref, campaign(), day='2025-05-01', campaign_root=tmp_path)


def test_only_complete_current_case_can_skip(tmp_path):
    ref = case_fixture(tmp_path)
    args = dict(day='2025-05-01', case='B0', campaign_root=tmp_path)
    assert recovery_state(ref, campaign(), **args)['skip_computation']
    assert not recovery_state(None, campaign(), **args)['skip_computation']
    new = deepcopy(campaign()['identity']['inputs']); new['V40G_source_SHA'] = digest('changed')
    assert recovery_state(ref, campaign_identity(new), **args)['status'] == 'STALE_DIFFERENT_IDENTITY'


def stage_data():
    parents = [{'beam_state_id': 'ROOT', 'parent_state_id': None, 'trajectory_slots': [], 'state_sha256': 'r'}]
    payload = {'retained_states': [{'beam_state_id': 'CHILD', 'parent_state_id': 'ROOT', 'trajectory_slots': [{'slot': 0, 'p_kw': 1}], 'state_sha256': 'c'}], 'trace': {}, 'dedup_audit': []}
    return parents, payload


@pytest.mark.parametrize('changed', ['traffic_forecast', 'route_table', 'A0_segment_SHA', 'electrical_coefficients'])
def test_stage_different_dependency_rejected_and_preserved(tmp_path, changed):
    parents, payload = stage_data(); path = tmp_path / 'STAGE_1.json'; old = m1_identity()
    cache.write_stage(path, payload, old, parents, 1); before = path.read_bytes()
    current = m1_identity(**{changed: digest('changed')})
    assert cache.restore_stage(path, current, parents, 1) is None and path.read_bytes() == before
    assert read(path.with_name(path.name + '.NON_REUSABLE.json'))['STALE_STAGE_RESTORE_ALLOWED'] == 'NO'
    cache.write_stage(path, payload, current, parents, 1)
    assert list((tmp_path / 'non_reusable').glob('STAGE_1_*.json'))


def test_exact_current_stage_resumes_and_parent_mutation_rejected(tmp_path):
    parents, payload = stage_data(); path = tmp_path / 'STAGE_1.json'; identity = m1_identity()
    cache.write_stage(path, payload, identity, parents, 1)
    assert cache.restore_stage(path, identity, parents, 1) == payload
    parents[0]['state_sha256'] = 'changed'
    assert cache.restore_stage(path, identity, parents, 1) is None


def test_full_and_restricted_caches_share_family(tmp_path):
    identity = m1_identity()
    for kind in ('RESTRICTED', 'FULL_CHILD', 'MIPSTART'):
        expected = cache.cache_identity(identity, kind=kind, candidate='a', parent_SHA='parent', fixed_trajectory_SHA='trajectory', step=1)
        path = tmp_path / (kind + '.json'); cache.store_candidate(path, expected, {'rho': .5})
        assert cache.restore_candidate(path, expected)
        changed = cache.cache_identity(m1_identity(traffic_forecast='different'), kind=kind, candidate='a', parent_SHA='parent', fixed_trajectory_SHA='trajectory', step=1)
        assert cache.restore_candidate(path, changed) is None


def test_obsolete_matrix_cannot_reach_launcher(tmp_path):
    from dayahead.v40h.launcher import prelaunch
    old = tmp_path / 'V40B_MAY_EXECUTION_MATRIX.json'; write_json(old, {'rows': []})
    with pytest.raises(IntegrityError, match='OBSOLETE_EXECUTION_MATRIX'): prelaunch(tmp_path, old, campaign)


def electrical_fixture(tmp_path):
    assets = tmp_path / 'feeder'; assets.mkdir(); master = assets / 'master.dss'; child = assets / 'child.dss'
    master.write_text('Redirect child.dss'); child.write_text('New Load.x kW=1')
    demand = tmp_path / 'demand.json'; demand.write_text('1')
    mapper = tmp_path / 'mapper.py'; mapper.write_text('allocation=1')
    def expected():
        values = {k: digest(k) for k in electrical.ROLES}
        values.update(day='2025-05-01', feeder_manifest=electrical.feeder_manifest([assets], [master]),
            OpenDSS_master=file_record(master), native_mapper=file_record(mapper), demand=file_record(demand), alpha_grid={'value': .7481417265421424, 'authority': digest('scale')})
        return electrical.electrical_identity(values)
    outputs = {}
    def producer(identity):
        for role in electrical.OUTPUTS:
            p = tmp_path / (role + '.npz'); p.write_bytes(b'coefficient bytes'); outputs[role] = p
        return outputs
    cert = tmp_path / 'electrical.json'; electrical.generate(cert, expected, producer)
    return cert, expected, demand, mapper, child


@pytest.mark.parametrize('target', [2, 3, 4])
def test_stale_electrical_demand_mapper_or_feeder_rejected(tmp_path, target):
    data = electrical_fixture(tmp_path); cert, expected = data[:2]
    assert set(electrical.load(cert, expected)) == set(electrical.OUTPUTS)
    data[target].write_text('changed input; coefficient file still intact')
    with pytest.raises(ValueError, match='STALE_ELECTRICAL_AUTHORITY'): electrical.load(cert, expected)


def test_electrical_namespace_scale_same_actual_values_can_differ(tmp_path):
    cert, expected, *_ = electrical_fixture(tmp_path); planning = expected()
    inp = deepcopy(planning['identity']['inputs']); inp.update(demand='realized', PV='realized', weather='realized')
    actual = electrical.electrical_identity(inp)
    assert electrical.namespace_gate(planning, planning, actual)['status'] == 'PASS'
    inp['alpha_grid']['value'] = 1
    with pytest.raises(IntegrityError): electrical.namespace_gate(planning, planning, electrical.electrical_identity(inp))


@pytest.mark.parametrize('changed', ['V40G_source_SHA', 'common_T_DA_SHA', 'electrical_authority_SHA'])
def test_b1_external_generation_identity_rejects_stale(tmp_path, changed):
    ctx, _ = context96(); jobs = [migrant()]; power = planning_power(jobs, ctx)
    inputs = {k: digest(k) for k in b1.ROLES}; expected = lambda: b1.generation_identity(inputs)
    path = tmp_path / 'B1.json'; traj = tmp_path / 'power.npz'; np.savez_compressed(traj, **power)
    b1.generate(path, expected, lambda identity: {'status': 'PASS', 'diagnostic_only': False, 'jobs': jobs,
        'final_decision_SHA': digest(jobs)})
    handle = b1.load_b1_as_a0(path, expected, traj, ctx)
    assert handle['B3_A0_AIDC_OPTIMIZE_CALLS'] == 0 and handle['B1_GENERATION_IDENTITY_SHA'] == handle['B3_A0_GENERATION_IDENTITY_SHA']
    inputs[changed] = digest('changed')
    with pytest.raises(IntegrityError, match='STALE_DIFFERENT_IDENTITY'): b1.load_b1_as_a0(path, expected, traj, ctx)


def regression_job(site='UNASSIGNED'):
    issue = datetime(2025, 5, 2, 18, tzinfo=timezone(timedelta(hours=10)))
    job = {'job_uid': '8749975', 'state_at_issue': 'PENDING', 'requested_GPU': 4, 'AIDC_site': site,
        'start_slot': 13, 'end_slot': 21, 'safe_duration_slots': 8, 'safe_duration_seconds': 7200,
        'qos': 'normal', 'migration_selected': False, 'submit_time': issue.isoformat(), 'requested_walltime_seconds': 12000,
        'Rack_label': None, 'accepted_A0_assignment_and_WAN': {}}
    obs = {'start_time': issue + timedelta(hours=2), 'end_time': issue + timedelta(hours=5, minutes=18, seconds=24), 'gpus_requested': 4}
    return issue, job, obs


@pytest.mark.parametrize('case', ['B1', 'B3'])
def test_8749975_counterfactual_day_overlap_fail_closed(case):
    from dayahead.v40h.pre_day_complete import classify, SITE_BLOCKER
    from dayahead.v40h.actual import replay_jobs
    issue, job, obs = regression_job()
    result = classify(job, obs, issue)
    assert result['status'] != 'PRE_DAY_COMPLETE' and result['reason'] == SITE_BLOCKER
    assert result['earliest_counterfactual_end_slot'] == pytest.approx(26.226666666666667)
    assert result['earliest_counterfactual_D_day_compute_seconds'] == pytest.approx(2004)
    with pytest.raises(ValueError, match=SITE_BLOCKER): replay_jobs(import_frozen([job]), {'8749975': obs}, issue_time=issue, site_capacity={}, racks=[])


def test_known_site_overlap_is_preserved_in_actual_gpu():
    from dayahead.v40h.actual import replay_jobs
    from dayahead.v40h.pre_day_complete import classify, require_safe_exclusion
    from dayahead.v40d_actual.rack_dispatch import Rack
    issue, job, obs = regression_job('AIDC01')
    result = replay_jobs(import_frozen([job]), {'8749975': obs}, issue_time=issue, site_capacity={'AIDC01': 64}, racks=[Rack('AIDC01', 'R', 64)])
    ledger = result['job_ledger']; gpu, _ = occupancy(ledger, ['AIDC01'], actual=True)
    assert gpu[:3, 0].tolist() == [4, 4, 4] and gpu[3:].sum() == 0
    assert ledger[0]['counterfactual_day_classification']['D_DAY_GPU_SERVICE'] == pytest.approx(2004 * 4 / 3600)
    early = dict(job, start_slot=0, end_slot=8)
    proof = classify(early, obs, issue, execution_segments=[{'site': 'AIDC01', 'start': 0, 'end': 11904 / 900}])
    require_safe_exclusion(proof)
    assert proof['D_DAY_GPU_SERVICE'] == 0


def test_8666895_required_canonical_migration_example():
    # Read the preserved accepted row, not a restatement of the expected answer.
    root = Path(__file__).resolve().parents[2]
    artifact = read(root / 'dayahead/artifacts/v40g_segment_integration/smoke/2025-05-01/B3_A0_STATIC_REUSE/CANONICAL_B1_FINAL_AS_A0.json')
    jobs = artifact['jobs'] if isinstance(artifact, dict) else artifact
    actual = next(r for r in jobs if str(r['job_uid']) == '8666895')
    segments = actual['compute_segments']
    assert [(s['site'], s['start'], s['end']) for s in segments] == [('AIDC05', 0, 25), ('AIDC01', 28, 110)]
    assert actual['requested_GPU'] == 1
    assert sum(s['end'] - s['start'] for s in segments) == 107
    assert all(not any(s['start'] <= t < s['end'] for s in segments) for t in range(25, 28))
    row = migrant(); row['compute_segments'] = [{'site': row['AIDC_site'], 'start': 0, 'end': row['end_slot']}]
    with pytest.raises(ValueError): import_frozen([row])


@pytest.mark.parametrize('stage', ['A1', 'MF'])
def test_lower_priority_cannot_lose_tiny_primary_gain(stage):
    from dayahead.v40h.primary import preserve
    primary = {'rho': .5 - 5e-8}; lower = {'rho': .5}
    accepted, audit = preserve(primary, primary['rho'], lower, lambda x: x['rho'])
    assert accepted == primary and audit['primary_degradation_due_to_lower_priorities'] == 0


def test_actual_a1_primary_extraction_report():
    from dayahead.v40h.feedback import solve_feedback
    from tests.dayahead.test_v40a_coordination import trajectory
    ctx, pending = context96(); result = solve_feedback([pending], trajectory(), ctx)
    assert result['status'] == 'PASS'
    assert result['A1_primary_degradation_due_to_lower_priorities'] == 0
    assert result['A1_final_recomputed_rho'] <= result['strict_primary_guard']['primary_materialized_rho'] + 1e-10


def test_hardened_beam_blocks_without_identity_before_any_work():
    from dayahead.v40h import beam_driver
    with pytest.raises(IntegrityError, match='M1_TRANSITIVE_IDENTITY_REQUIRED'): beam_driver._run_case('B3', 2, 1)


def test_restricted_pickle_cache_validates_before_deserialization(tmp_path, monkeypatch):
    from dayahead.v40h.candidate_cache import CandidateResultCache
    from dayahead.v37.execution_acceleration import CandidateResultCache as Old
    x = m1_identity()
    instance = CandidateResultCache(tmp_path, {'V40H_execution_identity': x, 'execution_fingerprint_sha256': x['identity_SHA'],
        'beam_parent_fingerprint': 'parent', 'fixed_previous_MESS_trajectory_SHA': 'prior',
        'parent_state_content_SHA': 'exact-parent', 'fixed_previous_MESS_trajectory_exact_SHA': 'exact-trajectory'})
    spec = instance.specification('candidate', 1)
    CandidateResultCache.store(spec, {'result': np.array([1., 2.])})
    assert np.array_equal(CandidateResultCache.load(spec)['result'], [1., 2.])
    path = Path(spec['path']); original = path.read_bytes(); path.write_bytes(original + b'mutated')
    monkeypatch.setattr(Old, 'load', lambda spec: pytest.fail('unpickle reached before SHA rejection'))
    assert CandidateResultCache.load(spec) is None and path.read_bytes() == original + b'mutated'


def test_generation_detects_changed_input_during_producer(tmp_path):
    cert, expected, demand, mapper, child = electrical_fixture(tmp_path)
    outputs = electrical.load(cert, expected)
    def producer(identity):
        demand.write_text('2')
        return outputs
    with pytest.raises(IntegrityError): electrical.generate(tmp_path / 'new_cert.json', expected, producer)
    assert not (tmp_path / 'new_cert.json').exists()


def test_reused_expected_object_cannot_hide_mutated_input(tmp_path):
    cert, expected, demand, mapper, child = electrical_fixture(tmp_path)
    outputs = electrical.load(cert, expected)
    identity = expected(); electrical.generate(tmp_path / 'cert.json', lambda: identity, lambda _: outputs)
    demand.write_text('2')
    with pytest.raises(IntegrityError): electrical.load(tmp_path / 'cert.json', lambda: identity)


def test_unattested_b1_no_posthoc_adoption(tmp_path):
    path = tmp_path / 'old_b1.json'; write_json(path, {'status': 'PASS', 'diagnostic_only': False})
    expected = b1.generation_identity({k: digest(k) for k in b1.ROLES})
    with pytest.raises(IntegrityError, match='NO_POST_HOC_ADOPTION'):
        b1.load_b1_as_a0(path, lambda: expected, tmp_path / 'missing.npz', None)


def test_numerical_generator_namespace_preserves_old_evidence():
    from dayahead.v40h.numerical_context import _kernel
    from dayahead.v40e import electrical as frozen
    k = _kernel()
    assert k['REL'] == CAMPAIGN and frozen.REL != CAMPAIGN
    for name in ('upstream', 'rebuild_day', 'electrical_context', 'planning_context'):
        assert k[name].__globals__ is k
        assert k[name].__code__ == getattr(getattr(frozen, name), '__wrapped__', getattr(frozen, name)).__code__


def test_numeric_context_without_generation_certificate_rejected(tmp_path):
    from dayahead.v40h.numerical_context import require_attested_context
    from types import SimpleNamespace
    cert, expected, *_ = electrical_fixture(tmp_path)
    outputs = electrical.load(cert, expected)
    certificate = tmp_path / 'cert.json'; electrical.generate(certificate, expected, lambda _: outputs)
    with pytest.raises(IntegrityError, match='UNATTESTED_NUMERICAL_CONTEXT'):
        require_attested_context(SimpleNamespace(), certificate, expected)


def test_real_mf_bounded_primary_report():
    from dayahead.v40h.recourse import solve_fixed_route
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from tests.dayahead.test_v40a_coordination import trajectory
    from dataclasses import replace
    ctx, _ = context96(); ctx.coefficients = ctx.coefficients[:2]
    authority = MessElectricalAuthority.from_repository()
    first = replace(trajectory().slots[0], battery_energy_kwh=authority.initial_energy_kwh,
                    soc_fraction=authority.initial_energy_kwh / authority.capacity_kwh)
    mess = MessTrajectory(tuple(replace(first, slot=t) for t in range(2)))
    result = solve_fixed_route(np.ones((2, 12)), mess, ctx)
    assert result['status'] == 'PASS' and result['lower_priority_stages'] == 0
    assert result['MF_primary_degradation_due_to_lower_priorities'] == 0
    assert np.isfinite(result['MF_primary_incumbent']) and np.isfinite(result['MF_primary_bound'])
    assert result['MF_final_recomputed_rho'] == result['grid']['rho_max']


def test_full_child_identity_binds_exact_unrounded_parent():
    from dayahead.v40h.candidate_cache import full_child_identity
    x = m1_identity(); context = {'V40H_execution_identity': x, 'execution_fingerprint_sha256': x['identity_SHA']}
    arguments = dict(parent_state_sha256='rounded-parent', fixed_trajectory_sha256='rounded-trajectory',
        parent_content_sha256='exact-parent', fixed_trajectory_exact_sha256='exact-trajectory',
        mess_step=1, candidate_id='candidate', seed_trajectory_sha256='seed')
    first = full_child_identity(context, **arguments)
    arguments['fixed_trajectory_exact_sha256'] = 'changed-smaller-than-old-quantization'
    assert full_child_identity(context, **arguments) != first


def test_retained_state_recomputes_internal_trajectory_identity():
    from dayahead.v35r3e_r1.beam import canonical_sha256, trajectory_equivalence_sha
    from tests.dayahead.test_v40a_coordination import trajectory
    slots = [trajectory().slots[0].to_dict()]
    raw = dict(case_id='B3', beam_state_id='B3-S1', parent_state_id='B3-ROOT', completed_vehicles=['MESS01'],
               trajectory_slots=slots, trajectory_equivalence_sha256=trajectory_equivalence_sha(slots))
    raw['state_sha256'] = canonical_sha256({'case': 'B3', 'completed_vehicles': ['MESS01'],
        'trajectory_equivalence_sha256': raw['trajectory_equivalence_sha256']})
    cache.state_record(raw)
    raw['trajectory_slots'][0]['p_kw'] += .001
    with pytest.raises(IntegrityError, match='INTERNAL_TRAJECTORY'): cache.state_record(raw)
