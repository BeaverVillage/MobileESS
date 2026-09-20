import optimize as op
from optimize import *
op.SLOTS=list(range(68,86));op.TARGET_RHO=.75;op.TRUST_REGION=True
def main():
 name=sys.argv[1];policy=sys.argv[2];layout=read(H/'placements'/name/'LAYOUT.json');folder=H/'placements'/name/f'{policy}_EXACT_PROXY';folder.mkdir(exist_ok=True)
 p=BASE_P.copy()
 if policy=='B3':
  ppath=H/'placements'/name/'B3/B_DC_1/POWER.npz'
  if not ppath.exists():ppath=ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916/B_DC_1/POWER.npz'
  with np.load(ppath) as z:p=z['pcc'].copy()
 cap=H/'placements'/name/'capability_expanded';r=read(cap/'RESULT.json');mm={(x['slot'],x['station']):(x['P'],x['Q']) for x in read(cap/f'MESS_{r["iteration"]}.json')};mm=op.energy_recovery({k:v for k,v in mm.items() if k[0] in op.SLOTS})
 best=None;start_it=0
 if (folder/'RESULT.json').exists():
  best=read(folder/'RESULT.json');mm={(x['slot'],x['station']):(x['P'],x['Q']) for x in read(folder/'MESS.json')};bestmm=mm;start_it=best['iteration']+1
 for it in range(start_it,5):
  z=op.coefficients(layout,p,folder/f'coeff_{it}',mm);ans,candidate=op.solve_lp(layout,p,z)
  for factor in [1.,.5,.25,0.]:
   trial={key:tuple(factor*np.array(val)+(1-factor)*np.array(mm.get(key,(0,0)))) for key,val in candidate.items()};trial=op.energy_recovery(trial)
   ac=replay(layout,p,folder/f'AC_{it}_{factor:g}',trial,slots=op.SLOTS);ph=physics(trial)
   record=dict(iteration=it,factor=factor,proxy_rho=float(ans.fun),**ac,storage=ph['status'])
   if ac['physical_pass'] and ph['status']=='PASS' and (best is None or ac['max_phase_line_loading_pu']<best['max_phase_line_loading_pu']-1e-7):
    best=record;bestmm=trial;save(folder/'MESS.json',[dict(slot=t,station=sid,P=pq[0],Q=pq[1]) for (t,sid),pq in trial.items()]);save(folder/'PHYSICS.json',ph);np.savez_compressed(folder/'POWER.npz',pcc=p);save(folder/'RESULT.json',best)
    mm=trial;break
  print(name,policy,json.dumps(best),flush=True)
  if best is None:break
  if best['iteration']<it:break
 if best:
  rec=replay(layout,p,folder/'RECOVERY_AC',bestmm,slots=list(range(34,54)));best['recovery_AC']=rec;best['physical_pass'] &= rec['physical_pass'];save(folder/'RESULT.json',best)
if __name__=='__main__':main()
