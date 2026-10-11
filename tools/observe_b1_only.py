"""Read-only process/ledger observation saved under a unique timestamp."""
from pathlib import Path
import sys,time,json,urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import b1_only_v3 as b

def observe():
    root=b.DEFAULT_ROOT;m=b.verify_only(root);ledger=b.read(root/'CAMPAIGN_LEDGER.json')
    rows=[r for r in ledger['dates'].values() if r['status']=='RUNNING']
    observations=[]
    for r in rows:
        request=b.read(r['request']);p=Path(request['progress']);attempt=Path(request['result']).parent
        observations.append(dict(row=r,worker_live=b.live(r.get('worker',{})),
            actual_worker=b.identity(b.psutil.Process(r['worker']['PID'])) if b.live(r.get('worker',{})) else None,
            progress=b.read(p) if p.exists() else None,
            heartbeat=b.read(attempt/'HEARTBEAT.json') if (attempt/'HEARTBEAT.json').exists() else None,
            native_ledgers=[dict(receipt=b.record(p),contents=b.read(p)) for p in attempt.rglob('NATIVE_RUNTIME_LEDGER.json')]))
    with urllib.request.urlopen('http://127.0.0.1:8801/api/state',timeout=10) as f:monitor=json.load(f)
    before=b.read(root/'PROTECTED_STATE_BEFORE.json');after=b.protected_state()
    state=dict(campaign_id=m['run_id'],scientific_source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],
        manifest=b.record(root/'CAMPAIGN_MANIFEST.json'),source_commit=m['source_commit'],
        campaign_execution_SHA=b.digest(dict(scientific=m['execution_SHA'],operations=m['operations_SHA'],manifest=b.sha(root/'CAMPAIGN_MANIFEST.json'))),
        source_git_HEAD=b.subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        status=ledger['status'],counts=monitor['counts'],running=observations,
        supervisor=b.read(root/'SUPERVISOR_PROCESS.json') if (root/'SUPERVISOR_PROCESS.json').exists() else None,
        supervisor_heartbeat=b.read(root/'SUPERVISOR_HEARTBEAT.json') if (root/'SUPERVISOR_HEARTBEAT.json').exists() else None,
        resource_sample=b.read(root/'CURRENT_RESOURCE_SAMPLE.json') if (root/'CURRENT_RESOURCE_SAMPLE.json').exists() else None,
        original_hold_markers_unchanged=before['hold_markers']==after['hold_markers'],
        original_repository_HEADs_unchanged=before['original_repositories']==after['original_repositories'],
        monitor=monitor,UTC=b.now())
    folder=root/'observations';folder.mkdir(exist_ok=True)
    path=folder/(str(time.time_ns())+'.json');b.atomic(path,state)
    print(json.dumps(dict(snapshot=str(path),status=state['status'],counts=state['counts'],
        workers=[dict(PID=o['row']['worker']['PID'],phase=(o['progress'] or {}).get('phase'),Native_Runtime=(o['progress'] or {}).get('Native_Runtime'),
            call_count=sum(len(x['contents'].get('calls',[])) for x in o['native_ledgers']),
            native_inflight=any(x['contents'].get('inflight') for x in o['native_ledgers'])) for o in observations],
        original_hold_markers_unchanged=state['original_hold_markers_unchanged'])))
    return path

if __name__=='__main__':observe()
