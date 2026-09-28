"""Resume diagnostics after timezone-array arithmetic repair; keep frozen predictions."""
from common9 import *
from evaluate_april9 import *
def main():
    assert_freeze();f=pd.read_parquet(V8/'APRIL_JOBS.parquet');pred=pd.read_parquet(ROOT/'APRIL_PREDICTIONS.parquet')
    saved=np.load(LOCAL/'APRIL_PARAMETERS.npz');par=saved['parameters'];rawq=saved['raw_quantiles']
    model=Distribution.load(ROOT/'RUNTIME_PROVIDER/model');contract=read(ROOT/'RUNTIME_PROVIDER/runtime_contract.json')
    delta,audit,daily=april_calibration(model,par,f,rawq,contract)
    q=model.quantiles(par,delta);error=float(np.max(abs(q[:,[0,3]]-pred[['V9_Q50','V9_Q90']].to_numpy())));assert error==0
    rem=remaining_diagnostics(f,pred,model,par,delta,daily,contract);m=f.label_valid.to_numpy()
    write('APRIL_EVALUATION_RECEIPT.json',dict(time=now(),mature_N=int(sum(m)),unresolved_N=int(sum(~m)),remaining=rem,APRIL_USED_FOR_SELECTION=False,
        APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,FUTURE_CALIBRATION_RESIDUAL_READS=0,MAY_PAYLOAD_OPENED=False,source=record(V8/'APRIL_JOBS.parquet')))
    write('APRIL_DIAGNOSTIC_REPAIR.json',dict(time=now(),reason='Timezone-aware pandas timestamps had object dtype; use DatetimeIndex for checkpoint timedelta arithmetic',
        predictions_reused=True,prediction_max_absolute_change=error,provider_or_model_changed=False,remaining_definition_changed=False))
    assert_freeze();print('APRIL_DIAGNOSTICS_COMPLETE',rem,flush=True)
if __name__=='__main__':main()
