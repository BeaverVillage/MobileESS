"""Read-only comparison of selected planning report and restoration precondition."""
from bootstrap import *
from dayahead.v40h.beam_driver import _restore_slots
from dayahead.v40a.grid import controls_from_trajectory
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v40h.recourse import validate_physics
def main():
    selected=read(H/'B2/ORIGINAL_SELECTED_BEFORE_EXACT.json')
    trajectory=MessTrajectory(tuple(_restore_slots(selected['trajectory_slots'])))
    pcc=np.load(H/'MAY01_B0_AIDC_POWER.npz')['pcc']
    coeff=Coefficients()
    controls=controls_from_trajectory(coeff,pcc,trajectory.slots)
    result=evaluate_grid(coeff,controls,AX['nodes'])
    report=dict(status='DIAGNOSTIC_ONLY',selected=record(H/'B2/ORIGINAL_SELECTED_BEFORE_EXACT.json'),
        original_report=selected['planning'],restoration_entry_grid=result,
        physics=validate_physics(trajectory),original_grid_tolerance=1e-9,
        constraints_or_acceptance_changed=False,unix=time.time())
    save(H/'B2_CLOSURE_INITIAL_GRID_DIAGNOSTIC.json',report)
    print({k:v for k,v in result.items() if k!='coefficient_SHAs'},flush=True)
if __name__=='__main__':main()
