"""Forecast-only engineering check; this does not start the Actual campaign."""
from bootstrap import *
from actual_native import Native, Evaluator
import fleet_binding

def main():
 out=P/'performance_verification/native_forecast';out.mkdir(parents=True,exist_ok=True)
 e=Engine(out/'input_probe')
 data=dict(md=e.md.copy(),mpv=e.mpv.copy(),PCC_P=e.ap.copy(),PCC_Q=e.aq.copy(),locations=np.tile(list(fleet_binding.INITIAL.values()),(96,1)),connected=np.ones((96,6),dtype=bool))
 e.close();engine=Evaluator(out,data);baseline=Native(out/'independent_continuous',data);errors={k:0. for k in ('v','line','tx','kva')};zero=np.zeros(6);started=time.time()
 try:
  for t in range(96):
   # A rejected trial must not leave regulator/capacitor state in the accepted replay.
   chosen=engine.evaluate(t,zero,zero)
   if t in (0,32,65,66,95):engine.evaluate(t,np.full(6,100.),np.full(6,150.))
   repeat=engine.evaluate(t,zero,zero)
   clean=baseline.apply(t,zero,zero)
   for k in errors:errors[k]=max(errors[k],float(np.max(abs(chosen[k]-clean[k]))),float(np.max(abs(chosen[k]-repeat[k]))))
   if not (chosen['taps']==repeat['taps']==clean['taps'] and chosen['caps']==repeat['caps']==clean['caps']):
    mismatch=dict(slot=t,chosen={k:chosen[k] for k in ('taps','caps')},repeat={k:repeat[k] for k in ('taps','caps')},clean={k:clean[k] for k in ('taps','caps')},errors=errors)
    save(out/'CONTROL_MISMATCH.json',mismatch);print(json.dumps(mismatch),flush=True);raise AssertionError('CACHED_NATIVE_CONTROL_STATE_MISMATCH')
   assert max(errors.values())<1e-9,(t,errors)
   engine.accept(zero,zero,chosen)
 finally:engine.close();baseline.close()
 report=dict(status='PASS',kind='FORECAST_ONLY_ENGINEERING_CHECK_NO_ACTUAL_CAMPAIGN',slots=96,trial_count=engine.trials,maximum_absolute_errors=errors,fallback=engine.fallback,native_solves=engine.solves,wall_seconds=time.time()-started,source=record(P/'actual_native.py'))
 save(out/'RESULT.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':main()
