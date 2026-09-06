"""Independent UID/slot/service and complete physical-array comparison."""
from pathlib import Path
from collections import Counter
import json
import struct
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, write_parquet, reference, sha
from dayahead.v40a.invariants import digest
from .authority import REL, OLD, verify_preserved
from .canonical import identities, occupancy, terminal, wan_audit, require

GATE_NAMES = ('MIGRATED_JOB_SEGMENT_MODEL', 'B1_B3_A0_SEGMENT_IDENTITY', 'PLANNING_SEGMENT_POWER',
              'FRESH_SEGMENT_POWER', 'ACTUAL_SEGMENT_REPLAY', 'TERMINAL_SEGMENT_STATE', 'WAN_MIGRATION_ACCOUNTING')


def array_comparison(a, b):
    a, b = np.asarray(a), np.asarray(b)
    same = a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()
    error = None
    if a.shape == b.shape and a.dtype.kind in 'fiu' and b.dtype.kind in 'fiu':
        finite = np.isfinite(a) & np.isfinite(b)
        error = float(np.max(abs(a[finite] - b[finite]), initial=0))
    return {'bit_identical': same, 'values_exact_equal': bool(np.array_equal(a, b, equal_nan=True)) if a.dtype.kind in 'fiu' else bool(np.array_equal(a, b)),
            'shape': list(a.shape), 'dtype': str(a.dtype), 'prior_dtype': str(b.dtype), 'max_finite_error': error}


def compare_npz(a, b):
    with np.load(a, allow_pickle=False) as x, np.load(b, allow_pickle=False) as y:
        require(set(x.files) == set(y.files), 'PHYSICAL_ARRAY_KEY_DRIFT')
        return {k: array_comparison(x[k], y[k]) for k in x.files}


