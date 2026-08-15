#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parent
M=(R/'r25m_b6_exact_path_decomposition.py').read_text()
C=json.loads((R/'R25N_B6C5_CONTRACT.json').read_text())
checks={
 'C1_pristine_authority':'bp_continuous_authority=m.copy()' in M and 'B6-C1 missing pristine continuous authority' in M,
 'C1_no_post_mip_relax':'bp_base=m.relax()' not in M,
 'C2_global_cache':'global_path_cache={mid:{} for mid in mids}' in M and 'node_inherited_columns' in M,
 'C2_child_batch':'MOBILEESS_R25M_B6C2_CHILD_PRICING_BATCH' in M and 'k_shortest_paths_with_node_restrictions' in M,
 'C3_stabilization':'MOBILEESS_R25M_B6C3_DUAL_STABILIZATION' in M and 'stabilized_dual_certificate_authority' in M,
 'C3_true_dual_closure':'TRUE_CURRENT_DUAL_EXACT_MINIMUM_PATH_ONLY' in M,
 'C4_strong_branch':'MOBILEESS_R25M_B6C4_STRONG_BRANCHING' in M and 'strong_branch_score' in M,
 'C4_probe_not_authority':"'certificate_authority':False" in M,
 'exact_child_pricing':'child_lower_bound_requires_true_dual_all_column_pricing_closure' in (R/'R25M_B6C4_CONTRACT.json').read_text(),
 'scientific_main_unchanged':hashlib.sha256((R/'main.py').read_bytes()).hexdigest()==C['hashes']['main_py_sha256'],
 'freeze_requires_3pct':C['runtime_gate']['admit_final_freeze_only_if_global_3pct_certificate'] is True,
 'diagnostic_no_commit':C['runtime_gate']['diagnostic_only'] is True and C['runtime_gate']['physical_h0_commit'] is False,
}
out={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'pass_count':sum(checks.values()),'check_count':len(checks)}
print(json.dumps(out,indent=2));raise SystemExit(0 if all(checks.values()) else 2)
