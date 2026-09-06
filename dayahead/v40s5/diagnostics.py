"""Fixed diagnostics, with no model fitting, selection or feature changes."""
from .common import *

def psi(reference,values):
    r=np.asarray(reference,float);v=np.asarray(values,float)
    r=r[np.isfinite(r)];v=v[np.isfinite(v)]
    inner=np.unique(np.quantile(r,np.arange(.1,1,.1)))
    edges=np.r_[-np.inf,inner,np.inf]
    a=np.histogram(r,edges)[0]/len(r);b=np.histogram(v,edges)[0]/len(v)
    aa=np.maximum(a,1e-6);bb=np.maximum(b,1e-6)
    return dict(value=float(np.sum((bb-aa)*np.log(bb/aa))),interior_edges=inner.tolist(),reference_frequencies=a.tolist(),split_frequencies=b.tolist())

def sanity(f,p):
    p=np.asarray(p);return dict(distribution=distribution(p),negative_fraction=float((p<0).mean()),zero_fraction=float((p==0).mean()),
      greater_than_request_fraction=float((p>f.requested_seconds).mean()),greater_than_24h_fraction=float((p>86400).mean()),
      greater_than_72h_fraction=float((p>3*86400).mean()),greater_than_7d_fraction=float((p>7*86400).mean()),upper_cap_applied=False)

