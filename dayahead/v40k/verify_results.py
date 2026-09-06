"""Independent accounting and reload verification; never refits any candidate."""
import numpy as np
from .common import *
from .data import frame,timestamp_mask,utc
from .evaluate import central_predictions,verify_lock
from .models import features
from .protocol import SPLIT

def main():
    with Firewall('final_result_verification'):
        lock=verify_lock();f=frame(OUT/'POINT_HOLDOUT_PREDICTIONS.parquet')
        assert timestamp_mask(f).all()
        assert (f.submit_time>=utc('2025-04-01')).all() and (f.submit_time<utc('2025-04-08')).all() and (f.end_time<utc('2025-04-08')).all()
        assert not f.job_id.duplicated().any()
        p=central_predictions(f,f.K0.to_numpy());comp=read('V40K_POINT_MODEL_COMPARISON.json');checks={}
        for cid,pred in p.items():
            assert pred.tobytes()==f[cid].to_numpy().tobytes(),('PREDICTION_RELOAD_CHANGED',cid)
            error=f.runtime_seconds.to_numpy()-pred;n=len(error)
            calculated={'MAE':float(np.sum(np.abs(error))/n),'pinball_Q50':float(np.sum(np.abs(error))*.5/n),
              'underprediction':float(np.count_nonzero(error>0)/n),'median_calibration_error':float(abs(np.count_nonzero(error>0)/n-.5))}
            target=comp['baseline']['overall'] if cid=='K0' else comp['candidates'][cid]['metrics']['overall']
            assert all(abs(v-target[k])<1e-10 for k,v in calculated.items())
            checks[cid]={'prediction_reload_bytes_identical':True,'independent_metric_accounting':True}
        assert read('V40K_POINT_SELECTION.json')['winner'] is None
        assert not (OUT/'V40K_POINT_MODEL_FREEZE.json').exists()
        assert not any((OUT/(s+'_ROWS.parquet')).exists() for s in ['SAFE_FIT','SAFE_SELECTION','FINAL_SHADOW'])
        events=[json.loads(s) for s in (OUT/'V40K_EVENTS.jsonl').read_text().splitlines() if s]
        registered=min(e['timestamp'] for e in events if e['kind']=='preregistration_committed')
        freeze=min(e['timestamp'] for e in events if e['kind']=='preholdout_execution_committed')
        opened=min(e['timestamp'] for e in events if e['kind']=='first_stage_payload_open')
        selected=min(e['timestamp'] for e in events if e['kind']=='point_selection_frozen')
        assert registered<freeze<opened<selected
        write('V40K_RESULT_VERIFICATION.json',{'status':'PASS','prediction_rows':len(f),'candidates':checks,
          'chronology':{'preregistration_committed':registered,'execution_freeze_committed':freeze,'first_new_holdout_payload':opened,'point_selection_frozen':selected},
          'point_source_and_models_unchanged':True,'safe_bound_blocks_opened':False,'shadow_opened':False,
          'CPU_scientific_results_only':True,'no_retraining_in_this_verification':True})
        print('RESULT_VERIFICATION_PASS',len(f),len(checks),flush=True)
if __name__=='__main__':main()
