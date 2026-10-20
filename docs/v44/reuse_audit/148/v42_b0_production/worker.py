"""One isolated native B0 stage; explicit config and accepted-input file manifest."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from v42_orchestrator.ledger import atomic
from v42_campaign.authority import file_sha
from .authority import read, record, INPUT
from .config import B0Config


def all_planning_frozen(root, authority):
    state = read(root / 'CAMPAIGN_STATE.json')
    if state['identity']['mode'] != 'B0_PRODUCTION':
        raise PermissionError('Synthetic checkpoints cannot authorize Actual data access')
    for day in authority['days']:
        row = state['stages'][f'B0/{day}/PLANNING_FREEZE']
        if row['status'] != 'PASS':
            raise PermissionError('All 31 new Planning freezes required before Actual truth')
        path = root / row['receipt_path']
        if file_sha(path) != row['receipt_sha']:
            raise PermissionError('Planning receipt hash drift')


def guard_gurobi():
    import gurobipy as gp
    original = gp.Model
    models = []
    class B0Model(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setParam('Threads', 1)
            models.append(dict(Threads=int(self.Params.Threads)))
        def setParam(self, name, value):
            if str(name).lower() == 'threads' and value != 1:
                raise PermissionError('B0 native Threads must equal 1')
            return super().setParam(name, value)
        def optimize(self, *args, **kwargs):
            raise PermissionError('Existing fixed B0 contract has no optimizer; unexpected solve blocked')
    gp.Model = B0Model
    return models


def execute(request):
    root = Path(request['run_root']).resolve()
    authority = read(root / 'AUTHORITY.json')
    config = B0Config(**authority['config'])
    config.authorize('B0', request['stage'] if request['stage'] != 'TRUTH_PREPARATION' else None)
    if request['run_id'] != authority['run_id'] or request.get('arm') != 'B0':
        raise PermissionError('B0 run/arm identity mismatch')
    day = request.get('day')
    if day is not None and day not in authority['days']:
        raise PermissionError('Frozen May date required')
    for row in request.get('accepted_inputs', []):
        p = Path(row['path']).resolve()
        if not p.is_relative_to(root) or file_sha(p) != row['sha256']:
            raise PermissionError('Accepted production input hash/provenance failure')
    if request['stage'] in ('ACTUAL', 'FRESH_AC', 'TRUTH_PREPARATION'):
        all_planning_frozen(root, authority)
    models = guard_gurobi()
    from .c1_binding import bind_frozen_c1
    from v42_holdout.common import source_freeze
    bind_frozen_c1(source_freeze())
    output = Path(request['output']).resolve()
    if not output.is_relative_to(root):
        raise PermissionError('Native output outside this run')
    if output.exists():
        raise FileExistsError('Native attempt output already exists')
    output.mkdir(parents=True)
    stage = request['stage']
    from . import routing
    import numpy as np
    if stage in ('B0_PLANNING', 'FRESH_AC'):
        # Warm the current NormalAmps authority before the active native day session.
        from v42_thermal.authority import current_authority
        if current_authority()['transformer_current_authority_sha256'] != authority['checker_SHA']:
            raise PermissionError('Current source NormalAmps checker authority changed')
    if stage == 'B0_PLANNING':
        folder = routing.planning(day, output)
        plan = np.load(folder / 'PLANNING_PHYSICAL.npz')
        voltage = np.load(folder / 'V_PLAN.npz')['V_PLAN']
        capacity = np.all(plan['total_gpu'] <= plan['capacities'] + 1e-9)
        audit = read(folder / 'PLANNING_FREEZE.json')
        if (not capacity or not audit['no_Actual_read'] or audit['optimizer_calls'] != 0
                or audit['transformer_current_authority_sha256'] != authority['checker_SHA']):
            raise ValueError('B0_PLANNING_CAPACITY_OR_PROVENANCE_FAILURE')
        metrics = dict(voltage_min=float(voltage.min()), voltage_max=float(voltage.max()),
            Planning_voltage_violations=int(np.sum((voltage < .95) | (voltage > 1.05))),
            capacity_violations=int(np.sum(plan['total_gpu'] > plan['capacities'] + 1e-9)),
            runtime_shortfall_GPUh=float(plan['runtime_shortfall'].sum()/4),
            CC4_shortfall_GPUh=float(plan['CC4_shortfall'].sum()/4),
            planning_IT_kWh=float(plan['IT_kw'].sum()/4), planning_PCC_kWh=float(plan['PCC_P_kw'].sum()/4))
    elif stage == 'ACTUAL':
        folder = routing.actual(day, output, Path(request['planning_folder']), root / 'actual_truth')
        metrics = read(folder / 'ACTUAL_CAPACITY_RECEIPT.json')
        if (not metrics['IT_recomputed_from_actual_occupancy'] or metrics['DayAhead_power_arrays_copied']
                or metrics.get('capacity_violations', 0) != 0 or metrics.get('dropped_jobs', 0) != 0):
            raise ValueError('Actual physical reconstruction audit failed')
    elif stage == 'FRESH_AC':
        folder, metrics = routing.fresh(day, output, Path(request['planning_folder']),
            Path(request['actual_folder']), authority['run_id'])
        if not metrics['converged'] or metrics['converged_slots'] != 96:
            raise ValueError('Fresh OpenDSS nonconvergence')
    elif stage == 'TRUTH_PREPARATION':
        import v42_holdout.realization as frozen
        import types
        namespace = dict(frozen.truth.__globals__, OUT=output, INPUT=INPUT)
        function = types.FunctionType(frozen.truth.__code__, namespace)
        from v42_holdout.common import source_freeze
        function(source_freeze())
        folder = output
        metrics = read(output / 'ACTUAL_REALIZED_SERVICE_AUTHORITY_AUDIT.json')
        if metrics['missing_realized_duration_unique_jobs']:
            raise ValueError('Raw realized service authority missing')
    else:
        raise PermissionError('Only native B0 compute stages run in subprocess')
    # No caller can reinterpret a successful computation as scientific day PASS.
    from v42_april_port.audit import clean
    return clean(dict(status='COMPUTED', arm='B0', day=day, stage=stage, run_id=authority['run_id'],
        synthetic_only=False, native=True, folder=str(folder), metrics=metrics,
        output_files=[record(p) for p in sorted(output.rglob('*')) if p.is_file()],
        source_checker_SHA=authority['checker_SHA'], GUROBI_THREADS=1,
        Gurobi_models_parameter_readback=models, Gurobi_optimize_calls=0,
        M1_calls=0, B1_calls=0, B2_calls=0, B3_calls=0, Branch_and_Price_calls=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    args = parser.parse_args()
    request = read(args.request)
    started = time.monotonic()
    result_path = Path(request['result'])
    try:
        result = execute(request)
        result.update(worker_PID=os.getpid(), runtime_seconds=time.monotonic()-started)
        atomic(result_path, result)
    except BaseException as error:
        atomic(result_path, dict(status='ERROR', error_type=type(error).__name__, reason=str(error),
            worker_PID=os.getpid(), runtime_seconds=time.monotonic()-started))
        raise


if __name__ == '__main__':
    main()
