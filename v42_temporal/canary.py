from .common import *
from v42_final.gates import require_a1
from v42_native.supervision import supervise
import os

def main():
    os.environ['PYTHONUTF8']='1'
    require_a1(read(OUT/'MAY01_TS_CC4_RESOURCE_FEASIBILITY.json'))
    sources=[rec(p) for p in (OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json',OUT/'PREREGISTRATION.json',
        OUT/'TS_HIERARCHICAL_BACKOFF_AUTHORITY.json',OUT/'TS_HIERARCHICAL_BACKOFF_LEDGER.csv',
        OUT/'CC4_SERVICE_TIMING_ENVELOPE.csv',OLD/'CC4_EXECUTION_LAG_KERNEL.csv')]
    sources += [rec(p) for directory in ('v42_temporal','v42_native') for p in (ROOT/directory).glob('*.py')]
    folder=LOCAL/'A1'
    if folder.exists():
        old=read(folder/'stage_receipt.json')
        require(old['timeout_reason']=='WORKER_FAILURE' and not (folder/'solver_progress.json').exists(),'NO_SOLVER_RERUN')
        folder=LOCAL/'A1_utf8_repair'
    candidate,receipt=supervise('A1','v42_native.temporal_worker:worker','v42_native.temporal_worker:validator',
        dict(sources=sources),folder,seconds=600)
    dump('A1_SUPERVISOR_RECEIPT.json',receipt);print(receipt)

if __name__=='__main__':main()
