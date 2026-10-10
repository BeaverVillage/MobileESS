"""Accepted current P1 -> frozen Actual -> original 96-slot Fresh OpenDSS.

The historical four-objective replay gate is untouched.  This namespace port
admits only this campaign's current accepted P1 receipt, and restores the
original MESS injection binding for B2.  It contains no optimizer or repair.
"""
import ast
import inspect
import textwrap
from pathlib import Path
import os
import numpy as np
from .common import ROOT, DAYS, atomic, read, record, digest, sha, d_path
from .a_routing import InputDirectory, rebound


def _verified(receipt):
    path = Path(receipt['path'])
    if sha(path) != receipt['sha256']:
        raise ValueError('OPERATIONS_SOURCE_SHA_DRIFT:' + str(path))
    return path


def _notify(progress, phase, request):
    if progress:
        progress(dict(phase=phase, day=request['day'], arm=request['arm'],
                      Actual_reoptimization=0, P2_calls=0))


def _identity(request, stage='PLANNING_FREEZE'):
    return dict(run_id=request['run_id'], day=request['day'], arm=request['arm'],
                stage=stage, day_input_SHA=sha(Path(request['input_folder']) / 'NATIVE_INPUT.json'),
                schema='V42_MAY_CURRENT_P1_FIXED_REPLAY_V1')


