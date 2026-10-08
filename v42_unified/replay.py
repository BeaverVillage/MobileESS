"""Original integer/physical replay and immutable P1-only handoff materialization."""
from contextlib import ExitStack
from fractions import Fraction
import gzip
import json
import pickle
from time import perf_counter
from types import FunctionType
from unittest.mock import patch
import numpy as np
from .audit import ROOT, REPORTS, A_HEAD, git, write
from .storage import FrozenStore, sha, setup
from .interface import build_handoff, m1_payload

A_OUT = ROOT/'docs/v42_may12_p1_exact_rescue_20261008'


def read(path):
    return json.loads(__import__('pathlib').Path(path).read_text(encoding='utf-8-sig'))


def pinned(path, head=A_HEAD):
    raw = git('show', f'{head}:{path.relative_to(ROOT).as_posix()}')
    import hashlib
    if hashlib.sha256(raw).hexdigest() != sha(path):
        raise ValueError('COMMITTED_EVIDENCE_DRIFT:'+str(path))
    return json.loads(raw)


def forbid_native(stack):
    import gurobipy as gp
    def forbidden(*a, **k):
        raise PermissionError('V42_INTEGRATION_NATIVE_OPTIMIZE_FORBIDDEN')
    stack.enter_context(patch.object(gp.Model, 'optimize', forbidden))
    stack.enter_context(patch.object(gp.Model, 'presolve', forbidden))


