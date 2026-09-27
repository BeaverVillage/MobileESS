from pathlib import Path
import datetime,hashlib,json
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'tests.log';text=p.read_text(encoding='utf-8')
assert 'Ran 14 tests' in text and text.rstrip().endswith('OK')
with (ROOT/'TEST_RESULTS.json').open('x',encoding='utf-8') as f:
    json.dump(dict(PASS=True,tests=14,time=datetime.datetime.now(datetime.timezone.utc).isoformat(),log_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),f,indent=2)
