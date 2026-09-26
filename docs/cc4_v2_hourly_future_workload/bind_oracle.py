"""Bind directly reconstructed atomic targets to all frozen PR57 May H4 windows."""
from common import *


if __name__=='__main__':
    manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    oldpath=next(Path(s['path']) for s in manifest['sources'] if s['purpose']=='PR59 target and 71-feature lineage')
    oracle=next(Path(s['path']).parent for s in manifest['sources'] if s['purpose']=='PR57 immutable ceiling finding')
    z=np.load(oldpath)
    frozen=pd.read_csv(oracle/'CC4_ALL_MAY_WINDOWS.csv',float_precision='round_trip')
    errors=[]
    for day,g in frozen.groupby('date'):
        i=np.flatnonzero(z['days']==day)[0]
        y=np.lib.stride_tricks.sliding_window_view(z['atomic'][i],16).sum(-1)
        actual=g.sort_values('window_index').Y_k_GPUh.to_numpy()
        require(len(actual)==81,'oracle population')
        error=float(abs(y-actual).max())
        require(error<1e-7,'PR57 target mismatch')
        errors.append(dict(day=day,N_windows=81,max_abs_error_GPUh=error))
    require(len(frozen)==2511 and len(errors)==31,'oracle day count')
    require(json.loads((ROOT/'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))['status']=='PASS','raw bridge failed')
    dump('RAW_PR57_BRIDGE.json',dict(status='PASS',frozen_source=source_record(oracle/'CC4_ALL_MAY_WINDOWS.csv','all PR57 target windows'),
        reconstructed_atomic_source_sha256=sha(oldpath),raw_atomic_audit_sha256=sha(ROOT/'TARGET_RECONSTRUCTION_AUDIT.json'),
        N_windows=len(frozen),N_days=len(errors),max_abs_error_GPUh=max(x['max_abs_error_GPUh'] for x in errors),
        days=errors,May21='retained; raw target agrees with stored final score despite missing contributor table'))
    print('RAW -> PR59 atomic -> PR57 H4: PASS',max(x['max_abs_error_GPUh'] for x in errors))
