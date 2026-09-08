"""One expanding, fully mature, out-of-sample residual policy; no model fit."""
from .common import *

def order_statistic(values):
    values=np.asarray(values,float); n=len(values)
    if n==0: return None,None
    k=min(max((17*(n+1)+19)//20,1),n)
    return float(np.partition(values,k-1)[k-1]),k

def effective_availability(frame):
    end=frame.target_day_end.dt.as_unit('ns').astype('int64').to_numpy()
    label=frame.raw_label_available_at.dt.as_unit('ns').astype('int64').to_numpy()
    return np.maximum(end,label)

def rolling(frame,roles):
    outputs=[]; ledger=[]; proofs=[]
    for horizon in HORIZONS:
        hf=frame[frame.horizon==horizon].reset_index(drop=True)
        availability=effective_availability(hf); days=hf.day.to_numpy(); y=hf.target_GPUh.to_numpy()
        group_indices={d:np.flatnonzero(days==d) for d in sorted(hf.day.unique())}
        targets=hf[hf.role.isin(roles)][['day','issue_time','role']].drop_duplicates().sort_values('day')
        for candidate,base_name in [('R85_B1','base_B1_Q90'),('R85_B2','base_B2_Q90')]:
            base=hf[base_name].to_numpy(); residual=np.log1p(y)-np.log1p(np.maximum(base,0))
            previous=set()
            for target in targets.itertuples(index=False):
                issue=target.issue_time.value
                eligible=availability<issue
                assert not ((days>=target.day)&eligible).any()
                assert hf.loc[eligible,'role'].isin(['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']).all()
                if target.role=='CALIBRATION': assert not (hf.loc[eligible,'role']=='EXPOSED_EVALUATION').any()
                library_days=sorted(np.unique(days[eligible])); current=set(hf.loc[eligible,'row_id'].tolist())
                assert previous.issubset(current),'EXPANDING_LIBRARY_CANNOT_SHRINK'
                previous=current
                n=int(eligible.sum()); nd=len(library_days)
                sufficient=(nd>=20 and n>=500) if horizon=='H4' else nd>=30
                q,k=order_statistic(residual[eligible]); delta=max(0.,q) if sufficient else np.nan
                ti=group_indices[target.day]; u=np.expm1(np.log1p(np.maximum(base[ti],0))+delta)
                assert not sufficient or (np.isfinite(u).all() and (u+1e-10*np.maximum(np.abs(base[ti]),1)>=np.maximum(base[ti],0)).all())
                output=hf.iloc[ti][['row_id','day','issue_time','role','horizon','window_start_slot','target_GPUh',
                    'base_B1_Q50','base_B2_Q50','base_B1_Q90','base_B2_Q90','static_U2']].copy()
                output['candidate']=candidate; output['base_upper']=base[ti]; output['rolling_upper']=u
                output['delta']=delta; output['eligible_residual_days']=nd; output['eligible_residual_rows']=n
                output['status']='SUPPORTED' if sufficient else 'INSUFFICIENT_CALIBRATION_SUPPORT'
                outputs.append(output)
                base_summary={'min':float(base[ti].min()),'mean':float(base[ti].mean()),'max':float(base[ti].max())}
                upper_summary={'min':float(u.min()),'mean':float(u.mean()),'max':float(u.max())} if sufficient else {'min':None,'mean':None,'max':None}
                ledger.append({'issue_time':target.issue_time,'target_day':target.day,'role':target.role,'horizon':horizon,
                    'base_family':CANDIDATES[candidate],'candidate':candidate,'eligible_residual_days':nd,'eligible_residual_rows':n,
                    'order_statistic_k':k,'q85_residual':q,'delta':delta,'negative_q85_floored':bool(q is not None and q<0),
                    'base_upper_min':base_summary['min'],'base_upper_mean':base_summary['mean'],'base_upper_max':base_summary['max'],
                    'final_upper_min':upper_summary['min'],'final_upper_mean':upper_summary['mean'],'final_upper_max':upper_summary['max'],
                    'library_first_day':library_days[0] if library_days else None,'library_last_day':library_days[-1] if library_days else None,
                    'latest_included_availability_ns':int(availability[eligible].max()) if n else None,
                    'membership_SHA256':hashlib.sha256(np.asarray(sorted(current),dtype='<i8').tobytes()).hexdigest(),
                    'status':'SUPPORTED' if sufficient else 'INSUFFICIENT_CALIBRATION_SUPPORT'})
                for d in library_days:
                    ri=group_indices[d]
                    assert eligible[ri].all(),'No partially included historical day'
                    first=hf.iloc[ri[0]]
                    proofs.append({'candidate':candidate,'horizon':horizon,'target_day':target.day,'issue_time':target.issue_time,
                        'residual_day':d,'residual_role':first.role,'residual_day_end':first.target_day_end,
                        'raw_label_available_at':first.raw_label_available_at,
                        'effective_available_at':pd.Timestamp(int(availability[ri].max()),tz='UTC'),
                        'residual_rows':len(ri),'source_row_ids_SHA256':hashlib.sha256(np.asarray(sorted(hf.iloc[ri].row_id),dtype='<i8').tobytes()).hexdigest(),
                        'entire_day_included':True,'available_strictly_before_issue':True})
    return pd.concat(outputs,ignore_index=True),pd.DataFrame(ledger),pd.DataFrame(proofs)
