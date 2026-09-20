from bootstrap import *
import traceback
def main():
 protect();clock_binding()
 import aidc_runtime,grid8500
 from dayahead.v40h.beam_driver import _restore_slots
 from dayahead.v40a.grid import controls_from_trajectory
 from dayahead.v40g_segments.canonical import planning_power,import_frozen
 from v41r4_loop_budget import LoopBoundedLex,LoopBudget
 assert issubclass(aidc_runtime.ProductionLex,LoopBoundedLex)
 state(status='RUNNING',stage='B3_A1:PRESEARCH_CONTEXT',search_started=False)
 ctx=new_context();reuse=read(H/'FINAL_B1_REUSE.json');jobs=read(reuse['jobs']['path'])
 p1=planning_power(import_frozen(jobs),ctx)
 with np.load(reuse['power']['path']) as z:
  for k in ('pcc','qcc'):assert np.max(abs(p1[k]-z[k]))<1e-9
 m1=tuple(_restore_slots(read(H/'B3_M1/FINAL_AUTHORITY.json')['trajectory_slots']))
 assert len(m1)==576
 ctx.v41_fixed_mess=m1;ctx.v41_a1_seed_jobs=jobs;ctx.v41_a1_seed_pcc=p1['pcc'];ctx.ieee8500_final_B1_seed=reuse['seed_bundle']
 seed_ac=exact(p1['pcc'],m1,H/'B3_A1_seed_exact');assert seed_ac['status']=='PASS'
 controls=controls_from_trajectory(ctx.coefficients,p1['pcc'],m1)
 grid=evaluate_grid(ctx.coefficients,controls,ctx.nodes);assert grid['status']=='PASS'
 save(H/'DEADLINE_INCUMBENT.json',dict(status='INDEPENDENTLY_VALIDATED',seed=True,jobs=reuse['jobs'],power=reuse['power'],power_is_physical=False,exact_AC=record(H/'B3_A1_seed_exact/AC_VALIDATION.json'),P1=grid['rho_max'],iteration=0,incumbent_updates=0,accepted_elapsed=0,published_elapsed=0))
 save(H/'A0_REUSE_GATE.json',dict(status='PASS',B1_search_calls=0,source=reuse,power_recomputed_equal=True,fixed_M1=record(H/'B3_M1/FINAL_AUTHORITY.json')))
 state(stage='B3_A1:PRESEARCH_FIXED_M1_ELECTRICAL_ROWS',search_started=False)
 grid8500.prepare(ctx,H/'B3_A1_electrical_rows',controls)
 result=aidc_runtime.run(ctx,'B3_A1')
 save(H/'A1_NATURAL_RETURN.json',dict(status='RETURNED',unix=time.time(),planning_P1=result['grid']['rho_max']))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'A1_WORKER_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
