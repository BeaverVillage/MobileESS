"""Narrow user-authorized retention of the already-validated May-1 B0 freeze."""
import ast
import hashlib
import subprocess
from pathlib import Path
from dayahead.paper_analysis.storage import read
from dayahead.v40a.invariants import digest as source_digest
from dayahead.v40h.identity import verify_file
from .preflight import ROOT,OUT,record
from .reserve import require

ALLOWED_FUNCTIONS={
    'dayahead/v41/execution.py':{'verify_dayahead','actual'},
    'dayahead/v41/release.py':{'pilot_report','freeze_release'},
    'dayahead/v41/campaign.py':{'verify_receipt','phase'},
}
ADDED_ACTUAL_MODULES={'dayahead/v41/actual_audit.py','dayahead/v41/actual_dispatch.py','dayahead/v41/retention.py'}


def unchanged_nodes(source,allowed):
    tree=ast.parse(source)
    def prune(node):
        if hasattr(node,'body') and isinstance(node.body,list):
            node.body=[n for n in node.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name not in allowed]
        for child in ast.iter_child_nodes(node): prune(child)
    prune(tree)
    return ast.dump(tree,include_attributes=False)


def validate(receipt,current_source):
    pre=read(OUT/'V41_B0_DAYAHEAD_RETENTION_PRECHECK.json')
    require(pre['status']=='PASS' and pre['captured_before_Actual_code_change'],'MISSING_PRE_CHANGE_DAYAHEAD_RETENTION_PROOF')
    require(receipt.get('day')=='2025-05-01' and receipt.get('policy')=='B0','ONLY_MAY01_B0_RETENTION_AUTHORIZED')
    require(record(pre['receipt']['path'])==pre['receipt'] and read(pre['receipt']['path'])==receipt,'RETAINED_B0_RECEIPT_DRIFT')
    require(receipt['science']==pre['source'] and receipt['scientific_commit']==pre['producer_commit'],'RETAINED_SOURCE_PROVENANCE_DRIFT')
    old=pre['source']; require(old['manifest_SHA']==source_digest(old['files']),'RETAINED_SOURCE_MANIFEST_CONTENT_DRIFT')
    require(current_source['manifest_SHA']==source_digest(current_source['files']),'CURRENT_SOURCE_MANIFEST_CONTENT_DRIFT')
    old_paths={r['relative_path'] for r in old['files']}; current_paths={r['relative_path'] for r in current_source['files']}
    require(old_paths<=current_paths and current_paths-old_paths<=ADDED_ACTUAL_MODULES,'UNAUTHORIZED_SOURCE_TOPOLOGY_CHANGE')
    changed={}
    for entry in old['files']:
        path=Path(entry['path']); rel=entry['relative_path']; current=record(path)
        if current['sha256']==entry['sha256']:
            verify_file(entry,root=ROOT); continue
        require(rel in ALLOWED_FUNCTIONS,'NON_ACTUAL_SCIENTIFIC_SOURCE_CHANGED:'+rel)
        before=subprocess.check_output(['git','show',pre['producer_commit']+':'+rel],cwd=ROOT)
        require(hashlib.sha256(before).hexdigest()==entry['sha256'] and len(before)==entry['bytes'],'ORIGINAL_COMMIT_BLOB_MISMATCH')
        require(unchanged_nodes(before.decode('utf-8-sig'),ALLOWED_FUNCTIONS[rel])==
                unchanged_nodes(path.read_text(encoding='utf-8-sig'),ALLOWED_FUNCTIONS[rel]),
                'DAYAHEAD_SEMANTICS_CHANGED:'+rel)
        changed[str(path.resolve())]=entry
    for item in pre['full_file_records']: require(record(item['path'])==item,'RETAINED_DAYAHEAD_ARTIFACT_CHANGED')
    return changed


def verify_bound(value,allowed_original_sources):
    """Recheck every input; only the attested old source bytes use Git provenance."""
    seen=set()
    def walk(node):
        if isinstance(node,dict):
            if {'path','bytes','sha256'}<=set(node):
                key=(node['path'],node['bytes'],node['sha256'])
                if key not in seen:
                    old=allowed_original_sources.get(str(Path(node['path']).resolve()))
                    if old is None or any(node[k]!=old[k] for k in ('bytes','sha256')): verify_file(node)
                    seen.add(key)
            if {'manifest_SHA','files'}<=set(node): require(node['manifest_SHA']==source_digest(node['files']),'RETAINED_BOUND_MANIFEST_DRIFT')
            for child in node.values(): walk(child)
        elif isinstance(node,(list,tuple)):
            for child in node: walk(child)
    walk(value)
    return len(seen)


def evidence(receipt,current_source):
    changed=validate(receipt,current_source)
    from .scientific_archive import document
    value=dict(status='PASS',scope='Only the prechecked May-1 B0 DayAhead; original bytes and producer commit retained',
        authority='Final Actual AIDC semantics: physical execution dispatch only, no DayAhead feedback or rerun',
        precheck=record(OUT/'V41_B0_DAYAHEAD_RETENTION_PRECHECK.json'),original_producer_commit=receipt['scientific_commit'],
        current_Actual_source=current_source,changed_existing_files=list(changed),
        unchanged_DayAhead_function_AST=True,unchanged_all_frozen_DayAhead_files=True,
        original_source_git_blobs_verified=True,Actual_metadata_not_claimed_as_DayAhead_producer=True)
    document(OUT/'V41_B0_DAYAHEAD_RETENTION_AUDIT.json',value)
    return value