def _accepted(request, stage, output):
    """Verify and materialize the newly accepted arm's own frozen arrays."""
    arm, day = request['arm'], request['day']
    gap = stage.get('certified_gap', stage.get('gap'))
    if (arm not in ('B1', 'B2') or day not in DAYS or stage.get('PASS') is not True
            or stage.get('accepted') is not True or stage.get('arm') != arm
            or stage.get('day') != day or gap is None or not np.isfinite(gap)
            or not 0 <= gap <= (.005 if arm == 'B1' else .03)
            or stage.get('P2_calls') != 0 or stage.get('UB') is None or stage.get('LB') is None
            or not np.isfinite([stage['UB'], stage['LB']]).all() or stage['UB'] < stage['LB']):
        raise ValueError('NEW_CURRENT_P1_ACCEPTED_STAGE_REQUIRED')
    if arm == 'B1':
        accepted_path = _verified(stage['freeze'])
        accepted = read(accepted_path)
        if (accepted.get('A1_P1_ONLY_ACCEPTED') is not True or accepted.get('A1_ACCEPTED') is not False
                or accepted.get('PASS') is not True or accepted.get('accepted') is not True
                or accepted.get('day') != day or accepted.get('arm') != arm
                or accepted.get('P2_calls') != 0 or accepted.get('MESS_optimization_calls') != 0
                or accepted.get('all_MESS_PQ_zero') is not True):
            raise ValueError('NEW_B1_P1_ONLY_FREEZE_REQUIRED')
        for name in ('physical', 'acceptance', 'global_bound'):
            _verified(accepted[name])
        with np.load(_verified(stage['planning']), allow_pickle=False) as archive:
            planning = {k: archive[k].copy() for k in archive.files}
        selected = accepted['selected_jobs']
        mess = dict(P_kw=np.zeros((96, 4)), Q_kvar=np.zeros((96, 4)),
                    locations=np.asarray([['STA01', 'STA12', 'STA08', 'STA06']] * 96),
                    unit_ids=np.asarray(['MESS01', 'MESS02', 'MESS03', 'MESS04']),
                    SOC_kwh=None, routes=[])
    else:
        folder = Path(request['input_folder'])
        fixed = read(folder / 'B2_FIXED_AIDC.json')
        identity = fixed['identity']
        if (identity.get('PASS') is not True or identity.get('day') != day
                or identity.get('arm') != 'B2' or identity.get('AIDC_optimization_calls') != 0
                or identity.get('B0_B1_schedule_result_reads') != 0
                or stage.get('AIDC_optimization_calls') != 0):
            raise ValueError('INDEPENDENT_B2_FIXED_AIDC_REQUIRED')
        with np.load(_verified(fixed['physical']), allow_pickle=False) as archive:
            planning = {k: archive[k].copy() for k in archive.files}
        if set(stage['planning']) != set(planning) or any(
                not np.array_equal(stage['planning'][k], planning[k]) for k in planning):
            raise ValueError('B2_FIXED_AIDC_PLANNING_CHANGED')
        selected = fixed['selected_jobs']
        accepted_path = _verified(stage['mess_plan'])
        plan = read(accepted_path)
        if (plan != stage['mess'] or plan.get('day') != day or plan.get('arm') != arm
                or plan.get('case_sha') != stage.get('case_sha')):
            raise ValueError('NEW_B2_OPTIMIZED_MESS_PLAN_REQUIRED')
        for name in ('strict_UB', 'exact_LB'):
            _verified(stage['certificate'][name])
        mess = dict(P_kw=np.asarray(plan['P_kw'], dtype=float), Q_kvar=np.asarray(plan['Q_kvar'], dtype=float),
                    locations=np.asarray(plan['locations'], dtype=str), unit_ids=np.asarray(plan['unit_ids'], dtype=str),
                    SOC_kwh=np.asarray(plan['SOC_kwh'], dtype=float), routes=plan['routes'])
    native_bundle = read(Path(request['input_folder']) / 'NATIVE_INPUT.json')
    site_axis = sorted(native_bundle['capacities'])
    if (native_bundle.get('day') != day or len(site_axis) != 12
            or list(map(str, planning['sites'])) != site_axis):
        raise ValueError('FROZEN_AIDC_SITE_AXIS')
    for name in ('PCC_P_kw', 'PCC_Q_kvar', 'IT_kw', 'GPU'):
        if np.shape(planning[name]) != (96, 12) or not np.isfinite(planning[name]).all():
            raise ValueError('FROZEN_AIDC_PHYSICAL_AXIS:' + name)
    for name in ('P_kw', 'Q_kvar'):
        if mess[name].shape != (96, 4) or not np.isfinite(mess[name]).all():
            raise ValueError('FROZEN_MESS_PHYSICAL_AXIS:' + name)
    if (mess['locations'].shape != (96, 4) or list(mess['unit_ids']) != [f'MESS{i:02d}' for i in range(1, 5)]
            or (arm == 'B2' and (mess['SOC_kwh'].shape != (97, 4) or not np.isfinite(mess['SOC_kwh']).all()))):
        raise ValueError('FROZEN_MESS_LOCATION_SOC_AXIS')
    for t in range(96):
        for j, location in enumerate(mess['locations'][t]):
            if str(location).startswith('TRANSIT_') and (abs(mess['P_kw'][t, j]) > 1e-9 or abs(mess['Q_kvar'][t, j]) > 1e-9):
                raise ValueError('V28R2_OPENDSS_NONZERO_MESS_IN_TRANSIT')
    # B2 reference records embed their own UID; the old DTO constructor supplies
    # that same UID from the dictionary key. This is solely a schema binding.
    selected = {uid: {k: v for k, v in value.items() if k != 'job_uid'} for uid, value in selected.items()}
    np.savez_compressed(output / 'PLANNING_PHYSICAL.npz', **planning)
    arrays = {k: v for k, v in mess.items() if k not in ('routes', 'SOC_kwh')}
    if mess['SOC_kwh'] is not None:
        arrays['SOC_kwh'] = mess['SOC_kwh']
    np.savez_compressed(output / 'PLANNING_MESS.npz', **arrays)
    evidence = {k: stage.get(k) for k in ('day', 'arm', 'PASS', 'accepted', 'UB', 'LB', 'certified_gap', 'gap',
                    'P2_calls', 'case_sha', 'certificate', 'freeze', 'planning', 'mess_plan')}
    if arm == 'B2':
        evidence['planning'] = fixed['physical']
        evidence['independent_AIDC'] = record(Path(request['input_folder']) / 'B2_FIXED_AIDC.json')
    atomic(output / 'ACCEPTED_STAGE_RECEIPT.json', evidence)
    accepted = dict(PASS=True, accepted=True, day=day, arm=arm, selected_jobs=selected,
                    domain_status=None, source_receipt=record(accepted_path))
    return accepted, planning, mess


