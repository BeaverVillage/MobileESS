"""Isolated diagnostic: solve ONLY the existing first 20-state seed relaxation.
No route search, separation loop, OpenDSS or production outputs are executed.
Unused coefficient rows are omitted; every seed row is copied exactly.
"""
import sys,pathlib,json,pickle,hashlib,time,os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
sys.dont_write_bytecode=True
D=pathlib.Path(__file__).absolute().parent;H=D.parent.parent;W=H.parent.parent
sys.path.insert(0,str(H))
import fleet_binding
fleet_binding.install()
import numpy as np
from dayahead.v28r2.electrical_subproblem import SlotCoefficients
from dayahead.v35r3.algorithm import build_fixed_candidate_model
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
results={}
for label,root,coeffroot in [('previous',W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913',W/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912'),('current',H,H)]:
 case_root=pathlib.Path(rd(D/'B2_ARCHIVE_RELOCATION.json')['archived_path']) if label=='current' and (D/'B2_ARCHIVE_RELOCATION.json').exists() else root/'B2'
 cache=sorted((case_root/'candidate_cache').rglob('*.pkl'),key=lambda p:p.stat().st_mtime)[0]
 result=pickle.loads(cache.read_bytes())['result'];candidate=result[1]['candidate'];assert candidate.is_stay
 congestion=rd(case_root/'beam/2025-05-01/B2/B2/CONGESTION_MAP.json');states=congestion['states'];assert len(states)==20
 names=tuple([f'aidc_load_kw[AIDC{i:02}]' for i in range(1,13)]+[f'mess_{q}[{s}{i:02}]' for q in ('p_kw','q_kvar') for s in ('IDC','STA') for i in range(1,13)])
 axes=rd(root/'AXES.json');coeff={};seed=[]
 for t in sorted({r['slot'] for r in states}):
  indices=sorted({r['branch_index'] for r in states if r['slot']==t});path=coeffroot/'coefficients'/f'slot_{t:02}'/'COEFFICIENTS.npz'
  with np.load(path) as z:x=z['x'];a=z['line'][indices];j=z['line_J'][:,indices]
  norm=np.abs(a);ji=np.divide(np.real(j*np.conj(a)[None,:]),norm[None,:],out=np.zeros(j.shape,float),where=norm[None,:]>0);con=a-x@j
  branches=tuple(axes['line'][i].split('|')[0].lower()+'::'+str(i) for i in indices)
  c=SlotCoefficients(t,names,branches,x,np.zeros(1),np.zeros((60,1)),norm-x@ji,ji,con.real,con.imag,j.real.T,j.imag.T,tuple(np.ones(len(indices))),tuple([None]*len(indices)),hashlib.sha256((label+str(t)).encode()).hexdigest())
  coeff[t]=c;seed.extend((t,indices.index(r['branch_index'])) for r in states if r['slot']==t)
 dummy=next(iter(coeff.values()));cc=tuple(coeff.get(t,dummy) for t in range(96))
 with np.load(root/'MAY01_B0_AIDC_POWER.npz') as z:aidc=z['pcc'].copy()
 began=time.perf_counter();item=build_fixed_candidate_model(candidate=candidate,aidc_pcc_kw_96x12=aidc,coefficients=cc,services=tuple(f'{s}{i:02}' for s in ('IDC','STA') for i in range(1,13)),line_states=seed)
 item.model.Params.Threads=1;item.model.optimize()
 results[label]={'status':item.model.Status,'initial_seed_rho':item.eta.X if item.model.SolCount else None,'seed_states':len(seed),'rows':item.model.NumConstrs,'vars':item.model.NumVars,'solver_seconds':item.model.Runtime,'wall_seconds':time.perf_counter()-began,'scope':'Original first STAY 20-state seed relaxation only; no separation/evaluation; not production result','production_modified':False}
 if label=='current' and '--first-separation' in sys.argv:
  from dayahead.v35r3.algorithm import fixed_candidate_dispatch,evaluate_opportunity_dispatch
  from numerical_coefficients import Coefficients,NT,NL,AX,build
  from dataclasses import replace
  def full_coefficients():
   for t in range(96):yield replace(build(t),transformer_ratings=tuple([None]*NL+[1.]*NT+AX['winding_rating_kVA']))
  v=evaluate_opportunity_dispatch(dispatch=fixed_candidate_dispatch(item),coefficients=full_coefficients(),aidc_pcc_kw_96x12=aidc,services=item.services)
  initial={(r['slot'],r['branch_index']) for r in states}
  results[label]['first_separation_additions']={'line':len(set(v['line_separation_states'])-initial),'voltage':len(v['voltage_violation_states']),'tx_current':len(v['transformer_current_violation_states']),'tx_kva':len(v['transformer_kva_violation_states'])}
  results[label]['first_full_linear_rho']=v['rho'];results[label]['first_full_certificate']=v['exact_optimality_certificate']
  results[label]['scope']='Original 20-state seed relaxation plus first full linear evaluation only; no separation-state materialization and no production result'
 item.model.dispose();print(label,results[label],flush=True)
(D/'seed_probe.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
