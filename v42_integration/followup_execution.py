"""Same-case admission of saved A1/A2 commands into current-event Actual.

The existing A1 -> M1 -> A2 -> M2 coordinator supplies the final saved A
result. This entry point executes it without calling any planning optimizer.
Historical diagnostic FCFS and an uncertified initial boundary cannot enter.
"""
from copy import deepcopy
from pathlib import Path

import numpy as np

from .followup_contract import require_planning_actual_handoff, same_case, require_initial_state_alignment
from .m_engine import _write
from .unified_contract import digest


def run_saved_planning_current_actual(arguments, *, a_result, planning_identity,
        actual_identity, observed_state, planning_slot_zero_seconds, frozen_policy,
        resource_bridge, expected_bindings, output):
    from .aidc_sensitivity_runtime import CurrentEventSensitivityPolicy, run_current_event_actual
    if not isinstance(frozen_policy, CurrentEventSensitivityPolicy):
        raise ValueError('FOLLOWUP_CURRENT_EVENT_POLICY_REQUIRED')
    args = dict(arguments)
    output = Path(output)
    commands = deepcopy(args.get('known_schedule', {}))
    handoff = require_planning_actual_handoff(a_result, planning_identity, actual_identity,
        commands, observed_state, begin_seconds=args['begin'],
        planning_slot_zero_seconds=planning_slot_zero_seconds)
    handoff['actual_initial_state_join']=require_initial_state_alignment(observed_state,args,
        actual_identity,evidence_scope=frozen_policy.evidence_scope)
    same_case(resource_bridge.identity, actual_identity)
    declared = frozen_policy.spec.get('source_identity', {}).get('planning_identity', {})
    same_case(declared, actual_identity)
    if (resource_bridge.begin != args['begin'] or
            set(resource_bridge.sites) != set(args['capacities']) or
            resource_bridge.source_sha != digest(a_result)):
        raise ValueError('FOLLOWUP_ACTUAL_RESOURCE_BRIDGE_DRIFT')
    if digest(frozen_policy.reference.commands) != digest(commands):
        raise ValueError('FOLLOWUP_POLICY_PLANNING_COMMAND_DRIFT')
    sites = tuple(resource_bridge.sites)
    reference = frozen_policy.reference
    if reference.sites != sites or reference.begin != args['begin']:
        raise ValueError('FOLLOWUP_ACTUAL_TIME_SITE_AXIS_DRIFT')
    for key, field in (('G_Known_Plan', 'known_site_GPU'), ('G_Unknown_Q50_Plan', 'nominal_site_GPU')):
        if not np.array_equal(reference.arrays[key], resource_bridge.matrices[field]):
            raise ValueError('FOLLOWUP_POLICY_PLANNING_RESOURCE_MATRIX_DRIFT:' + key)
    _write(output / 'KNOWN_PLANNING_ACTUAL_HANDOFF.json', handoff)
    _write(output / 'PLANNING_COMMAND.json', commands)
    result = run_current_event_actual(args, frozen_policy=frozen_policy,
        resource_bridge=resource_bridge, expected_bindings=expected_bindings, handoff_gate=handoff)
    if (result['receipt']['actual_global_reoptimization'] != 0 or
            digest(commands) != handoff['planning_commands_sha']):
        raise ValueError('FOLLOWUP_ACTUAL_GLOBAL_SOLVE_OR_PLANNING_MUTATION')
    state = result['carryout']['controller']['current_event_state']
    _write(output / 'ACTUAL_CORRECTIVE_COMMAND.json', state['actual_corrective_commands'])
    _write(output / 'AIDC_PLANNING_ACTUAL_RESOURCE_BRIDGE.json', resource_bridge.export())
    _write(output / 'ACTUAL_RESULT.json', result)
    return result
