"""Correct queue accounting of the mandatory first control slot; no selection change."""
from common9 import *
from metrics9 import calibration
import pandas as pd,numpy as np
def main():
    src=ROOT/'PREAPRIL_QUEUE_REPLAY.csv';frame=pd.read_csv(src);before=sha(src);rows=[]
    days=read(ROOT/'EXPERIMENT_PROTOCOL.json')['queue']['days']
    for i in range(1,6):
        folder=LOCAL/f'fold{i}';val=pd.read_parquet(folder/'VALID.parquet');cal=pd.read_parquet(folder/'CAL.parquet');base=pd.read_parquet(folder/'baselines.parquet')
        day=pd.Timestamp(days[i-1],tz='UTC')
        valid=val.submit_time.ge(day)&val.submit_time.lt(day+pd.Timedelta(days=1))&(val.num_gpus_req>0)&(val.num_nodes_req>0)&(val.num_gpus_req<=4*val.num_nodes_req)&(val.num_gpus_req<=780)&(val.requested_seconds>0)&val.num_gpus_req.eq(np.floor(val.num_gpus_req))&val.num_nodes_req.eq(np.floor(val.num_nodes_req))
        for idx,r in frame[frame.fold.eq(i)].iterrows():
            if r.arm=='W0':q=val.requested_seconds.to_numpy()
            elif r.arm in ['B0','Bconst','V8']:q=base[r.arm+'_Q90'].to_numpy()
            else:
                arm,mode=r.arm.split('__');saved=np.load(folder/(arm+'.npz'));d,_=calibration(cal,val,saved['cal_quantiles'],saved['val_quantiles'],mode);q=np.maximum(saved['val_quantiles'][:,3]+d,0)
            mask=valid&q.__eq__(0);extra=float(val.loc[mask,'num_gpus_req'].sum()*.25)
            frame.loc[idx,'reserved_GPUh']+=extra;frame.loc[idx,'minimum_control_slot_N']=int(mask.sum())
            if extra:rows.append(dict(fold=i,arm=r.arm,zero_prediction_jobs=int(mask.sum()),additional_reserved_GPUh=extra))
    frame.to_csv(src,index=False)
    write('QUEUE_ACCOUNTING_CORRECTION.json',dict(time=now(),before_sha256=before,after_sha256=sha(src),changes=rows,
        reason='Forecast queue always allocates min1 control slot including Q90=0. Correct reported queue reservation GPUh to match occupancy.',
        model_selection_changed=False,starts_changed=False,capacity_or_overrun_changed=False,legacy_total_prediction_reservation_metric_unchanged=True,April_opened=False))
if __name__=='__main__':main()
