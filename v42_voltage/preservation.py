"""Strict historical preservation with explicit user-authorized supersessions."""
import subprocess
from v42_root.common import ROOT,read,sha


def assert_authorized(path,current_sha,previous_sha=None):
    audit=read(ROOT/'docs/v42_a1_bootstrap_m1_robust/LEGACY_PRESERVATION_AUDIT.json')
    changed={r['path']:r for r in audit['authorized_changes']}
    assert path in changed,'UNAUTHORIZED_LEGACY_CHANGE:'+path
    row=changed[path]
    assert current_sha==row['current_sha256'],'UNSEALED_CURRENT_CHANGE:'+path
    if previous_sha is not None:assert previous_sha in row['historical_sha256'],'BASELINE_HASH_MISMATCH:'+path


def assert_legacy(rows):
    for row in rows:
        actual=sha(ROOT/row['path'])
        if actual!=row['sha256']:assert_authorized(row['path'],actual,row['sha256'])


def assert_legacy_text(path,old):
    current=(ROOT/path).read_bytes()
    if old.replace(b'\r\n',b'\n')==current.replace(b'\r\n',b'\n'):return
    assert_authorized(path,sha(ROOT/path))
    original=subprocess.check_output(['git','show','bd88de5f5b79df7584519ae0e457ce67d3826b61:'+path],cwd=ROOT)
    assert old.replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n'),'UNAUTHORIZED_PREEXISTING_DRIFT:'+path