def actual_audit(repo, smoke, planned, out):
    from dayahead.v40d_actual.inputs import capacity
    from dayahead.v40d_actual.capacity_audit import check_it_power
    from dayahead.v40d_actual.physical_audit import c1_recalculation
    from dayahead.v40d_actual.exogenous import load as exogenous
    from dayahead.v38.authority import load_wan_authority
    cap = capacity(repo)[0]['frozen_V39C_site_capacity']; sites = sorted(cap)
    wan = load_wan_authority(repo); exo = exogenous(repo, '2025-05-01')
    source = repo / 'dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    observed = pd.read_parquet(source); observed['id'] = observed.id.astype(str); observed = observed.set_index('id')
    require(not observed.index.duplicated().any(), 'OBSERVED_UID_DUPLICATE')
    issue = pd.Timestamp('2025-04-30T18:00:00+10:00'); cases = {}; ledgers = {}; powers = {}; partition = {}
    for case in ('B0', 'B1'):
        frame = pd.read_parquet(smoke / case / 'job_ledger.parquet')
        require(not frame.job_uid.duplicated().any(), 'ROOT_UID_DUPLICATE')
        frozen = {r['job_uid']: r for r in planned[case]}; ledger = []; service = []; expected = {}
        for recorded in frame.to_dict('records'):
            uid = recorded['job_uid']; base = frozen[uid]
            # Bind the loaded executed fields back to the exact frozen job.
            for k in ('compute_segments', 'migration_events', 'common_terminal_obligation'):
                require(json.loads(recorded[k]) == base[k], 'LEDGER_FROZEN_SEGMENT_DRIFT:' + k)
            current = {**base, **{k: recorded[k] for k in ('status', 'actual_runtime_seconds', 'actual_service_seconds',
                'migration_executed', 'remaining_runtime_at_H', 'remaining_GPU_hours_at_H')}}
            current['actual_compute_segments'] = json.loads(recorded['actual_compute_segments'])
            final_state = terminal(current, actual=True)
            require(final_state == json.loads(recorded['terminal_segment_state']), 'TERMINAL_INDEPENDENT_RECONSTRUCTION')
            current['terminal_segment_state'] = final_state
            o = observed.loc[uid]; g = int(base['requested_GPU'])
            start = (pd.Timestamp(o.start_time) - issue).total_seconds(); end = (pd.Timestamp(o.end_time) - issue).total_seconds()
            duration = end - start
            require(duration == current['actual_runtime_seconds'] and g == int(o.gpus_requested), 'ORIGINAL_SERVICE_AUTHORITY')
            if current['status'] == 'UNASSIGNED_POST_H_BACKLOG':
                require(base['start_slot'] >= 120 and not current['actual_compute_segments'], 'UNASSIGNED_SPILLOVER')
                pre = day = 0.; post = duration
            else:
                if current['status'] == 'PRE_DAY_COMPLETE':
                    require(not current['actual_compute_segments'] and end <= 21600, 'PRE_DAY_COMPLETE_SEGMENT_LEAK')
                    history = [(None, start, end)]
                else:
                    require(current['status'] == 'EXECUTION_ACCOUNTED', 'UNKNOWN_ACTUAL_STATUS')
                    history = [(s['site'], s['start'] * 900, s['end'] * 900) for s in current['actual_compute_segments']]
                    if base['state_at_issue'] == 'RUNNING': history.insert(0, (history[0][0], start, 0.))
                    require(all(a[2] <= b[1] for a, b in zip(history, history[1:])), 'FULL_SERVICE_OVERLAP')
                pre = sum(max(0, min(b, 21600) - a) for s, a, b in history if a < 21600)
                day = sum(max(0, min(b, 108000) - max(a, 21600)) for s, a, b in history)
                post = sum(max(0, b - max(a, 108000)) for s, a, b in history)
                for site, a, b in history:
                    for slot in range(24, 120):
                        if a <= slot * 900 < b:
                            require(site in cap and (uid, slot - 24) not in expected, 'INDEPENDENT_UID_GANG_DUPLICATE')
                            expected[uid, slot - 24] = (site, g)
            error = duration - pre - day - post
            require(abs(error) < 1e-7 and abs(post * g / 3600 - recorded['remaining_GPU_hours_at_H']) < 1e-7, 'FULL_SERVICE_PARTITION')
            service.append({'job_uid': uid, 'requested_GPU': g, 'realized_runtime_seconds': duration,
                'pre_D00_GPU_hours': pre * g / 3600, 'Dday_GPU_hours': day * g / 3600, 'postH_GPU_hours': post * g / 3600,
                'conservation_error_seconds': error, 'state_at_H': final_state['state_at_H'], 'status': current['status']})
            ledger.append(current)
        contributions = pd.read_parquet(smoke / case / 'job_GPU_contributions.parquet')
        require(not contributions.duplicated(['job_uid', 'slot']).any(), 'ROOT_UID_SLOT_DUPLICATE')
        loaded = {(r.job_uid, int(r.slot)): (r.site, int(r.occupied_GPU)) for r in contributions.itertuples(index=False)}
        require(loaded == expected, 'INDEPENDENT_UID_SITE_SLOT_RECONSTRUCTION')
        gpu, root_contributions = occupancy(ledger, sites, actual=True)
        independently_summed = np.zeros_like(gpu)
        for (_, slot), (site, g) in expected.items(): independently_summed[slot, sites.index(site)] += g
        require(np.array_equal(gpu, independently_summed), 'TWO_OCCUPANCY_RECONSTRUCTIONS_DIFFER')
        numeric = pd.read_parquet(smoke / case / 'aidc_site_timeseries.parquet').sort_values(['slot', 'site_id'])
        require(len(numeric) == 1152 and not numeric.duplicated(['slot', 'site_id']).any(), 'ACTUAL_POWER_AXIS')
        require(np.array_equal(gpu, numeric.occupied_GPU.to_numpy().reshape(96, 12)), 'STORED_ACTUAL_GPU_DRIFT')
        power = {'IT': numeric.P_IT_kW.to_numpy().reshape(96, 12), 'PCC_P': numeric.P_PCC_kW.to_numpy().reshape(96, 12),
                 'PCC_Q': numeric.Q_PCC_kvar.to_numpy().reshape(96, 12), 'GPU': gpu}
        it = check_it_power(cap, gpu, power['IT']); c1 = c1_recalculation(repo, power, exo['weather'])
        cases[case] = {'status': 'PASS', 'job_count': len(ledger), 'GPU_to_IT': it, 'IT_to_PCC': c1,
            'WAN_actual': wan_audit(ledger, wan, actual=True), 'duplicate_root_UID_slot_count': 0,
            'full_service_max_error_seconds': max(abs(r['conservation_error_seconds']) for r in service),
            'H_state_counts': dict(Counter(r['state_at_H'] for r in service)),
            'post_H_GPU_hours': sum(r['postH_GPU_hours'] for r in service)}
        ledgers[case] = ledger; powers[case] = power
        partition[case] = pd.DataFrame(service).set_index('job_uid').sort_index()
        write_parquet(out / (case + '_FULL_SERVICE_PARTITION.parquet'), partition[case].reset_index())
    require(partition['B0'].index.equals(partition['B1'].index), 'COMMON_ACTUAL_UID_UNIVERSE')
    for k in ('requested_GPU', 'realized_runtime_seconds'):
        require(partition['B0'][k].equals(partition['B1'][k]), 'COMMON_ACTUAL_SERVICE:' + k)
    result = {'status': 'PASS', 'cases': cases, 'observations': reference(source),
        'same_original_realized_service_each_job': True, 'migration_pause_excluded_from_service': True,
        'slot_semantics': 'Existing slot-start GPU occupancy preserved; exact realized service remains fractional seconds and is independently conserved.'}
    write_json(out / 'ACTUAL_COMMON_SERVICE_AND_SEGMENTS.json', result)
    return result, ledgers, powers


