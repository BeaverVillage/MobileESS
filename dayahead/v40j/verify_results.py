"""Verify frozen result evidence without refitting or selecting another method."""
import json
import pickle
import numpy as np
from .contracts import OUT, SPLIT, CANDIDATES, SUPPORT
from .data import read_frame, train_mask, block_mask
from .methods import raw_features, ConditionalCalibration, safety_metrics
from .firewall import ReadFirewall, write

def main():
    fw=ReadFirewall('result_verification').install()
    try:
        selection=json.loads((OUT/'V40J_SELECTION_FREEZE.json').read_text())
        assert selection['winner'] is None
        frame=read_frame(OUT/'DEVELOPMENT_GPU_ROWS.parquet')
        calibration=[]
        for fold in SPLIT['folds']:
            cal=frame.loc[block_mask(frame,fold['calibration'],fold['validation'][0])]
            x=raw_features(cal);y=cal.runtime_seconds.to_numpy()
            for entry in CANDIDATES:
                cid=entry['id']
                if cid in ['C0','C4']:continue
                model=pickle.loads((OUT/'models'/f"{fold['id']}_{cid}.pkl").read_bytes())
                p=model.predict(x)
                for n in SUPPORT:
                    name=f"CALIBRATION_{fold['id']}_{cid}_{n}.json"
                    before=json.loads((OUT/name).read_text())
                    after=ConditionalCalibration(n).fit(x,y,p).json()
                    assert before==after,'CALIBRATION_NONDETERMINISM:'+name
                    calibration.append({'artifact':name,'independent_calibration_rebuild_identical':True})
        variants=[]
        report=json.loads((OUT/'V40J_CONDITIONAL_CALIBRATION_REPORT.json').read_text())['comparisons']
        for r in report:
            row=read_frame(OUT/(r['id']+'_validation.parquet'))
            assert len(row)==22121 and row.job_id.nunique()==len(row)
            assert (row.upper95>=row.upper90).all() and (row.upper90>=row.point).all()
            anchors=row.start_time.dt.as_unit('ns').astype('int64').to_numpy()/1e9%300
            rebuilt=safety_metrics(row.runtime_seconds,row.safe,row.num_gpus_req,anchors)
            assert rebuilt==r['metrics'],'METRIC_REBUILD_MISMATCH'
            native=safety_metrics(row.runtime_seconds,row.upper90,row.num_gpus_req,anchors)
            assert native==r['native_upper90_metrics']
            variants.append({'id':r['id'],'unique_row_domain_PASS':True,'quantile_monotonicity_PASS':True,'GPU_metrics_independent_rebuild_PASS':True})
        write('V40J_RESULT_REPRODUCIBILITY.json',{'status':'PASS','calibrations':calibration,'variants':variants,
            'shadow_rows_opened':0,'winner_reselection':False})
        print('RESULT_REPRODUCIBILITY_PASS',len(calibration),len(variants),flush=True)
    finally:fw.close()

if __name__=='__main__':main()
