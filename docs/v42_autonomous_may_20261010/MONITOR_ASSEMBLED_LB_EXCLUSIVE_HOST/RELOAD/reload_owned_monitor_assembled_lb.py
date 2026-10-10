"""Reload only the exactly owned display host; preserve scientific identities."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, psutil, subprocess, time, urllib.request
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
host = read(ROOT / 'AUTONOMOUS_MONITOR_SERVER.json')['process']
old = identity(host['PID'])
assert old['PID'] == 102084 and old['created'] == host['created'] and old['command'] == host['command']
assert Path(old['cwd']).resolve() == CODE
assert old['command'][0].lower().endswith('pythonw.exe')
assert old['command'][1:] == ['-B','-X','utf8','-m','v42_autonomous_monitor.host',str(ROOT),'--port','8794']
assert any(c.status == 'LISTEN' and c.laddr.ip == '127.0.0.1' and c.laddr.port == 8794
    for c in psutil.Process(old['PID']).net_connections(kind='inet'))
cp = read(ROOT / 'SUPERVISOR_STATE.json'); workers = {}; prefixes = {}
for key, worker in cp['workers'].items():
    actual = identity(worker['PID'])
    assert actual['created'] == worker['created'] and actual['command'] == worker['command']
    assert Path(actual['cwd']).resolve() == Path('D:/v42run35')
    request = Path(worker['request']); req = read(request)
    assert req['implementation_SHA'] == 'a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
    ledger_path = request.parent / 'NATIVE_RUNTIME_LEDGER.json'
    raw = ledger_path.read_bytes(); ledger = json.loads(raw)
    assert ledger['P2_calls'] == 0 and ledger['Native_ceiling_seconds'] == 5400
    saved = OUT / ('MONITOR_ASSEMBLED_LB_PRE_' + key.replace('/','_') + '_NATIVE.json')
    assert not saved.exists(); saved.write_bytes(raw)
    workers[key] = dict(process=actual, request=record(request), ledger_snapshot=record(saved),
        original_ledger=str(ledger_path), measured_Native_Runtime=ledger['measured_Native_Runtime'])
    prefixes[key] = ledger['calls']
assert set(workers) == {'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
supervisor = read(ROOT / 'SUPERVISOR_PROCESS.json'); sup = identity(supervisor['PID'])
assert sup['PID'] == 107788 and sup['created'] == supervisor['created'] and sup['command'] == supervisor['command']
sources = [record(CODE / name) for name in ('v42_autonomous_monitor/monitor.py',
    'v42_autonomous_monitor/current_certificates.py','v42_b2_monitor_v16/certificates.py')]
before = seal('MONITOR_ASSEMBLED_LB_RELOAD_BEFORE.json', dict(
    UTC=datetime.now(timezone.utc).isoformat(), monitor=old, workers=workers, supervisor=sup,
    rows=compact(api()), sources=sources, lease_token=lease['token']))

# The display server is the only process terminated by this helper.
process = psutil.Process(old['PID']); process.terminate(); process.wait(timeout=10)
with (OUT/'monitor_assembled_lb_stdout.log').open('ab') as stdout, (OUT/'monitor_assembled_lb_stderr.log').open('ab') as stderr:
    replacement = subprocess.Popen(old['command'], cwd=CODE, stdin=subprocess.DEVNULL,
        stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
for attempt in range(60):
    try:
        new_host = read(ROOT/'AUTONOMOUS_MONITOR_SERVER.json')['process']; new = identity(new_host['PID'])
        assert new['PID'] == replacement.pid and new['created'] == new_host['created']
        assert new['command'] == old['command'] and Path(new['cwd']).resolve() == CODE
        status = api(); rows = status['rows'][:3]
        assert status['supervisor_alive'] is True and status['live_worker_count'] == 3
        assert all(row['B2']['bounds']['status'] == 'CERTIFIED' for row in rows)
        assert all(row['B2']['source_SHA'] == 'a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14' for row in rows)
        assert all(row['B2']['bounds']['LB'] > 0 for row in rows[:2])
        break
    except (OSError, AssertionError):
        time.sleep(.5)
else:
    raise RuntimeError('OWNED_MONITOR_ASSEMBLED_LB_HTTP_VERIFICATION_REQUIRED')
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
    URL='http://127.0.0.1:8794/', GUI_render_not_verified=True, final_scientific_PASS_not_claimed=True))
print(json.dumps(dict(PASS=True, receipt=receipt, new_monitor_PID=new['PID'], workers_untouched=True)))
