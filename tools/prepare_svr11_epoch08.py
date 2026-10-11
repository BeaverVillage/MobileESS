"""Stage the exact I/O fix; freeze complete models after healthy origin drain."""
from pathlib import Path
import sys,shutil,subprocess
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
import prepare_svr11_epoch07 as common
root=Path(r'D:\v42_svr11_may_20261011_08');old=Path(r'D:\v42_svr11_may_20261011_06')
common.root=root;common.old=old

def stage():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    q=record(old/'DISPATCH_QUIESCENCE_FOR_FORECAST_RECEIPT_FIX.json')
    assert read(q['path'])['worker_terminated']==0
    (root/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (old/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,root/'hardware'/p.name)
    atomic(root/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(old/'CAMPAIGN_MANIFEST.json'),source_SHA=read(old/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
        dispatch_quiescence=q,reason='Canonical Forecast receipt identity and exact NPZ field-read cache; healthy origin Workers drain',
        all_old_results_preserved=True,qualified_completed_dates_reused=True,UTC=now()))
    from v42_svr11.prepare import raw
    raw(root)
    shutil.copyfile(old/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json',root/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json')
    print('STAGED; ORIGIN WORKERS PRESERVED')

def ready():
    values={}
    for day in [f'2025-05-{i:02d}' for i in range(1,7)]:
        p=old/'models'/day/'MODEL_GENERATION_PROGRESS.json'
        values[day]=read(p)['completed_slots'] if p.exists() else 0
    print('ORIGIN_MODEL_SLOTS',values)
    return all(n==96 for n in values.values())

def finalize():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists() and ready(), 'WAIT_HEALTHY_ORIGIN_MODELS_96; NO_WORKER_INTERRUPTION'
    # A released model contract is never extended. All six complete models
    # enter this immutable release, including preserved mixed generation SHA.
    common.freeze_slots()
    contract=read(root/'MODEL_CHECKPOINT_REUSE_CONTRACT.json')
    contract['forecast_junction_diagnosis']=record(root/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json')
    atomic(root/'MODEL_CHECKPOINT_REUSE_CONTRACT.json',contract)
    from v42_svr11.prepare import release
    release(root);common.reuse()
    from reuse_svr11_completed import admit_before_first_dispatch
    admit_before_first_dispatch(root)
    print('FROZEN; MIGRATION STILL REQUIRES HEALTHY ORIGIN WORKER DRAIN')

if __name__=='__main__':{'stage':stage,'ready':ready,'finalize':finalize}[sys.argv[1]]()
