import subprocess
import json
from .common import ROOT,BASE,OUT,REF,LOCAL,POLICY,sha,read,write
from .resources import gate

def run():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==BASE
    gate('prepare')
    files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    write('PR134_BYTE_PRESERVATION.json',dict(base=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in files if p],all_inherited_artifacts_preserved=True))
    manifest=read(REF/'SHA256_MANIFEST.json')
    drift=[r['path'] for r in manifest['files']+manifest['sources'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift
    write('SINGLE_WORKER_RESOURCE_POLICY.json',dict(MAX_HEAVY_WORKERS=1,Gurobi_Threads=1,OMP_NUM_THREADS=1,MKL_NUM_THREADS=1,OPENBLAS_NUM_THREADS=1,NUMEXPR_NUM_THREADS=1,resource_and_watchdog_support_threads_not_solver_workers=True,no_parallel_tests=True,P1_optimization_calls_max=1,P1_retries=0,P2_calls_max=2,P2_requires_new_P1_acceptance=True,A1_optimization_calls=0,policy=POLICY,scientific_parameters_unchanged_except_DegenMoves=True,heavy_callback_filesystem_writes=0,source_data_read_only=True))
    write('EXECUTION_PREREGISTRATION.json',dict(base=BASE,one_P1_call=True,DegenMoves=0,new_zero_action_Start_only_if_full_unreduced_rows_and_integrality_and_physics_PASS=True,Start_failure_no_repair_and_no_Start=True,preflight_optimize_calls=0,no_new_LP_solves=True,no_old_UB_LB_gap=True,early_stop='At 600 s, terminate if no first nonroot/branch, no incumbent, and root processing completion unobserved. A directly observed nonroot or model-feasible incumbent plus actual MIP_CUTCNT>0 allows continued same solve.',checkpoint_values='Callback values carry their exact observation time. Stale last-MIP values are separated; unobservable exact-600 state remains NULL.',incumbent_validation='Capture all MIPSOL points; check full raw rows inside MIPSOL only. Independently audit route/PQ/SOC/source grid for every point after terminal. Publish only fully validated scientific UB.',classification='ACCEPTED: nonroot/branch <=600 with unchanged model. PARTIAL: valid incumbent or nonroot observed only after600. FAILED: correctness error or no incumbent/nonroot/branch.',callback_overhead='Measure every handler call body wall and thread CPU; retain native Gurobi total calls/time and compare its reported time with PR134 66.91 s.',causal_claim=False,P2_order=['movement_energy','movement_count'],P2_P1_lock_slack=0.,P2_energy_lock_slack=1e-8,P2_TimeLimit_each=1800,downstream_NOT_RUN=['A2','M2','Actual','Fresh AC']))
    print('PR134_PREREGISTERED',len([p for p in files if p]),flush=True)
if __name__=='__main__':run()