def aidc_replay():
    setup()
    start = perf_counter()
    freeze = pinned(A_OUT/'P1_ONLY_FREEZE.json')
    identity = pinned(A_OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY_FINAL.json')
    store = FrozenStore()
    for r in identity['files']:
        if r['expected'] != r['actual'] or not r['PASS']:
            raise ValueError('FROZEN_INPUT_IDENTITY_NOT_PASS')
        store.copy(r['expected'])
    # Independently reconstruct every frozen array identity from the D copies.
    bundle_path = store.copy(identity['files'][0]['expected'])
    bundle = read(bundle_path)
    grid_arrays = []
    import hashlib
    for archive, receipt in bundle['grid_outputs'].items():
        with np.load(store.copy(receipt), allow_pickle=False) as z:
            for name in z.files:
                a = z[name]
                payload = np.ascontiguousarray(a).tobytes()
                grid_arrays.append(dict(archive=archive, array=name, dtype=a.dtype.str,
                    shape=list(a.shape), sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)))
    if grid_arrays != identity['original_grid_array_identities']:
        raise ValueError('GRID_ARRAY_IDENTITY_DRIFT')
    axes = []
    for key in ('known_population', 'racks', 'capacities', 'WAN', 'runtime_survival_kernel',
                'C0_Q50', 'C0_Q90', 'CC4_reserve_GPU', 'unknown_nominal_GPU'):
        axes.append(dict(axis=key, canonical_JSON_sha256=hashlib.sha256(json.dumps(
            bundle[key], sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            allow_nan=False).encode()).hexdigest()))
    if axes != identity['original_workload_axis_identities']:
        raise ValueError('WORKLOAD_AXIS_IDENTITY_DRIFT')
    certificate = read(store.copy(bundle['electrical_certificate']))
    for key in ('AIDC_power_C1', 'weather'):
        store.collect(certificate['input_identity']['identity']['inputs'][key], recursive_json=False)
    store.collect(certificate['outputs'], recursive_json=False)
    model_path = store.copy(freeze['integer_model_checkpoint'])
    point_path = store.copy(freeze['validated_original_integer_point'])
    with gzip.open(model_path, 'rb') as stream:
        saved = pickle.load(stream)
    state, typed = saved['state']['state'], saved['state']['typed']
    point = np.load(point_path)['X']
    integer = pinned(A_OUT/'P1_INTEGER_RESULT.json')
    native = pinned(A_OUT/(__import__('pathlib').Path(integer['native_result']['path']).relative_to(
        __import__('pathlib').Path('D:/v42_may12_p1_exact_rescue_20261008/docs/v42_may12_p1_exact_rescue_20261008'))))
    model_identity = pinned(A_OUT/(__import__('pathlib').Path(native['model_identity']['path']).relative_to(
        __import__('pathlib').Path('D:/v42_may12_p1_exact_rescue_20261008/docs/v42_may12_p1_exact_rescue_20261008'))))
    if typed.fingerprint() != model_identity['original_snapshot_sha256']:
        raise ValueError('ORIGINAL_INTEGER_MATRIX_IDENTITY_DRIFT')
    from v42_may12_rescue.exact import replay as exact_replay
    from v42_a_stage_lexfull.runner import objective_value
    from v42_pr134_sc.snapshot import certify
    from v42_pr134_b1.native import date_route
    import v42_temporal.native as temporal
    import v42_may01.prepare as original
    import v42_exact.validation as validation
    import v42_native.voltage as voltage
    import v42_thermal.authority as thermal
    import v42_thermal.planning as planning
    thermal_path = ROOT/'docs/v42_transformer_normalamps_contract/SOURCE_COMPILED_NORMALAMPS_AUTHORITY.json'
    thermal_frozen = pinned(thermal_path)
    if thermal.digest(thermal_frozen['identity']) != thermal_frozen['transformer_current_authority_sha256']:
        raise ValueError('FROZEN_NORMALAMPS_AUTHORITY_DRIFT')
    if thermal_frozen['Planning'] != thermal_frozen['Actual']:
        raise ValueError('PLANNING_ACTUAL_THERMAL_IDENTITY_DRIFT')
    # Replay uses the already compiled, source-backed authority. No new AC run.
    # Original numeric constructors/validators execute; only paths/day/authority
    # loading are bound explicitly to identical frozen D bytes.
    load_power = FunctionType(temporal.load_power.__code__, dict(temporal.load_power.__globals__,
        read=lambda p: store.operational_view(read(p))), argdefs=temporal.load_power.__defaults__)
    native_coefficients = FunctionType(original.native_coefficients.__code__,
        dict(original.native_coefficients.__globals__, DAY=bundle['day']),
        argdefs=original.native_coefficients.__defaults__)
    data = (store.operational_view(bundle), *state['data'][1:])
    if 'scientific_descriptor' in state:
        descriptor = dict(state['scientific_descriptor'], units=state['reference_descriptor']['units'])
    else:
        authority = pinned(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json')
        path = store.copy(authority['global_descriptor'])
        with gzip.open(path, 'rb') as stream:
            descriptor = dict(pickle.load(stream), units=state['reference_descriptor']['units'])
    descriptor['levels'] = [(o.name, ('e', float(o.constant), np.asarray(list(o.coefficients()), int),
                                    np.asarray([float(v) for v in o.coefficients().values()]))) for o in typed.objectives]
    build_start = perf_counter()
    with ExitStack() as stack:
        forbid_native(stack)
        stack.enter_context(patch.object(temporal, 'load_power', load_power))
        stack.enter_context(patch.object(original, 'native_coefficients', native_coefficients))
        stack.enter_context(patch.object(validation, 'check', date_route(validation.check)))
        stack.enter_context(patch.object(thermal, 'current_authority', lambda: thermal_frozen))
        stack.enter_context(patch.object(planning, 'current_authority', lambda: thermal_frozen))
        stack.enter_context(patch.dict(voltage._MAPPING, {s: voltage.Voltage('INTEGRATED_ZERO_MARGIN', .95, 1.05, .95**2, 1.05**2)
                                                        for s in (voltage.Stage.A1, voltage.Stage.M1, voltage.Stage.A2, voltage.Stage.M2)}))
        cert, *_ = load_power(data[0])
        coeff = native_coefficients(cert)
        coefficients_seconds = perf_counter()-build_start
        exact = exact_replay(typed, point)  # Original 1e-6, unchanged.
        physical, selected, controls, globals_ = certify(descriptor, data, point, exact, coeff)
    from v42_may12_rescue.verify_integer import saved_schedule_equal
    U = objective_value(typed, point, 'rho')
    result = dict(PASS=bool(exact['PASS'] and physical['PASS']), native_optimize_calls=0,
                  original_rows=exact, physical=physical, original_population=len(data[1]),
                  selected_jobs_match_saved_schedule=saved_schedule_equal(selected, freeze['selected_jobs']),
                  controls_match_saved=controls == freeze['controls'], globals_match_saved=globals_ == freeze['globals'],
                  exact_UB=str(U), integrality_residual=float(np.max(abs(point[typed.vtypes!='C']-np.rint(point[typed.vtypes!='C'])), initial=0)),
                  typed_matrix_identity=typed.fingerprint(), grid_arrays=len(grid_arrays), frozen_input_files=len(identity['files']),
                  original_grid_and_workload_hashes_PASS=True, coefficients_seconds=coefficients_seconds,
                  validation_wall_seconds=perf_counter()-start, frozen_NormalAmps_replay=True, Fresh_AC=False,
                  D_source_copy_manifest=store.seal())
    result['PASS'] = result['PASS'] and all(result[k] for k in
        ('selected_jobs_match_saved_schedule', 'controls_match_saved', 'globals_match_saved')) and result['integrality_residual'] <= 1e-5
    write(REPORTS/'A1_ORIGINAL_INTEGER_PHYSICAL_REPLAY.json', result)
    if not result['PASS']:
        raise ValueError('INDEPENDENT_P1_ONLY_REPLAY_FAILED')
    certificates = {k: pinned(A_OUT/n) for k, n in dict(zero='PHASE1_ZERO_CERTIFICATE.json',
        closure='COMPLETE_PRICING_CLOSURE.json', bound='P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',
        integer='P1_INTEGER_RESULT.json', physical='ORIGINAL_PHYSICAL_REPLAY.json').items()}
    handoff = build_handoff(freeze, certificates, identity, coeff[0].control_names,
                           replay=result, source_hash=sha(A_OUT/'P1_ONLY_FREEZE.json'))
    from .verify_interface import verify
    interface_check = verify(handoff, freeze, identity, certificates, result,
                             sha(A_OUT/'P1_ONLY_FREEZE.json'), coeff[0].control_names)
    write(REPORTS/'INDEPENDENT_P1_ONLY_INTERFACE_VERIFICATION.json', interface_check)
    from v42_native.contracts import digest
    mess = dict(route_table_sha256=bundle['route_table']['sha256'], battery_sha256=digest(bundle['battery']),
                initial_sites_sha256=digest(bundle['initial_MESS_sites']), traffic_forecast_sha256=bundle['traffic_forecast_sha'])
    payload = m1_payload(handoff, mess)
    write(REPORTS/'A1_P1_ONLY_TO_M1_HANDOFF.json', handoff)
    write(REPORTS/'M1_P1_ONLY_INPUT.json', payload)
    return result, handoff, payload


if __name__ == '__main__':
    result, _, _ = aidc_replay()
    print('P1_ONLY_TO_M1_ORIGINAL_REPLAY', result['PASS'], result['original_population'], result['validation_wall_seconds'])
