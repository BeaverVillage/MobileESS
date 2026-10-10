"""Reload only the exactly owned display host; preserve scientific identities."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, psutil, subprocess, time, urllib.request
import sys
sys.path.insert(0, 'D:/MobileESS_v42_autonomous')
from v42_autonomous.recovery import assert_lease

ROOT = Path('D:/v42_may_restart_20261010_02')
CODE = Path('D:/MobileESS_v42_autonomous')
OUT = ROOT / 'autonomous'

def read(path): return json.loads(Path(path).read_bytes())
def record(path):
    path = Path(path); raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
def identity(pid):
    p = psutil.Process(pid)
    return dict(PID=p.pid, created=p.create_time(), command=p.cmdline(), cwd=p.cwd())
def seal(name, value):
    path = OUT / name; assert not path.exists()
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return record(path)
def api():
    with urllib.request.urlopen('http://127.0.0.1:8794/api/status', timeout=5) as response:
        return json.load(response)
def compact(status):
    return [dict(day=row['day'], **{key:row['B2'].get(key) for key in
        ('status','current_attempt','source_SHA','Native_Runtime','phase','bounds','error')})
        for row in status['rows'][:3]]

lease = read(ROOT / 'REPAIR_LEASE.json'); assert_lease(ROOT, lease['token'])
before_path=OUT/'MONITOR_ASSEMBLED_LB_RELOAD_BEFORE.json'; before_doc=read(before_path); before=record(before_path)
assert before_doc['lease_token']==lease['token']
workers=before_doc['workers']; sup=before_doc['supervisor']; sources=before_doc['sources']
hosts={int(pid):value for pid,value in before_doc['monitors'].items()}
assert set(hosts)=={7340,102084}
for pid in hosts: assert not psutil.pid_exists(pid)
prefixes={key:read(saved['ledger_snapshot']['path'])['calls'] for key,saved in workers.items()}
new_host=read(ROOT/'AUTONOMOUS_MONITOR_SERVER.json')['process']; new=identity(new_host['PID'])
assert new['PID']==105976 and new['created']==new_host['created']
assert new['command']==hosts[102084]['command'] and Path(new['cwd']).resolve()==CODE
status=api(); rows=status['rows'][:3]
assert status['supervisor_alive'] is True and status['live_worker_count']==3
assert all(row['B2']['bounds']['status']=='CERTIFIED' and row['B2']['bounds']['LB']>0 for row in rows)
assert all(row['B2']['source_SHA']=='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14' for row in rows)
listeners={c.pid for c in psutil.net_connections(kind='inet') if c.status=='LISTEN' and c.laddr.ip=='127.0.0.1' and c.laddr.port==8794}
assert listeners=={new['PID']}
observations = {}
for key, saved in workers.items():
    assert identity(saved['process']['PID']) == saved['process']
    assert record(saved['request']['path']) == saved['request']
    ledger = read(saved['original_ledger'])
    assert ledger['calls'][:len(prefixes[key])] == prefixes[key]
    assert ledger['measured_Native_Runtime'] >= saved['measured_Native_Runtime']
    assert ledger['P2_calls'] == 0 and ledger['Native_ceiling_seconds'] == 5400
    observations[key] = dict(exact_process_and_request_preserved=True,
        completed_Native_prefix_preserved=True, current_measured_Native_Runtime=ledger['measured_Native_Runtime'])
assert identity(sup['PID']) == sup
assert all(record(item['path']) == item for item in sources)
receipt = seal('MONITOR_ASSEMBLED_LB_RELOAD_VERIFICATION.json', dict(
    PASS=True, UTC=datetime.now(timezone.utc).isoformat(), before=before, monitor=new,
    rows=compact(status), worker_observations=observations, supervisor=sup, sources=sources,
    scientific_worker_terminate_calls=0, supervisor_terminate_calls=0,
    Native_optimize_calls=0, model_constructions=0, lease_token=lease['token'],
    replaced_exact_owned_monitors=hosts, only_one_actual_listener=True,
    verification_continued_read_only_after_helper03_stale_metadata_psutil_NoSuchProcess=True,
    continuation_helper_process_mutations=0, initial_reload_helper=record(OUT/'reload_owned_monitor_assembled_lb_03.py'),
    URL='http://127.0.0.1:8794/', GUI_render_not_verified=True, final_scientific_PASS_not_claimed=True))
print(json.dumps(dict(PASS=True, receipt=receipt, new_monitor_PID=new['PID'], workers_untouched=True)))
