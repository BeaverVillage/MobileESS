"""Native0 E0..E3 original CommonClock causal voltage audit; no repairs."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration.rc02_voltage_audit import (SCOPE, write_new, replay,
    episode_roster, experiment_inputs)
from v42_integration.actual_validation import read, record, _power_model, _validated_hardware_context
from v42_integration.isolated_unknown import INITIAL, BASE, RAW, no_native
from v42_integration.unified_contract import digest

RC01 = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
DEFAULT = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/VOLTAGE/ASOF_E0_E3_01'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT)
    options = parser.parse_args()
    output = options.output
    output.mkdir(parents=True, exist_ok=True)
    if (output/'EXECUTED_VOLTAGE_AUDIT_SOURCE.json').exists():
        raise FileExistsError('RC02_EXECUTED_ATTEMPT_IMMUTABLE')
    began = perf_counter()
    code = [ROOT/'v42_integration/rc02_voltage_audit.py', Path(__file__).resolve(),
            ROOT/'v42_voltage_control/timecontrol.py', ROOT/'v42_voltage_control/integration.py',
            ROOT/'v42_voltage_control/svr.py', ROOT/'v42_integration/actual_validation.py']
    frozen = read(RC01/'EXECUTED_SOURCE.json')['files']
    for receipt in frozen:
        if record(receipt['path']) != receipt:
            raise ValueError('RC02_RC01_EXECUTED_SOURCE_BYTES_CHANGED')
    source_before = [record(path) for path in code]
    write_new(output/'EXECUTED_VOLTAGE_AUDIT_SOURCE.json', dict(scope=SCOPE, code=source_before,
        frozen_RC01_Source7=frozen, Native_calls=0, prior_RC01_changed=False,
        physics_repair=False, voltage_limits=[.95,1.05], P2_calls=0))
    prefix = read(RC01/'C0/PUBLIC_PREFIX_ORIGINAL_C1.json')
    c1_prefix = read(RC01/'C1/PUBLIC_PREFIX_ORIGINAL_C1.json')
    initial = read(INITIAL)
    begin, end = prefix[0]['start_seconds'], prefix[-1]['end_seconds']
    sites = tuple(f'AIDC{j+1:02d}' for j in range(12))
    mess = read(BASE/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    common = read(RC01/'COMMON_RUN_INPUTS.json')
    if (mess['plan_sha'] != common['MESS_plan_sha'] or
            digest({k:v for k,v in mess.items() if k!='plan_sha'}) != mess['plan_sha']):
        raise ValueError('RC02_FIXED_M2_PLAN_DRIFT')
    queues = {label:read(RC01/label/'QUEUE_LEDGER.json') for label in ('C0','C1')}
    starts = {label:read(RC01/label/'ACTUAL_START_LEDGER.json') for label in ('C0','C1')}
    if any(r['site'] != r['basic_site'] for r in starts['C1'] if r['origin_unknown']):
        raise ValueError('RC02_EXPECTED_ZERO_ACTUAL_PRESITE_NOT_TRUE')
    for key in ('GPU','P','Q'):
        np.testing.assert_array_equal([r[key] for r in prefix], [r[key] for r in c1_prefix])
    rosters = {label:episode_roster(initial, queues['C1' if label=='E3' else 'C0'],
        starts['C1' if label=='E3' else 'C0'], label=label, begin=begin, end=end)
        for label in ('E0','E1','E2','E3')}
    if len(rosters['E0']) != 324 or sum(r['GPU'] for r in rosters['E0']) != 472:
        raise ValueError('RC02_INITIAL_RUNNING_COUNTS_DRIFT')
    freeze = read(BASE/'PLANNING_FREEZE.json')['source_freeze']
    manifest = read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    results = {}
    with no_native() as attempts, _validated_hardware_context(freeze,manifest) as scenario:
        model, power_receipts = _power_model(read(RAW/'POWER_AUTHORITY.json'),
                                             read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')['capacities'])
        if model.authority_sha != common['Original_C1_SHA']:
            raise ValueError('RC02_ORIGINAL_C1_AUTHORITY_DRIFT')
        inputs = {label:experiment_inputs(rosters[label], prefix, sites, model) for label in rosters}
        for key in ('GPU','P','Q'):
            np.testing.assert_allclose([r[key] for r in inputs['E2']], [r[key] for r in prefix], rtol=0,atol=1e-9)
            np.testing.assert_array_equal([r[key] for r in inputs['E2']], [r[key] for r in inputs['E3']])
            # The independent UID integral/C1 proof above can differ at roundoff
            # from the original insertion order. Replay the original literal
            # arrays for the requested byte-identical E2/E3 physical comparison.
            for label in ('E2','E3'):
                for t in range(len(prefix)):
                    inputs[label][t][key]=prefix[t][key]
        for label in ('E2','E0','E1','E3'):
            write_new(output/f'{label}_OBSERVED_EPISODE_ROSTER.json', rosters[label])
            write_new(output/f'{label}_ORIGINAL_C1_INPUTS.json', inputs[label])
        write_new(output/'COMMON_INPUTS.json', dict(scope=SCOPE,
            initial=record(INITIAL), initial_semantic_sha=initial['common_initial_state_sha'],
            begin_seconds=begin,end_seconds=end,MESS=record(BASE/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json'),
            MESS_plan_sha=mess['plan_sha'],Original_C1_SHA=model.authority_sha,power_sources=power_receipts,
            RC01_common=record(RC01/'COMMON_RUN_INPUTS.json'),
            episode_sources=[record(RC01/label/name) for label in ('C0','C1')
                             for name in ('QUEUE_LEDGER.json','ACTUAL_START_LEDGER.json','PUBLIC_PREFIX_ORIGINAL_C1.json')],
            E0_initial_Running_only=len(rosters['E0']), E1_added_Known=len(rosters['E1'])-len(rosters['E0']),
            E2_added_basic_Unknown=len(rosters['E2'])-len(rosters['E1']), E3_actual_presite_changes=0,
            retrospective_removal_not_rescheduling=True,
            no_public_or_private_future_values_used_for_new_planning=True,
            existing_observed_completion_used_only_for_retrospective_interval_integral=True))
        for label in ('E2','E0','E1','E3'):
            print('RC02_BEGIN', label, flush=True)
            results[label] = replay(inputs[label], mess, label=label, scenario=scenario, output=output)
            print('RC02_END', label, results[label]['voltage_min_pu'],results[label]['voltage_max_pu'],
                  results[label]['voltage_violation_cells'],flush=True)
    for receipt in frozen + source_before:
        if record(receipt['path']) != receipt:
            raise ValueError('RC02_SOURCE_BYTES_CHANGED_DURING_EXECUTION')
    old = read(RC01/'ASOF_PREFIX_ALL_SUBSTEP_RAW.json')
    new = read(output/'E2_STEP_INDEX.json')
    comparison = dict(same_time_axis=len(old)==len(new),same_physical=True,same_SVR=True)
    if len(old) != len(new):
        raise ValueError('RC02_RC01_E2_SUBSTEP_COUNT_DRIFT')
    for a,b in zip(old,new):
        comparison['same_time_axis'] &= (a['slot'],a['native_seconds'])==(b['slot'],b['native_seconds'])
        comparison['same_physical'] &= a['physical_sha']==b['physical_sha']
        comparison['same_SVR'] &= a['SVR_sha']==b['SVR_sha']
    write_new(output/'RC01_E2_SAME_INPUT_PHYSICAL_SVR_EQUIVALENCE.json', dict(
        status='PASS' if all(comparison.values()) else 'NOT_CERTIFIED', **comparison,
        RC01_original_proof=record(RC01/'ASOF_PREFIX_ALL_SUBSTEP_RAW.json'),
        RC02_index=record(output/'E2_STEP_INDEX.json'),voltage_limits_changed=False))
    finish = dict(scope=SCOPE,status='PHYSICAL_FAIL' if any(r['violating_substeps'] for r in results.values()) else 'PASS_DIAGNOSTIC_SCOPE',
        E0_E1_E2_E3=results,physical_cause_not_internal_iterations=True,
        RC01_same_input_equivalence=comparison,Source7_byte_immutable=True,
        Original_controls_MESS_limits_unchanged=True,Native_calls=0,blocked_native_attempts=attempts,
        P2_calls=0,total_wall_seconds=perf_counter()-began,
        new_production_D0_or_Full96_or_campaign_certificate=False)
    write_new(output/'E0_E1_E2_E3_DIAGNOSIS.json', finish)
    print(json.dumps({k:v for k,v in finish.items() if k!='E0_E1_E2_E3'},indent=2),flush=True)


if __name__ == '__main__':
    main()
