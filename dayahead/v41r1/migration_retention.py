"""Retain the completed, byte-identical May-1 B0 across exact B1 memory changes."""
import hashlib
import subprocess
from pathlib import Path
from dayahead.paper_analysis.storage import read
from dayahead.v40a.invariants import digest
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.reserve import require

PRODUCER='2b0638654d5b2ba88850a02dbe4e42cd9dd53b06'
# B0 evaluates the fixed reference; it never enters either optimizer builder.
# All common/domain/ML/electrical/Actual sources must remain byte identical.
CHANGED={'dayahead/v40g/optimizer.py','dayahead/v41r1/migration_factor.py',
         'dayahead/v41/retention.py','dayahead/v41/solver_observer.py',
         'dayahead/v40a/feedback.py','dayahead/v40h/feedback.py'}
ADDED={'dayahead/v41r1/migration_load.py','dayahead/v41r1/migration_memory.py',
       'dayahead/v41r1/migration_retention.py'}


def validate(receipt,current_source):
    gate_path=OUT/'Q90_BASELINE_RETAINED_B0_GATE.json'
    if gate_path.exists():
        return validate_baseline_revision(receipt,current_source,read(gate_path))
    pre=read(OUT/'V41R1_RETAINED_B0_PRECHECK.json')
    require(pre['status']=='PASS' and pre['producer_commit']==PRODUCER,'B0_RETENTION_AUTHORITY')
    require(record(pre['authorization']['path'])==pre['authorization'],'B0_RETENTION_USER_CONTRACT_DRIFT')
    require(receipt.get('day')=='2025-05-01' and receipt.get('policy')=='B0' and
            receipt['status']=='COMPLETE' and receipt['scientific_commit']==PRODUCER,'ONLY_COMPLETED_MAY01_B0_RETENTION')
    require(any(record(r['path'])==r and read(r['path'])==receipt for r in pre['receipts']),
            'RETAINED_RECEIPT_DRIFT')
    old=pre['source'];require(receipt['science']==old,'RETAINED_PRODUCER_SOURCE_DRIFT')
    for source in (old,current_source):
        require(source['manifest_SHA']==digest(source['files']),'SOURCE_MANIFEST_CONTENT_DRIFT')
    old_paths={r['relative_path'] for r in old['files']}
    new_paths={r['relative_path'] for r in current_source['files']}
    require(old_paths<=new_paths and new_paths-old_paths<=ADDED,'B0_RETENTION_UNAPPROVED_NEW_SOURCE')
    from .migration_factor import verify_gate
    gate=verify_gate()
    gated={str(Path(r['path']).resolve()):r for r in gate['sources']}
    changed={}
    for entry in old['files']:
        rel=entry['relative_path'];path=Path(entry['path']);current=record(path)
        original=subprocess.check_output(['git','show',PRODUCER+':'+rel],cwd=ROOT)
        require(hashlib.sha256(original).hexdigest()==entry['sha256'] and len(original)==entry['bytes'],
                'B0_ORIGINAL_GIT_BLOB_MISMATCH:'+rel)
        if current['sha256']==entry['sha256']:continue
        require(rel in CHANGED,'B0_EXECUTED_SCIENTIFIC_SOURCE_CHANGED:'+rel)
        require(str(path.resolve()) in gated and current==gated[str(path.resolve())],
                'B0_RETENTION_CHANGE_OUTSIDE_VERIFIED_EXACT_GATE:'+rel)
        changed[str(path.resolve())]=entry
    for entry in current_source['files']:
        if entry['relative_path'] in new_paths-old_paths:
            require(record(entry['path'])==gated.get(str(Path(entry['path']).resolve())),
                    'UNGATED_RETENTION_ADDED_MODULE')
    for entry in pre['full_file_records']:
        require(record(entry['path'])==entry,'COMPLETED_B0_ARTIFACT_BYTES_CHANGED')
    return changed


def validate_baseline_revision(receipt,current_source,gate):
    """Retain only enumerated B0 phases with an exactly identical rebuilt input."""
    require(gate['status']=='PASS' and gate['current_source']==current_source,'BASELINE_RETENTION_SOURCE_DRIFT')
    require(receipt.get('policy')=='B0' and receipt.get('status')=='COMPLETE','ONLY_COMPLETED_B0_BASELINE_RETENTION')
    entries=[e for e in gate['receipts'] if e['day']==receipt.get('day') and read(e['receipt']['path'])==receipt]
    require(len(entries)==1,'BASELINE_RECEIPT_NOT_IN_EXACT_RETENTION_GATE')
    entry=entries[0]
    require(record(entry['receipt']['path'])==entry['receipt'],'BASELINE_RETAINED_RECEIPT_DRIFT')
    for ref in entry['input_equality_evidence']+[gate['audit'],gate['proof']]:
        require(record(ref['path'])==ref,'BASELINE_RETENTION_EVIDENCE_DRIFT')
    require(entry['old_reference']['sha256']==entry['new_reference']['sha256'],'BASELINE_REFERENCE_NOT_BYTE_IDENTICAL')
    for ref in (entry['old_reference'],entry['new_reference']):require(record(ref['path'])==ref,'BASELINE_REFERENCE_DRIFT')
    changed={}
    old=receipt['science'];require(old['manifest_SHA']==digest(old['files']),'RETAINED_SOURCE_MANIFEST_DRIFT')
    require(current_source['manifest_SHA']==digest(current_source['files']),'CURRENT_SOURCE_MANIFEST_DRIFT')
    for ref in old['files']:
        original=subprocess.check_output(['git','show',receipt['scientific_commit']+':'+ref['relative_path']],cwd=ROOT)
        require(hashlib.sha256(original).hexdigest()==ref['sha256'] and len(original)==ref['bytes'],'RETAINED_ORIGINAL_GIT_BLOB_DRIFT')
        if record(ref['path'])['sha256']!=ref['sha256']:changed[str(Path(ref['path']).resolve())]=ref
    require(set(changed)<=set(entry['attested_changed_paths']),'BASELINE_UNATTESTED_SOURCE_CHANGE')
    return changed
