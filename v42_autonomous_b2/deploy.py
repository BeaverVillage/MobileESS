"""Evidence-preserving source transition after a provenance-only failed sweep."""
from pathlib import Path
from copy import deepcopy
import argparse
from v42_b2_seed_recovery_v19.common import read,atomic,record,digest,now,process,same_process
from .worker import sources,verify_request

MANIFEST='CONTINUATION_AUTONOMOUS_B2_02_MANIFEST.json'

def deploy(root,commit):
    root=Path(root).resolve();cp=read(root/'SUPERVISOR_STATE.json')
    if (root/MANIFEST).exists():raise PermissionError('DEPLOYMENT_NEVER_RESET')
    if any(same_process(w) for w in cp['workers'].values()):raise PermissionError('NO_LIVE_WORKER_REPLACEMENT')
    old=read(root/'CONTINUATION_V19_MANIFEST.json')
    prior={}
    for d in old['input_folders']:
        if d in ('2025-05-02','2025-05-03'):continue
        a=root/'dates/B2'/d/'attempts/seed_policy_v19_01'
        result=read(a/'RESULT.json');ledger=read(a/'NATIVE_RUNTIME_LEDGER.json')
        if result['status']!='INPUT_FAILURE' or ledger['calls'] or ledger['inflight'] is not None:
            raise PermissionError('PROVEN_NATIVE_ZERO_INPUT_FAILURE_REQUIRED:'+d)
        prior[d]=dict(ledger=record(a/'NATIVE_RUNTIME_LEDGER.json'),result=record(a/'RESULT.json'),
            request=record(a/'request.json'),Native_Runtime=ledger['measured_Native_Runtime'])
    m=deepcopy(old);s=sources()
    m.update(schema='V42_AUTONOMOUS_B2_V20',attempt_id='autonomous_b2_v20_01',source_commit=commit,
        previous_manifest=record(root/'CONTINUATION_V19_MANIFEST.json'),execution_sources=s,execution_SHA=digest(s),
        prior_attempts=prior,provenance_transport_only=True,UTC=now())
    m['attempt_ids']=[f'autonomous_b2_v20_slot{i}_01' for i in (1,2,3)]
    atomic(root/MANIFEST,m)
    from v42_b2_seed_recovery_v19.policy import exact_prior_runtime
    for d,r in prior.items():exact_prior_runtime(r,root=root,day=d)
    atomic(root/'SUPERVISOR_BEFORE_V20.json',cp)
    for k,w in list(cp['workers'].items()):
        from v42_autonomous.supervisor import collect
        collect(root,cp,k,w)
    for d in prior:
        cp['dates']['B2/'+d].update(status='RETRY_READY',previous_result=cp['dates']['B2/'+d].get('result'))
    # No B3 model ever ran in the missing-package dispatches. Preserve exit
    # receipts and give the upcoming qualified B3 implementation fresh attempts.
    for k,v in cp['dates'].items():
        if v['arm']=='B3':v.update(status='PENDING')
    from v42_autonomous.supervisor import transition
    transition(cp,'B2_REPAIR_RUNNING');cp.update(UTC=now())
    atomic(root/'SUPERVISOR_STATE.json',cp)
    return m

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--commit',required=True)
    a=p.parse_args();print(deploy(a.root,a.commit)['execution_SHA'])
