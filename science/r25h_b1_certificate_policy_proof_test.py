#!/usr/bin/env python3
from pathlib import Path
import ast, json, re, sys
R=Path(__file__).resolve().parent
p=R/'main.py'
s=p.read_text()
ast.parse(s)
checks={}
checks['flag_present']='MOBILEESS_R25H_B1_CERTIFICATE_FOCUS' in s
checks['requires_r25g']='R25H B1 certificate-focused search policy requires frozen R25G hybrid STAY-binary foundation' in s
checks['policy_name']='R25H_B1_CERTIFICATE_FOCUS_MF3_NO_IMPROVESTART' in s
checks['improve_start_disabled_when_active']='m.Params.ImproveStartGap=(0.0 if r25h_b1_certificate_focus else 0.032)' in s
checks['rolling_primal_recovery_gated']='int(issue)>113 and not r25h_b1_certificate_focus' in s
checks['certificate_mipfocus_model']='if r25h_b1_certificate_focus and int(issue)>113:\n  m.Params.MIPFocus=3' in s
checks['certificate_improvestart_model']='m.Params.MIPFocus=3\n  m.Params.ImproveStartGap=0.0' in s
checks['certificate_mipfocus_multiobj']='econ_env.setParam("MIPFocus",3)' in s
checks['certificate_improvestart_multiobj']='econ_env.setParam("ImproveStartGap",0.0)' in s
checks['dedicated_runtime_audit']='ConversationA_R25H_B1_CERTIFICATE_SEARCH_POLICY.json' in s
checks['target_mipgap_unchanged']='m.Params.MIPGap=econ_gap;m.Params.MIPGapAbs=0.0;m.Params.MIPFocus=3' in s
checks['threads_contract_unchanged']='m.Params.Threads=threads_req' in s
checks['heuristics_rolling_unchanged']='_r11_heuristics=(0.10 if int(issue)>113 else float(os.environ.get("MOBILEESS_FINAL_HEURISTICS","0.05")))' in s
checks['varhint_only_contract']='"previous_plan_role":"VarHint only"' in s and '"rolling_MIP_start":"none for issue>113"' in s
checks['no_cutoff_injection']='m.Params.Cutoff' not in s
checks['no_bestobjstop_injection']='m.Params.BestObjStop' not in s
checks['no_worklimit_injection']='m.Params.WorkLimit' not in s
# Ensure the legacy rolling MIPFocus=1 assignment still exists only inside the gated block.
legacy_positions=[m.start() for m in re.finditer(r'm\.Params\.MIPFocus=1',s)]
checks['legacy_mipfocus1_single_site']=len(legacy_positions)==1
if legacy_positions:
    window=s[max(0,legacy_positions[0]-250):legacy_positions[0]+120]
    checks['legacy_mipfocus1_inside_gated_block']='not r25h_b1_certificate_focus' in window and 'if _rolling_primal_recovery:' in window
else:
    checks['legacy_mipfocus1_inside_gated_block']=False
# B1 is solver-search only: no new variables/constraints/objective API calls should carry R25H markers.
for forbidden in ['addVar','addVars','addConstr','addLConstr','addQConstr','setObjective','setObjectiveN']:
    checks[f'no_r25h_model_api_{forbidden}']=not bool(re.search(rf'R25H[^\n]*{forbidden}|{forbidden}[^\n]*R25H',s))
result={'release':'R25H_B1_CERTIFICATE_SEARCH_POLICY','status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
        'scientific_model_changed':False,'feasible_set_changed':False,'objective_changed':False,
        'long_solver_run':False}
print(json.dumps(result,indent=2,sort_keys=True))
if result['status']!='PASS': sys.exit(2)
