#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r25b_main',HERE/'main.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def mm(D,E,slot,src='IDC01',dst='STA01'):
 return {'D':D,'energy_kWh':E,'source':src,'dest':dst,'slot':slot}

results=[]
# PASS: two incomparable routes; no hidden dominated choice.
with tempfile.TemporaryDirectory() as td:
 moves={(0,1):mm(2,7,1),(0,2):mm(3,5,2)}
 allowed={'MESS01':[(0,1),(0,2)]}
 reach={'MESS01':[{'IDC01'},{'IDC01'},{'STA01'},{'STA01'},{'STA01'}]+[{'STA01'}]*(mod.H-4)}
 a=mod.r25b_route_transition_dominance_audit(moves,allowed,reach,['MESS01'],Path(td))
 results.append(('incomparable_preserved',a['status']=='PASS_COMPLETE_NO_ESCAPED_DOMINANCE'))

# DETECT: route 2 is later and more energy than route 1; upstream compiler must have removed it.
with tempfile.TemporaryDirectory() as td:
 moves={(0,1):mm(2,5,1),(0,2):mm(3,6,2)}
 allowed={'MESS01':[(0,1),(0,2)]}
 reach={'MESS01':[{'IDC01'},{'IDC01'}]+[{'STA01'}]*(mod.H-1)}
 caught=False
 try:mod.r25b_route_transition_dominance_audit(moves,allowed,reach,['MESS01'],Path(td))
 except RuntimeError:caught=True
 rec=json.loads((Path(td)/'ConversationA_R25B_K3_ROUTE_DOMINANCE_EQUIVALENCE_AUDIT.json').read_text())
 results.append(('escaped_dominance_detected',caught and rec['escaped_dominated_route_count']>=1))

# DETECT equivalent planning-state duplicate by canonical slot tie.
with tempfile.TemporaryDirectory() as td:
 moves={(0,1):mm(2,5,1),(0,2):mm(2,5,2)}
 allowed={'MESS01':[(0,1),(0,2)]}
 reach={'MESS01':[{'IDC01'},{'IDC01'}]+[{'STA01'}]*(mod.H-1)}
 caught=False
 try:mod.r25b_route_transition_dominance_audit(moves,allowed,reach,['MESS01'],Path(td))
 except RuntimeError:caught=True
 rec=json.loads((Path(td)/'ConversationA_R25B_K3_ROUTE_DOMINANCE_EQUIVALENCE_AUDIT.json').read_text())
 results.append(('equivalent_state_duplicate_detected',caught and rec['escaped_equivalent_route_count']>=1))

# No dominance when the earlier route cannot emulate the later state by a valid STAY chain.
with tempfile.TemporaryDirectory() as td:
 moves={(0,1):mm(2,5,1),(0,2):mm(4,6,2)}
 allowed={'MESS01':[(0,1),(0,2)]}
 # Build reach with STA01 intentionally absent at t=3, so the exact continuation certificate fails.
 rr=[set() for _ in range(mod.H+1)];rr[0]={'IDC01'};rr[2]={'STA01'};rr[4]={'STA01'}
 allowed2={'MESS01':[(0,1),(0,2)]}
 a=mod.r25b_route_transition_dominance_audit(moves,allowed2,{'MESS01':rr},['MESS01'],Path(td))
 results.append(('missing_stay_chain_blocks_dominance',a['escaped_dominated_route_count']==0))

out={'status':'PASS' if all(v for k,v in results) else 'FAIL','tests':dict(results),'test_count':len(results)}
print(json.dumps(out,indent=2,sort_keys=True))
if out['status']!='PASS':raise SystemExit(1)