def _freeze_port(original, namespace, arm):
    """Only route old B1 schema labels; retain original power/decision arithmetic."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    changes = []
    class Route(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == 'B1':
                changes.append(node.lineno)
                return ast.copy_location(ast.Name(id='_campaign_arm', ctx=ast.Load()), node)
            return node
        def visit_keyword(self, node):
            node = self.generic_visit(node)
            if node.arg in ('MESS_OFF', 'current_V42_A1_only'):
                node.value = ast.Name(id='_campaign_b1', ctx=ast.Load())
            return node
    tree = Route().visit(tree)
    if len(changes) != 2:
        raise ValueError('ORIGINAL_FREEZE_B1_SCHEMA_DRIFT')
    namespace.update(_campaign_arm=arm, _campaign_b1=arm == 'B1')
    ast.fix_missing_locations(tree)
    exec(compile(tree, inspect.getfile(original), 'exec'), namespace)
    return namespace[original.__name__]


def freeze_planning(request, accepted, mess, output):
    from v42_pr134_b1 import replay
    from .execution import authorize
    source = output.parent / 'SOURCE'
    identity = _identity(request)
    def routed_read(path):
        if Path(path) == source / 'A1_FREEZE.json':
            return accepted
        return read(path)
    def routed_record(path):
        if Path(path) == source / 'A1_FREEZE.json':
            return record(source / 'ACCEPTED_STAGE_RECEIPT.json')
        return record(path)
    def freeze_write(path, payload):
        payload.update(current_P1_acceptance=True, historical_four_objective_acceptance=False,
            MESS_plan=record(source / 'PLANNING_MESS.npz'), MESS_routes=mess['routes'],
            accepted_source=accepted['source_receipt'], P2_calls=0, Actual_reoptimization=0,
            original_freeze_source=record(ROOT / 'v42_pr134_b1/replay.py'))
        atomic(path, payload)
    namespace = dict(vars(replay), read=routed_read, record=routed_record, atomic=freeze_write,
        require_action_authorized=authorize, require_production_domain_accepted=lambda value: None,
        identity=lambda *args: identity)
    port = _freeze_port(replay.freeze_planning, namespace, request['arm'])
    return port(InputDirectory(request['day'], request['input_folder']), request['day'], source, output,
                dict(day_input_SHA={request['day']: identity['day_input_SHA']}))


def actual(request, planning, source, output):
    """Execute the old fixed-decision materializer, including its unchanged DTO."""
    from v42_pr134_b1 import replay
    from .execution import authorize
    expected = _identity(request)
    with np.load(source / 'PLANNING_MESS.npz', allow_pickle=False) as archive:
        mess = {k: archive[k].copy() for k in archive.files}
    np.savez_compressed(output / 'ACTUAL_MESS_TRAJECTORY.npz', **mess)
    def write_actual(path, payload):
        payload.update(arm=request['arm'], MESS_PQ=0 if request['arm'] == 'B1' else 'FROZEN_OPTIMIZED_PLANNING',
            M1=0, M2=0, AIDC_optimizer_calls=0, MESS_optimizer_calls=0, P2_calls=0,
            MESS_frozen_trajectory=record(output / 'ACTUAL_MESS_TRAJECTORY.npz'),
            MESS_Planning=record(source / 'PLANNING_MESS.npz'), source=record(ROOT / 'v42_pr134_b1/replay.py'))
        atomic(path, payload)
    namespace = dict(vars(replay), require_action_authorized=lambda *args: authorize(request['day'], 'ACTUAL'),
                     atomic=write_actual)
    namespace['build_day'] = rebound(replay.build_day, namespace)
    result = rebound(replay.actual, namespace)(planning, expected, output)
    with np.load(output / 'ACTUAL_FIXED_TRAJECTORY.npz', allow_pickle=False) as archive:
        p, q = archive['PCC_P_kw'].copy(), archive['PCC_Q_kvar'].copy()
    with np.load(source / 'PLANNING_PHYSICAL.npz', allow_pickle=False) as archive:
        if not np.array_equal(p, archive['PCC_P_kw']) or not np.array_equal(q, archive['PCC_Q_kvar']):
            raise ValueError('ACTUAL_FROZEN_PCC_CHANGED')
    with np.load(output / 'ACTUAL_MESS_TRAJECTORY.npz', allow_pickle=False) as archive:
        if set(archive.files) != set(mess) or any(not np.array_equal(archive[k], mess[k]) for k in mess):
            raise ValueError('ACTUAL_FROZEN_MESS_CHANGED')
    return result


def actual_sources(request, output):
    """Reuse the original raw-month Actual producer after the accepted freeze."""
    import pandas as pd
    from v42_capacity.common import resolve, day_folder
    folder = Path(request['input_folder'])
    ops = read(folder / 'OPERATIONS.json')
    original = Path(ops['current_day_folder'])
    provenance = read(original / 'SOURCE_PROVENANCE.json')
    destination = output / 'INPUT/BUNDLE' / day_folder(request['day'])
    destination.mkdir(parents=True, exist_ok=True)
    atomic(destination / 'SOURCE_PROVENANCE.json', provenance)
    if request['arm'] == 'B2':
        from v42_holdout import realization
        from v42_holdout.common import source_freeze
        raw = output / 'RAW' / request['day']
        raw.mkdir(parents=True, exist_ok=True)
        atomic(raw / 'aemo_forecast.json', ops['forecast_inputs']['AEMO'])
        namespace = dict(vars(realization), DAYS=(request['day'],), INPUT=output / 'INPUT', RAW=output / 'RAW')
        # Existing demand interval-end selection, PV repeat-two, within-day
        # weather interpolation and exact forecast UTC-axis check are unchanged.
        rebound(realization.exogenous, namespace)(source_freeze())
    provenance = read(destination / 'SOURCE_PROVENANCE.json')
    path = resolve(provenance['daily_sources']['aemo_actual.parquet'])
    frame = pd.read_parquet(path)
    if (len(frame) != 96 or not set(('ts_fixed_aest_end', 'demand_mw', 'rooftop_pv_mw')) <= set(frame)
            or not np.isfinite(frame[['demand_mw', 'rooftop_pv_mw']].to_numpy(float)).all()
            or not pd.DatetimeIndex(frame.ts_fixed_aest_end).tz_convert('UTC').equals(
                pd.DatetimeIndex(ops['forecast_inputs']['AEMO']['timestamps_96']).tz_convert('UTC'))):
        raise ValueError('ACTUAL_SOURCE_EXACT_DAILY_AXIS')
    atomic(output / 'ACTUAL_SOURCE_RECEIPT.json', dict(PASS=True, day=request['day'], arm=request['arm'],
        source=record(path), provenance=record(destination / 'SOURCE_PROVENANCE.json'),
        original_producer=record(ROOT / 'v42_holdout/realization.py'), Native_calls=0,
        post_accepted_Planning_freeze=True, existing_Actual_data_rules_unchanged=True))
    return destination


def _fresh_port(original, namespace):
    """Route only trajectory and injection bindings of the existing Fresh port."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    changes = dict(trajectory=0, injection=0, zero=0)
    class Route(ast.NodeTransformer):
        def visit_Assign(self, node):
            node = self.generic_visit(node)
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == 'trajectory' and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == 'FrozenTrajectory'):
                node.value = ast.Call(func=ast.Name(id='_campaign_trajectory', ctx=ast.Load()),
                    args=[ast.Name(id='p', ctx=ast.Load()), ast.Name(id='q', ctx=ast.Load()),
                          ast.Attribute(value=ast.Name(id='aidc', ctx=ast.Load()), attr='contract_sha256', ctx=ast.Load())], keywords=[])
                changes['trajectory'] += 1
            return node
        def visit_FunctionDef(self, node):
            if node.name == 'apply_current':
                if (len(node.body) != 7 or not isinstance(node.body[0], ast.Assign)
                        or not isinstance(node.body[-2], ast.Expr) or not isinstance(node.body[-1], ast.Expr)):
                    raise ValueError('ORIGINAL_FRESH_INJECTION_SOURCE_DRIFT')
                call = ast.Expr(value=ast.Call(func=ast.Name(id='_campaign_apply', ctx=ast.Load()),
                    args=[ast.Name(id=k, ctx=ast.Load()) for k in ('engine', 'ad', '_context', 'tr', 't')], keywords=[]))
                append = ast.Expr(value=ast.Call(func=ast.Name(id='_campaign_applied', ctx=ast.Load()),
                    args=[ast.Name(id=k, ctx=ast.Load()) for k in ('applied', 'tr', 't', 'allocation')], keywords=[]))
                node.body = [node.body[0], call, node.body[-2], append]
                changes['injection'] += 1
                return node
            return self.generic_visit(node)
        def visit_keyword(self, node):
            node = self.generic_visit(node)
            if node.arg == 'all_MESS_PQ_zero':
                if not isinstance(node.value, ast.Constant) or node.value.value is not True:
                    raise ValueError('ORIGINAL_FRESH_ZERO_RECEIPT_DRIFT')
                node.value = ast.Name(id='_campaign_mess_zero', ctx=ast.Load())
                changes['zero'] += 1
            return node
    tree = Route().visit(tree)
    if changes != dict(trajectory=1, injection=1, zero=1):
        raise ValueError('ORIGINAL_FRESH_BINDING_COUNT_DRIFT:' + str(changes))
    ast.fix_missing_locations(tree)
    exec(compile(tree, inspect.getfile(original), 'exec'), namespace)
    return namespace[original.__name__]


