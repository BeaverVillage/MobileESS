"""Every completed S0 point and all five causal receipts; read-only, no solve."""
import gzip,pickle,time
import numpy as np,scipy.sparse as sp
from .common import *
def main():
    from v42_pr134_b1.common import verify_freeze,valid_receipt,identity,STAGES
    from v42_pr134_sc.build import replay
    freeze=read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(freeze)
    cp=read(PRODUCTION/'CHECKPOINT.json');days=[d for d,r in cp['dates'].items() if r['status']=='PASS']
    if len(days)!=27:raise ValueError('27_COMPLETE_DATES_REQUIRED')
    results=[]
    for day in sorted(days):
        receipts=[]
        for stage in STAGES:
            saved=cp['stages'][day+'/'+stage];path=Path(saved['receipt']);r=read(path)
            if sha(path)!=saved['sha256'] or not valid_receipt(r,identity(freeze,day,stage),PRODUCTION):raise ValueError('CAUSAL_RECEIPT_DRIFT:'+day+':'+stage)
            receipts.append(record(path))
        folder=PRODUCTION/'stages'/day/'A1'/'1'/'output'
        a=sp.load_npz(folder/'A0_MATRIX.npz');z=dict(np.load(folder/'A0_ATTRIBUTES_CODED.npz'))
        p=dict(np.load(folder/'A2SC_PROOF.npz'));mapping=p['mapping'] if 'mapping' in p else np.cumsum(p['mapping_delta'],dtype=np.int64)
        raw=dict(np.load(folder/'PASS_4_RAW_POINT.npz'))['values'];x=np.zeros(len(mapping));kept=mapping>=0;x[kept]=raw[mapping[kept]]
        audit=replay(a,z,x)
        if not audit['PASS']:raise ValueError('STORED_S0_RAW_WITNESS_REPLAY:'+day)
        results.append(dict(day=day,PASS=True,raw_all_original_rows_bounds_integer_replay=audit,causal_receipts=receipts,
            raw_point=record(folder/'PASS_4_RAW_POINT.npz'),matrix=record(folder/'A0_MATRIX.npz'),attributes=record(folder/'A0_ATTRIBUTES_CODED.npz'),
            source_identity=identity(freeze,day,'A1'),adaptive_decision='STOP_AT_S0',expanded_options=0,optimization_calls=0))
        atomic(OUT/'PASS27_S0_REUSE_AUDIT.json',dict(PASS=len(results)==27,complete_dates=len(results),expected_dates=27,dates=results,
            original_production_source=freeze['Git_SHA'],source_freeze=record(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json'),days_rerun=0,controller_stop_at_S0=True))
        print('S0_REUSE_AUDIT',day,'PASS',len(results),flush=True)
if __name__=='__main__':main()
