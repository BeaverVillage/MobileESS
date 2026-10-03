"""Strict historical preservation with explicit user-authorized supersessions."""
import subprocess
import hashlib
from functools import lru_cache
from v42_root.common import ROOT,read,sha

ARCHITECTURE_BASE='e2d4779685fff6d0cf022c649733b2ca41fdfc08'
ARCHITECTURE_CHANGES={'.gitattributes','README.md','v42_native/coordinator.py','v42_native/actual.py',
    'v42_final/gates.py','v42_voltage/preservation.py','tests/test_v42_final.py','tests/test_v42_may01.py',
    'tests/v42_benders_fullscale/test_fullscale_orchestration.py',
    'tests/v42_benders_v2/test_v42_native_recourse.py',
    'tests/v42_certificate/test_native_evidence.py','tests/v42_threshold/test_native.py',
    'tests/v42_threshold/test_completion.py'}


def assert_authorized(path,current_sha,previous_sha=None):
    from v42_integrated.supersession import assert_successor as integrated_successor
    if integrated_successor(path,current_sha,previous_sha):return
    from v42_thermal.supersession import assert_successor
    if assert_successor(path,current_sha,previous_sha):return
    successor=ROOT/'docs/v42_day_ahead_planning_direct_dday_actual/AUTHORIZED_ARCHITECTURE_SUPERSESSION.json'
    if path in ARCHITECTURE_CHANGES and successor.is_file():
        manifest=read(successor)
        assert manifest['base_head']==ARCHITECTURE_BASE and not manifest['production_execution_authorized']
        row=next(r for r in manifest['files'] if r['path']==path)
        assert current_sha==row['current_sha256'],'UNSEALED_CURRENT_CHANGE:'+path
        assert row['base_sha256']==hashlib.sha256(baseline_blobs()[path]).hexdigest(),'ARCHITECTURE_BASE_HASH:'+path
        if previous_sha is not None:assert previous_sha in row['historical_sha256'],'BASELINE_HASH_MISMATCH:'+path
        return
    # PR108 successor explicitly authorizes only this optional native hook.
    # Keep old evidence immutable and require the full default-model receipt.
    successor=ROOT/'docs/v42_m1_relaxation_strengthening/AUTHORIZED_HOOK_SUPERSESSION.json'
    if path=='v42_native/mess.py' and successor.is_file():
        row=read(successor)
        regression=read(ROOT/'docs/v42_m1_relaxation_strengthening/DEFAULT_PATH_REGRESSION.json')
        assert row['base_head']=='c9233bd9d3977984e6de31e1d2924f10d1287a84'
        assert row['path']==path and current_sha==row['current_sha256'],'UNSEALED_CURRENT_CHANGE:'+path
        assert regression['PASS'] and regression['native_source_sha256']==current_sha,'DEFAULT_MODEL_REGRESSION_MISSING'
        if previous_sha is not None:assert previous_sha in row['historical_sha256'],'BASELINE_HASH_MISMATCH:'+path
        return
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


@lru_cache(None)
def baseline_blobs():
    entries=subprocess.check_output(['git','ls-tree','-rz',ARCHITECTURE_BASE],cwd=ROOT).split(b'\0')
    rows=[]
    for item in entries:
        if item:
            info,path=item.split(b'\t',1);rows.append((path.decode(),info.split()[2]))
    raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,
        input=b'\n'.join(blob for _,blob in rows)+b'\n')
    position=0;result={}
    for path,blob in rows:
        end=raw.index(b'\n',position);size=int(raw[position:end].split()[2])
        result[path]=raw[end+1:end+1+size];position=end+size+2
    return result


def assert_snapshot(rows):
    """Read-only historical receipt audit, with exact successor SHA allowlist.

    Some inherited receipts hash Windows checkout CRLF while Git stores LF.
    Verify that variant against the immutable base blob; never alter evidence
    or weaken the legacy production verify_inherited/require_scope gates.
    """
    blobs=baseline_blobs()
    for row in rows:
        path=row['path'];base=blobs[path];lf=base.replace(b'\r\n',b'\n')
        variants=(base,lf,lf.replace(b'\n',b'\r\n'))
        assert row['sha256'] in {hashlib.sha256(v).hexdigest() for v in variants},'HISTORICAL_RECEIPT_DRIFT:'+path
        current=(ROOT/path).read_bytes()
        if current not in variants:assert_authorized(path,sha(ROOT/path),row['sha256'])
    return True
