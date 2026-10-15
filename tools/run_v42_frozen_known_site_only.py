"""Current D-day Known baseline and Unknown site selection; no native solve."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v42_integration.unified_contract import REPORT, load_contracts, file_sha
from v42_integration.m_engine import _write, file_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--slots', type=int, default=8)
    parser.add_argument('--fresh-ac', action='store_true')
    parser.add_argument('--wall-seconds', type=float, default=600.)
    args = parser.parse_args()
    if not 1 <= args.slots <= 16:
        raise ValueError('MAY01_SITE_ONLY_SHORT_PREFIX_AT_MOST_16_SLOTS')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Fail before any accidental native optimization, presolve, or IIS.
    import gurobipy as gp
    native_attempts = []
    def forbidden(*a, **kw):
        native_attempts.append('FORBIDDEN_NATIVE_CALL')
        raise RuntimeError('SITE_ONLY_ACTUAL_GLOBAL_NATIVE_FORBIDDEN')
    gp.Model.optimize = forbidden
    gp.Model.presolve = forbidden
    gp.Model.computeIIS = forbidden
    from v42_integration.unified_resource import UnifiedResearchBudget
    budget = UnifiedResearchBudget()
    _write(out/'RESOURCE_ADMISSION.json', budget.preflight())
    common = load_contracts()
    names = ('v42_integration/aidc_sensitivity_runtime.py',
             'v42_integration/actual.py', 'v42_integration/actual_validation.py',
             'v42_integration/production_case.py', 'v42_integration/sensitivity_policy.py',
             'v42_integration/reservation_state.py', 'tools/run_v42_frozen_known_site_only.py')
    root = REPORT.parents[1]
    freeze = {name: file_sha(root/name) for name in names}
    _write(out/'EXECUTION_FREEZE.json', dict(study_bindings=common['bindings'], source_files=freeze,
        day='2025-05-01', arm='B1', MESS='OFF', SVR=11, slots=args.slots,
        Known_rule='CURRENT_OBSERVED_DDAY_DETERMINISTIC_SOURCE_FCFS_DIAGNOSTIC',
        historical_A1_execution_authority=False, new_Known_Native_calls=0,
        time_shifting=False, runtime_repair=False, migration=False, Actual_global_MILP_calls=0))
    began = perf_counter()
    stop = threading.Event()
    def watchdog():
        import os
        import psutil
        while not stop.wait(1.):
            available = psutil.virtual_memory().available
            if available < 4*1024**3 or perf_counter()-began > args.wall_seconds:
                _write(out/'SUPERVISOR_STOP.json', dict(wall_seconds=perf_counter()-began,
                    available_RAM_bytes=available, reason='RAM_OR_OWN_PREFIX_WALL_LIMIT',
                    Native_calls=0, results_certified=False, auto_retry=False))
                os._exit(75)
    watcher = threading.Thread(target=watchdog, daemon=True)
    watcher.start()
    try:
        from v42_integration.aidc_sensitivity_runtime import run_dday_known_site_only_canary
        with budget.exclusive_worker():
            result = run_dday_known_site_only_canary(out/'ACTUAL', slots=args.slots,
                                                    shared_manifest=common)
        receipt = result['receipt']
        receipt.update(output_path=str(out), total_wall_seconds=perf_counter()-began,
                       forbidden_Native_attempts=len(native_attempts))
        fresh = {}
        if args.fresh_ac:
            import numpy as np
            from v42_integration.actual_validation import fresh_ac_minimum
            from v42_integration.partial_canary import SOURCE_DIR
            archive = Path('D:/v42_may_joint_repair_campaign_20261013')
            source = json.loads((SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf8'))
            for label, actual in result['results'].items():
                trace = out/(label+'_ACTUAL_PQ.npz')
                begin = receipt['same_input']['begin_seconds']
                np.savez_compressed(trace, PCC_P_kw=np.asarray(actual['physical']['PCC_P_kw']),
                    PCC_Q_kvar=np.asarray(actual['physical']['PCC_Q_kvar']), sites=np.asarray(actual['sites']),
                    timestamps_start_epoch_seconds=begin+np.arange(args.slots)*900)
                scope = dict(partial_actual_trace_authorized=True,
                    planning_case_sha=receipt['execution_bindings']['case_sha'],
                    common_initial_state_sha=receipt['execution_bindings']['initial_state_sha'],
                    label='DDAY_KNOWN_BASELINE_'+label+'_SITE_ONLY_DIAGNOSTIC',
                    historical_A1_certificate_transferred=False, study_bindings=common['bindings'],
                    source_canary=file_record(out/'ACTUAL/SITE_ONLY_CANARY_RECEIPT.json'))
                ac_began = perf_counter()
                try:
                    with budget.exclusive_worker():
                        physical = fresh_ac_minimum(archive/'raw/2025-05-01', out/'ACTUAL', out/(label+'_FRESH'),
                            source_freeze=source, campaign_manifest=archive/'CAMPAIGN_MANIFEST.json',
                            slots=args.slots, trace_path=trace, arm='B1', case_scope=scope)
                except BaseException:
                    budget.record_external('SITE_ONLY_FRESH:'+label, perf_counter()-ac_began,
                                           solver='AC', status='FAILED')
                    raise
                budget.record_external('SITE_ONLY_FRESH:'+label, physical['AC_wall_seconds'], solver='AC')
                fresh[label] = dict(PASS=physical['PASS'], status=physical['status'],
                    result=file_record(out/(label+'_FRESH')/'FRESH_PHYSICAL_RESULT.json'))
            receipt.update(Fresh_AC=fresh, all_variant_Fresh_AC_PASS=all(x['PASS'] for x in fresh.values()))
        if load_contracts()['bindings'] != common['bindings'] or any(file_sha(root/n) != sha for n, sha in freeze.items()):
            raise ValueError('SITE_ONLY_EXECUTED_SOURCE_OR_STUDY_DRIFT')
        receipt['total_wall_seconds'] = perf_counter()-began
        _write(out/'AIDC_SITE_ONLY_VALIDATION_RESULT.json', receipt)
        _write(REPORT/'AIDC_SITE_ONLY_VALIDATION_RESULT.json', receipt)
        print(json.dumps({k: receipt.get(k) for k in ('status', 'same_actual_Known_execution',
            'changed_executed_site_UIDs', 'changed_actual_prefix_compute_GPUh', 'comparison', 'Fresh_AC')}, indent=2))
    except BaseException as exc:
        _write(out/'EXECUTION_FAILURE.json', dict(error=repr(exc), wall_seconds=perf_counter()-began,
            forbidden_Native_attempts=len(native_attempts), Native_calls=0, auto_retry=False))
        raise
    finally:
        stop.set()


if __name__ == '__main__':
    main()