def _summary_pass(summary, converged):
    # Preserve the original Actual/Fresh completion contract. Source-backed
    # Actual exogenous conditions can produce physical exposures; the original
    # OpenDSS output declares those measured violations to be results. They do
    # not authorize an optimizer, repair, or a different Planning certificate.
    return (converged is True and summary.get('convergence_count') == 96
            and summary.get('OpenDSS_solve_count') == 96
            and summary.get('clean_engine_count') == 1
            and summary.get('schedule_mutation_count') == 0)


def isolated_compile(original, output, compilations):
    """Keep the original independent engine and route only its file directory."""
    sandbox = d_path(Path(output) / 'OPENDSS_SANDBOX')
    sandbox.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    try:
        engine, adapter, inventory = original()
        engine.Basic.DataPath(str(sandbox))
        actual = Path(engine.Basic.DataPath()).resolve()
        if actual != sandbox:
            raise ValueError('OPENDSS_DATE_DATA_PATH_ISOLATION_FAILURE')
        compilations.append(dict(PID=os.getpid(), context_index=len(compilations) + 1,
            data_path=str(actual), source_initial_inventory_SHA=digest(inventory),
            original_compiler_reused=True, scientific_control_settings_changed=False))
        return engine, adapter, inventory
    finally:
        os.chdir(previous)


