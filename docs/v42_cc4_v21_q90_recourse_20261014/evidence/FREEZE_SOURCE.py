"""Freeze a portable byte identity for C, retaining the original V5 receipt."""
from pathlib import Path
import hashlib,json,subprocess,datetime
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('D:/v42_common_am_qos_integration_20261013')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def freeze():
    prior=json.loads((BASE/'docs/v42_common_am_qos_integration/SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf8'))
    paths={Path(r['path']).relative_to(BASE) for r in prior['files']}
    tracked=[Path(p) for p in subprocess.check_output(['git','ls-files','*.py'],cwd=ROOT,text=True).splitlines() if not p.startswith('docs/')]
    unpopulated=[p.as_posix() for p in tracked if not (ROOT/p).is_file()]
    paths.update(p for p in tracked if (ROOT/p).is_file())
    paths.update(p.relative_to(ROOT) for p in (ROOT/'v42_integration').glob('q90_*.py'))
    paths.update(p.relative_to(ROOT) for p in (ROOT/'tests').glob('test_v42_q90_*.py'))
    paths.add(Path('docs/v42_autonomous_grid_controls_april_b0/audit_sources.py'))
    files=[dict(path=p.as_posix(),sha256=sha(ROOT/p),bytes=(ROOT/p).stat().st_size) for p in sorted(paths)]
    identity=dict(science_version='V42_CC4_V21_Q90_QUEUE_AWARE_RECOURSE_V1',
        base_commit='c6f1a0f41164b7da4afe406dd692abd583a29d1e',files=files)
    value=dict(identity,source_sha=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        original_V5_source_sha=prior['source_sha'],original_V5_files_unchanged=all(sha(Path(r['path']))==r['sha256'] for r in prior['files']),
        snapshot_semantics='ALL_SOURCE_BYTES_AND_TESTS_NOT_OLD_RESULT_CERTIFICATION',
        unpopulated_unexecuted_git_files=unpopulated,
        solver_calls=0,AC_calls=0,campaign31_HOLD=True,B2_B3_M_HOLD=True)
    if not value['original_V5_files_unchanged']:raise ValueError('PRESERVED_V5_SOURCE_DRIFT')
    target=ROOT/'audit/CONTROL_POLICY_SOURCE_SHA_MANIFEST.json'
    target.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(source_sha=value['source_sha'],files=len(files))))
    return value
if __name__=='__main__':freeze()
