"""One supervised 20+20-second original 4x24 SAME-pool comparison."""
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import argparse
import csv
import json
import sys
import threading

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_v42_original_beam_joint import load_packet, load_compressed_packet
from v42_integration.followup_resource import FollowupComparisonBudget
from v42_integration.m_engine import _native_joint, _BudgetAdapter, _write, file_record, vector_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT/'runtime/FOLLOWUP_ORIGINAL_BEAM_JOINT')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP')
    args = parser.parse_args()
    out = args.output.resolve(); runtime = args.runtime.resolve()
    target = runtime/'NATIVE_PAIR_20S'
    target.mkdir(parents=True, exist_ok=False)
    certificate = out/'JOINT_GRID_COMPRESSION_CERTIFICATE.json'
    c = json.loads(certificate.read_text(encoding='utf8'))
    source_full = json.loads((out/'ORIGINAL_BEAM_FULL_RAW_REPLAY.json').read_text(encoding='utf8'))
    if (source_full['status'] != 'PASS' or source_full['graph_counts'] !=
            dict(MESS_count=4, candidate_nodes=24, slots=96) or not source_full['center_raw_sha_matches']):
        raise ValueError('FOLLOWUP_ORIGINAL_FULL_PHYSICAL_START_REPLAY_REQUIRED')
    loaded = perf_counter()
    original, spec = load_packet(runtime/'ORIGINAL')
    original_load = perf_counter()-loaded
    loaded = perf_counter(); compressed = load_compressed_packet(runtime)
    compressed_load = perf_counter()-loaded
    packets = dict(ORIGINAL=original, COMPRESSED=compressed)
    identity = {k:c['identity'][k] for k in ('source_sha','case_sha','physical_sha','pool_sha')}
    identity.update(MESS_count=4, nodes=24, slots=96)
    budget = FollowupComparisonBudget(certificate_path=certificate,
        expected_certificate_sha=file_record(certificate)['sha256'], identity=identity,
        expected_packets=packets)
    _write(target/'RESOURCE_ADMISSION.json', budget.preflight())
    used_before = budget.used()
    stop = threading.Event(); peak = dict(RSS_bytes=0, private_commit_bytes=0)
    def observe_memory():
        process = psutil.Process()
        while not stop.wait(.1):
            m = process.memory_info()
            peak['RSS_bytes'] = max(peak['RSS_bytes'], m.rss)
            peak['private_commit_bytes'] = max(peak['private_commit_bytes'], getattr(m,'private',0))
    watcher = threading.Thread(target=observe_memory, daemon=True); watcher.start()
    results = {}; captures = {}; rows = []
    try:
        for label, packet in packets.items():
            budget.stage_context = dict(comparison_variant=label, original_case_sha=spec['case_sha'],
                original_source_git=spec['source_sha'], identity=identity,
                planning_stage='M1', execution_scope='PR221_HISTORICAL_EXACT_NUMERIC_SAME_POOL',
                same_pool=True, Actual_global_MILP_calls=0, maximum_native_seconds=20.)
            started = perf_counter()
            result, points = _native_joint(SimpleNamespace(), _BudgetAdapter(budget, 20.),
                packet, target/label, 20.)
            wall = perf_counter()-started
            results[label] = dict(result, native_build_readback_solve_capture_wall_seconds=wall,
                packet_load_wall_seconds=original_load if label=='ORIGINAL' else compressed_load)
            captures[label] = points
            a,d,_,_,_ = packet
            rows.append(dict(variant=label, status='DIAGNOSTIC_ONLY', variables=a.shape[1],
                binary=int(np.count_nonzero(d['types']=='B')), rows=a.shape[0], NNZ=a.nnz,
                Native_Runtime=result.get('Native_Runtime'), restricted_ObjBound=result.get('restricted_ObjBound_diagnostic'),
                current_pool_ObjVal=result.get('current_pool_ObjVal'),
                native_total_wall_seconds=wall,
                compression_proof_cache_wall_seconds=0. if label=='ORIGINAL' else c['compression_total_wall_seconds'],
                bound_scope='SAME_RESTRICTED_BEAM_POOL_NOT_GLOBAL'))
    finally:
        stop.set(); watcher.join(timeout=1.)
        _write(target/'NATIVE_PAIR_RECEIPT.json', dict(status='DIAGNOSTIC_ONLY', results=results,
            canonical_ledger_path=str(budget.path), historical_native_seconds_before=used_before,
            cumulative_native_seconds_after=budget.used(), usage_reset=False, peak=peak))
    # Each capture remains literal: FULL row + route/SOC/PCS/Mode validation,
    # with no rounding, clipping, repair or transfer to the new AIDC Case.
    from v42_integration.pr222_regression import load_case
    from v42_integration.m_engine import strict_full
    source_case = load_case('2025-05-01', target/'FULL_VALIDATION')
    validation = {}
    for label, points in captures.items():
        seen = set(); validations = []
        for ordinal, point in enumerate(points):
            sig = vector_sha(point['point'])
            if sig in seen: continue
            seen.add(sig)
            path = target/label/f'CAPTURE_{ordinal:03d}.npz'
            np.savez_compressed(path, point=point['point'])
            try:
                cert = strict_full(source_case, path)
                validations.append(dict(status='PASS', certificate=cert))
            except Exception as error:
                validations.append(dict(status='FAIL', reason=repr(error), Raw=file_record(path)))
        validation[label] = validations
    summary = dict(status='DIAGNOSTIC_ONLY', identity=identity, original_source_git=spec['source_sha'],
        same_Source_Case_pool_Start_parameters=True, same_restricted_bound_scope=True,
        original_columns_objective_domains_unchanged=True,
        results=results, original_FULL_capture_validation=validation, peak=peak,
        baseline_original_FULL_UB=source_full['original_center_objective'],
        new_AIDC_Case_numbers_transferred=False, incumbent_registry_mutations=0,
        restricted_ObjBound_is_Global_LB=False, total_beam_iteration_speedup='NOT_CERTIFIED',
        native_time_limit_comparison='20_SECONDS_EACH_ONE_WORKER_ONE_THREAD',
        ledger=file_record(budget.path), native_seconds_before=used_before,
        native_seconds_after=budget.used(), native_remaining_seconds=budget.remaining(),
        raw_runtime_evidence=file_record(target/'NATIVE_PAIR_RECEIPT.json'))
    _write(out/'MESS_4X24_NATIVE_COMPARISON.json', summary)
    with (out/'MESS_4X24_COMPRESSION_COMPARISON.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    _write(out/'MESS_NATIVE_PEAK_MEMORY.json', peak)
    print(json.dumps(dict(status=summary['status'], variants=rows,
        remaining_seconds=budget.remaining(), native_seconds_after=budget.used()), indent=2), flush=True)


if __name__ == '__main__':
    main()
