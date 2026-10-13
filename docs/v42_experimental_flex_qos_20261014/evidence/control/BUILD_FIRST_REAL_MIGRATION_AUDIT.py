"""Read a completed counterfactual; never import or execute production code."""
from pathlib import Path
import collections
import datetime
import gzip
import hashlib
import json
import math
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'audit/control/FINAL_FLEX_COMPARISON/E1_FLEX30_GREEDY'
EXPECTED_SOURCE = 'c4b59fb3898da7f3bed6b3b6818890165c74f7f1f90e4cd2470fa3abd5c56c0a'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = read(FOLDER / 'EXECUTION_RECEIPT.json')
    result_path = FOLDER / 'CONDITIONAL_ACTUAL_RESULT.json.gz'
    assert receipt['source_freeze_sha'] == EXPECTED_SOURCE
    assert sha(result_path) == receipt['result_sha256']
    with gzip.open(result_path, 'rt', encoding='utf-8-sig') as stream:
        data = json.load(stream)
    state = data['carryout']['controller']
    migrations = data['migration_receipts']
    assert len(migrations) == 1
    migration = migrations[0]
    uid = migration['job_id']
    metadata, job, request = (state[key][uid] for key in ('metadata', 'episode_jobs', 'requests'))
    budget = data['qos_budget_ledger'][uid]
    qos = next(row for row in data['qos_ledger'] if row['uid'] == uid)
    events = [row for row in data['job_event_ledger'] if row['uid'] == uid]
    choices = [row for row in data['rule_consumption_receipt'] if row.get('uid') == uid and row.get('action') == 'CHECKPOINT_MIGRATE']
    assert len(choices) == 1
    choice = choices[0]
    assert migration['policy_sha'] == receipt['policy_sha'] == choice['policy_sha']
    assert data['conditional_case']['case_sha'] == receipt['case_sha']
    assert choice['source'] == 'CURRENT_EPISODE_LEDGER_NOT_FUTURE_ACTUAL'
    assert choice['physical_feasible'] and choice['q50_hard_feasible']
    assert choice['q90_risk']['hard_feasible'] and choice['q90_mass_conservation']['conservation_PASS']
    source_path = ROOT / 'audit/migration/MIGRATION_SOURCE_NUMERIC_AUTHORITY.json'
    handoff_path = ROOT / 'audit/migration/MIGRATION_PACKET_API_HANDOFF.json'
    source, handoff = read(source_path), read(handoff_path)
    capability = migration['migration_capability_packet']
    route = capability['wan_path']
    scalar = source['scalar_authority']
    assert capability['source_sha'] == migration['capability_source_sha'] == handoff['packet_source_sha']
    route_row = source['routes'][route]
    assert route_row['source'] == migration['source'] and route_row['destination'] == migration['destination']
    assert route_row['links'] == capability['route_links']
    gpu = request['gpu']
    assert gpu == job['gpu'] == 1
    assert capability['payload_bytes'] == scalar['bytes_per_GPU'] * gpu == 80_000_000_000
    rate = min(source['links'][link]['bandwidth_bytes_per_second'] for link in capability['route_links'])
    assert rate == capability['bandwidth_bytes_per_second'] == 1_240_000_000
    assert all(migration['WAN_payload_bytes_on_each_ordered_link'][link] == capability['payload_bytes'] for link in capability['route_links'])
    times = migration['times']
    begin, end = receipt['begin_seconds'], receipt['end_seconds']
    sites = data['sites']
    indices = {site: index for index, site in enumerate(sites)}
    assert times['checkpoint'] == migration['physical_checkpoint_seconds'] == migration['control_checkpoint_seconds'] == times['transfer_start']
    assert times['transfer_end'] - times['transfer_start'] == max(900, math.ceil(capability['payload_bytes'] / rate / 900) * 900) == 900
    assert times['restart_start'] == times['transfer_end']
    assert times['restart_end'] - times['restart_start'] == capability['restart_seconds'] == scalar['current_conservative_restart_seconds'] == 900
    assert migration['interruption_seconds'] == times['restart_end'] - times['checkpoint'] == 1800
    assert capability['source_wait_seconds'] == 0
    assert migration['hold_contract'] == {'source_hold_until': 'transfer_start', 'destination_hold_from': 'transfer_end'}
    assert job['start_time'] == next(row['time_seconds'] for row in events if row['event'] == 'RUNNING')
    assert times['checkpoint'] - job['start_time'] == migration['accumulated_compute_seconds'] == scalar['checkpoint_interval_seconds'] == 1800
    assert budget['budget_seconds'] == qos['budget_seconds'] == 1800
    assert qos['intentional_start_delay_seconds'] + qos['migration_interruption_seconds'] == qos['total_intentional_burden_seconds'] == 1800
    assert metadata['migration_count'] == len([row for row in migrations if row['job_id'] == uid]) == scalar['maximum_migrations_per_job'] == 1
    assert qos['intentional_start_delay_seconds'] == metadata['additional_start_delay_seconds'] == 0
    assert metadata['cumulative_migration_interruption_seconds'] == 1800
    reference_rows = [row for row in data['experimental_reference_audit'] if row['uid'] == uid]
    references = [row for row in reference_rows if row['event'] == 'CAUSAL_REFERENCE_FROZEN']
    advances = [row for row in reference_rows if row['event'] == 'OBSERVED_PHYSICAL_REFERENCE_ADVANCE']
    assert len({row['first_reference_start_seconds'] for row in references}) == 1
    first, last = references[0]['first_reference_start_seconds'], references[-1]['reference_start_seconds']
    decision = state['decisions'][uid]
    window = decision['execution_window_receipt']
    assert decision['start_seconds'] == job['start_time']
    assert job['start_time'] in window['allowed_starts_seconds'] and job['start_time'] <= window['latest_start_seconds']
    assert window['budget_seconds'] == 1800 and window['first_causal_reference_start_seconds'] == first
    assert all(not row['immutable_budget_renewed'] and not row['intentional_spend_refunded'] for row in advances)
    assert sum(row['new_reference_start_seconds'] - row['old_reference_start_seconds'] for row in advances) == last - first
    for advance in advances:
        old = next(row for row in references if row['reference_start_seconds'] == advance['old_reference_start_seconds'])
        proof = advance['proof']
        assert proof['old_reference_start_seconds'] == advance['old_reference_start_seconds']
        assert old['reference_start_seconds'] <= proof['observed_at_seconds'] <= old['reference_start_seconds'] + 1800 - old['intentional_burden_at_reference_seconds']
        assert proof.get('observed_GPU') and proof.get('public_resource_sha')
        assert advance['wait_class'] != 'GRID_REQUIRED_WAIT' or proof.get('original_grid_violations')

    occupation_array = np.zeros((96, len(sites)))
    compute_array = np.zeros_like(occupation_array)
    point_events, unstarted = [], []
    uid_intervals = {}

    def add(array, site, start, finish, quantity):
        start, finish = max(float(start), begin), min(float(finish), end)
        if finish <= start:
            return
        for slot in range(96):
            overlap = max(0, min(finish, begin + (slot + 1) * 900) - max(start, begin + slot * 900))
            if overlap:
                array[slot, indices[site]] += quantity * overlap / 900

    def occupation(site, start, finish, quantity):
        add(occupation_array, site, start, finish, quantity)
        start, finish = max(float(start), begin), min(float(finish), end)
        if finish > start:
            point_events.extend([(start, site, quantity), (finish, site, -quantity)])

    for episode_uid, episode in state['episode_jobs'].items():
        start = episode['start_time']
        if start is None:
            assert episode['latest_observed_state'] == 'PENDING'
            unstarted.append(episode_uid)
            continue
        release = episode.get('release_control_time')
        release = end if release is None else min(release, end)
        completion = episode.get('completion_observed_time')
        completion = end if completion is None else min(completion, end)
        movement = episode.get('migration_receipt')
        if movement:
            clock = movement['times']
            occupation(movement['source'], start, clock['transfer_start'], episode['gpu'])
            occupation(movement['destination'], clock['transfer_end'], release, episode['gpu'])
            add(compute_array, movement['source'], start, clock['checkpoint'], episode['gpu'])
            add(compute_array, movement['destination'], clock['restart_end'], completion, episode['gpu'])
            if episode_uid == uid:
                uid_intervals = {'occupation': [dict(site=movement['source'], begin=start, end=clock['transfer_start'], GPU=episode['gpu']), dict(site=movement['destination'], begin=clock['transfer_end'], end=release, GPU=episode['gpu'])], 'compute': [dict(site=movement['source'], begin=start, end=clock['checkpoint'], GPU=episode['gpu']), dict(site=movement['destination'], begin=clock['restart_end'], end=completion, GPU=episode['gpu'])]}
        else:
            occupation(episode['initial_site'], start, release, episode['gpu'])
            add(compute_array, episode['initial_site'], start, completion, episode['gpu'])
    occupation_error = float(np.max(np.abs(occupation_array - np.asarray(data['occupancy_GPU']))))
    compute_error = float(np.max(np.abs(compute_array - np.asarray(data['compute_occupancy_GPU']))))
    assert occupation_error < 1e-10 and compute_error < 1e-10
    capacities = {site: state['reservations']['capacities']['gpu:' + site] for site in sites}
    use = {site: 0 for site in sites}
    peaks = use.copy()
    by_time = collections.defaultdict(lambda: collections.defaultdict(float))
    for clock, site, delta in point_events:
        by_time[clock][site] += delta
    for clock in sorted(by_time):
        for site, delta in by_time[clock].items():
            use[site] += delta
            peaks[site] = max(peaks[site], use[site])
        assert all(-1e-9 <= use[site] <= capacities[site] + 1e-9 for site in sites)
    assert peaks == receipt['actual_receipt']['max_per_site_GPU']
    segments = {row['resource']: row for row in migration['segments']}
    wan_checks = []
    for resource in ('wan:' + route, 'active:WAN', *('wan:LINK::' + link for link in capability['route_links'])):
        segment = segments[resource]
        limit = state['reservations']['capacities'][resource]
        assert segment['begin'] == times['transfer_start'] and segment['end'] == times['transfer_end'] and 0 < segment['quantity'] <= limit
        wan_checks.append(dict(resource=resource, quantity=segment['quantity'], capacity=limit, PASS=True))
    assert segments['active:WAN']['quantity'] == scalar['maximum_active_transfers_network_wide'] == 1
    assert all(row['quantity'] == gpu for row in migration['segments'] if row['resource'].startswith('gpu:'))
    assert not any(row['resource'] == 'gpu:' + migration['source'] and row['end'] > times['transfer_start'] for row in migration['segments'])
    compute_seconds = sum((row['end'] - row['begin']) * row['GPU'] for row in uid_intervals['compute'])
    occupation_seconds = sum((row['end'] - row['begin']) * row['GPU'] for row in uid_intervals['occupation'])
    assert compute_seconds == metadata['accumulated_compute_seconds'] * gpu == 19082
    assert compute_seconds == (job['completion_observed_time'] - job['start_time'] - migration['interruption_seconds']) * gpu
    assert uid_intervals['compute'][0]['end'] <= uid_intervals['compute'][1]['begin']
    cc4 = [row for row in data['cc4_depletion_ledger'] if row.get('uid') == uid]
    assert len(cc4) == 1 and cc4[0]['depletion_count'] == 1 and cc4[0]['observed_at'] == job['submit_time'] == request['submit']
    array_path = FOLDER / 'ACTUAL_PHYSICAL_ARRAYS.npz'
    array_checks = {}
    with np.load(array_path, allow_pickle=False) as arrays:
        mapping = {'occupancy_GPU': data['occupancy_GPU'], 'compute_occupancy_GPU': data['compute_occupancy_GPU'], 'physical_IT_kw': data['physical']['IT_kw'], 'physical_PCC_P_kw': data['physical']['PCC_P_kw'], 'physical_PCC_Q_kvar': data['physical']['PCC_Q_kvar']}
        for name, rows in mapping.items():
            array_checks[name] = dict(shape=list(arrays[name].shape), bitwise_json_match=np.array_equal(arrays[name], np.asarray(rows)))
            assert array_checks[name]['bitwise_json_match'] and arrays[name].shape == (96, 12)
        energy = source['energy']
        expected_it = energy['idle_kW_per_installed_GPU'] * np.array([capacities[site] for site in sites]) + energy['active_swing_kW_per_GPU'] * arrays['occupancy_GPU']
        it_error = float(np.max(np.abs(expected_it - arrays['physical_IT_kw'])))
        q_error = float(np.max(np.abs(arrays['physical_PCC_Q_kvar'] - arrays['physical_PCC_P_kw'] * math.tan(math.acos(energy['power_factor'])))))
        assert it_error < 1e-10 and q_error < 1e-10
        phase_slots = [dict(slot=slot, clock=begin + slot * 900, source_total_GPU=float(arrays['occupancy_GPU'][slot, indices[migration['source']]]), destination_total_GPU=float(arrays['occupancy_GPU'][slot, indices[migration['destination']]]), source_PCC_P_kw=float(arrays['physical_PCC_P_kw'][slot, indices[migration['source']]]), destination_PCC_P_kw=float(arrays['physical_PCC_P_kw'][slot, indices[migration['destination']]]), source_PCC_Q_kvar=float(arrays['physical_PCC_Q_kvar'][slot, indices[migration['source']]]), destination_PCC_Q_kvar=float(arrays['physical_PCC_Q_kvar'][slot, indices[migration['destination']]])) for slot in range(int((job['start_time'] - begin) // 900), int((times['restart_end'] - begin) // 900) + 1)]
    actual = receipt['actual_receipt']
    assert actual['future_duration_controller_reads'] == actual['future_completion_controller_reads'] == actual['capacity_violations'] == actual['dropped_jobs'] == 0
    assert actual['actual_power_recomputed'] and not actual['planning_power_copied'] and data['physical']['IT_recomputed_from_actual_occupation']
    assert receipt['retrospective_service_audit']['PASS'] and receipt['retrospective_service_audit']['controller_private_reads'] == 0
    report = dict(schema='FIRST_REAL_MIGRATION_INDEPENDENT_AUDIT_V1', status='PASS', reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), evidence_kind='SOURCE_REAL_UID_CAUSAL_COUNTERFACTUAL_EXECUTED_MIGRATION;NOT_Kestrel_OBSERVED_MIGRATION', source_sha=EXPECTED_SOURCE, case_sha=receipt['case_sha'], policy_sha=receipt['policy_sha'], input_file_receipts=dict(execution_receipt_sha256=sha(FOLDER / 'EXECUTION_RECEIPT.json'), actual_result_sha256=sha(result_path), actual_array_npz_sha256=sha(array_path), migration_source_numeric_sha256=sha(source_path), migration_packet_handoff_sha256=sha(handoff_path)), uid=uid, episode_id=migration['episode_id'], origin_unknown_preserved=metadata['origin_unknown'], public_observed_submit_seconds=request['submit'], replay_start_seconds=job['start_time'], physical_checkpoint_seconds=migration['physical_checkpoint_seconds'], control_checkpoint_seconds=migration['control_checkpoint_seconds'], phase_times=times, source=migration['source'], destination=migration['destination'], whole_gang_GPU=gpu, WAN_route=route, WAN_ordered_links=capability['route_links'], payload_bytes_each_link=migration['WAN_payload_bytes_on_each_ordered_link'], rounded_bandwidth_reservation_bytes_each_link=migration['WAN_reservation_bytes_on_each_link'], reserved_bandwidth_bytes_are_not_transmitted_payload=True, WAN_route_link_global_capacity_checks=wan_checks, hold_contract=migration['hold_contract'], physical_job_intervals=uid_intervals, double_compute_or_partial_gang=False, first_R0_seconds=first, current_R0_at_start_seconds=last, observed_reference_advance_total_seconds=last - first, advance_seconds_by_wait_class={key: sum(row['new_reference_start_seconds'] - row['old_reference_start_seconds'] for row in advances if row['wait_class'] == key) for key in {row['wait_class'] for row in advances}}, all_R0_advance_proofs_timely_public_physical=True, R0_reference_audit=reference_rows, start_inside_saved_window=True, saved_execution_window_deadline_seconds=window['latest_start_seconds'], immutable_budget_seconds=budget['budget_seconds'], committed_start_delay_seconds=qos['intentional_start_delay_seconds'], migration_interruption_seconds=qos['migration_interruption_seconds'], shared_total_intentional_burden_seconds=qos['total_intentional_burden_seconds'], budget_renewal_or_spend_refund=False, migration_count=metadata['migration_count'], source_max_migrations=scalar['maximum_migrations_per_job'], legacy_issuer_latest_start_excess_seconds=qos['latest_start_excess_seconds'], actual_queue_wait_seconds=qos['actual_wait_seconds'], elapsed_submit_to_start_is_not_all_intentional_delay=True, source_observed_whole_SLA_certified=False, post_execution_compute_audit=dict(scope='POST_EXECUTION_PUBLIC_COMPLETION_AND_EPISODE_CLOCKS;NEVER_FUTURE_CONTROLLER_INPUT', service_compute_GPU_seconds=compute_seconds, occupation_GPU_seconds=occupation_seconds, Q50_prediction_seconds=request['q50'], observed_service_overrun_seconds=compute_seconds / gpu - request['q50'], completion_observed_replay_seconds=job['completion_observed_time'], GPU_release_control_seconds=job['release_control_time'], compute_preserved_after_migration=True, compute_vs_occupation_distinct=True, never_started_episodes_no_physical_occupation=len(unstarted), all_jobs_interval_reconstruction_max_absolute_occupation_GPU_error=occupation_error, all_jobs_interval_reconstruction_max_absolute_compute_GPU_error=compute_error, all_jobs_pointwise_whole_gang_capacity_violations=0, all_jobs_pointwise_peak_GPU_by_site=peaks), CC4_UID_depletion_count=len(cc4), all96_actual_power_array_checks=array_checks, IT_from_actual_occupation_max_absolute_error_kW=it_error, PCC_Q_power_factor_max_absolute_error_kvar=q_error, original_C1_callback_execution_recomputed_flag=actual['actual_power_recomputed'], original_C1_not_reexecuted_by_reviewer=True, power_authority_sha=data['physical']['authority_sha'], phase_slot_PCC_array_linkage=phase_slots, selected_Q50_peak_score=choice['q50_peak_score'], selected_Q90_CDF_risk=choice['q90_risk'], selected_Q90_extra_mass=choice['q90_mass_conservation'], retrospective_population_service_mass_audit=receipt['retrospective_service_audit'], future_private_controller_reads=0, checkpoint_payload_Kestrel_measured=False, checkpoint_and_hold_protocol='EXPLICIT_EXPERIMENTAL_ASSUMPTION_REUSING_SOURCE_NUMERIC_ENGINEERING_MODEL', source_engineering_payload_bytes_per_GPU=scalar['bytes_per_GPU'], source_historical_restart_seconds=scalar['historical_restart_seconds'], experimental_conservative_restart_seconds=capability['restart_seconds'], WAN_transfer_energy_kWh=None, checkpoint_save_IO_energy_kWh=None, missing_energy_is_zero=False, Fresh_AC='NOT_RUN', Actual_Maximum_Line_Loading=None, replay_actual_power_is_not_a_new_AC_certificate=True, source_or_production_edits=0, Actual_runs_by_reviewer=0, Native_runs_by_reviewer=0, AC_runs_by_reviewer=0, events=events)
    target = ROOT / 'audit/control/FIRST_REAL_MIGRATION_INDEPENDENT_AUDIT.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], uid=uid, compute_seconds=compute_seconds, occupation_seconds=occupation_seconds, occupation_error=occupation_error, compute_error=compute_error, wait_class_seconds=report['advance_seconds_by_wait_class'], IT_error=it_error, PCC_Q_error=q_error, output=str(target), SHA256=sha(target))))


if __name__ == '__main__':
    main()
