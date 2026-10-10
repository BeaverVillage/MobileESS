"""Freeze selected existing series hardware by independent unsolved Fresh readback.

No trajectory solve or optimizer is admitted. Original compile voltage-base
zero-load initialization is explicitly separate from runtime SolveSnap calls.
Existing source/tests and completed experiments are never modified.
"""
import argparse
from contextlib import ExitStack
import copy
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
from pathlib import Path
import shutil
import sys
from unittest.mock import patch


def record(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def dump(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--predecessor-receipt', type=Path)
    args = parser.parse_args()
    source, input_path, output = args.source.resolve(), args.input.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(source))
    from v42_b3_joint.contracts import canonical, digest
    from v42_voltage_control import authority as newauthority, integration, svr, timecontrol
    from v42_regcontrol import authority as original
    from v42_may_campaign_native90.preflight import native_zero
    import opendssdirect as dss

    sources_before = newauthority.source_files()
    source_sha = digest(sources_before)
    old = json.loads(input_path.read_text(encoding='utf8'))
    integration.validate_scenario(old)
    assert old['case'] == 'B' and old['time_mode'] == 'TIME' and old['capcontrol'] is None
    assert [u['id'] for u in old['svr']['units']] == ['STA01', 'STA06', 'STA08', 'BUS83']
    selected_units_identity = canonical(old['svr']['units'])
    predecessor = None
    predecessor_state_physical_sha = None
    if args.predecessor_receipt:
        predecessor = json.loads(args.predecessor_receipt.read_text(encoding='utf8'))
        assert predecessor['PASS'] is True
        assert predecessor['status'] == 'FROZEN_HARDWARE_ONLY_NOT_E2E_QUALIFIED'
        prior_scenario_row = predecessor['scenario']
        assert record(prior_scenario_row['path']) == prior_scenario_row
        prior_scenario = json.loads(Path(prior_scenario_row['path']).read_text(encoding='utf8'))
        assert canonical(prior_scenario['svr']['units']) == selected_units_identity
        old_manifest_path = Path(args.predecessor_receipt).parent/'EXECUTION_SOURCE_MANIFEST.json'
        prior_sources = json.loads(old_manifest_path.read_text(encoding='utf8'))['execution_sources']
        component_names = ('v42_voltage_control/svr.py', 'v42_voltage_control/timecontrol.py',
                           'v42_voltage_control/capcontrol.py', 'v42_regcontrol/authority.py',
                           'v42_regcontrol/common.py', 'v42_b3_joint/contracts.py')
        assert all(prior_sources[name] == sources_before[name] for name in component_names)
        prior_initial_row = predecessor['independent_namespaces'][0]['initial_state_receipt']
        assert record(prior_initial_row['path']) == prior_initial_row
        prior_initial = json.loads(Path(prior_initial_row['path']).read_text(encoding='utf8'))['initial_state']
        prior_initial.pop('source_SHA')
        predecessor_state_physical_sha = digest(prior_initial)
    assert old['svr']['status'] == 'DEVELOPMENT_NOT_FROZEN_NOT_CANARY'
    frozen = copy.deepcopy(old)
    frozen['svr']['status'] = 'FROZEN'
    frozen['scenario_SHA'] = digest(integration.scenario_identity(frozen))
    integration.validate_scenario(frozen)
    assert canonical(frozen['svr']['units']) == selected_units_identity
    expected_old = copy.deepcopy(frozen)
    expected_old['svr']['status'] = old['svr']['status']
    expected_old['scenario_SHA'] = old['scenario_SHA']
    assert canonical(expected_old) == canonical(old)
    assert frozen['scenario_SHA'] != old['scenario_SHA']
    dump(output/'SCENARIO.json', frozen)
    dump(output/'SVR_CONTROLLER_CONTRACT.json', frozen['svr'])
    shutil.copyfile(input_path, output/'ORIGINAL_DEVELOPMENT_SCENARIO.json')
    assert record(input_path)['sha256'] == record(output/'ORIGINAL_DEVELOPMENT_SCENARIO.json')['sha256']

    original_source = original.source()
    external_rows = original_source['audit']['static_source_graph']['files'] + original_source['audit']['code_read']
    external_paths = {str(original.resolve(row)): original.resolve(row) for row in external_rows}
    external_paths[str(Path(inspect.getfile(original_source['inventory'])).resolve())] = Path(inspect.getfile(original_source['inventory'])).resolve()
    external_paths[str(Path(inspect.getfile(original_source['compile'])).resolve())] = Path(inspect.getfile(original_source['compile'])).resolve()
    external_rows_resolved = [record(p) for p in external_paths.values()]
    source_archive = newauthority.archive_source(output/'SOURCE_EPOCH', source_SHA=source_sha,
                                               external_receipts=external_rows_resolved)
    dump(output/'EXECUTION_SOURCE_MANIFEST.json', dict(source_SHA=source_sha,
        execution_sources=sources_before, source_archive_receipt=source_archive))
    shutil.copyfile(__file__, output/'FREEZE_SCRIPT_USED.py')
    assert record(__file__)['sha256'] == record(output/'FREEZE_SCRIPT_USED.py')['sha256']

    denied_runtime_calls = []
    commands = []
    original_setter_attempts = []
    solution_type = type(dss.Solution)
    text_type = type(dss.Text)
    original_text_command = text_type.Command
    transformer_type = type(dss.Transformers)
    original_tap = transformer_type.Tap
    capacitor_type = type(dss.Capacitors)
    original_states = capacitor_type.States

    def no_runtime_solve(*a, **k):
        denied_runtime_calls.append('runtime physical solve attempted')
        raise PermissionError('HARDWARE_FREEZE_NO_RUNTIME_SOLVE')

    def tap_read_only(instance, *a):
        if a:
            original_setter_attempts.append('Transformer.Tap setter')
            raise PermissionError('HARDWARE_FREEZE_NO_TAP_SETTER')
        return original_tap(instance)

    def states_read_only(instance, *a):
        if a:
            original_setter_attempts.append('Capacitor.States setter')
            raise PermissionError('HARDWARE_FREEZE_NO_CAP_STATE_SETTER')
        return original_states(instance)

    def logged_command(instance, *a):
        if a:
            command = str(a[0])
            commands.append(command)
            first = command.strip().lower()
            forbidden = ('solve', 'solvenocontrol', 'solvedirect', 'solvesnap',
                         'sample', 'docontrolactions', 'disable', 'enable')
            if first.split(maxsplit=1)[0] in forbidden:
                raise PermissionError('HARDWARE_FREEZE_UNAUTHORIZED_RUNTIME_COMMAND:'+command)
            if first.startswith('edit regcontrol.creg') or ('controlmode=off' in first):
                original_setter_attempts.append(command)
                raise PermissionError('HARDWARE_FREEZE_ORIGINAL_CONTROL_EDIT_FORBIDDEN')
        return original_text_command(instance, *a)

    namespace_rows = []
    identities = []
    physical_identities = []
    engines = []
    with native_zero() as native_attempts, ExitStack() as stack:
        for method in ('Solve', 'SolveSnap', 'SolveDirect', 'SolveNoControl', 'SolvePlusControl',
                       'SampleControlDevices', 'DoControlActions'):
            if hasattr(solution_type, method):
                stack.enter_context(patch.object(solution_type, method, no_runtime_solve))
        stack.enter_context(patch.object(text_type, 'Command', logged_command))
        stack.enter_context(patch.object(transformer_type, 'Tap', tap_read_only))
        stack.enter_context(patch.object(capacitor_type, 'States', states_read_only))
        try:
            for namespace in ('DAYAHEAD', 'ACTUAL'):
                e, adapter, initial = original.compile_verified()
                engines.append(e)
                assert initial == original_source['expected']
                assert [r['initial_tap'] for r in initial['regulators']] == [1.0]*7
                assert [r['states'] for r in initial['capacitors']] == [[1]]*4
                before_equipment = integration._equipment(e)
                before_nodes = list(map(str, e.Circuit.AllNodeNames()))
                clock = timecontrol.CommonClock(namespace, '2025-05-01')
                clock_initial = clock.bind(e)
                bank = svr.install(e, frozen['svr'])
                installed = original_source['inventory'](e)
                integration.assert_control_inventory(installed, frozen, initial=True)
                after_equipment = integration._equipment(e)
                for name, row in before_equipment.items():
                    after = copy.deepcopy(after_equipment[name])
                    expected = copy.deepcopy(row)
                    unit = next((u for u in frozen['svr']['units'] if u['cut_element'].lower() == name), None)
                    if unit is not None:
                        expected['buses'][unit['cut_terminal']-1] = unit['upstream_new_bus']+'.1.2.3'
                    assert after == expected, ('ORIGINAL_EQUIPMENT_DRIFT', name)
                new_taps = {}
                for name in bank.installation_receipt['added_transformer_names']:
                    e.Transformers.Name(name)
                    taps = []
                    for w in (1,2):
                        e.Transformers.Wdg(w)
                        taps.append(float(e.Transformers.Tap()))
                    assert taps == [1.0,1.0]
                    new_taps[name] = taps
                assert len(new_taps) == 12
                assert len(bank.installation_receipt['added_RegControl_names']) == 12
                assert installed['RegControl_count'] == 19 and installed['CapControl_count'] == 0
                assert e.Solution.Hour() == 0 and e.Solution.Seconds() == 0
                assert int(e.Solution.ControlMode()) == 2 and int(e.Solution.Mode()) == 0
                assert timecontrol.queue(e) == []
                assert e.CtrlQueue.QueueSize() == 0
                assert int(e.Solution.MaxControlIterations()) == 100 and int(e.Solution.MaxIterations()) == 15
                retired = integration._retired_inventory(e)
                assert retired['retired_objects_count'] == 0
                original_names = {r['name'] for r in initial['regulators']}
                original_regs = [r for r in installed['regulators'] if r['name'] in original_names]
                assert integration.original_parameters(dict(regulators=original_regs)) == integration.original_parameters(initial)
                assert [r['initial_tap'] for r in original_regs] == [1.0]*7
                assert installed['capacitors'] == initial['capacitors']
                buses = []
                for u in frozen['svr']['units']:
                    e.Circuit.SetActiveBus(u['upstream_new_bus'])
                    buses.append(dict(name=u['upstream_new_bus'], nodes=list(map(int,e.Bus.Nodes())),
                                      kVBase=float(e.Bus.kVBase())))
                    assert set(e.Bus.Nodes()) == {1,2,3}
                    assert math.isclose(e.Bus.kVBase(),u['nominal_kv_ln'],abs_tol=1e-7)
                    assert all(math.isfinite(float(u[k])) and float(u[k])>0 for k in
                               ('phase_kva','nominal_kv_ln','sensed_kv_ln','xhl_pct','winding_r_pct','delay_seconds','tap_delay_seconds'))
                init_doc = dict(schema='V42_SVR4_NATIVE_COMPILED_SOURCE_INITIAL_STATE_V1',
                    scenario_SHA=frozen['scenario_SHA'], source_SHA=source_sha,
                    original_initial_inventory=initial, installed_inventory=installed,
                    source_equipment_before=before_equipment, installed_equipment_after=after_equipment,
                    original_node_names=before_nodes, installed_node_names=list(map(str,e.Circuit.AllNodeNames())),
                    installation_receipt=bank.installation_receipt,
                    new_SVR_initial_winding_taps=new_taps, added_bus_readback=buses,
                    retired_inventory=retired,
                    native_clock=dict(Hour=int(e.Solution.Hour()), Seconds=float(e.Solution.Seconds()),
                        control_mode=int(e.Solution.ControlMode()), solution_mode=int(e.Solution.Mode()),
                        maxcontroliter=int(e.Solution.MaxControlIterations()), maxiter=int(e.Solution.MaxIterations()),
                        queue=timecontrol.queue(e), queue_size=int(e.CtrlQueue.QueueSize())),
                    injection_adapter=adapter)
                identity = digest(init_doc)
                physical_init_doc = copy.deepcopy(init_doc)
                physical_init_doc.pop('source_SHA')
                physical_identity = digest(physical_init_doc)
                if predecessor_state_physical_sha is not None:
                    assert physical_identity == predecessor_state_physical_sha
                path = output/(namespace+'_SOURCE_INITIAL_STATE.json')
                dump(path, dict(namespace=namespace, day_label='2025-05-01',
                    initial_state_SHA=identity, initial_state=init_doc,
                    clock_bind_receipt=clock_initial,
                    runtime_physical_solve_count=0, physical_voltage_current_qualification=None))
                identities.append(identity)
                physical_identities.append(physical_identity)
                namespace_rows.append(dict(namespace=namespace, day_label='2025-05-01',
                    independently_compiled=True, initial_state_SHA=identity, initial_state_receipt=record(path),
                    clock_is_independent=True, native_queue_initial_empty=True,
                    original7_initial_taps=[1.0]*7, new12_initial_winding_taps_all1=True,
                    Cap4_fixed_ON=True, native_TIME_at_zero=True, RegControl_count=19, CapControl_count=0))
            assert engines[0] is not engines[1]
            assert identities[0] == identities[1]
            assert physical_identities[0] == physical_identities[1]
            assert not native_attempts and not denied_runtime_calls and not original_setter_attempts
        finally:
            for e in engines:
                e.Basic.ClearAll()

    assert newauthority.source_files() == sources_before
    assert all(record(r['path']) == r for r in external_rows_resolved)
    assert canonical(json.loads(input_path.read_text(encoding='utf8'))['svr']['units']) == selected_units_identity
    dump(output/'COMMAND_AND_GUARD_RECEIPT.json', dict(commands=commands,
        direct_CalcVoltageBases_commands=sum(c.strip().lower()=='calcvoltagebases' for c in commands),
        runtime_solve_or_control_action_attempts=denied_runtime_calls,
        original_tap_or_cap_state_setter_attempts=original_setter_attempts,
        Native_optimizer_attempts=native_attempts,
        native_internal_compile_initialization_note='Original compile CalcVoltageBases invokes CAPI SetVoltageBases -> SolveZeroLoadSnapShot. Native initialization is retained. Runtime Solve/SolveSnap/control trials are zero; no claim that every native electrical initialization is zero.',
        fresh_context_count=2, no_trajectory_slots_run=True))
    value = dict(schema='V42_SVR4_HARDWARE_FREEZE_RECEIPT_V1',
        status='FROZEN_HARDWARE_ONLY_NOT_E2E_QUALIFIED', PASS=True,
        frozen_at_UTC=datetime.now(timezone.utc).isoformat(),
        execution_SourceSHA_before=source_sha, execution_SourceSHA_after=digest(newauthority.source_files()),
        SourceCode_before_after_equal=True, source_archive_receipt=source_archive,
        scenario=record(output/'SCENARIO.json'), scenario_SHA=frozen['scenario_SHA'],
        controller_contract=record(output/'SVR_CONTROLLER_CONTRACT.json'),
        predecessor_development_scenario=record(input_path), predecessor_scenario_SHA=old['scenario_SHA'],
        original_development_scenario_copy=record(output/'ORIGINAL_DEVELOPMENT_SCENARIO.json'),
        selected_units_canonical_SHA_before=digest(old['svr']['units']),
        selected_units_canonical_SHA_after=digest(frozen['svr']['units']),
        only_scenario_metadata_change='svr.status DEVELOPMENT_NOT_FROZEN_NOT_CANARY -> FROZEN; recomputed scenario_SHA',
        selected_bank_ids=['STA01','STA06','STA08','BUS83'], three_phase_bank_count=4,
        additional_single_phase_transformer_count=12, additional_RegControl_count=12,
        original_RegControl_count=7, CapControl_count=0, Cap4_fixed_ON_total_nameplate_kvar=750,
        phase_nameplate_kVA_by_bank={u['id']:u['phase_kva'] for u in frozen['svr']['units']},
        bank_nameplate_kVA_by_bank={u['id']:3*u['phase_kva'] for u in frozen['svr']['units']},
        hardware_and_control_law_changes_from_selected_development_units=0,
        original_equipment_rating_changes=0, original_RegControl_settings_changes=0,
        original_RegControl_tap_setters=0, original_Capacitor_state_setters=0,
        Native_optimizer_calls=0, runtime_physical_solve_count=0, replay_logical_slots=0,
        original_native_compile_voltage_base_initialization_retained=True,
        initialization_guard_receipt=record(output/'COMMAND_AND_GUARD_RECEIPT.json'),
        source_initial_state_SHA=identities[0], independent_namespaces=namespace_rows,
        physical_source_initial_state_SHA_excluding_execution_source_SHA=physical_identities[0],
        predecessor_hardware_freeze_receipt=None if predecessor is None else record(args.predecessor_receipt),
        predecessor_same_physical_initial_state=None if predecessor is None else physical_identities[0] == predecessor_state_physical_sha,
        predecessor_same_physical_hardware_component_sources=None if predecessor is None else True,
        Planning_Actual_independent_Source_Initial_State=True,
        across_days_start_from_common_initial_state=True,
        existing_original_band_pu=[.95,1.05], Planning_band_pu=[.95,1.05], Actual_band_pu=[.95,1.05],
        manufacturer_proof='UNKNOWN',
        engineering_assumptions={u['id']:u['engineering_assumptions'] for u in frozen['svr']['units']},
        full_network_physical_PASS=None, new_model_regenerated=False,
        optimized_Planning_Actual_E2E_qualified=False, all31May_qualified=False,
        previous_diagnostic_results_are_for_previous_scenario_SHA=True,
        new_frozen_scenario_source_matched_96_reverification_required=True,
        expectation='Each DAYAHEAD/ACTUAL and each May day compiles fresh common source initial state; only chronological within-day native state carries. No Planning/Actual state or queues copied.',
        source_and_tests_modified=0, external_original_source_receipts=external_rows_resolved,
        freeze_script=record(__file__), freeze_script_used_copy=record(output/'FREEZE_SCRIPT_USED.py'))
    assert value['execution_SourceSHA_before']==value['execution_SourceSHA_after']
    assert value['selected_units_canonical_SHA_before']==value['selected_units_canonical_SHA_after']
    dump(output/'HARDWARE_FREEZE_RECEIPT.json',value)
    print(json.dumps({k:value[k] for k in ('PASS','status','scenario_SHA','execution_SourceSHA_before',
        'source_initial_state_SHA','selected_bank_ids','runtime_physical_solve_count','Native_optimizer_calls')},indent=2))


if __name__ == '__main__':
    main()
