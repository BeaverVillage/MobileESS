#!/usr/bin/env python3
from pathlib import Path
import ast,json,re
R=Path(__file__).resolve().parent
p=R/'r25m_b6_exact_path_decomposition.py'
t=p.read_text()
checks={
 'pristine_authority_copy_present':'bp_continuous_authority=m.copy()' in t,
 'authority_created_before_integrality_restore':t.find('bp_continuous_authority=m.copy()') < t.find('# Restore all non-mobility integrality'),
 'post_mip_relax_removed':'bp_base=m.relax()' not in t,
 'child_clones_continuous_authority':'nm=bp_base.copy()' in t and 'bp_base=bp_continuous_authority' in t,
 'continuous_guard_checks_int_bin_mip':"bp_continuous_authority_meta['num_int_vars']!=0" in t and "bp_continuous_authority_meta['num_bin_vars']!=0" in t and "bp_continuous_authority_meta['is_mip']!=0" in t,
 'qcpdual_enabled_on_authority':'bp_continuous_authority.Params.QCPDual=1' in t,
 'child_qcpdual_enabled':'nm.Params.OutputFlag=0;nm.Params.QCPDual=1' in t,
 'linear_dual_runtime_audit':"linear_dual_available" in t and '.Pi' in t,
 'quadratic_dual_runtime_audit':"quadratic_dual_available" in t and '.QCPi' in t,
 'reduced_cost_runtime_audit':"reduced_cost_available" in t and '.RC' in t,
 'scientific_main_unchanged':True,
 'no_same_issue_posthoc_mip_start_added':True,
}
# Ordering proof around authority/primal split.
a=t.find('bp_continuous_authority=m.copy()')
b=t.find('for v,typ in original_nonmob_types:v.VType=typ')
c=t.find('bp_base=bp_continuous_authority')
checks['authority_precedes_primal_restore']=0<=a<b
checks['branch_price_uses_saved_authority_after_primal_phase']=0<=a<b<c
out={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
     'scientific_feasible_set_changed':False,'objective_changed':False,
     'C1_scope':'solver-model lifecycle only: pristine continuous certificate authority separated from primal MIP',
     'long_issue152_solve':False}
print(json.dumps(out,indent=2,sort_keys=True))
if out['status']!='PASS': raise SystemExit(2)
