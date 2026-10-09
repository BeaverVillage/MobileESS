"""P1-only A1 -> M1 contract. P2 is neither executed nor certified here."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import json
import numpy as np
from v42_native.contracts import digest, require
from v42_may12_rescue.contract import decide
from .storage import sha

SCHEMA = 'V42_A1_P1_ONLY_TO_M1_V1'


def build_handoff(freeze, certificates, identity, control_names, *, replay, source_hash):
    require(freeze.get('PASS') is True and freeze.get('state') == 'A1_P1_ONLY_ACCEPTED', 'P1_ONLY_FREEZE_REQUIRED')
    require(freeze.get('A1_ACCEPTED') is False, 'P1_ONLY_MUST_NOT_CLAIM_FOUR_OBJECTIVE_ACCEPTANCE')
    decision = decide(*(certificates[k] for k in ('zero', 'closure', 'bound', 'integer', 'physical')))
    require(decision['A1_P1_ONLY_ACCEPTED'] is True, 'INDEPENDENT_P1_CERTIFICATES_REQUIRED')
    require(identity.get('PASS') is True and replay.get('PASS') is True, 'INPUT_AND_PHYSICAL_REPLAY_REQUIRED')
    require(identity['day'] == freeze['day'], 'A1_FROZEN_INPUT_DAY_MISMATCH')
    require(replay['selected_jobs_match_saved_schedule'] is True, 'SELECTED_SCHEDULE_IDENTITY_REQUIRED')
    require(replay['controls_match_saved'] is True, 'CONTROL_FOOTPRINT_IDENTITY_REQUIRED')
    require(replay['exact_UB'] == decision['exact_UB'], 'ORIGINAL_RHO_IDENTITY_REQUIRED')
    controls = np.asarray(freeze['controls'], dtype=float)
    require(controls.ndim == 2 and controls.shape == (96, len(control_names)) and np.isfinite(controls).all(), 'FROZEN_CONTROL_AXIS')
    require(len(set(control_names)) == len(control_names), 'DUPLICATE_CONTROL_AXIS')
    fixed = [i for i, n in enumerate(control_names) if n.startswith('aidc_load_kw[')]
    require(len(fixed) == 12 and all(n.startswith(('aidc_load_kw[', 'mess_p_kw[', 'mess_q_kvar[')) and n.endswith(']')
                                  for n in control_names), 'UNRECOGNIZED_CONTROL_AXIS')
    input_hashes = {r['axis']: r['expected']['sha256'] for r in identity['files']}
    arrays = identity['original_grid_array_identities']
    jobs = deepcopy(freeze['selected_jobs'])
    require(len(jobs) == replay['original_population'], 'ORIGINAL_JOB_POPULATION_MISMATCH')
    anchor = dict(source_stage='A1', day=freeze['day'], control_names=list(control_names),
                  controls=controls.tolist(), fixed_AIDC_control_columns=fixed,
                  A1_P1_ONLY_ACCEPTED=True, A1_ACCEPTED=False,
                  P2_objectives_optimized=False, P2_certificate=None,
                  M1_AIDC_decision_variables=0, AIDC_Q_decision=False,
                  selected_jobs=jobs, selected_jobs_sha256=digest(jobs),
                  input_authority_hashes=input_hashes, grid_array_identities=arrays,
                  workload_axis_identities=identity['original_workload_axis_identities'],
                  source_freeze_sha256=source_hash, exact_P1=decision,
                  unknown_individual_jobs_fabricated=False,
                  unknown_arrival_policy=dict(interface='v42_native.actual.unknown_arrival',
                      planning_future_actual_reads=0, observed_site_only=True,
                      requires_frozen_runtime_CC4_and_kernel=True))
    doc = dict(schema=SCHEMA, anchor=anchor, anchor_sha256=digest(anchor),
               acceptance_scope='P1_ORIGINAL_INTEGER_GLOBAL_GAP_ONLY',
               allowed_next_stage='M1', downstream_accepted=False,
               A1_ACCEPTED=False, P2_certificate=None)
    validate_handoff(doc)
    return doc


def validate_handoff(doc, *, expected_identity=None):
    require(doc.get('schema') == SCHEMA, 'P1_ONLY_INTERFACE_SCHEMA')
    a = doc['anchor']
    require(doc['anchor_sha256'] == digest(a), 'A1_FROZEN_ANCHOR_DRIFT')
    require(a['A1_P1_ONLY_ACCEPTED'] is True and a['A1_ACCEPTED'] is False and doc['A1_ACCEPTED'] is False,
            'P1_ONLY_ACCEPTANCE_SCOPE_DRIFT')
    require(a['P2_objectives_optimized'] is False and a['P2_certificate'] is None and doc['P2_certificate'] is None,
            'P2_CERTIFICATE_FABRICATION')
    require(doc['allowed_next_stage'] == 'M1' and doc['downstream_accepted'] is False,
            'P1_ONLY_INTERFACE_DOES_NOT_ACCEPT_DOWNSTREAM')
    require(a['M1_AIDC_decision_variables'] == 0 and not a['AIDC_Q_decision'], 'M1_AIDC_CONSTANTS_REQUIRED')
    require(a['selected_jobs_sha256'] == digest(a['selected_jobs']), 'FROZEN_JOB_ACTIONS_DRIFT')
    require(a['exact_P1']['A1_P1_ONLY_ACCEPTED'] is True and a['exact_P1']['A1_ACCEPTED'] is False,
            'P1_ACCEPTANCE_REQUIRED')
    L, U = Fraction(a['exact_P1']['exact_LB']), Fraction(a['exact_P1']['exact_UB'])
    require(U >= L and U >= 0 and (U == L == 0 or U > 0 and (U-L)/U <= Fraction(1,200)),
            'GLOBAL_P1_GAP_NOT_ACCEPTED')
    if expected_identity is not None:
        require(a['input_authority_hashes'] == expected_identity['input_authority_hashes'] and
                a['grid_array_identities'] == expected_identity['grid_array_identities'] and
                a['day'] == expected_identity['day'], 'M1_FROZEN_INPUT_IDENTITY_MISMATCH')
    return True


def m1_payload(handoff, mess_authority):
    validate_handoff(handoff)
    required = ('route_table_sha256', 'battery_sha256', 'initial_sites_sha256', 'traffic_forecast_sha256')
    require(all(isinstance(mess_authority.get(k), str) and len(mess_authority[k]) == 64 for k in required),
            'FROZEN_MESS_AUTHORITY_REQUIRED')
    return dict(stage='M1', day=handoff['anchor']['day'], A1_handoff_sha256=digest(handoff),
                frozen_AIDC=deepcopy(handoff['anchor']), MESS_authority=deepcopy(mess_authority),
                decision_variables=['route', 'charge_mode', 'Pch', 'Pdis', 'Q', 'SOC', 'rho'],
                objective_groups=['MAX_LINE_LOADING', 'MIN_INTERVENTION'],
                constraints=['route_flow', 'travel_energy', 'connection_delay', 'initial_SOC', 'terminal_SOC',
                             'energy_balance', 'no_simultaneous_charge_discharge', 'PCS16',
                             'voltage', 'line_thermal', 'transformer_NormalAmps', 'transformer_kVA'],
                P2_certificate_from_A1=None, M1_ACCEPTED=False)