def main():
    guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    lib=library();datasets={'HISTORICAL_TRAINING_LIBRARY':lib,**{r:panel(r) for r in ROLES}}
    shift={};forensic={}
    for r,f in datasets.items():
        dist={c:distribution(f[c]) for c in NUM+['runtime_seconds','submit_hour','submit_dow']}
        dist['actual_request_ratio']=distribution(f.runtime_seconds/f.requested_seconds)
        shift[r]=dict(N=len(f),distributions=dist,categorical_frequencies={c:categories(f[c]).value_counts().to_dict() for c in CAT},
          PSI={c:psi(numeric(lib[c],c),numeric(f[c],c)) for c in NUM})
        forensic[r]=dict(N=len(f),actual_gt_request_N=int((f.runtime_seconds>f.requested_seconds).sum()),
          actual_gt_request_fraction=float((f.runtime_seconds>f.requested_seconds).mean()),ratio=dist['actual_request_ratio'],rows_removed=0)
    write('TEMPORAL_SHIFT_AUDIT',dict(reference='HISTORICAL_TRAINING_LIBRARY',diagnostic_only=True,adaptive_retraining=False,splits=shift))
    write('ACTUAL_REQUEST_FORENSIC',forensic)
    crossings={};margins={};safe={};unique={};daily={};under={};over={};walltime={};q_reports={f'Q{int(a*100)}':{} for a in QUANTILES}
    for track in ['P','PW']:
        crossings[track]={};margins[track]={};safe[track]={};unique[track]={}
        for role in ROLES:
            f=datasets[role];d=pd.read_parquet(OUT/f'V40S5_{track}_{role}_PREDICTIONS.parquet');report=read(f'{track}_{role}_REPORT')
            raw=d[[f'raw_Q{int(a*100)}' for a in QUANTILES]].to_numpy();q=d[[f'Q{int(a*100)}' for a in QUANTILES]].to_numpy()
            cross=(np.diff(raw,axis=1)<0).any(axis=1);after=(np.diff(q,axis=1)<0).any(axis=1)
            crossings[track][role]=dict(N=len(d),raw_crossing_N=int(cross.sum()),raw_crossing_fraction=float(cross.mean()),corrected_crossing_N=int(after.sum()),
              corrected_crossing_fraction=float(after.mean()),raw_negative_value_N=int((raw<0).sum()),lower_floor_value_N=int((raw<0).sum()),
              correction_magnitude_sec=distribution((q-raw).ravel()),monotone_only_correction_sec=distribution((q-np.maximum(raw,0)).ravel()))
            aa=.2*d.Q99.to_numpy();bb=.5*d.sigma.to_numpy()
            margins[track][role]=dict(fraction_A_ge_B=float((aa>=bb).mean()),fraction_B_gt_A=float((bb>aa).mean()),
              A_sec=distribution(aa),B_sec=distribution(bb),margin_sec=distribution(np.maximum(aa,bb)),sigma_sec=distribution(d.sigma),
              predicted_r2_negative_N=int((d.predicted_r2<0).sum()))
            safe[track][role]={c:sanity(d,d[c]) for c in CANDIDATES}
            u=d.sort_values(['issue_time','job_uid']).drop_duplicates('job_uid')
            unique[track][role]=dict(N=len(u),rule='earliest issue per job within this split',results={c:metrics(u,u[c]) for c in CANDIDATES},winner_reselection=False)
            if track=='P':
                daily[role]=report['daily'];under[role]={c:{k:report['results'][c][k] for k in ['under_sec','GPU_under_sec']} for c in CANDIDATES}
                over[role]={c:{k:report['results'][c][k] for k in ['over_sec','GPU_over_h','EXTREME_CONSERVATISM_WARNING']} for c in CANDIDATES}
                for a in QUANTILES:q_reports[f'Q{int(a*100)}'][role]=report['quantiles'][f'Q{int(a*100)}']
    for role in ROLES:
        p=read(f'P_{role}_REPORT');w=read(f'PW_{role}_REPORT')
        walltime[role]=dict(Q50_MAE_delta_PW_minus_P=w['quantiles']['Q50']['metrics']['MAE']-p['quantiles']['Q50']['metrics']['MAE'],
          pinball_delta_PW_minus_P={q:w['quantiles'][q]['raw_pinball']-p['quantiles'][q]['raw_pinball'] for q in ['Q90','Q95','Q99']},
          candidate_delta_PW_minus_P={c:{k:w['results'][c][k]-p['results'][c][k] for k in ['coverage','GPU_coverage','GPU_over_h','GPU_under_sec']} for c in CANDIDATES[2:]})
    write('QUANTILE_CROSSING_AUDIT',crossings);write('UARP_MARGIN_ABLATION',margins);write('SAFE_DURATION_SANITY_AUDIT',safe)
    write('UNIQUE_JOB_SENSITIVITY',dict(diagnostic_only=True,no_reselection=True,results=unique))
    write('DAILY_SAFETY_AUDIT',dict(minimum_N=100,coverage_gate=.88,GPU_coverage_gate=.88,splits=daily))
    write('GPU_WEIGHTED_UNDERPREDICTION',under);write('OVERRESERVATION_AUDIT',over)
    write('WALLTIME_DEPENDENCE_ANALYSIS',dict(primary_track='P',sensitivity='PW',removed_features=['requested_seconds'],
      selected_formula=read('SELECTION_FREEZE')['selected_model'],shared_config=read('HYPERPARAMETER_FREEZE')['selected'],
      winner_reselection=False,NONE_handling='All four already-registered formulas retained for diagnostic comparison; no PW winner.',
      deltas=walltime,importance=read('FEATURE_IMPORTANCE_DIAGNOSTIC'),general_walltime_useless_claim=False))
    for q,values in q_reports.items():
        write(q+'_MODEL_REPORT',dict(model='LightGBM quantile',config=read('HYPERPARAMETER_FREEZE')['selected'],alpha=int(q[1:])/100,
          model_SHA256=file_sha(OUT/'models'/f'P_{q}.txt'),historical_fit_N=len(lib),HIST_TUNE_results=read('HYPERPARAMETER_FREEZE')['results'],
          splits=values,importance=read('FEATURE_IMPORTANCE_DIAGNOSTIC')[q]))
    write('UARP_STYLE_REPORT',dict(name='U1_PUBLISHED_STYLE_ADAPTIVE_RUNTIME',candidate='R5_UARP_STYLE',formula='Q99+max(.20*Q99,.50*sigma)',
      coefficients=[.2,.5],coefficient_tuning=False,upper_cap=False,paper=read('PREREGISTRATION')['paper'],
      margin_decomposition=margins['P'],results={r:read(f'P_{r}_REPORT')['results']['R5_UARP_STYLE'] for r in ROLES},
      interpretation='Literature formula adaptation with historical OOF residual evidence; no guaranteed coverage or scheduler integration claim.'))
    print('All fixed diagnostic artifacts generated; no refit or reselection.',flush=True)

if __name__=='__main__':main()
