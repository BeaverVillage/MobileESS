"""Fresh independent arm/date input routing to the existing frozen producers.

B2 never consumes a B0/B1 decision, point, reference result, UB or LB. Its causal
job population is regenerated from raw descriptors and D1 observations, then the
unchanged common FCFS/Q50 V2 producer constructs its fixed AIDC power trajectory.
"""
from pathlib import Path
from copy import deepcopy
from types import FunctionType
from datetime import datetime, timezone
import gzip
import json
import shutil
import numpy as np
import pandas as pd
from .common import ROOT, DAYS, atomic, read, record, digest, d_path, sha

TRAFFIC = Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic')
CODE = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')


def clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def day_routes(day, folder):
    if day not in DAYS:
        raise ValueError('MAY_DATE_REQUIRED')
    source = TRAFFIC / day / 'ROUTE_TABLE.json.gz'
    forecast = TRAFFIC / day / 'TRAFFIC_FORECAST.npz'
    table = json.loads(gzip.decompress(source.read_bytes()))
    with np.load(forecast, allow_pickle=False) as frozen:
        metadata = json.loads(str(frozen['metadata']))
        forecast_sha = metadata['bundle_sha']
        if (metadata['forecast_day'] != day or metadata['causality_pass'] is not True
                or metadata['future_actual_read_count'] != 0):
            raise ValueError('SAME_DAY_CAUSAL_ROUTE_FORECAST')
    if ({r['traffic_forecast_sha'] for r in table['routes']} != {forecast_sha}
            or len(table['service_ids']) != 24 or table['departure_slots'] != list(range(96))):
        raise ValueError('SAME_DAY_ROUTE_FORECAST_AXIS')
    destination = folder / 'ROUTE_TABLE.json.gz'
    shutil.copyfile(source, destination)
    shutil.copyfile(forecast, folder / 'TRAFFIC_FORECAST.npz')
    if sha(destination) != sha(source):
        raise ValueError('ROUTE_COPY_SHA')
    return dict(record(destination), period=day, units='seconds,kWh', role='same-day original frozen Route Table'), forecast_sha


def produce_b1(root):
    """Invoke the old May31 scientific producer in an entirely new output tree."""
    from v42_pr134_b1.inputs import produce
    root = d_path(root)
    generated = root / 'input_generation' / 'B1'
    generated.mkdir(parents=True, exist_ok=True)
    # Resume only already-generated causal inputs, never an optimization result.
    if all((generated / 'inputs' / day / 'NATIVE_INPUT.json').exists() for day in DAYS):
        rows = [dict(day=day, PASS=True, resumed_original_input=True) for day in DAYS]
    else:
        rows = produce(generated)
    if len(rows) != 31 or not all(row['PASS'] for row in rows):
        raise ValueError('B1_MAY31_ORIGINAL_INPUT_GENERATION_FAILED')
    for day in DAYS:
        source = generated / 'inputs' / day
        dest = root / 'inputs' / 'B1' / day
        shutil.copytree(source, dest, dirs_exist_ok=True)
        bundle = read(dest / 'NATIVE_INPUT.json')
        route, forecast = day_routes(day, dest)
        bundle.update(route_table=route, traffic_forecast_sha=forecast)
        atomic(dest / 'NATIVE_INPUT.json', bundle)
        atomic(dest / 'INPUT_IDENTITY.json', dict(PASS=True, day=day, arm='B1',
            original_producer=record(ROOT / 'v42_pr134_b1/inputs.py'),
            bundle=record(dest / 'NATIVE_INPUT.json'), windows=record(dest / 'WINDOWS.json'),
            operations=record(dest / 'OPERATIONS.json'), independently_generated=True,
            Native_calls=0, P2_calls=0, historical_optimizer_results_read=False))
    return rows