def fresh(request, planning, actual_folder, source_folder, output, progress=None):
    from v42_pr134_b1 import replay
    from v42_regcontrol.authority import source
    from .execution import authorize
    source()
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2 import opendss_mapping, opendss_backend
    with np.load(actual_folder / 'ACTUAL_MESS_TRAJECTORY.npz', allow_pickle=False) as archive:
        mess = {k: archive[k].copy() for k in archive.files}
    before = record(actual_folder / 'ACTUAL_MESS_TRAJECTORY.npz')
    original_backend_code = opendss_backend.run_fresh_opendss.__code__
    def trajectory(p, q, contract):
        schedule = digest(dict(day=request['day'], arm=request['arm'], AIDC_contract_SHA=contract,
                               frozen_MESS_SHA=before['sha256']))
        result = FrozenTrajectory(request['day'], 'ACTUAL', request['arm'], p, q,
            mess['P_kw'], mess['Q_kvar'], tuple(mess['unit_ids']), mess['locations'], schedule)
        result.validate()
        return result
    def apply_mapping(engine, adapter, context, tr, slot):
        # Same binding as existing v40e corrected_mapping: native background was
        # already allocated once, so the original mapping receives no bg loads.
        opendss_mapping.apply_trajectory_slot(engine, dict(adapter, loads=[]), context, tr, slot)
    def applied(log, tr, slot, allocation):
        log.append(dict(slot=slot, PCC_P_kw=tr.pcc_p_kw[slot].tolist(), PCC_Q_kvar=tr.pcc_q_kvar[slot].tolist(),
            MESS_P_kw=tr.mess_p_kw[slot].tolist(), MESS_Q_kvar=tr.mess_q_kvar[slot].tolist(),
            MESS_locations=list(map(str, tr.mess_locations_96x4[slot])), allocation=allocation))
    def routed_read(path):
        value = read(path)
        if Path(path) == Path(request['input_folder']) / 'OPERATIONS.json':
            value = dict(value, current_day_folder=str(source_folder))
        return value
    expected = _identity(request)
    namespace = dict(vars(replay), read=routed_read, require_action_authorized=authorize,
        identity=lambda *args: expected, _campaign_trajectory=trajectory,
        _campaign_apply=apply_mapping, _campaign_applied=applied,
        _campaign_mess_zero=bool(np.all(mess['P_kw'] == 0) and np.all(mess['Q_kvar'] == 0)))
    namespace['build_day'] = rebound(replay.build_day, namespace)
    from v42_regcontrol import authority
    from unittest.mock import patch
    compilations = []
    original_compile = authority.compile_verified
    with patch.object(authority, 'compile_verified', lambda: isolated_compile(original_compile, output, compilations)):
        result = _fresh_port(replay.fresh, namespace)(InputDirectory(request['day'], request['input_folder']),
            request['day'], planning, actual_folder, output, {}, progress)
    atomic(output / 'OPENDSS_PROCESS_CONTEXT_ISOLATION.json', dict(PASS=True,
        arm=request['arm'], day=request['day'], PID=os.getpid(), compilations=compilations,
        scope='One independent Worker process and date; original NewContext compiler',
        common_output_writes=0, original_backend_body_unchanged=True))
    if (opendss_backend.run_fresh_opendss.__code__ is not original_backend_code
            or sha(before['path']) != before['sha256']):
        raise ValueError('FRESH_ORIGINAL_BODY_OR_FROZEN_MESS_MUTATION')
    receipt = read(output / 'FRESH_RESULT.json')
    controls = read(output / 'RAW_CONTROL_LOG.json')['slots']
    inputs = read(output / 'RAW_PHYSICAL_INPUT_LOG.json')['slots']
    # A new source epoch may explicitly add native capacitor controllers. The
    # admitted scope independently checks their exact equipment/settings; the
    # original fixed-on path still requires zero controllers.
    from v42_voltage_control.integration import current_declared_capcontrol_count
    expected_capcontrols = current_declared_capcontrol_count()
    passed = (_summary_pass(result['summary'], result['converged'])
        and receipt['checker_SHA'] == replay.CHECKER and receipt['NormalAmps_current'] is True
        and receipt['Planning_tap_replay'] is False and receipt['Actual_reoptimization'] == 0
        and receipt['local_PQ_repair'] == 0 and receipt['global_PQ_repair'] == 0
        and len(controls) == len(inputs) == 96
        and all(row['all_7_RegControls_enabled'] is True and row['CapControl_count'] == expected_capcontrols
                and row['Planning_tap_replay'] is False for row in controls))
    result.update(PASS=bool(passed), receipt=record(output / 'FRESH_RESULT.json'),
        control_log=record(output / 'RAW_CONTROL_LOG.json'), physical_input_log=record(output / 'RAW_PHYSICAL_INPUT_LOG.json'),
        original_backend_body_unchanged=True, transformer_all_phases_NormalAmps=True,
        physical_violations_are_results=True, physical_violation=result['summary']['physical_violation'])
    return result


