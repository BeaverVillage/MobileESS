"""Capture a reproducible focused test receipt without changing experiment code."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
assert not (ROOT / 'TEST_RESULTS.json').exists(), 'TEST_RECEIPT_ALREADY_EXISTS'
command = [sys.executable, '-m', 'unittest', 'test_contract', 'test_request_features', '-v']
result = subprocess.run(command, cwd=ROOT, capture_output=True)
payload = result.stdout + result.stderr
(ROOT / 'tests_final.log').write_bytes(payload)
receipt = dict(time=datetime.now(timezone.utc).isoformat(), command=command,
               returncode=result.returncode, PASS=result.returncode == 0,
               log_sha256=hashlib.sha256(payload).hexdigest())
with (ROOT / 'TEST_RESULTS.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(receipt, stream, indent=2)
print(payload.decode('utf-8', errors='replace'))
raise SystemExit(result.returncode)
