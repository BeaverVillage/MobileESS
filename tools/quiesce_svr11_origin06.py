"""Run identity checks from the actual origin checkout; preserve every Worker."""
from pathlib import Path
import sys
origin=Path(r'D:\v42_svr11_may_20261011_06');root=Path(r'D:\v42_svr11_may_20261011_08')
sys.path.insert(0,r'D:\v42_svr11_epoch06_20261011')
import psutil
from v42_pr134_b1.common import read,record,atomic,now,sha
from v42_svr11.authority import verify
from v42_svr11.processes import live,workers
m=verify(origin/'CAMPAIGN_MANIFEST.json');sup=read(origin/'SUPERVISOR_PROCESS.json')
assert live(sup) and sup['source_SHA']==m['execution_SHA']
assert read(origin/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json')['PASS']
proof=read(Path(r'D:\v42_svr11_may_20261011_07\COEFFICIENT_IO_EQUIVALENCE.json'))
assert proof['PASS'] and record(proof['old_loader_source']['path'])==proof['old_loader_source']
assert sha(Path(__file__).resolve().parents[1]/'v42_svr11/model.py')==proof['new_loader_source']['sha256']
root.mkdir(exist_ok=True);atomic(root/'COEFFICIENT_IO_EQUIVALENCE.json',dict(proof,
    original_benchmark=record(Path(r'D:\v42_svr11_may_20261011_07\COEFFICIENT_IO_EQUIVALENCE.json')),
    new_loader_source=record(Path(__file__).resolve().parents[1]/'v42_svr11/model.py')))
peers=workers(origin,m['execution_SHA']);p=psutil.Process(sup['PID']);assert p.status()!=psutil.STATUS_STOPPED
p.suspend()
atomic(origin/'DISPATCH_QUIESCENCE_FOR_FORECAST_RECEIPT_FIX.json',dict(PASS=True,process=sup,root=str(origin),
    source_SHA=m['execution_SHA'],new_dispatch_quiesced=True,worker_terminated=0,current_workers_preserved=peers,
    reason='Correct final Forecast C/D junction receipt identity and exact NPZ read cache in immutable successor',
    diagnosis=record(origin/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json'),UTC=now()))
assert all(live(w) for w in peers)
isolated=Path(r'D:\v42_svr11_may_20261011_07')
ledger=read(isolated/'CAMPAIGN_LEDGER.json');ledger.update(status='SOURCE_EPOCH_ISOLATED',
    reason='Unexecuted candidate failed predecessor inventory admission; never start this root',UTC=now())
atomic(isolated/'CAMPAIGN_LEDGER.json',ledger)
atomic(isolated/'NEVER_EXECUTED_ISOLATION.json',dict(PASS=True,scientific_workers_started=0,
    Native_calls=0,reason=ledger['reason'],manifest=record(isolated/'CAMPAIGN_MANIFEST.json'),UTC=now()))
print('DISPATCH_ONLY_QUIESCED; HEALTHY_WORKERS_PRESERVED',len(peers))
