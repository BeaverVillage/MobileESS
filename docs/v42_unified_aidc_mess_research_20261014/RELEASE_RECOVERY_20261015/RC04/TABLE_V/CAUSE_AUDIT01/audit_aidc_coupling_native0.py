"""Read-only arithmetic relaxation of failed B1's public Known/CC4 domain.

No imported production modules, Gurobi, private trace, or model operations.
This cannot certify FULL feasibility or identify an IIS.
"""
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
EXEC = BASE.parent / 'EXECUTION01'
POLICY = EXEC / 'INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json'
FORECAST = EXEC / 'INPUTS/BASIC/D0_CC4_FORECAST_RECEIPT.json'
TIMING = Path('D:/MobileESS_V42/docs/v42_ts_cc4_temporal_refinement/CC4_SERVICE_TIMING_ENVELOPE.csv')
RESULT = EXEC / 'B1/A1/P1_ONLY_RESULT.json'
REFERENCE = EXEC / 'REFERENCE_RESULT.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def record(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


def write_new(path, content):
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(content)


def main():
    began = time.perf_counter()
    inputs = [POLICY, FORECAST, TIMING, RESULT, REFERENCE]
    before = [record(p) for p in inputs]
    policy, forecast, result, reference = map(read, (POLICY, FORECAST, RESULT, REFERENCE))
    rows = list(csv.DictReader(TIMING.open(encoding='utf-8-sig', newline='')))
    lower = np.array([float(r['Q10']) for r in rows])
    upper = np.array([float(r['Q90']) for r in rows])
    assert np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))
    assert np.all((0 <= lower) & (lower <= upper) & (upper <= 1))
    assert np.all(np.diff(lower) >= 0) and np.all(np.diff(upper) >= 0)
    begin = float(forecast['day_begin_seconds'])
    windows = [(a, b) for a in range(96) for b in range(a+1, 97)]
    left = np.array([r[0] for r in windows], dtype=int)
    right = np.array([r[1] for r in windows], dtype=int)
    known = {name: np.zeros(len(windows)) for name in ('failed_compiler', 'original_receipt')}
    counts = dict(positive_remaining_UIDs=len(policy['domain_mask']), source_window_UIDs=0,
                  removed_start_count=0, E1_participant_UIDs=0, checkpoint_UIDs=0)
    for row in policy['domain_mask']:
        uid = row['uid']; receipt = policy['known_issued_receipts'][uid]
        gpu = float(row['source_hard_contract']['gpu'])
        duration = int(row['full_service_slots'])
        compiled = np.array(row['allowed_native_starts'], dtype=int)-24
        restored = (np.array([24], dtype=int) if row['state']=='RUNNING' else np.array([
            24+round((float(s)-begin)/900) for s in receipt['allowed_starts_seconds']
            if begin <= float(s) < begin+86400], dtype=int))-24
        assert len(compiled) and len(restored) and duration > 0 and gpu > 0
        removed = set(restored)-set(compiled)
        counts['source_window_UIDs'] += bool(removed)
        counts['removed_start_count'] += len(removed)
        counts['E1_participant_UIDs'] += row['participant'] is True and row['eligible'] is True
        counts['checkpoint_UIDs'] += row['checkpoint_authorized'] is True
        for name, starts in (('failed_compiler', compiled), ('original_receipt', restored)):
            minima = np.full(len(windows), np.inf)
            for start in starts:
                # Any legal migration only delays remaining service. Allowing
                # its entire remaining budget to remove service arbitrarily
                # from a window is a conservative relaxation of the original
                # checkpoint/one-WAN-transfer geometry, never a new authority.
                interruption = (max(0, int(np.floor((float(row['budget_seconds'])-
                    max(0, int(start)+24-int(row['reference_native_slot']))*900)/900)))
                    if row['checkpoint_authorized'] is True else 0)
                overlap = np.maximum(0, np.minimum(right, int(start)+duration)-np.maximum(left, int(start)))
                minima = np.minimum(minima, np.maximum(0, overlap-interruption)*gpu)
            known[name] += minima
    # Q50-expired running jobs have an explicit physical current-slot hold.
    expired = reference['fixed_Q50_expired_running_holds']
    assert len(expired) == 69
    fixed = sum(float(r['gpu']) for r in expired.values())
    assert fixed == 187
    for name in known:
        known[name] += ((left == 0) & (right > 0))*fixed

    def cumulative_envelope(cohort, boundary, curve):
        lag = boundary-1-4*cohort
        return np.where(lag < 0, 0, curve[np.minimum(np.maximum(lag, 0), len(curve)-1)])

    cc4 = np.zeros(len(windows))
    for hour, work in enumerate(forecast['Q50_GPUh']):
        lo = cumulative_envelope(hour, right, lower)
        hi = cumulative_envelope(hour, left, upper)
        # Original x units are GPUh; 15-minute instantaneous GPU = 4*x.
        cc4 += 4*float(work)*np.maximum(0, lo-hi)
    capacity = (right-left)*780.
    output_rows = []
    summary = {}
    for name, demand in known.items():
        excess = demand+cc4-capacity
        worst = int(np.argmax(excess))
        summary[name] = dict(necessary_capacity_excess_windows=int(np.sum(excess > 1e-7)),
            maximum_lower_bound_minus_capacity_GPU_slots=float(excess[worst]),
            tightest_window_D0_slots=list(windows[worst]),
            tightest_window_known_min_GPU_slots=float(demand[worst]),
            tightest_window_CC4_min_GPU_slots=float(cc4[worst]),
            tightest_window_capacity_GPU_slots=float(capacity[worst]),
            interpretation='EXCESS_IS_STRUCTURAL_INFEASIBILITY_PROOF; NO_EXCESS_IS_INCONCLUSIVE')
    for index, (a, b) in enumerate(windows):
        output_rows.append(dict(begin_D0_slot=a, end_exclusive_D0_slot=b,
            interval_capacity_GPU_slots=float(capacity[index]),
            CC4_nominal_min_GPU_slots=float(cc4[index]),
            failed_compiler_Known_min_GPU_slots=float(known['failed_compiler'][index]),
            failed_compiler_excess_GPU_slots=float(known['failed_compiler'][index]+cc4[index]-capacity[index]),
            original_receipt_Known_min_GPU_slots=float(known['original_receipt'][index]),
            original_receipt_excess_GPU_slots=float(known['original_receipt'][index]+cc4[index]-capacity[index])))
    csv_path = BASE/'AIDC_CC4_WINDOW_CAPACITY_NECESSARY_BOUNDS.csv'
    with csv_path.open('x', encoding='utf-8', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(output_rows[0]));writer.writeheader();writer.writerows(output_rows)
    assert before == [record(p) for p in inputs]
    source_paths = ['v42_integration/a_engine.py','v42_integration/tablev_fullflex_actual.py',
        'v42_integration/release_production_actual.py','v42_integration/aidc_sensitivity_runtime.py',
        'v42_final/reserve.py','v42_temporal/service.py','v42_root/native.py',
        'v42_a_stage_domain_v2/domain.py','v42_native/service.py']
    # __file__ lies six directories below the repo root (docs/.../CAUSE_AUDIT01).
    repo = next(p for p in BASE.parents if (p/'v42_integration').is_dir())
    report = dict(schema='TABLE_V_AIDC_PUBLIC_COUPLING_NATIVE0_AUDIT_V1',
        scope='FAILED_B1_ATTEMPT_ONLY_READONLY_ARITHMETIC_RELAXATION',
        failed_stage_case_sha=result['case_sha'],failed_source_identity=result['source_identity'],
        failed_solver_status=result['Native_call']['status'],failed_Native_Runtime=result['Native_call']['Native_Runtime'],
        public_counts=counts, Q50_expired_current_slot_hold_UIDs=len(expired),
        Q50_expired_current_slot_hold_GPU=fixed, intervals_examined=len(windows),
        necessary_window_capacity=summary,
        findings=[
            dict(status='CONFIRMED_DOMAIN_SHRINK',claim='Pending compiler deleted receipt-authorized starts earlier than causal reference; authorized_data adds no independent reference hard-earliest.',
                 does_not_prove='This finding alone does not prove the solver infeasibility cause.'),
            dict(status='NO_ADDITIONAL_ACTUAL_WINDOW_FILTER_FOUND',claim='Known immutable commands are checked against receipt.allowed_starts_seconds; Can_TimeShift=False does not remove a receipt-authorized earlier command. Additional delay is max(0, planned-reference).'),
            dict(status='RUNTIME_ANCHOR_ALREADY_CORRECTED',claim='Original risk_nominal_completion_issue_slot is shifted by new_reference-original_reference for Pending, preserving risk anchor minus reference_end.'),
            dict(status='SOFT_RESERVE_TARGETS',claim='bind_headroom permits achieved CC4/runtime reserves zero with nonnegative unbounded shortfall. Only Known+nominal CC4+achieved reserve occupancy is hard; targets themselves do not force occupancy.'),
            dict(status='ORIGINAL_HARD_COUPLING_RETAINED',claim='Known nominal and CC4 nominal allocations drive Original C1/PCC and signed full network F2CRA; all physical bounds remain hard and cannot be relaxed from this audit.')],
        limitations=['No LP/MILP, presolve, IIS, point replay or full feasibility certificate.',
            'Necessary aggregate capacity bounds relax per-site GPU/rack, timing correlations, checkpoint/WAN geometry, and all electrical inequalities.',
            'No-excess intervals cannot establish feasibility or identify the remaining cause of INFEASIBLE.',
            'Original/frozen source files and failed result are unchanged. No private future observations read.'],
        counts_operation=dict(Gurobi_imported='gurobipy' in sys.modules, model_builds=0,optimize=0,presolve=0,IIS=0,private_future_reads=0),
        public_input_records=before,source_records=[record(repo/p) for p in source_paths],
        arithmetic_source=record(Path(__file__)),window_csv=record(csv_path),
        wall_seconds=time.perf_counter()-began)
    write_new(BASE/'AIDC_COUPLING_AUDIT.json',json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status='AUDIT_COMPLETE',counts=counts,necessary_window_capacity=summary,
        Gurobi_imported=report['counts_operation']['Gurobi_imported'],wall_seconds=report['wall_seconds'])))


if __name__ == '__main__':main()
