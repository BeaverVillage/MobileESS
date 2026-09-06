from pathlib import Path
from dayahead.v39l.infrastructure import durable_atomic_json as write, read_json as read, sha256_file as sha, now_utc
from dayahead.v40a.invariants import digest

REPO = Path(__file__).resolve().parents[2]
OLD = Path('C:/codex_mobileess_workspace/MobileESS_v39a_causal_aidc')
ROOT = REPO / 'dayahead/artifacts/v40b_v40a_may_launch'
V40A = REPO / 'dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt'
DAYS = tuple(f'2025-05-{n:02d}' for n in range(1,32))
CASES = ('B0','B1','B2','B3')

def audit(base, files):
    drift = {}
    for name, expected in files.items():
        expected = expected['sha256'] if isinstance(expected, dict) else expected
        path = base / name
        actual = sha(path) if path.is_file() else None
        if actual != expected: drift[name] = {'expected':expected, 'actual':actual}
    return {'status':'FAIL' if drift else 'PASS','files_checked':len(files),'drift':drift}
