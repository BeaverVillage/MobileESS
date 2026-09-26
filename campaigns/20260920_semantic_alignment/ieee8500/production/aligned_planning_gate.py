from bootstrap import *
from dayahead.v40g_segments.canonical import planning_power,import_frozen
from dayahead.v40h.beam_driver import _restore_slots
from dayahead.v40h.recourse import validate_physics
from dayahead.v33m.mess_trajectory import MessTrajectory
def main():
 protect();assert not (P/'SEMANTIC_ALIGNMENT_STOP.json').exists()
 policies={};refs=[];ctx=new_context(load_options=False)
 for policy in ('B0','B1','B2','B3'):
  if policy=='B0':jobs=read(P/'REFERENCE_JOBS.json');slots=();pcc=np.load(P/'MAY01_B0_AIDC_POWER.npz')['pcc']
  elif policy=='B1':jobs=read(P/'B1/FINAL_JOBS.json');slots=();pcc=np.load(P/'B1/FINAL_POWER.npz')['pcc']
  else:
   authority=read(P/policy/'FINAL_AUTHORITY.json')
   # A worker adopted before the output-receipt fix can have a separate final closure authority.
   if policy=='B2' and (P/'B2/CLOSED_AUTHORITY.json').exists():authority=read(P/'B2/CLOSED_AUTHORITY.json')
   jobs=read(P/('REFERENCE_JOBS.json' if policy=='B2' else 'B3_A1/FINAL_JOBS.json'))
   slots=tuple(_restore_slots(authority['trajectory_slots']));assert validate_physics(MessTrajectory(slots))['status']=='PASS'
   pcc=planning_power(import_frozen(jobs),ctx)['pcc']
  fresh=exact(pcc,slots,P/policy/'aligned_final_Fresh');assert fresh['status']=='PASS',policy
  approx=evaluate_grid(ctx.coefficients,__import__('dayahead.v40a.grid',fromlist=['controls_from_trajectory']).controls_from_trajectory(ctx.coefficients,pcc,slots),ctx.nodes)
  selected=dict(status='PASS',jobs=jobs,trajectory_slots=[r.to_dict() for r in slots],P1=approx['rho_max'],AC=fresh['metrics'])
  save(P/policy/'ALIGNED_SELECTED.json',selected)
  policies[policy]=dict(Planning_rho=approx['rho_max'],Fresh_rho=fresh['metrics']['max_phase_line_loading_pu'],metrics=fresh['metrics'],selected=record(P/policy/'ALIGNED_SELECTED.json'),Fresh=record(P/policy/'aligned_final_Fresh/AC_VALIDATION.json'))
  refs += [record(P/policy/'ALIGNED_SELECTED.json'),record(P/policy/'aligned_final_Fresh/AC_VALIDATION.json')]
 source=record(P/'actual_controller.py');other=P.parent.parent/'IEEE123_ACTUAL_QFIRST_MINP_20260920/actual_controller.py';assert source['sha256']==sha(other)
 save(P/'ALIGNED_PLANNING_GATE.json',dict(status='PASS',all_Fresh_PASS=True,policies=policies,Actual_inputs=refs,controller=source,physical_scales=read(P/'PHYSICAL_SCALE_CONTRACT.json'),ordering_forced=False))
if __name__=='__main__':main()
