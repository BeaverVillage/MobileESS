from io import BytesIO
import pickle
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from .preflight import pm

def table(p):return pq.read_table(BytesIO(p.read_bytes())).to_pandas()
def summary(f):
    y=f.runtime_seconds.to_numpy(float)
    return {'N':len(f),'runtime_Q10_Q50_Q90':np.quantile(y,[.1,.5,.9]).tolist(),
      'runtime_mean':float(y.mean()),'early_fraction':float(((y<=300)|(f.job_state=='FAILED')).mean()),
      'COMPLETED_fraction':float((f.job_state=='COMPLETED').mean()),
      'walltime_Q50':float(f.requested_seconds.median())}

def main():
    with Firewall('point_swing_forensic'):
        f=table(J/'DEVELOPMENT_GPU_ROWS.parquet');report={};examples={}
        for cid in ['C1_L1','C1_Q50','C2_MIXTURE']:
            v=table(J/(cid+'_N100_R0_VALIDATION.parquet'))
            mask=v.partition.str.contains('h100',case=False,na=False)&v.qos.eq('standby')&v.job_state.eq('COMPLETED')
            target=v.loc[mask].copy()
            report[cid]={'COMPLETED_H100_standby':pm(target),'folds':{},'requested_walltime':[]}
            if cid=='C1_L1':
                b=target.copy();b['point']=b.baseline_point;report['C0']={'COMPLETED_H100_standby':pm(b),'folds':{k:pm(x) for k,x in b.groupby('fold')}}
            for fold,part in target.groupby('fold'):
                report[cid]['folds'][fold]=pm(part)
            for wall,g in target.groupby('requested_seconds'):
                if len(g)>=20:report[cid]['requested_walltime'].append({'walltime':float(wall),**pm(g)})
            # Validate row correspondence and report transforms against saved source/model.
            report[cid]['runtime_negative_or_nonfinite']=int((~np.isfinite(v.point)|(v.point<0)).sum())
            report[cid]['point_above_request_count']=int((v.point>v.requested_seconds).sum())
            if cid in ['C1_L1','C1_Q50']:
                examples[cid]={}
                for fid,when in [('F1','2025-02-08'),('F2','2025-02-15'),('F3','2025-02-22')]:
                    m=pickle.loads((J/'models'/f'{fid}_{cid}.pkl').read_bytes())
                    b=m.models[0].booster_
                    gains=dict(zip(b.feature_name(),b.feature_importance('gain').tolist()))
                    examples[cid][fid]={'gain_importance':gains,'trees':b.num_trees(),'parameters':m.models[0].get_params()}
        training={}
        for fid,when in [('F1','2025-02-08'),('F2','2025-02-15'),('F3','2025-02-22')]:
            t=pd.Timestamp(when,tz='UTC');tr=f.loc[(f.end_time<t)&(f.end_time>=t-pd.Timedelta(days=120))&(f.submit_time<t)]
            hs=tr.loc[tr.partition.str.contains('h100',case=False,na=False)&tr.qos.eq('standby')]
            training[fid]={'all_GPU':summary(tr),'H100_standby':summary(hs),
               'H100_standby_COMPLETED':summary(hs.loc[hs.job_state=='COMPLETED']),
               'walltime_regimes':[{'requested_seconds':float(w),**summary(g)} for w,g in hs.groupby('requested_seconds') if len(g)>=100]}
        conclusions={
          'A':'L1/Q50 optimize global absolute/quantile loss on all historical GPU statuses with shared finite trees. They are not calibrated subgroup medians. The training/requested-walltime regime and held-out COMPLETED subgroup differ; fold and regime statistics below quantify this. No claim of a uniquely identified causal mechanism from observational diagnostics.',
          'B':'All valid end-known statuses enter nominal training without status at inference. Retrospective COMPLETED-only acceptance changes the evaluation population. Raw-second L1/Q50 and hours-scaled Huber also have different numerical optimization scales.',
          'C':'Requested walltime is a continuous causal feature; inspect regime-wise prediction/target medians and gain importance. No dedicated 12h coefficient or manual offset is inferred.',
          'D':'Early=FAILED OR runtime<=300 mixes status failure with duration. This shifts the unconditional central target; rates by training fold/status are reported.',
          'E':'V40J C2 uses probability-weighted smearing-corrected component log-regression means, not the 0.5 quantile of a mixture CDF. This estimand mismatch is established directly from frozen source.',
          'F':'V40J L1/Q50 have only nonnegative clipping, no log inverse or requested cap. Mixture applies exponential smearing for component means. No inverse-transform implementation error is found; the mean-versus-median distinction is substantive.',
          'G':'Fold signs and magnitudes are reported directly; pooled direction must not be described as universal without consulting these values.'}
        write('V40K_POINT_SWING_ROOT_CAUSE.json',{'created_at':now(),'May_used':False,'V40J_modified':False,
           'source_sha256':sha(ROOT/'dayahead/v40j/methods.py'),'candidate_metrics':report,'training_populations':training,'model_diagnostics':examples,'findings':conclusions})
        lines=['# V40K point swing audit','', 'V40J를 변경하지 않은 pre-May 진단이다. 통계적 estimand와 cohort 차이를 구분한다.','',
          '| Model | Underprediction | Mean actual−point (s) | MAE (s) |','|---|---:|---:|---:|']
        for cid,r in report.items():
            a=r['COMPLETED_H100_standby'];lines.append(f"| {cid} | {a['underprediction']:.6%} | {a['mean_signed_error']:.3f} | {a['MAE']:.3f} |")
        lines+=['','V40J mixture는 weighted mean이며 conditional median이 아니다. L1/Q50에는 log inverse나 walltime cap이 없으므로 이 두 변환을 원인으로 지목할 수 없다. 전체 historical-status 학습과 COMPLETED H100-standby 평가 cohort의 차이, 요청 walltime 분포와 finite-tree approximation을 함께 조사했다. 원인을 하나로 단정하지 않는다.','']
        for cid,r in report.items():lines.append(cid+' fold signed bias: '+', '.join(f"{k}={v['mean_signed_error']:.1f}s" for k,v in r['folds'].items()))
        lines+=['','정량 target 분포·early 비율·regime별 metric·feature gain은 동명 JSON에 있다. 새 estimand는 Q50이며 mean signed error는 diagnostic으로만 사용한다.']
        (OUT/'V40K_POINT_SWING_ROOT_CAUSE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps({k:v['COMPLETED_H100_standby'] for k,v in report.items()},indent=2),flush=True)
if __name__=='__main__':main()
