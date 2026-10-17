"""Native0: current parent FULL replay and exact diagnostic row partition."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r026
from v44.common import read,record,verify,atomic,now
from v44_recovery_r026.parent_admission import validate,original_point
from v44_recovery_r026.wall_resume import arrays
from v42_m1_research.check_ub import matrix_replay
from v42_may_campaign_native90.preflight import native_zero
from scipy import sparse
import numpy as np

def run():
    parent=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt001')
    output=Path('D:/MobileESS_V44/development/r026/latest_parent_validation');output.mkdir(exist_ok=False)
    baseline=[record(parent/'M1/RESULT.json'),record(parent/'M1/ACCEPTED_M_POINT.npz'),record(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json')]
    with native_zero() as denied:
        proof=validate(parent,output/'PARENT',read(parent/'A2/request.json'))
        names,x=original_point(parent/'M1');d=arrays(parent/'M1/FULL_DATA.npz');A=sparse.load_npz(parent/'M1/FULL_A.npz')
        assert np.array_equal(names,d['names'])
        families=np.array([str(n).split('[',1)[0] for n in d['row_names']])
        voltage=np.isin(families,('voltage_lower','voltage_upper'));keep=~voltage
        tight=np.isin(families[keep],('flow','terminal_location','NormalAmps','line_thermal_face','transformer_kVA'))
        selected=dict(d,rhs=d['rhs'][keep],sense=d['sense'][keep],row_names=d['row_names'][keep])
        replay=matrix_replay(A[keep],selected,x,tolerance=1e-6,row_tolerances=np.where(tight,1e-8,1e-6))
        assert replay['PASS'] and voltage.any() and not denied
        verify(baseline)
        result=dict(UTC=now(),PASS=True,Native_calls=0,parent=record(output/'PARENT/R026_PARENT_COMPATIBILITY.json'),
            reconstructed_original_FULL_columns=len(x),excluded_only_voltage_rows=int(voltage.sum()),
            nonvoltage_matrix_replay=replay,original_route_SOC_PCS=proof['M1_FULL_original_replay']['physical'],
            original_files_unchanged=baseline,
            scope='COMPLETED_M1_REVALIDATION_ONLY; NEW_A2_AND_M2_EXECUTION_RESULTS_ARE_NOT_CLAIMED')
        atomic(output/'RESULT.json',result)
    print('CURRENT_PARENT_NATIVE0_PASS',len(x),int(voltage.sum()),flush=True)

if __name__=='__main__':run()