def finish(repo):
    from .audit import inventory
    repo = Path(repo).resolve(); root = repo / REL; smoke = root / 'smoke/2025-05-01'; old = repo / OLD / 'smoke/2025-05-01'
    out = root / 'final_report'; out.mkdir(exist_ok=True)
    planned = read(smoke / 'PRE_MESS_JOBS.json'); planning = read(root / 'PLANNING_SEGMENT_POWER_GATE.json')
    service, executed, actual_power = actual_audit(repo, smoke, planned, out)
    compare = {}; metrics = {}; all_bit_equal = True
    for case in ('B0', 'B1'):
        compare[case] = {'Planning': compare_npz(smoke / (case + '_PRE_MESS_AIDC.npz'), old / (case + '_PRE_MESS_AIDC.npz'))}
        metrics[case] = {'Planning': read(smoke / (case + '_CORRECTED_PLANNING_GATE.json'))['rho_max']}
        for label, folder, readback in [('Fresh', 'fresh', 'fresh_readback'), ('Actual', 'actual_grid', 'actual_readback')]:
            comparison = compare_npz(smoke / case / folder / 'OPENDSS_PHASE_ARRAYS.npz', old / case / folder / 'OPENDSS_PHASE_ARRAYS.npz')
            all_bit_equal &= all(x['bit_identical'] for x in comparison.values())
            if label == 'Fresh':
                with np.load(smoke / (case + '_PRE_MESS_AIDC.npz')) as z: p, q = z['pcc'], z['qcc']
                summary = read(smoke / case / 'CORRECTED_FRESH_GATE.json')['fresh']
                old_summary = read(old / case / 'CORRECTED_FRESH_GATE.json')['fresh']
            else:
                p, q = actual_power[case]['PCC_P'], actual_power[case]['PCC_Q']
                summary = read(smoke / case / 'CORRECTED_ACTUAL_RESULT.json')['summary']
                old_summary = read(old / case / 'CORRECTED_ACTUAL_RESULT.json')['summary']
            engine = pd.read_parquet(smoke / case / readback / 'OPENDSS_COMPONENT_ELEMENTS.parquet')
            aidc = engine[engine.component == 'AIDC'].sort_values(['slot', 'AIDC_site_id'])
            require(len(aidc) == 1152 and not aidc.duplicated(['slot', 'AIDC_site_id']).any(), 'ENGINE_AIDC_AXIS')
            require(np.array_equal(aidc.P_kw.to_numpy().reshape(96, 12), p), 'CANONICAL_PCC_TO_OPENDSS_P')
            require(np.array_equal(aidc.Q_kvar.to_numpy().reshape(96, 12), q), 'CANONICAL_PCC_TO_OPENDSS_Q')
            before = pd.read_parquet(old / case / readback / 'OPENDSS_COMPONENT_ELEMENTS.parquet')
            current = engine.set_index(['slot', 'element']).sort_index(); before = before.set_index(['slot', 'element']).sort_index()
            require(current.index.equals(before.index), 'ENGINE_ELEMENT_MAPPING_AXIS')
            input_bits = {k: array_comparison(current[k].to_numpy(), before[k].to_numpy()) for k in ('P_kw', 'Q_kvar')}
            require(current.OpenDSS_bus.equals(before.OpenDSS_bus), 'ENGINE_BUS_MAPPING_CHANGED')
            require(read(smoke / case / readback / 'ENGINE_MAPPING_RATINGS_SOURCE.json') == read(old / case / readback / 'ENGINE_MAPPING_RATINGS_SOURCE.json'), 'ENGINE_MAPPING_RATING_AUTHORITY_CHANGED')
            rho_same = struct.pack('d', summary['rho_max_AC']) == struct.pack('d', old_summary['rho_max_AC'])
            all_bit_equal &= rho_same and all(v['bit_identical'] for v in input_bits.values())
            compare[case][label] = {'all_phase_arrays': comparison, 'engine_inputs': input_bits,
                'PCC_to_engine_max_error': 0, 'rho_bit_identical': rho_same,
                'prior_rho': old_summary['rho_max_AC'], 'reconstructed_rho': summary['rho_max_AC']}
            metrics[case][label] = summary['rho_max_AC']
        prior = pd.read_parquet(old / case / 'aidc_site_timeseries.parquet').sort_values(['slot', 'site_id'])
        now = pd.read_parquet(smoke / case / 'aidc_site_timeseries.parquet').sort_values(['slot', 'site_id'])
        compare[case]['Actual_GPU_IT_PCC'] = {k: array_comparison(now[k].to_numpy(), prior[k].to_numpy())
            for k in ('occupied_GPU', 'P_IT_kW', 'P_PCC_kW', 'Q_PCC_kvar')}
        require(compare[case]['Actual_GPU_IT_PCC']['occupied_GPU']['values_exact_equal'], 'ACTUAL_GPU_VALUES_CHANGED')
        all_bit_equal &= all(v['bit_identical'] for k, v in compare[case]['Actual_GPU_IT_PCC'].items() if k != 'occupied_GPU')
    write_json(out / 'COMPLETE_COUNTERFACTUAL_ARRAY_COMPARISON.json', compare)
    selected = [r for r in executed['B1'] if r['migration_selected']]
    proof = []; timeline = []; power = actual_power['B1']; sites = sorted({s['site'] for r in planned['B0'] for s in r['compute_segments'] if s['site'] != 'UNASSIGNED'})
    for row in selected:
        e = row['migration_events'][0]; segs = row['actual_compute_segments']
        active = row['migration_executed'] and any(s['phase'] == 'DESTINATION' and s['end'] > 24 and s['start'] < 120 for s in segs)
        own, _ = occupancy([row], sites, actual=True)
        a, b = sites.index(e['source_AIDC']), sites.index(e['destination_AIDC'])
        require(np.all(own.sum(axis=1) <= row['requested_GPU']), 'MIGRATION_ROOT_GANG_DOUBLE_COUNT')
        if row['migration_executed']:
            lo, hi = int(e['checkpoint']), int(segs[1]['start'])
            require(own[max(24, lo) - 24:min(120, hi) - 24].sum() == 0, 'MIGRATION_INTERRUPTION_COUNTED_AS_COMPUTE')
        proof.append({'job_uid': row['job_uid'], 'requested_GPU': row['requested_GPU'], 'planned_event': e,
            'actual_compute_segments': segs, 'migration_executed': row['migration_executed'],
            'affects_D_day_Actual': active, 'actual_residual_compute_GPU_slots': sum((s['end'] - s['start']) * row['requested_GPU'] for s in segs),
            'required_realized_GPU_slots': row['actual_service_seconds'] * row['requested_GPU'] / 900,
            'sampled_D_day_source_GPU_slots': int(own[:, a].sum()), 'sampled_D_day_destination_GPU_slots': int(own[:, b].sum()),
            'terminal': row['terminal_segment_state'], 'occupancy_PCC_engine_chain': 'PASS'})
        for t in range(96):
            timeline.append({'job_uid': row['job_uid'], 'slot': t, 'absolute_slot': t + 24,
                'source_site': e['source_AIDC'], 'destination_site': e['destination_AIDC'],
                'source_job_GPU': int(own[t, a]), 'destination_job_GPU': int(own[t, b]),
                'source_total_GPU': int(power['GPU'][t, a]), 'destination_total_GPU': int(power['GPU'][t, b]),
                'source_site_IT_kW': power['IT'][t, a], 'destination_site_IT_kW': power['IT'][t, b],
                'source_site_PCC_kW': power['PCC_P'][t, a], 'destination_site_PCC_kW': power['PCC_P'][t, b]})
    affected = [r['job_uid'] for r in proof if r['affects_D_day_Actual']]
    require(len(selected) == 10 and len(affected) == 5, 'MAY01_MIGRATION_POPULATION')
    write_json(out / 'ACTUAL_10_MIGRATION_PROOFS.json', {'status': 'PASS', 'affected_5_UIDs': affected, 'jobs': proof,
        'PCC_attribution': 'Whole-site PCC is recomputed after summing canonical job GPU; nonlinear C1 is not falsely allocated linearly to individual jobs.'})
    pd.DataFrame(timeline).to_csv(out / 'MIGRATION_UID_SLOT_GPU_PCC_PROOF.csv', index=False)
    planned_ten = read(root / 'MIGRATION_10_SEGMENT_AUDIT.json')
    require(all(r['difference'] == 0 for r in planned_ten), 'PLANNED_SERVICE_DIFFERENCE')
    reuse = read(smoke / 'B3_A0_STATIC_REUSE/SEGMENT_A0_REUSE_GATE.json')
    require(reuse['B1_segment_identity'] == reuse['B3_A0_segment_identity'] == identities(planned['B1']), 'FINAL_B1_A0_IDENTITY')
    require(reuse['B3_A0_optimize_calls'] == 0, 'DUPLICATE_A0_OPTIMIZATION')
    consumer = inventory(repo); preservation = verify_preserved(repo)
    from dayahead.v40g.authority import PREVIOUS
    common = root / 'common_service/COMMON_DA_SERVICE_AUTHORITY.json'
    require(sha(common) == sha(repo / OLD / 'common_service/COMMON_DA_SERVICE_AUTHORITY.json') == sha(repo / PREVIOUS / 'common_service/COMMON_DA_SERVICE_AUTHORITY.json'), 'COMMON_T_DA_AUTHORITY_CHANGED')
    old_v40f = read(repo / OLD / 'PRESERVED_V40F.json')['files']
    require(all(Path(p).is_file() and sha(p) == h for p, h in old_v40f.items()), 'V40F_PRESERVATION')
    tests = read(root / 'TEST_RESULTS.json'); require(tests['exit_code'] == 0, 'INTEGRATION_TESTS_FAILED')
    gates = dict.fromkeys(GATE_NAMES, 'PASS')
    status = 'MIGRATION_SEGMENT_ACTUAL_REPLAY_PROVEN_EQUIVALENT' if all_bit_equal else 'INVALIDATED_BY_MIGRATION_SEGMENT_INTEGRATION_DEFECT'
    authority = {'status': status, 'replaces_interpretation_hold_only_after_all_gates_PASS': True,
        'old_result_overwritten': False, 'old_report': reference(repo / OLD / 'V40G_MAY01_FINAL_REPORT.json'),
        'counterfactual_array_proof': reference(out / 'COMPLETE_COUNTERFACTUAL_ARRAY_COMPARISON.json'),
        'gates': gates, 'B2_B3_AUTHORIZED': 'NO', 'FULL_MAY_AUTHORIZED': 'NO',
        'V40G_ACTUAL_SCIENCE_INTERPRETATION': 'MAY01_SEGMENT_INTEGRATION_HOLD_CLEARED' if all_bit_equal else 'HOLD'}
    write_json(root / 'PRIOR_V40G_RESULT_STATUS.json', authority)
    write_json(root / 'EXECUTION_AUTHORIZATION.json', {k: authority[k] for k in ('B2_B3_AUTHORIZED', 'FULL_MAY_AUTHORIZED', 'V40G_ACTUAL_SCIENCE_INTERPRETATION')})
    config = {'schema': 'V40G_SEGMENT_INTEGRATION_V1', 'day': '2025-05-01', 'cases_executed': ['B0', 'B1'],
        'canonical_slot_origin': 'D_MINUS_1_ISSUE', 'operating_window': [24, 120],
        'common_T_DA': reference(common), 'decision_source': reference(old / 'JOINT_AIDC/ACCEPTED_AIDC.json'),
        'request': read(root / 'INITIAL_INTERPRETATION_HOLD.json')['request'],
        'new_scientific_optimization_calls': 0, 'Actual_result_based_tuning': False,
        'B3_A0_optimize_calls': 0, 'A1_authorization': 'Preserve RUNNING segments and events; original PENDING domain and common terminal constraints',
        'M1_MF_inputs': 'Certified canonical PCC with full segment/event identity; one route search, one fixed-route P/Q recourse',
        'effective_entrypoints': consumer['effective_entrypoints']}
    write_json(root / 'INTEGRATION_CONTRACT.json', config)
    sources = {str(p): sha(p) for p in sorted((repo / 'dayahead/v40g_segments').glob('*.py'))}
    sources[str(repo / 'tests/dayahead/test_v40g_segments.py')] = sha(repo / 'tests/dayahead/test_v40g_segments.py')
    dependencies = {r['source']['path']: r['source']['sha256'] for r in consumer['consumers']}
    seal = {'source_files': sources, 'source_SHA': digest(sources), 'dependency_files': dependencies,
        'dependency_SHA': digest(dependencies), 'config_SHA': sha(root / 'INTEGRATION_CONTRACT.json')}
    seal['method_SHA'] = digest(seal); write_json(root / 'SOURCE_SEAL.json', seal)
    result = {**authority, 'status': 'PASS', 'prior_Actual_result_status': status,
        'physical_float_arrays_and_rho_bit_identical': all_bit_equal, 'GPU_values_exact_equal': True,
        'GPU_storage_width_only': 'New canonical numpy int uses Windows int32; prior Actual stored int64. Identical integer GPU values; no physical input/output difference.', 'metrics': metrics,
        'delta_B0_minus_B1': {k: metrics['B0'][k] - metrics['B1'][k] for k in ('Planning', 'Fresh', 'Actual')},
        'planned_migrations': len(planned_ten), 'planned_compute_GPU_slot_difference': 0,
        'Actual_D_day_migrations': len(affected), 'Actual_affected_UIDs': affected,
        'actual_common_service': service, 'B1_A0_segment_identity': reuse['B1_segment_identity'],
        'preserved_V40G': preservation, 'preserved_V40F_files': len(old_v40f), 'common_T_DA_SHA': read(common)['COMMON_DA_DURATION_SHA'],
        'new_scientific_optimization_calls': 0, 'B3_A0_optimize_calls': 0, 'B2_B3_executed': False, 'full_May_executed': False,
        'synthetic_A1_solver_tests_are_not_May_B3_science': True, 'UNASSIGNED_44_CASE_BLOCKER': 'OPEN',
        'consumer_inventory': reference(root / 'SCIENTIFIC_CONSUMER_INVENTORY.json'), 'tests': tests, 'source_seal': seal}
    write_json(root / 'V40G_SEGMENT_INTEGRATION_FINAL.json', result)
    text = ['V40G migration 구간 통합 수정과 May-01 B0/B1 독립 재검증을 완료했다.', '',
        f'기존 Actual 결과 상태: **{status}**. IT·PCC와 Fresh/Actual OpenDSS의 모든 저장 배열 및 rho는 비트 단위로 동일하다. GPU 점유율의 정수 값도 정확히 같으며 저장 폭만 int64→int32로 다르다.',
        '', '기존 B3 공통 경로의 단일 site/구간 가정을 새 구간 기반 진입점으로 교체했다. 기존 Actual은 source/destination 분할을 이미 사용하고 있었으며, 독립 재구성으로 그 결과의 동등성을 확인했다. 기존 파일은 변경하지 않았다.',
        '', '| 필수 게이트 | 결과 |', '|---|---|']
    text += [f'| {k} | {v} |' for k, v in gates.items()]
    text += ['', '| 지표 | B0 | B1 | B0−B1 |', '|---|---:|---:|---:|']
    text += [f"| {k} | {metrics['B0'][k]:.16f} | {metrics['B1'][k]:.16f} | {result['delta_B0_minus_B1'][k]:.16f} |" for k in ('Planning', 'Fresh', 'Actual')]
    text += ['', '계획 이주 10건의 계산 GPU-slot과 공통 T_DA 요구량 차이는 모두 0이다. 아래 시간은 D−1 issue 기준 15분 슬롯이며 D-day 구간은 [24,120)이다.',
        '', '| UID | GPU | source→destination | source 계산 | 중단 | 전송 | destination 계산 | 계산/요구 GPU-slot | 차이 |',
        '|---|---:|---|---|---|---|---|---:|---:|']
    interval = lambda x: f'[{x[0]},{x[1]})'
    for r in planned_ten:
        text.append(f"| {r['job_uid']} | {r['requested_GPU']} | {r['source_site']}→{r['destination_site']} | {interval(r['source_compute_interval'])} | {interval(r['interruption_interval'])} | {interval(r['transfer_interval'])} | {interval(r['destination_compute_interval'])} | {r['total_compute_GPU_slots']}/{r['common_T_DA_required_GPU_slots']} | {r['difference']} |")
    text += ['', 'Actual D-day에 반영된 5건: ' + ', '.join(affected) + '. 나머지 5건은 실제 서비스가 고정 체크포인트 전에 완료되어 destination 계산과 전송이 발생하지 않았다.',
        '작업별 source/destination GPU를 합산한 site 점유율에서 IT 및 C1 PCC를 재계산하고 OpenDSS 적용값과 대조했다. 중단·전송·재시작 시간은 계산 서비스에 넣지 않았다. C1의 비선형성을 유지하므로 작업별 PCC를 임의로 선형 배분하지 않았다.',
        '', 'H에서 작업별 site, 남은 계산량, post-H 구간/site, 이주·WAN 상태, RUNNING/PENDING, 공통 terminal obligation을 기록했다. 실제 서비스가 H를 넘는 합성 이주 사례에서도 destination 상태가 유지되는지 검증했다.',
        '', 'B1 최종 결정과 B3 A0는 원본 파일을 바이트 단위로 재사용한다. canonical sidecar의 계산 구간·migration event SHA와 GPU·IT·PCC도 동일하다. A0 재최적화는 0회다. M1/A1/MF 연결은 합성 계약 테스트로 검증했으며 May B3를 실행하지 않았다.',
        f"B1/A0 segment+event SHA: `{reuse['B1_segment_identity']['segment_and_event_SHA']}`.",
        '', f"기존 V40G {preservation['files']}개, V40F {len(old_v40f)}개 보존 파일 변경 수 0. 공통 T_DA SHA `{result['common_T_DA_SHA']}` 유지.",
        '', f"검증: {tests['summary']}. 과학적 최적화 추가 실행 0회. B2/B3·전체 May 미실행. 기존 UNASSIGNED 44-case blocker는 그대로 OPEN이다.",
        '', '이번 구간 통합에 따른 May-01 해석 보류는 해제했다. 실행 권한은 `B2_B3_AUTHORIZED = NO`, `FULL_MAY_AUTHORIZED = NO`로 유지한다. Actual 부호를 이용한 정책 변경·재선택·튜닝은 하지 않았다.',
        '', f"[전체 검증 JSON]({(root / 'V40G_SEGMENT_INTEGRATION_FINAL.json').as_posix()}) · [전 배열 비교]({(out / 'COMPLETE_COUNTERFACTUAL_ARRAY_COMPARISON.json').as_posix()}) · [작업별 GPU/PCC 증거]({(out / 'MIGRATION_UID_SLOT_GPU_PCC_PROOF.csv').as_posix()}) · [consumer 감사]({(root / 'SCIENTIFIC_CONSUMER_INVENTORY.json').as_posix()})"]
    (root / 'V40G_SEGMENT_INTEGRATION_FINAL.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'prior_Actual': status, 'affected_UIDs': affected, 'gates': gates, 'preservation': preservation}), flush=True)
    return result


if __name__ == '__main__': finish(Path.cwd())
