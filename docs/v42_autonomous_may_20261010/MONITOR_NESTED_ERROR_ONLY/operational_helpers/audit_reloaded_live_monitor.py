"""Read-only independent post-reload monitor audit; no campaign writes/control."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import psutil

ROOT = Path('D:/v42_may_restart_20261010_02')
REPO = Path('D:/MobileESS_v42_autonomous')
OUT = Path(__file__).resolve().parent

def raw_document(path):
    data = path.read_bytes()
    return json.loads(data), dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

def record(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

def identity(pid):
    proc = psutil.Process(pid)
    return dict(PID=proc.pid, created=proc.create_time(), command=proc.cmdline(), cwd=proc.cwd())

started = datetime.now(timezone.utc).isoformat()
prior, prior_rec = raw_document(OUT/'MONITOR_SEALED_SCIENTIFIC_ERROR_AUDIT_02.json')
root_proof, root_rec = raw_document(ROOT/'autonomous/MONITOR_SCIENTIFIC_ERROR_RELOAD_VERIFICATION.json')
before, before_rec = raw_document(ROOT/'autonomous/MONITOR_SCIENTIFIC_ERROR_RELOAD_BEFORE.json')
server, server_rec = raw_document(ROOT/'AUTONOMOUS_MONITOR_SERVER.json')
cp, cp_rec = raw_document(ROOT/'SUPERVISOR_STATE.json')
actual_host = identity(server['process']['PID'])
host_equal = actual_host == root_proof['actual_monitor']
server_identity = all(actual_host[k] == server['process'][k] for k in ('PID','created','command'))
listener = any(item.status == 'LISTEN' and item.laddr.ip == '127.0.0.1' and item.laddr.port == 8794
               for item in psutil.Process(actual_host['PID']).net_connections(kind='inet'))
with urlopen('http://127.0.0.1:8794/api/status', timeout=10) as response:
    HTTP_status = response.status
    api = json.load(response)
codes = [record(Path(item['path'])) for item in prior['code_after']]
original_results = []
for case in prior['actual_cases']:
    saved = case['result']
    document, rec = raw_document(Path(saved['path']))
    original_results.append(dict(day=case['day'], original_record=saved, current_record=rec,
        unchanged=(saved['actual_sha'] == rec['sha256'] and saved['bytes'] == rec['bytes']),
        PASS=document['PASS'], status=document['status'], scientific_error=document['scientific']['error']))

rows = []
for api_row in api['rows'][:6]:
    arm = api_row['B2']
    observation = {key: arm.get(key) for key in
        ('status','worker_status','error','PASS','current_attempt','source_SHA','result','result_SHA')}
    verified_error = None
    if arm.get('result') and arm.get('result_SHA'):
        result, result_rec = raw_document(Path(arm['result']))
        top = result.get('error')
        scientific = result.get('scientific')
        nested = scientific.get('error') if isinstance(scientific, dict) else None
        verified_error = result_rec['sha256'] == arm['result_SHA'] and arm['error'] == (top or nested)
        observation['sealed_result'] = result_rec
    else:
        verified_error = arm.get('error') is None
    rows.append(dict(day=api_row['day'], B2=observation, current_error_matches_own_result=verified_error))

worker_continuity = []
for key, expected in root_proof['workers_exact_identity_preserved'].items():
    try:
        actual = identity(expected['PID'])
        worker_continuity.append(dict(key=key, expected=expected, actual=actual,
            same_exact_identity=actual == expected, absent_now=False))
    except psutil.NoSuchProcess:
        worker_continuity.append(dict(key=key, expected=expected, absent_now=True,
            observation='Exited after the Root reload proof; read-only audit cannot determine exit cause by absence alone.'))
current_workers = []
for key, row in cp.get('workers', {}).items():
    try:
        actual = identity(row['PID'])
        exact = all(actual.get(k) == row.get(k) for k in ('PID','created','command'))
        current_workers.append(dict(key=key, actual=actual, checkpoint_identity_matches=exact))
    except psutil.NoSuchProcess:
        current_workers.append(dict(key=key, checkpoint_PID=row['PID'], absent_now=True))

old_host = before['actual_monitor']
try:
    old_pid_now = identity(old_host['PID'])
    old_exact_still_live = old_pid_now == old_host
except psutil.NoSuchProcess:
    old_pid_now, old_exact_still_live = None, False

checks = dict(root_proof_PASS=root_proof['PASS'] is True,
    root_proof_SHA= root_rec['sha256'] == '65fc7502febb3246de7c37c040d182c9fbaa435066255a0c03917993293fc1ba',
    root_before_SHA=root_proof['before'] == before_rec,
    actual_host_matches_root_proof=host_equal, server_exact_identity=server_identity,
    owned_loopback_listener_8794=listener, old_exact_host_no_longer_live=not old_exact_still_live,
    HTTP_200=HTTP_status == 200, monitor_read_only=api['read_only'] is True,
    code_SHA_matches_tested=codes == prior['code_after'],
    original_first_three_RESULTS_unchanged=all(item['unchanged'] for item in original_results),
    first_six_current_errors_match_own_results=all(item['current_error_matches_own_result'] for item in rows),
    still_live_reload_workers_exact=all(item.get('absent_now') or item['same_exact_identity'] for item in worker_continuity))
receipt = dict(schema='V42_MONITOR_NESTED_ERROR_POST_RELOAD_INDEPENDENT_READ_ONLY_AUDIT_V1',
    PASS=all(checks.values()), started_UTC=started, finished_UTC=datetime.now(timezone.utc).isoformat(),
    checks=checks, earlier_test_receipt=prior_rec, root_reload_verification=root_rec,
    root_before=before_rec, server_receipt=server_rec, checkpoint_read=cp_rec,
    actual_host=actual_host, old_host_identity=old_host, old_PID_current_identity=old_pid_now,
    live_HTTP=dict(status=HTTP_status, snapshot_UTC=api['snapshot_UTC'], first_six=rows,
                   live_worker_count=api['live_worker_count']),
    original_results=original_results, code_records=codes, reload_worker_continuity=worker_continuity,
    current_checkpoint_workers=current_workers,
    operations=dict(read_only=True, process_control_calls=0, campaign_writes=0,
                    scientific_models_constructed=0, Native_optimize_calls=0,
                    audit_output_only=True),
    limitations=['Current API snapshot is time-specific; a newly started Source32 attempt correctly does not expose an older failed attempt as its current error.',
                 'No GUI render verification or final scientific PASS/performance improvement is claimed.',
                 'Only Root historical proof supports exact worker identities at replacement; this audit additionally re-reads identities still live now.'])
target = OUT/'MONITOR_NESTED_ERROR_POST_RELOAD_INDEPENDENT_READ_ONLY_AUDIT.json'
assert not target.exists()
target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps(dict(PASS=receipt['PASS'], checks=checks, receipt=record(target),
    host=actual_host, first_six=[dict(day=item['day'], status=item['B2']['status'],
        attempt=item['B2']['current_attempt'], error=item['B2']['error']) for item in rows]), ensure_ascii=False, indent=2))
raise SystemExit(0 if receipt['PASS'] else 1)
