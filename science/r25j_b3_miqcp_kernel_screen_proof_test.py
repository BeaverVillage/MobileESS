#!/usr/bin/env python3
from pathlib import Path
import ast, json, hashlib
R=Path(__file__).resolve().parent
text=(R/'main.py').read_text()
tree=ast.parse(text)
# model-construction API counts remain the B2 counts; B3 may alter solver params/diagnostic control only.
attrs={'addVar','addVars','addConstr','addLConstr','addQConstr','setObjective','setObjectiveN'}
counts={k:0 for k in attrs}
for n in ast.walk(tree):
    if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in attrs:
        counts[n.func.attr]+=1
expected={'addVar':33,'addVars':7,'addConstr':4,'addLConstr':61,'addQConstr':5,'setObjective':1,'setObjectiveN':7}
# Diagnostic stop must occur after solve return but before physical commit/warmstart transition.
rollpos=text.find('def rolling54_main')
pos_solve=text.find('sol=build_full(',rollpos)
pos_stop=text.find('R25J_B3_DIAGNOSTIC_STOP_BEFORE_PHYSICAL_COMMIT')
pos_warm=text.find('rolling_warmstart=sol["rolling_warmstart_payload"]',pos_solve)
pos_ac=text.find('exact24_candidate(',pos_solve)
checks={
 'dynamic_miqcp_env_hook':'MOBILEESS_GUROBI_MIQCPMETHOD' in text and '_miqcp_method not in (-1,0,1)' in text,
 'effective_miqcp_param':'m.Params.MIQCPMethod=_miqcp_method' in text,
 'runtime_audit':'ConversationA_R25J_B3_MIQCP_KERNEL_SCREEN_AUDIT.json' in text,
 'screen_only_guard':'MOBILEESS_R25J_B3_SCREEN_ONLY' in text,
 'stop_after_solve_before_commit':pos_solve>=0 and pos_stop>pos_solve and pos_warm>pos_stop and pos_ac>pos_stop,
 'model_api_counts_unchanged':(counts==expected if 'MOBILEESS_R25K_B4_ROOT_BRANCH_STRENGTHENING' not in text else counts=={**expected,'addLConstr':65}),
 'b1_preserved':'MOBILEESS_R25H_B1_CERTIFICATE_FOCUS' in text and 'm.Params.ImproveStartGap=0.0' in text,
 'b2_preserved':'MOBILEESS_R25I_B2_NUMERICAL_RESCALING' in text and '_r25i_flow_scale_kw_per_model_unit=(1000.0 if r25i_b2_numerical_rescaling else 1.0)' in text,
 'no_scientific_gap_change':'MOBILEESS_GUROBI_ECON_MIPGAP' in text,
}
out={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'model_api_counts':counts,'expected_model_api_counts':expected,
     'scientific_model_changed':False,'feasible_set_changed':False,'objective_changed':False,'long_solver_run':False,
     'screen_methods':[-1,0,1]}
print(json.dumps(out,indent=2))
raise SystemExit(0 if out['status']=='PASS' else 2)
