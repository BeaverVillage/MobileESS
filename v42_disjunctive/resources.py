from .common import ENV,write
import os
from v42_single_thread.resources import snapshot

def gate(label):
    value=snapshot()
    external=[p for p in value['heavy_processes'] if not p['self']]
    value.update(label=label,environment={k:os.environ.get(k) for k in ENV},
                 PASS=not external and all(os.environ.get(k)=='1' for k in ENV))
    write('RESOURCE_GATE_'+label+'.json',value)
    if not value['PASS']:raise RuntimeError('SINGLE_HEAVY_WORKER_REQUIRED:'+label)
    return value
