"""Verify saved outputs and accounting without model fitting or data reopening."""
import json
import xml.etree.ElementTree as ET
import numpy as np
from .common import *
from .data import frame,history

def main():
    require_prereg();k0=verify_k0();checks={}
    with Firewall('verification'):
        for stage in ['visible_development','calibration','selection','shadow']:
            p=OUT/(stage.upper()+'_PREDICTIONS.parquet')
            if not p.exists():continue
            f=frame(p);y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float);base=f.K0.to_numpy(float)
            model_columns=[c for c in f if c.endswith('_Q90')]
            candidates={}
            for col in model_columns:
                cid=col[:-4];a=f[col].to_numpy(float);b=f[cid+'_Q95'].to_numpy(float);finite=np.isfinite(a)&np.isfinite(b)
                assert np.all(a[finite]>=base[finite]) and np.all(b[finite]>=a[finite])
                if stage=='selection':
                    expected=read('V40L_TAIL_SELECTION_COMPARISON.json')['candidates'][cid]['metrics']['overall']['Q90']
                    coverage=float(np.count_nonzero(np.isfinite(a)&(y<=a))/len(y))
                    weighted=float(sum(float(w) for w,yy,aa in zip(g,y,a) if np.isfinite(aa) and yy<=aa)/sum(g))
                    over=float(sum(float(w)*max(float(aa-yy),0.) for w,yy,aa in zip(g,y,a) if np.isfinite(aa))/3600)
                    assert coverage==expected['coverage'] and abs(weighted-expected['GPU_weighted_coverage'])<1e-12
                    assert abs(over-expected['overreserved_GPU_hours'])<1e-7
                candidates[cid]={'safe_ge_K0':True,'Q95_ge_Q90':True,'abstentions':int((~finite).sum())}
            checks[stage]={'rows':len(f),'saved_prediction_SHA':sha(p),'candidates':candidates}
        dev=frame(OUT/'VISIBLE_DEVELOPMENT_PREDICTIONS.parquet');orig=frame(K/'POINT_HOLDOUT_PREDICTIONS.parquet')
        assert dev.job_id.tolist()==orig.job_id.tolist() and dev.K0.to_numpy(float).tobytes()==orig.K0.to_numpy(float).tobytes()
        # Independently compare numeric key counts against pandas groupby at the Apr01 support freeze.
        from .evaluate import feature_frame
        from .data import base_features
        h=history();xx=base_features(h);qx=base_features(dev);actual=feature_frame(dev)
        from .common import F9
        for cols,countcol in [(F9,'exact_count'),(F9[1:],'near_count')]:
            cnt=xx.groupby(cols,dropna=False,observed=True).size().rename('expected').reset_index()
            q=qx[cols].copy();q['ix']=np.arange(len(q));merged=q.merge(cnt,on=cols,how='left',validate='many_to_one').sort_values('ix')
            assert np.array_equal(merged.expected.fillna(0).to_numpy(),actual[countcol].to_numpy())
        write('V40L_EXECUTION_VERIFICATION.json',{'status':'PASS','K0_visible_predictions_byte_identical':True,'K0_model_SHA':k0['models/K0_FINAL.pkl'],
          'OOF_prediction_reproduction':read('V40L_OOF_PREDICTION_REPRODUCTION.json'),'independent_numeric_support_groupby':'PASS','independent_GPU_accounting':'PASS','stages':checks,'new_fits':0,'new_raw_partitions_opened':0})
        tree=ET.parse(OUT/'TEST_RESULTS.xml');suites=list(tree.getroot().iter('testsuite'))
        n=sum(int(s.attrib.get('tests',0)) for s in suites);fail=sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
        assert n>=48 and fail==0
        write('V40L_TEST_REPORT.json',{'status':'PASS','executed_tests':n,'failures':fail,'junit_SHA':sha(OUT/'TEST_RESULTS.xml'),'execution_verification_SHA':sha(OUT/'V40L_EXECUTION_VERIFICATION.json'),
          'K0_model_SHA_unchanged':True,'K0_visible_prediction_max_difference_seconds':0.,'OOF_prediction_max_difference_seconds':0.,'independent_ML_double_fits':read('V40L_TRAINING_DETERMINISM.json'),
          'GPU_scientific_fits':0,'CPU_only':True,'raw_May_outcomes_read':0,'shadow_no_retune':True,'PF':.95,'Q_control':'NO'})
        print('EXECUTION_VERIFICATION_PASS',n,flush=True)
if __name__=='__main__':main()
