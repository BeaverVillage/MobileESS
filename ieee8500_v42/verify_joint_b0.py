"""Independent fresh 96-slot AC replay of the geometric witness inputs only."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import build_candidate
from .common import REPORT,read,write,receipt
from .geometry import read_csv
from .screening import demand


def run():
    old=REPORT/'joint_selection_v2/scale_screening/bg1p0_gpu1p0'
    mapping=REPORT/'joint_selection_v2/expanded_orientation_v1/JOINT_SERVICE_MAPPING.csv'
    ref=np.load(old/'AC_96.npz',allow_pickle=False)
    expected={key:ref[key] for key in ref.files}
    errors={key:0. for key in ref.files}
    folder=REPORT/'joint_selection_v2/fresh_witness_replay'
    e=IEEE8500AC(output_dir=folder/'dss');c=build_candidate(1.)
    for r in read_csv(mapping):e.add_pcc(r['location_id'],r['candidate_bus'],'MV_3PH')
    base=read_csv(old/'REGCONTROL_TAP_VALIDATION.csv')
    taperrors=0
    for t in range(96):
        e.solve(1.,demand(c,t),reset_controls=False,snapshot=False)
        a=e.measurement_arrays()
        if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
            raise ValueError('FRESH_AC_NOT_SETTLED')
        for key in errors:errors[key]=max(errors[key],float(np.max(np.abs(a[key]-expected[key][t]))))
        tap=e.control_state()['taps']
        # Original source tap state only; never import Planning states as input.
        e.d.RegControls.First()
        for name in e.d.RegControls.AllNames():
            e.d.RegControls.Name(name)
            expect=next(int(x['tap_number']) for x in base if int(x['slot'])==t and x['name']==name)
            taperrors=max(taperrors,abs(e.d.RegControls.TapNumber()-expect))
    result=dict(PASS=max(errors.values())<1e-9 and taperrors==0,scope='INDEPENDENT_FRESH_PLANNING_INPUT_REPLAY_NOT_DDAY_ACTUAL',
        slots=96,source_context_fresh=True,Planning_taps_imported=False,source_state_only_initialization=True,
        maximum_absolute_errors=errors,tap_number_maximum_error=taperrors,source_bytes_unchanged=e.verify_source_unchanged(),
        independent_validation_day_claim=False,physical_ports_certified=False,Native_calls=0,
        mapping=receipt(mapping),archive=receipt(old/'AC_96.npz'))
    write(folder/'RECEIPT.json',result)
    if not result['PASS']:raise ValueError('FRESH_WITNESS_REPLAY_DRIFT')
    print('fresh witness replay PASS',errors,flush=True)


if __name__=='__main__':run()
