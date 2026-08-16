#!/usr/bin/env python3
import json
from r25l_b5_monolithic_gate import evaluate_b5
cases=[
 ({'gap':0.0299,'runtime_s':500,'nodes':100,'root_bound':-2017,'bound':-2000,'incumbent':-1945,'root_exit_s':80,'nodes_per_second':0.2},'GO_MONOLITHIC_STAGE1'),
 ({'gap':0.0308,'runtime_s':600,'nodes':1200,'root_bound':-2017,'bound':-2004.0,'incumbent':-1945,'root_exit_s':60,'nodes_per_second':2.0},'GO_MONOLITHIC_PROMISING'),
 ({'gap':0.034,'runtime_s':600,'nodes':1,'root_bound':-2017,'bound':-2010,'incumbent':-1945,'root_exit_s':None,'nodes_per_second':0.0017},'NO_GO_MONOLITHIC_ADVANCE_B6_EXACT_DECOMPOSITION'),
]
out=[]
for m,want in cases:
 r=evaluate_b5(m); out.append({'want':want,'got':r['decision'],'pass':r['decision']==want})
res={'status':'PASS' if all(x['pass'] for x in out) else 'FAIL','cases':out}
print(json.dumps(res,indent=2))
raise SystemExit(0 if res['status']=='PASS' else 2)