def run(request, stage_result, progress=None):
    request = dict(request)
    output = d_path(Path(request['output']) / 'OPERATIONS')
    if output.exists():
        raise PermissionError('OPERATIONS_COMPLETED_OR_PARTIAL_ATTEMPT_NEVER_REUSED')
    folders = {name: output / name for name in ('SOURCE', 'PLANNING', 'ACTUAL', 'ACTUAL_SOURCE', 'FRESH')}
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=False)
    _notify(progress, 'PLANNING_FIXED_DECISION_FREEZE', request)
    accepted, planning_arrays, mess = _accepted(request, stage_result, folders['SOURCE'])
    planning = freeze_planning(request, accepted, mess, folders['PLANNING'])
    freeze = record(folders['PLANNING'] / 'V42_DAYAHEAD_DECISION_FREEZE.json')
    _notify(progress, 'ACTUAL_FIXED_DECISION_MATERIALIZATION', request)
    actual_result = actual(request, folders['PLANNING'], folders['SOURCE'], folders['ACTUAL'])
    _notify(progress, 'ACTUAL_SOURCE_MATERIALIZATION', request)
    actual_source = actual_sources(request, folders['ACTUAL_SOURCE'])
    _notify(progress, 'FRESH_OPENDSS_ORIGINAL_96_SLOT_REPLAY', request)
    fresh_result = fresh(request, folders['PLANNING'], folders['ACTUAL'], actual_source, folders['FRESH'], progress)
    if sha(freeze['path']) != freeze['sha256']:
        raise ValueError('PLANNING_FREEZE_CHANGED_DURING_ACTUAL_FRESH')
    from v42_pr134_b1.common import CODE
    sources = [ROOT / 'v42_pr134_b1/replay.py', ROOT / 'v42_holdout/realization.py',
        ROOT / 'v42_regcontrol/authority.py', ROOT / 'v42_regcontrol/runner.py', ROOT / 'v42_thermal/authority.py',
        CODE / 'dayahead/v28r2/opendss_backend.py', CODE / 'dayahead/v28r2/opendss_mapping.py',
        CODE / 'dayahead/v28r2/trajectory.py', Path(__file__)]
    receipt = dict(PASS=fresh_result['PASS'], classification='PASS' if fresh_result['PASS'] else 'FRESH_AC_FAILURE',
        day=request['day'], arm=request['arm'], folder=str(output), Planning=planning, Actual=actual_result,
        Fresh=fresh_result, summary=fresh_result['summary'], Planning_freeze=freeze,
        Actual_receipt=record(folders['ACTUAL'] / 'ACTUAL_FIXED_REPLAY_RECEIPT.json'),
        Actual_source=record(folders['ACTUAL_SOURCE'] / 'ACTUAL_SOURCE_RECEIPT.json'),
        reviewer_source_SHA=[record(path) for path in sources], P2_calls=0, Native_calls=0,
        Actual_reoptimization=0, AIDC_optimizer_calls=0, MESS_optimizer_calls=0,
        local_PQ_repair=0, global_PQ_repair=0, historical_four_objective_gate_unchanged=True,
        original_96_slot_backend_body_unchanged=True, MESS_mapping_original=True,
        physical_violations_are_results=True, physical_violation=fresh_result['summary']['physical_violation'],
        all_MESS_PQ_zero=bool(np.all(mess['P_kw'] == 0) and np.all(mess['Q_kvar'] == 0)))
    atomic(output / 'OPERATIONS_RESULT.json', receipt)
    return receipt
