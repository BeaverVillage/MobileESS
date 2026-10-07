"""Exact V2 source successor seals; historical production gates stay closed."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='1e2d819406081af5b4bbee6fab3c4b5c3e102b2b'
CHECKPOINT='b4e061bdf2416eccd7aa2a42b3761db1affce8c1'
ARCHITECTURE_BASE='e2d4779685fff6d0cf022c649733b2ca41fdfc08'
RECEIPT=ROOT/'docs/v42_a_stage_fast_active_domain_20261007/AUTHORIZED_V2_SOURCE_SUPERSESSION.json'
# Every inherited source edit is explicitly scoped. New modules have no old
# source seal to supersede and are frozen separately by the execution permit.
CHANGES=frozenset('''
.gitattributes
v42_bootstrap/a1.py
v42_boundary/model.py
v42_boundary/resource.py
v42_compact/execute.py
v42_compact/formulation.py
v42_compact/native.py
v42_exact/native.py
v42_exact/worker.py
v42_final/checkpoint_resource_check.py
v42_final/resource_check.py
v42_integrated/a1.py
v42_native/__init__.py
v42_native/actual.py
v42_native/aidc.py
v42_native/planning.py
v42_native/solver.py
v42_native/stage_worker.py
v42_native/supervision.py
v42_pr134_adaptive/capacity_master.py
v42_pr134_adaptive/minimum_probe.py
v42_pr134_adaptive/restricted.py
v42_pr134_adaptive/solve_snapshot.py
v42_pr134_b1/coordinator.py
v42_pr134_b1/native.py
v42_pr134_b1/replay.py
v42_pr134_b1/worker.py
v42_pr134_may19/production.py
v42_pr134_may19/solve.py
v42_pr134_repair/certificate.py
v42_pr134_repair/original_diagnosis.py
v42_pr134_sc/build.py
v42_pr134_sc/materialize.py
v42_pr134_sc/snapshot.py
v42_root/eliminate.py
v42_root/factor.py
v42_root/native.py
v42_root/start.py
v42_root/worker.py
v42_single_thread/a1.py
v42_temporal/native.py
v42_temporal/resource.py
v42_two/production.py
v42_voltage/a1.py
v42_voltage/preservation.py
'''.split())
ADMIN_BASE_FACTS=frozenset(('.gitignore','README.md'))


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def variants(data):
    lf=data.replace(b'\r\n',b'\n')
    return sorted({digest(data),digest(lf),digest(lf.replace(b'\n',b'\r\n'))})


@lru_cache(None)
def historical_sources(path):
    commits=git('log','--format=%H',BASE,'--',path).decode().splitlines()
    rows=[]
    for commit in dict.fromkeys([BASE,*commits]):
        raw=subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True)
        if raw.returncode:continue
        rows.append(dict(git_commit=commit,blob_sha256=digest(raw.stdout),variant_sha256=variants(raw.stdout)))
    return rows


def current_diff(path):
    return git('-c','core.autocrlf=false','diff','--no-ext-diff','--no-color','--no-renames','--binary',BASE,'--',path)


def attribute_provenance(base):
    old=git('show',ARCHITECTURE_BASE+':.gitattributes')
    required={'v42_a_stage_domain_v2/** -text',
        'docs/v42_a_stage_domain_authority_v2_20261007/** -text',
        'docs/v42_a_stage_v2_stress4_20261007/** -text','tests/test_v42_a_stage*.py -text'}
    assert required.issubset(set((ROOT/'.gitattributes').read_text().splitlines())), 'V2_EXACT_BYTE_ATTRIBUTES_REQUIRED'
    return dict(architecture_base=ARCHITECTURE_BASE,architecture_base_sha256=digest(old),
        preexisting_BASE_difference=old!=base,
        preexisting_architecture_to_BASE_diff_sha256=digest(git('diff','--no-ext-diff','--no-color','--binary',ARCHITECTURE_BASE,BASE,'--','.gitattributes')),
        current_exact_byte_attributes_verified=True)


def admin_base_provenance(path,base):
    current=(ROOT/path).read_bytes();lf=base.replace(b'\r\n',b'\n')
    exact_variants=(base,lf,lf.replace(b'\n',b'\r\n'))
    assert current in exact_variants and not current_diff(path),'V2_ADMIN_REQUIRES_UNCHANGED_EXACT_BASE:'+path
    return dict(base_transport_sha256=variants(base),
        canonical_LF_sha256=digest(lf),current_is_exact_BASE_blob=current==base,
        current_is_verified_BASE_line_ending_transport=current!=base,
        source_content_changed_from_BASE=False)


def _row(path):
    if path not in CHANGES|ADMIN_BASE_FACTS or not RECEIPT.is_file():return None
    manifest=json.loads(RECEIPT.read_text(encoding='utf8'))
    assert manifest['schema']=='A_STAGE_V2_EXACT_SOURCE_SUPERSESSION_V1'
    assert manifest['PASS'] is True
    assert manifest['exact_base']==BASE and manifest['checkpoint_head']==CHECKPOINT
    assert manifest['historical_production_gates_unchanged'] is True
    assert manifest['supersession_grants_production_execution'] is False
    rows=manifest['files'];assert len({r['path'] for r in rows})==len(rows)
    assert all(r['path'] in CHANGES|ADMIN_BASE_FACTS for r in rows),'UNSCOPED_V2_SUCCESSOR_PATH'
    row=next((r for r in rows if r['path']==path),None)
    if row is None:return None
    base=git('show',BASE+':'+path)
    assert row['base_sha256']==digest(base),'V2_EXACT_BASE_SHA:'+path
    assert row['historical_blob_sources']==historical_sources(path),'V2_HISTORY_PROVENANCE:'+path
    expected=sorted(set().union(*(r['variant_sha256'] for r in historical_sources(path))))
    assert row['historical_sha256']==expected,'V2_HISTORY_ALLOWLIST:'+path
    assert row['base_to_current_diff_sha256']==digest(current_diff(path)),'V2_UNSEALED_DIFF:'+path
    assert row['current_sha256']==digest((ROOT/path).read_bytes()),'V2_UNSEALED_CURRENT_CHANGE:'+path
    if path in ADMIN_BASE_FACTS:
        assert row['source_policy']=='UNCHANGED_EXACT_BASE_ADMIN_FACT','V2_ADMIN_POLICY:'+path
        for key,value in admin_base_provenance(path,base).items():
            assert row.get(key)==value,'V2_ADMIN_BASE_PROVENANCE:'+key
    if path=='.gitattributes':
        for key,value in attribute_provenance(base).items():
            assert row.get(key)==value,'V2_ATTRIBUTE_PROVENANCE:'+key
    return row


def assert_successor(path,current_sha,previous_sha=None):
    row=_row(path)
    if row is None:return False
    assert current_sha==row['current_sha256'],'V2_CURRENT_SHA_MISMATCH:'+path
    if previous_sha is not None:
        assert previous_sha in row['historical_sha256'],'V2_UNVERIFIED_HISTORICAL_SHA:'+path
    return True


def assert_historical_source(path,previous_sha):
    """Prove inherited receipts against exact ancestor blobs, including BASE drift."""
    row=_row(path)
    if row is None:return False
    assert previous_sha in row['historical_sha256'],'V2_UNVERIFIED_HISTORICAL_SHA:'+path
    return True


def seal(output=None):
    """Root calls once after source finalization; this is never a run permit."""
    rows=[]
    for path in sorted(CHANGES|ADMIN_BASE_FACTS):
        base=git('show',BASE+':'+path);history=historical_sources(path)
        diff=current_diff(path)
        if path in ADMIN_BASE_FACTS:
            admin=admin_base_provenance(path,base)
        elif not diff:continue
        row=dict(path=path,base_sha256=digest(base),current_sha256=digest((ROOT/path).read_bytes()),
            base_to_current_diff_sha256=digest(diff),historical_blob_sources=history,
            historical_sha256=sorted(set().union(*(r['variant_sha256'] for r in history))),
            source_policy='UNCHANGED_EXACT_BASE_ADMIN_FACT' if path in ADMIN_BASE_FACTS else 'EXPLICIT_V2_SOURCE_EDIT')
        if path in ADMIN_BASE_FACTS:row.update(admin)
        if path=='.gitattributes':
            row.update(attribute_provenance(base))
        rows.append(row)
    result=dict(PASS=True,schema='A_STAGE_V2_EXACT_SOURCE_SUPERSESSION_V1',exact_base=BASE,checkpoint_head=CHECKPOINT,
        authorization='User attachments 1732fc8f-dd30-4565-b224-1e78d407194a, 83d71f06-2de3-49fa-b6d4-555df7f05ff9, b2130dd9-8835-4610-906a-08b0585231ef',
        historical_production_gates_unchanged=True,supersession_grants_production_execution=False,
        preserved_historical_receipts_modified=False,files=rows)
    target=Path(output) if output is not None else RECEIPT
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
    return result


if __name__=='__main__':seal()