def produce_b2_raw(root):
    """Route the existing causal May producer, without invoking its B0 loop."""
    import v42_holdout.inputs as original
    from v42_holdout.common import source_freeze
    from v42_capacity.common import resolve
    root = d_path(root)
    generated = root / 'input_generation' / 'B2'
    generated.mkdir(parents=True, exist_ok=True)
    spec = source_freeze()
    source_by_day = {row['day']: row for row in spec['day_sources']}
    # Frozen CC4 values are forecast inputs, never a baseline operation result.
    forecasts = {day: read(ROOT / 'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE' /
        ('DAY_' + day.replace('-', '')) / 'PLANNING_INPUT_BUNDLE.json')['forecast_inputs']['current_CC4']
        for day in DAYS}
    reads = []
    def forecast_inputs_only(path):
        value = read(path)
        reads.append(str(Path(path)))
        return value
    class RawDay:
        def __init__(self, day): self.day = day
        def __truediv__(self, name):
            if name != 'gfs_d1_weather.parquet':
                raise ValueError('UNREGISTERED_RAW_WEATHER_READ')
            return resolve(source_by_day[self.day]['weather'])
    class RawRouter:
        def __truediv__(self, day): return RawDay(day)
    namespace = dict(original.__dict__, OUT=generated, INPUT=generated / 'INPUT', RAW=RawRouter(),
                     source_freeze=lambda: spec, read=forecast_inputs_only, cc4=lambda: deepcopy(forecasts))
    # Only the source producer's final call is routed: produce each day's raw
    # bundle and coefficients, then the campaign independently calls V2 below.
    class NoBaselineLoop:
        def main(self): pass
    namespace['producer'] = lambda *args, **kwargs: NoBaselineLoop()
    for name in ('requests', 'coefficients', 'main'):
        namespace[name] = clone(getattr(original, name), namespace)
    if not all((generated / 'INPUT/BUNDLE' / ('DAY_' + day.replace('-', '')) / 'PLANNING_INPUT_BUNDLE.json').exists() for day in DAYS):
        namespace['main']()
    atomic(generated / 'B0_LOOP_ROUTING_RECEIPT.json', dict(PASS=True,
        original_causal_input_producer=True, baseline_operation_loop_executed=False, Native_calls=0))
    for day in DAYS:
        source = generated / 'INPUT/BUNDLE' / ('DAY_' + day.replace('-', ''))
        dest = root / 'inputs/B2' / day
        shutil.copytree(source, dest, dirs_exist_ok=True)
        p = read(dest / 'PLANNING_INPUT_BUNDLE.json')
        native = deepcopy(read(ROOT / 'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'))
        cert_path = CODE / 'frozen_artifacts/v41r4_may/e' / day.replace('-', '') / 'V41_ELECTRICAL_CERTIFICATE.json'
        certificate = read(cert_path)
        if certificate['input_identity']['identity']['inputs']['day'] != day:
            raise ValueError('B2_ELECTRICAL_DATE')
        native.update(day=day, issue_time=p['issue_time'], known_population=deepcopy(p['known_population']),
            electrical_certificate=record(cert_path), grid_outputs=certificate['outputs'],
            C0_Q50=p['forecast_inputs']['current_CC4']['Q50_GPUh'],
            C0_Q90=p['forecast_inputs']['current_CC4']['Q90_GPUh'])
        from v42_final.workload import profile
        kernel = pd.read_csv(ROOT / 'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
        native['unknown_nominal_GPU'] = profile(np.asarray(native['C0_Q50']), kernel).tolist()
        native['CC4_reserve_GPU'] = profile(np.asarray(native['C0_Q90']) - np.asarray(native['C0_Q50']), kernel).tolist()
        route, forecast = day_routes(day, dest)
        native.update(route_table=route, traffic_forecast_sha=forecast,
                      reference=dict(role='TO_BE_GENERATED_INDEPENDENTLY_INSIDE_B2', source='raw causal input'))
        atomic(dest / 'NATIVE_INPUT.json', native)
        atomic(dest / 'OPERATIONS.json', dict(current_day_folder=str(dest), forecast_inputs=p['forecast_inputs']))
        atomic(dest / 'INPUT_IDENTITY.json', dict(PASS=True, arm='B2', day=day,
            bundle=record(dest / 'NATIVE_INPUT.json'), causal=record(dest / 'PLANNING_INPUT_BUNDLE.json'),
            independent_producer=record(ROOT / 'v42_holdout/inputs.py'), source_snapshot=source_by_day[day]['snapshot'],
            source_archive=spec['archive'], historical_B0_B1_decision_reads=0,
            references_to_forecast_inputs_only=True, optimizer_calls=0, runtime_fit_calls=0))
        generate_b2(dict(root=str(root), input_folder=str(dest), day=day, arm='B2'))
        native['reference'] = dict(record(dest / 'B2_FIXED_AIDC.json'), role='Own B2 independently generated FCFS/Q50 reference')
        atomic(dest / 'NATIVE_INPUT.json', native)
        identity = read(dest / 'INPUT_IDENTITY.json')
        identity['bundle'] = record(dest / 'NATIVE_INPUT.json')
        identity['fixed_AIDC'] = record(dest / 'B2_FIXED_AIDC.json')
        atomic(dest / 'INPUT_IDENTITY.json', identity)
    atomic(generated / 'INDEPENDENT_INPUT_READ_AUDIT.json', dict(PASS=True, reads=reads,
        B0_B1_decision_reads=0, AIDC_optimizer_calls=0, Native_calls=0,
        reused_causal_raw_producer=True, baseline_operation_loop_executed=False))


def fixed_aidc(p, coefficient_path, power, *, reference_builder=None):
    """Same arithmetic and rules as existing capacity.planning, single date."""
    from v42_capacity.reference import build_reference
    from v42_modelable.power import known_occupancy
    from v42_capacity.queue import allocate, conservation
    reference_builder = reference_builder or build_reference
    refs, audit = reference_builder(p['known_population'], p['capacities'], p['rack_compatibility'], issue_time=p['issue_time'])
    if not audit['full_reference_ready']:
        raise ValueError('B2_COMMON_FCFS_REFERENCE_BLOCKED')
    sites = sorted(p['capacities'])
    caps = np.array([p['capacities'][s] for s in sites])
    known = known_occupancy(refs, sites)
    cc = p['forecast_inputs']['current_CC4']
    if cc['target_day'] != p['day'] or cc['future_job_ids']:
        raise ValueError('B2_CC4_CAUSAL_AXIS')
    anon, incoming, outgoing = allocate(known, cc['nominal_unknown_GPU_96'], caps)
    total = known + anon
    cons = conservation(sum(cc['Q50_GPUh']), anon, outgoing[-1], cc['full_tail_nominal_GPUh'])
    coefficients = pd.read_csv(coefficient_path)
    slope = coefficients.pivot(index='slot', columns='aidc_id', values='slope')[sites].to_numpy()
    intercept = coefficients.pivot(index='slot', columns='aidc_id', values='intercept_kw')[sites].to_numpy()
    it = power['current_IT_idle_kW_per_installed_GPU'] * caps + power['current_IT_swing_kW_per_active_GPU'] * total
    pcc = slope * it + intercept
    q = pcc * np.tan(np.arccos(.95))
    if (total.shape != (96, 12) or not np.isfinite(pcc).all() or not cons['PASS']
            or np.any(total > caps + 1e-9) or np.any(total < -1e-9)):
        raise ValueError('B2_FIXED_AIDC_PHYSICAL_OR_CONSERVATION')
    return dict(sites=np.array(sites), capacities=caps, GPU=total, known_gpu=known,
                cc4_served_gpu=anon, IT_kw=it, PCC_P_kw=pcc, PCC_Q_kvar=q), refs, audit, cons


def generate_b2(request):
    folder = d_path(request['input_folder'])
    day = request['day']
    if request.get('arm') != 'B2' or day not in DAYS:
        raise ValueError('INDEPENDENT_B2_DATE_REQUIRED')
    p, bundle = read(folder / 'PLANNING_INPUT_BUNDLE.json'), read(folder / 'NATIVE_INPUT.json')
    if p['day'] != day or bundle['day'] != day:
        raise ValueError('B2_INPUT_DATE_CONFLICT')
    power = read(folder / 'POWER_AUTHORITY.json')
    planning, refs, audit, conservation = fixed_aidc(p, folder / 'C1_PLANNING_COEFFICIENTS.csv', power)
    # Reconstruct again independently and compare exact arrays/identity.
    replay, replay_refs, replay_audit, replay_conservation = fixed_aidc(p, folder / 'C1_PLANNING_COEFFICIENTS.csv', power)
    if refs != replay_refs or audit != replay_audit or conservation != replay_conservation or any(
            not np.array_equal(planning[k], replay[k]) for k in planning):
        raise ValueError('B2_REFERENCE_INDEPENDENT_REPLAY')
    identity = dict(PASS=True, day=day, arm='B2', rule=audit['queue_rule'],
        input_SHA=sha(folder / 'PLANNING_INPUT_BUNDLE.json'), reference_SHA=digest(refs),
        job_ids_SHA=digest(sorted(r['job_uid'] for r in refs)), jobs=len(refs),
        time_axis=list(range(96)), sites=planning['sites'].tolist(),
        power_units=['kW', 'kvar'], AIDC_optimization_calls=0, MESS_optimizer_calls=0,
        B0_B1_schedule_result_reads=0, full_reference=audit, conservation=conservation,
        independent_exact_replay=True, source=record(ROOT / 'v42_capacity/reference.py'))
    selected = {r['job_uid']: r for r in refs}
    if (folder / 'B2_FIXED_AIDC.json').exists():
        prior = read(folder / 'B2_FIXED_AIDC.json')
        if (prior['identity'] != identity or prior['selected_jobs'] != selected
                or sha(prior['physical']['path']) != prior['physical']['sha256']):
            raise ValueError('FROZEN_B2_INPUT_IDENTITY_DRIFT')
        with np.load(folder / 'PLANNING_PHYSICAL.npz', allow_pickle=False) as frozen:
            if set(frozen.files) != set(planning) or any(not np.array_equal(frozen[k], planning[k]) for k in planning):
                raise ValueError('FROZEN_B2_PHYSICAL_POWER_DRIFT')
    else:
        np.savez_compressed(folder / 'PLANNING_PHYSICAL.npz', **planning)
        atomic(folder / 'B2_FIXED_AIDC.json', dict(identity=identity, selected_jobs=selected,
            physical=record(folder / 'PLANNING_PHYSICAL.npz')))
    return dict(bundle=bundle, planning=planning, selected_jobs={r['job_uid']: r for r in refs},
                identity=identity, anchor=dict(day=day, PCC_P_kw=planning['PCC_P_kw'].tolist()))
