from runtime import *
from legacy_slot import LegacyBatch
sys.path.insert(0,str(H/'shared'))
from qsafe_shell import correct_slot,VERSION
import traceback
def main():
 assert not(H/'SLOT_RESULT.json').exists()
 dta=data();t=43;lo,hi=q_bounds(dta['P_EXEC'][t],dta['connected'][t],AUTH)
 frozen_files=[BASE/'B2/FINAL_AUTHORITY.json',BASE/'actual_B2/B2/ACTUAL_INPUTS.npz',BASE/'actual_B2/B2/ACTUAL_MESS_AUDIT.json',BASE/'actual_B2/B2/ACTUAL_MESS_TIMESERIES.parquet',BASE/'electrical_engine.py',H/'shared/qsafe_shell.py',H/'legacy_slot.py',H/'slot_runner.py',METHOD/'METHOD_FREEZE.json',METHOD/'frozen_code/qsafe.py']
 records=[rec(p) for p in frozen_files]
 save(H/'RULE_FREEZE.json',dict(status='FROZEN_BEFORE_SEARCH',version=VERSION,date='2025-05-01',slot_zero_based=t,slot_one_based=t+1,connected=int(dta['connected'][t].sum()),evaluator='Original full chronological clean OpenDSS context 0..t for every trial; checkpoint evaluator prohibited',Q1='Complete first feasible deviation shell; exact floating objective equality; lexicographic tie-break',Q2=dict(name='existing local_refinement SLSQP',rule=RULES['local_refinement']),no_global_candidate_or_time_cap=True,workers=4,physical_semantics_unchanged=True,files=records))
 batch=LegacyBatch(t,4);start=time.perf_counter()
 try:
  def progress(v):save(H/'SEARCH_PROGRESS.json',v);state(status='RUNNING',stage='LEGACY_EXACT_SHELL_SEARCH',slot=t,**v)
  q,r,event=correct_slot(batch.one,dta['Q_EXEC'][t],lo,hi,q_da=dta['Q_DA'][t],rules=RULES,feasible=feasible,constraints=constraints,evaluate_many=batch.many,progress=progress)
  for record in records:assert sha(record['path'])==record['sha256'],record['path']
  assert np.all(q>=lo-1e-9) and np.all(q<=hi+1e-9)
  status='IEEE8500_QSAFE_V2_SEARCH_PASS' if feasible(r) else 'IEEE8500_QSAFE_V2_SEARCH_FAIL'
  result=dict(status=status,slot=t,selected_Q=q,final_Q_deviation=float(np.sum((q-dta['Q_DA'][t])**2)),Vmin=float(r['v'].min()),Vmax=float(r['v'].max()),line_max=float(r['line'].max()),transformer_current_max=float(r['tx'].max()),transformer_kVA_max=float(r['kva'].max()),taps=r['taps'],caps=r['caps'],converged=r['converged'],controls_settled=r['controls_settled'],event=event,total_exact_replay_count=batch.count,total_AC_solves=batch.count*(t+1),prefix_AC_solves=batch.count*t,current_slot_AC_solves=batch.count,wall_seconds=time.perf_counter()-start,P_SOC_route_invariance='PASS: original inputs and DA command SHA unchanged; only Q supplied to evaluator',frozen_P=dta['P_EXEC'][t],SOC=dta['SoC_after'][t],energy=dta['energy_after'][t],locations=dta['locations'][t],same_legacy_evaluator=True,checkpoint_evaluator_used=False,B2_full_Actual_restarted=False)
  np.savez_compressed(H/'SELECTED_EXACT_ARRAYS.npz',Q=q,**{k:r[k] for k in ('v','line','tx','ipu','kva')})
  save(H/'SLOT_RESULT.json',result);state(status=status,stage='PROBLEMATIC_SLOT_COMPLETE',slot=t)
  print(status,json.dumps(clean(result)),flush=True)
 finally:batch.close()
if __name__=='__main__':
 try:main()
 except BaseException as error:save(H/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()));raise
