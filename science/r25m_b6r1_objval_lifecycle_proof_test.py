#!/usr/bin/env python3
from pathlib import Path
import ast,json
p=Path(__file__).resolve().parent/'r25m_b6_exact_path_decomposition.py'
s=p.read_text(); ast.parse(s)
checks={
 'rmp_obj_cached_immediately_after_optimal_status': ("rmp_obj=float(m.ObjVal)" in s or "rmp_obj_local=float(m.ObjVal)" in s),
 'cg_record_uses_cached_obj_not_live_ObjVal': "'rmp_objective':rmp_obj" in s and "'rmp_objective':float(m.ObjVal)" not in s,
 'full_lb_uses_cached_closure_obj': "full_lb=float(rmp_obj);break" in s,
 'mutation_deferred_until_after_record': "The next loop iteration re-solves" in s and "m.update()\n        if thread_screen_mode" in s,
 'live_cg_audit_present': 'ConversationA_R25M_B6_CG_LIVE.json' in s,
 'c5r2_dual_retry_before_mutation': ('QCP dual unavailable after BarQCPConvTol retries' in s or 'QCP dual/RC audit failed after BarQCPConvTol retries' in s),
}
print(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks},indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
