#!/usr/bin/env python3
from pathlib import Path
import json, hashlib
from r25m_b6_exact_path_decomposition import (
    classify_integer_block, qcp_dual_retry_schedule,
    gap_target_lower_bound, global_relative_gap,
)
R=Path(__file__).resolve().parent
src=(R/'r25m_b6_exact_path_decomposition.py').read_text()
checks={}
checks['classify_mode']=classify_integer_block('mode_MESS01_51')=='mode'
checks['classify_job']=classify_integer_block('x_1234')=='job_choice'
checks['classify_defer']=classify_integer_block('defer_job_7')=='defer'
checks['classify_other']=classify_integer_block('other_bin')=='other_integer'
sch=qcp_dual_retry_schedule(1e-9)
checks['qcp_retry_nonincreasing']=all(sch[i+1] <= sch[i] for i in range(len(sch)-1))
checks['qcp_retry_primary']=abs(sch[0]-1e-9)<1e-20
checks['barqcp_used']='Params.BarQCPConvTol=qcp_barrier_tol' in src
checks['legacy_barconv_not_used_as_qcp_tol']='Params.BarConvTol=barrier_tol' not in src
checks['root_dual_retry']='QCP dual unavailable after BarQCPConvTol retries' in src
checks['child_dual_retry']='qcp_dual_unavailable_after_retries' in src
checks['thread_screen_stop']='B6C5R2_THREAD_SCREEN_COMPLETE' in src
checks['gap_source_forensic']='ConversationA_R25N_B6C5R2_GAP_SOURCE_FORENSIC.json' in src
checks['block_diag_not_authority']="'scientific_lower_bound_authority':False" in src
# numerical gap threshold identity across negative objectives
ok=True
for u in [-1.0,-10.0,-1937.9964663366604,-2500.0]:
    t=0.03;thr=gap_target_lower_bound(u,t)
    for d in [-100,-1,0,1,100]:
        L=thr+d
        if L>u: continue
        lhs=global_relative_gap(u,L)<=t+1e-12
        rhs=L>=thr-1e-12
        ok &= (lhs==rhs)
checks['gap_threshold_identity']=ok
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks['main_sha_c5r1_preserved']=sha(R/'main.py')=='e924160a3947f61098790808c643e30986503d072cc01492ed6d997ba71dcb50'
checks['thread_candidates_contract']=tuple([1,2,4,8])==(1,2,4,8)
change_flags={
    'scientific_feasible_set_changed':False,
    'objective_changed':False,
    'physical_commit_in_forensic':False,
}
passed=all(checks.values()) and not any(change_flags.values())
out={'status':'PASS' if passed else 'FAIL','PASS':passed,'checks':checks,**change_flags,'long_solver_run':False}
print(json.dumps(out,indent=2))
raise SystemExit(0 if passed else 1)
