"""Fresh source-only replay of the selected research B0, not an unseen day."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import build_candidate
from .common import REPORT, read, write, receipt
from .geometry import read_csv
from .screening import demand
from .selected_case_v3 import MAPPING


def run():
    archive = REPORT/'joint_selection_v3/selected_ac/bg0p552_gpu1p0'
    folder = REPORT/'joint_selection_v3/fresh_selected_b0_replay'
    with np.load(archive/'AC_96.npz', allow_pickle=False) as ref:
        expected = {key: ref[key] for key in ref.files}
    states = read(archive/'CONTROL_STATES.json')
    e = IEEE8500AC(output_dir=folder/'dss')
    for row in read_csv(MAPPING):
        e.add_pcc(row['location_id'], row['candidate_bus'],
                  'MV_3PH' if row['role']=='AIDC' else 'LV_SPLIT_240')
    c = build_candidate(1.)
    errors = {key: 0. for key in expected}
    state_errors = []
    for t in range(96):
        # No archived taps/capacitor states are used as replay inputs.
        e.solve(.552, demand(c, t), reset_controls=False, snapshot=False)
        a = e.measurement_arrays()
        if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
            raise ValueError('FRESH_RESEARCH_B0_NOT_SETTLED')
        for key in errors:
            errors[key] = max(errors[key], float(np.abs(a[key]-expected[key][t]).max()))
        if e.control_state() != states[t]:
            state_errors.append(t)
    result = dict(PASS=max(errors.values())<1e-9 and not state_errors,
        scope='FRESH_SAME_PLANNING_INPUT_REPLAY_NOT_DDAY_ACTUAL_OR_UNSEEN_DAY',
        slots=96, source_only_initialization=True, archived_control_states_imported=False,
        maximum_absolute_errors=errors, control_state_mismatch_slots=state_errors,
        original_source_identity=e.verify_source_unchanged(), mapping=receipt(MAPPING),
        archive=receipt(archive/'AC_96.npz'), Native_calls=0,
        operational_constraints_pass=False, production_ready=False,
        reason='same-input reproduction does not remove archived original-band overvoltage failures')
    write(folder/'RECEIPT.json', result)
    if not result['PASS']:
        raise ValueError('FRESH_RESEARCH_B0_REPLAY_DRIFT')
    print('fresh selected B0 replay PASS', errors, flush=True)


if __name__=='__main__':
    run()
