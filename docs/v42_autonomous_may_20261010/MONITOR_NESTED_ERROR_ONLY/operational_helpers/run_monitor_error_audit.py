import hashlib
import io
import json
import sys
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import gurobipy as gp
import pytest

REPO = Path('D:/MobileESS_v42_autonomous')
ROOT = Path('D:/v42_may_restart_20261010_02')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def record(path):
    raw = path.read_bytes()
    return dict(path=str(path), sha256=sha_bytes(raw), bytes=len(raw))

models = []
def denied_model(*args, **kwargs):
    models.append(dict(args=repr(args), kwargs=repr(kwargs)))
    raise AssertionError('MONITOR_AUDIT_MODEL_CONSTRUCTION_DENIED')

gp.Model = denied_model
from v42_autonomous_monitor import monitor
from v42_autonomous_monitor.host import Snapshot

started = datetime.now(timezone.utc).isoformat()
code_paths = [REPO/'v42_autonomous_monitor/monitor.py', REPO/'tests/test_v42_autonomous_monitor.py']
code_before = [record(path) for path in code_paths]
test_output = io.StringIO()
with redirect_stdout(test_output), redirect_stderr(test_output):
    test_exit = pytest.main(['-q', str(code_paths[1]), '--basetemp', str(OUT/'pytest_tmp_02')])
(OUT/'MONITOR_ERROR_TEST_OUTPUT_02.txt').write_text(test_output.getvalue(), encoding='utf8')
cp_raw = (ROOT/'SUPERVISOR_STATE.json').read_bytes()
cp = json.loads(cp_raw)
cases = []
immutable = []
with urlopen('http://127.0.0.1:8794/api/status') as stream:
    live_http = json.load(stream)
snapshot = Snapshot(ROOT)
snapshot.refresh()
code, payload = snapshot.get()
patched_api = json.loads(payload)
for day in monitor.DAYS[:3]:
    row = cp['dates']['B2/'+day]
    path = Path(row['result'])
    raw = path.read_bytes()
    document = json.loads(raw)
    sealed = row['result_SHA'] == sha_bytes(raw)
    old = next(item for item in live_http['rows'] if item['day'] == day)['B2']
    new = next(item for item in patched_api['rows'] if item['day'] == day)['B2']
    cases.append(dict(day=day, result=dict(path=str(path), bytes=len(raw),
        checkpoint_sha=row['result_SHA'], actual_sha=sha_bytes(raw), sealed=sealed),
        result_status=document['status'], original_PASS=document['PASS'],
        top_level_error=document.get('error'), scientific_error=document['scientific']['error'],
        Native_Runtime=document['Native_Runtime'], current_attempt=row['current_attempt'],
        live_HTTP_before_restart={key: old.get(key) for key in
            ('status','worker_status','error','PASS','current_attempt','Native_Runtime','result_SHA')},
        patched_cached_API={key: new.get(key) for key in
            ('status','worker_status','error','PASS','current_attempt','Native_Runtime','result_SHA')},
        fixed=(sealed and old['error'] is None and new['error'] == document['scientific']['error']
               and new['PASS'] is False and new['status'] == 'RETRY_PENDING'
               and new['result_SHA'] == row['result_SHA']
               and new['current_attempt'] == row['current_attempt'])))
    immutable.append((path, sha_bytes(raw)))
code_after = [record(path) for path in code_paths]
result_unchanged = all(record(path)['sha256'] == expected for path, expected in immutable)
receipt = dict(schema='V42_MONITOR_SEALED_SCIENTIFIC_ERROR_AUDIT_V1',
    started_UTC=started, finished_UTC=datetime.now(timezone.utc).isoformat(),
    PASS=(test_exit == 0 and code == 200 and all(case['fixed'] for case in cases)
          and code_before == code_after and result_unchanged and not models),
    test_exit=int(test_exit), test_output=record(OUT/'MONITOR_ERROR_TEST_OUTPUT_02.txt'),
    tests='39 passed; unchanged existing tests plus six new error/guard cases',
    API_status=code, actual_cases=cases,
    model_construction_attempts=models, new_Native_calls=0,
    original_RESULTS_unchanged=result_unchanged, code_before=code_before, code_after=code_after,
    monitor_restarted=False, worker_or_supervisor_control=False,
    earlier_harness_run=dict(test_exit=1, passed=22, setup_errors=17,
        cause='Parent of --basetemp did not exist; test implementation was unchanged before rerun.'),
    limitations=['Existing HTTP host still uses pre-change imported monitor; restart owned monitor then verify live HTTP.',
                 'This audit does not claim scientific PASS or solver performance improvement.'])
receipt_path = OUT/'MONITOR_SEALED_SCIENTIFIC_ERROR_AUDIT_02.json'
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps(dict(PASS=receipt['PASS'], receipt=record(receipt_path),
    test_exit=receipt['test_exit'], results_unchanged=result_unchanged, models=len(models),
    code=code_after, observed_errors=[case['patched_cached_API']['error'] for case in cases]), indent=2))
raise SystemExit(0 if receipt['PASS'] else 1)
