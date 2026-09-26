from bootstrap import *
import traceback
def main():
 protect()
 import mess_runtime
 from dayahead.v40h.beam_driver import _restore_slots
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from dayahead.v40a.grid import controls_from_trajectory
 chosen=read(H/'FOUR_HOUR_A2_INCUMBENT.json');jobs=read(chosen['jobs']['path'])
 with np.load(chosen['power']['path']) as z:power={k:z[k].copy() for k in z.files}
 ctx=new_context();m1=MessTrajectory(tuple(_restore_slots(read(H/'B3_M1/FINAL_AUTHORITY.json')['trajectory_slots'])))
 seed=exact(power['pcc'],m1.slots,H/'B3_A2/DA_FINAL_96');clean=exact(power['pcc'],m1.slots,H/'B3_A2/DA_INDEPENDENT_CLEAN_96')
 assert seed['status']==clean['status']=='PASS'
 assert all(abs(seed['metrics'][k]-clean['metrics'][k])<1e-10 for k in seed['metrics'])
 save(H/'B3_A2/ACCEPTED_AIDC_DEADLINE.json',dict(status='PASS',jobs=jobs,P1=chosen['P1'],source=record(H/'FOUR_HOUR_A2_INCUMBENT.json')))
 state(status='RUNNING',stage='B3_MF:FIXED_ROUTE_PQ',search_stopped=True)
 start=time.perf_counter();final=mess_runtime.recourse(ctx,power['pcc'],m1)
 ac=exact(power['pcc'],final.slots,H/'B3/final_exact');clean=exact(power['pcc'],final.slots,H/'B3/independent_clean_exact')
 fresh=exact(power['pcc'],final.slots,H/'B3/Fresh')
 assert ac['status']==clean['status']==fresh['status']=='PASS'
 assert all(abs(ac['metrics'][k]-clean['metrics'][k])<1e-10 for k in ac['metrics'])
 lin=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,power['pcc'],final.slots),ctx.nodes)
 save(H/'B3/FINAL_AUTHORITY.json',dict(status='PASS',P1=lin['rho_max'],AC=ac['metrics'],jobs=jobs,trajectory_slots=[r.to_dict() for r in final.slots],B1_production_reuse=False,route_searches=1,AIDC_passes=2,MF_passes=1,AIDC_continuous_wall_seconds_each=14400,MF_wall_seconds=time.perf_counter()-start,deadline_incumbent=record(H/'FOUR_HOUR_A2_INCUMBENT.json')))
 np.savez_compressed(H/'B3/FINAL_POWER_NORMALIZED.npz',**power)
 save(H/'B3/COMPLETE.json',dict(status='PASS',unix=time.time()))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'MF_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
