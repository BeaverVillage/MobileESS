from common8500 import *
import shutil
from terminal_ac_gate import select_terminal
from dayahead.tools import run_v35r3e_r1_beam as beam
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v40a.grid import controls_from_trajectory
OLD=P.parent/'IEEE8500_v41r4_production_20260911_r2'
def copy_identical(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();shutil.copyfile(source,dest);assert sha(source)==sha(dest)
    return dict(source=record(source),copy=record(dest))
def main():
    install_output_paths();verify()
    release=read(OLD/'PRODUCTION_RELEASE.json')
    for row in release['code']:assert sha(row['path'])==row['sha256']
    b1=read(OLD/'B1/FINAL_AUTHORITY.json');assert b1['status']=='PASS' and b1['search_budget_seconds']==14400
    for k in ('decision','exact'):assert sha(b1[k]['path'])==b1[k]['sha256']
    copies=[]
    for rel in ['B0/FINAL.json','B0/POWER.npz','B1/ACCEPTED_AIDC.json','B1/FINAL_AUTHORITY.json','B1/FINAL_POWER.npz','B1/POLICY_FEASIBLE_SEED.npz','B1/SCALABILITY_METRICS.json']:
        copies.append(copy_identical(OLD/rel,P/rel))
    accepted=read(OLD/'B1/ACCEPTED_AIDC.json');checkpoint=accepted['solver_stages'][-1]['checkpoint'];assert sha(checkpoint['path'])==checkpoint['sha256']
    target=P/'B1/bounded_checkpoints'/Path(checkpoint['path']).name;copies.append(copy_identical(Path(checkpoint['path']),target))
    save(P/'FINAL_B1_REUSE.json',dict(status='PASS',B1_rerun=False,source_release=record(OLD/'PRODUCTION_RELEASE.json'),copied_files=copies,checkpoint=record(target)))
    initial=read(OLD/'B2/beam/2025-05-21/B2/B2/STAGE_4.json')
    kept=[beam.BeamState.from_dict(x) for x in initial['retained_states']];pruned=[beam.BeamState.from_dict(x) for x in initial['pruned_states']]
    with np.load(P/'B0/POWER.npz') as z:pcc=z['pcc'].copy()
    choice=select_terminal(kept,pruned,pcc,P/'B2')
    traj=MessTrajectory(tuple(beam._restore_slots(choice.trajectory_slots)))
    ac=exact(pcc,traj.slots,P/'B2/final_exact');assert ac['status']=='PASS'
    linear=evaluate_grid(Coefficients(),controls_from_trajectory(Coefficients(),pcc,traj.slots),AX['nodes']);assert linear['status']=='PASS'
    previous=read(OLD/'B2/beam/2025-05-21/B2/B2/FINAL_RESULT.json')
    save(P/'B2/FINAL_AUTHORITY.json',dict(status='PASS',P1=linear['rho_max'],AC=ac['metrics'],selected_state=choice.beam_state_id,trajectory_slots=[r.to_dict() for r in traj.slots],original_search_wall_seconds=previous['run_wallclock_seconds'],exact_recovery=record(P/'B2/TERMINAL_AC_ADMISSION.json'),original_failed_result_preserved=record(OLD/'B2/beam/2025-05-21/B2/B2/FINAL_RESULT.json'),new_search_calls=0,operating_point_and_limits_unchanged=True))
    save(P/'RECOVERY_PREPARATION_PASS.json',dict(status='PASS',B1=record(P/'FINAL_B1_REUSE.json'),B2=record(P/'B2/FINAL_AUTHORITY.json'),physical_replay=record(P/'B2/final_exact/AC_VALIDATION.json'),linear_full_rows=linear))
    state(status='READY_TO_RESUME',stage='B2_RECOVERED_PASS',search_started=False,search_stopped=True,policy_results={'B0':dict(status='PASS',P1=read(P/'B0/FINAL.json')['metrics']['max_phase_line_loading_pu']),'B1':b1,'B2':read(P/'B2/FINAL_AUTHORITY.json')})
    print('RECOVERY_PREPARATION_PASS',flush=True)
if __name__=='__main__':main()
