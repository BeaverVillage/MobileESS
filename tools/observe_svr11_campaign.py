"""Passive, identity-checked campaign/resource observation; no Native calls."""
from pathlib import Path
import sys,json,urllib.request,datetime,sqlite3
import psutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,atomic,now
from v42_svr11.authority import verify
from v42_svr11.processes import live,workers

def run(root):
    root=Path(root);m=verify(root/'CAMPAIGN_MANIFEST.json')
    with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:s=json.load(response)
    assert s['source_SHA']==m['execution_SHA'] and Path(s['root'])==root
    migration=read(root/'MIGRATION_STATUS.json') if (root/'MIGRATION_STATUS.json').exists() else {}
    waiting=migration.get('status')=='WAITING_PREDECESSOR_DRAIN'
    if waiting:
        supervisor=None
        peers=[p for p in migration['predecessor_workers'] if live(p)]
        assert len(peers)<=3
    else:
        supervisor=read(root/'SUPERVISOR_PROCESS.json');assert live(supervisor)
        peers=workers(root,m['execution_SHA']);assert len(peers)<=m['worker_counts'][s['policy']]
    result=dict(UTC=now(),source_SHA=m['execution_SHA'],policy=s['policy'],counts=s['counts'],supervisor_PID=supervisor['PID'] if supervisor else None,migration_status=migration.get('status'),workers=[])
    for w in s['workers']:
        p=psutil.Process(w['PID'])
        owned_root=Path(read(migration['predecessor_manifest']['path'])['root']) if waiting else root
        progress=list((owned_root/'models'/w['day']).rglob('MODEL_GENERATION_PROGRESS.json'))
        v=read(progress[0]) if progress else {}
        result['workers'].append(dict(day=w['day'],PID=p.pid,phase=w['phase'],Native_Runtime=w['Native_Runtime'],
            completed_model_slots=v.get('completed_slots'),model_wall_seconds=v.get('wall_seconds'),RSS_MB=round(p.memory_info().rss/1024**2,1)))
    result['errors']=s['errors']
    result['current_epoch_failures']=[dict(arm=r['arm'],day=r['day'],reason=r.get('reason'),result=r.get('result'))
        for r in s['dates'] if r['status']=='FAIL' and r.get('result') and Path(r['result']).resolve().is_relative_to(root.resolve()/'dates')]
    atomic(root/'LIVE_OBSERVATION.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':run(sys.argv[1])
