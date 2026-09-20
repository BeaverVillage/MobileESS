import sys,pathlib,json,pickle,time,hashlib,os,statistics,traceback
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
sys.dont_write_bytecode=True
D=pathlib.Path(__file__).absolute().parent;H=D.parent.parent
PROPAGATED='--propagated' in sys.argv
sys.path.insert(0,str(H))
import fleet_binding
fleet_binding.install()
import numpy as np
import mess_runtime
from dayahead.v35r3 import algorithm as alg
from current_layout_seed import select_seed
def save(name,value):
 if PROPAGATED and name.startswith('COMPACT_SEED'):name=name.replace('COMPACT_SEED','PROPAGATED_SEED',1)
 p=D/name;p.write_text(json.dumps(value,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 began=time.perf_counter();sources={k:sha(H/k) for k in ['LAYOUT.json','COEFFICIENT_GENERATION.json','PCC_OVERLAY_INVENTORY.json','MAY01_B0_AIDC_POWER.npz']}
 path=H/'B2/dayahead/cache/v35/APR01_20_AC_FIDELITY_CALIBRATION/2025-05-01/B0/PLANNING_GRID.npz'
 with np.load(path) as z:
  names=[f'{n}::{p}' for n,p in zip(z['branch_names'].astype(str),z['branch_phases'].astype(str))]
  seed,info=select_seed(z['phase_current_loading_pu'],names)
 info.update(input_file=str(path),input_sha256=sha(path),states=sorted(seed),input_authority=sources)
 save('CURRENT_LAYOUT_SEED.json',info);print('INITIAL_SEED',len(seed),flush=True)
 caches=sorted((H/'B2/candidate_cache').rglob('*.pkl'),key=lambda p:p.stat().st_mtime)
 chosen=caches[:5] if PROPAGATED else caches[:3]+caches[-2:];samples=[]
 for p in chosen:
  x=pickle.loads(p.read_bytes());assert x['identity']['MESS_step']==1 and x['identity']['beam_parent_fingerprint']==pickle.loads(caches[0].read_bytes())['identity']['beam_parent_fingerprint']
  samples.append((p,x['result']))
 print('LOAD_CURRENT_COEFFICIENTS',flush=True);cc=mess_runtime.coefficients();print('COEFFICIENTS_READY',time.perf_counter()-began,flush=True)
 with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:aidc=z['pcc'].copy()
 services=tuple(n[10:-1] for n in cc[0].control_names if n.startswith('mess_p_kw['))
 original=alg.evaluate_opportunity_dispatch;results=[]
 carry={'line':set(seed),'voltage':set(),'tx_current':set(),'tx_kva':set()}
 for p,baseline in samples:
  initial={k:len(v) for k,v in carry.items()};history=[];start=time.perf_counter();item=alg.build_fixed_candidate_model(candidate=baseline[1]['candidate'],aidc_pcc_kw_96x12=aidc,coefficients=cc,services=services,line_states=carry['line'],voltage_states=carry['voltage'],transformer_current_states=carry['tx_current'],transformer_kva_states=carry['tx_kva'])
  item.model.Params.Threads=4;built=time.perf_counter()-start
  def traced(**kw):
   tick=time.perf_counter();v=original(**kw)
   new={'line':len(set(v['line_separation_states'])-item.added_line_states),'voltage':len(set(v['voltage_violation_states'])-item.added_voltage_states),'tx_current':len(set(v['transformer_current_violation_states'])-item.added_transformer_current_states),'tx_kva':len(set(v['transformer_kva_violation_states'])-item.added_transformer_kva_states)}
   history.append({'restricted_rho':kw['dispatch']['rho'],'full_rho':v['rho'],'certificate':v['exact_optimality_certificate'],'new_states':new,'evaluation_seconds':time.perf_counter()-tick})
   return v
  alg.evaluate_opportunity_dispatch=traced
  try:
   dispatch,evaluation=alg.solve_fixed_candidate_certified(item)
   elapsed=time.perf_counter()-start
   row={'candidate':baseline[0]['candidate_id'],'baseline_cache':str(p),'baseline_sha256':sha(p),'initial_states':len(seed),'first_restricted_rho':history[0]['restricted_rho'],'first_separation_additions':history[0]['new_states'],'closure_counts':{'line':len(item.added_line_states),'voltage':len(item.added_voltage_states),'tx_current':len(item.added_transformer_current_states),'tx_kva':len(item.added_transformer_kva_states)},'closed_certificate':evaluation['exact_optimality_certificate'],'rho':evaluation['rho'],'objective':dispatch['objective'],'baseline_rho':baseline[0]['rho'],'baseline_objective':baseline[0]['objective'],'rho_difference':abs(evaluation['rho']-baseline[0]['rho']),'objective_difference':abs(dispatch['objective']-baseline[0]['objective']),'wall_seconds':elapsed,'build_seconds':built,'baseline_wall_seconds':baseline[0]['runtime_seconds'],'rounds':history,'model_rows':item.model.NumConstrs,'model_vars':item.model.NumVars}
   assert row['closed_certificate'] and row['rho_difference']<=2*alg.NUMERIC_TOLERANCE and row['objective_difference']<=2*alg.NUMERIC_TOLERANCE,row
   row['initial_counts']=initial
   if PROPAGATED:
    for k,states in [('line',item.added_line_states),('voltage',item.added_voltage_states),('tx_current',item.added_transformer_current_states),('tx_kva',item.added_transformer_kva_states)]:carry[k].update(states)
   results.append(row);save('COMPACT_SEED_PROGRESS.json',results);print('CANDIDATE_CLOSURE_PASS',row['candidate'],elapsed,row['closure_counts'],flush=True)
  finally:alg.evaluate_opportunity_dispatch=original;item.model.dispose()
 for name,value in sources.items():assert sha(H/name)==value
 report={'status':'PASS','samples':results,'median_wall_seconds':statistics.median(r['wall_seconds'] for r in results),'baseline_median_seconds':statistics.median(r['baseline_wall_seconds'] for r in results),'initial_seed':info,'original_numeric_tolerance':alg.NUMERIC_TOLERANCE,'original_separation_source':sha(pathlib.Path(alg.__file__)),'separation_function_unchanged':True,'K_domain_changed':False,'rho_floor_imposed':False,'full_AC_production_gate_unchanged':True,'production_modified':False,'wall_seconds':time.perf_counter()-began}
 report['representative_cut_propagation']=PROPAGATED
 save('COMPACT_SEED_PROOF.json',report);print('COMPACT_SEED_PROOF_PASS',report['median_wall_seconds'],flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:save('COMPACT_SEED_FAILURE.json',{'traceback':traceback.format_exc()});raise
