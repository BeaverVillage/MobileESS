from pathlib import Path
import hashlib
import json
import subprocess
import sys
import datetime

root = Path(__file__).resolve().parents[1]
receipt = root / 'TEST_RESULTS.json'
assert not receipt.exists()
command = [sys.executable, '-m', 'unittest', 'test_contract', 'test_prepare_targets', '-v']
result = subprocess.run(command, cwd=root, capture_output=True)
payload = result.stdout + result.stderr
with (root / 'tests_final.log').open('xb') as stream: stream.write(payload)
with receipt.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=command,
        returncode=result.returncode, PASS=result.returncode == 0,
        log_sha256=hashlib.sha256(payload).hexdigest()), stream, indent=2)
print(payload.decode(errors='replace'))
sys.exit(result.returncode)
