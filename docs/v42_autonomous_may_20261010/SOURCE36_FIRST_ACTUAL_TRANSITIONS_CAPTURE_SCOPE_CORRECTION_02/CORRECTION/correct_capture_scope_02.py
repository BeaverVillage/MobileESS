"""Correct documentation interpretation using already captured bytes only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

REPO=Path(r'D:\MobileESS_v42_autonomous')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
BASE=REPO/'docs/v42_autonomous_may_20261010'
OLD=BASE/'SOURCE36_FIRST_ACTUAL_TRANSITIONS'
DEST=BASE/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_CAPTURE_SCOPE_CORRECTION_02'
OUT=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_bytes().decode('utf-8-sig'))
def rec(p):
    raw=Path(p).read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def hashes(paths):return {str(p):rec(p)['sha256'] for p in paths}
def save(p,obj):
    assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf8'));return rec(p)
def main():
    assert not DEST.exists()
    old_inventory=rec(OLD/'SHA_INVENTORY.json')
    assert old_inventory['sha256']=='150c9b49aeec2e63c6c6f7a1136e4c79bc1c6a46333b4674e25fdea8a9639693'
    entries=read(OLD/'SHA_INVENTORY.json')['files']
    old_files={str(OLD/name):ref['sha256'] for name,ref in entries.items()}
    old_files[str(OLD/'SHA_INVENTORY.json')]=old_inventory['sha256']
    assert hashes(old_files)==old_files
    previous=hashes(BASE.rglob('SHA_INVENTORY*.json'))
    m=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
    protected={str(REPO/p):h for p,h in m['builder_original_sources'].items()}
    protected.update({str(REPO/p):h for p,h in m['execution_sources'].items()})
    for v in ('35','36'):
        protected.update({r['path']:r['sha256'] for r in read(ROOT/f'autonomous/V{v}_SPARSE_IMMUTABLE_FREEZE.json')['source_files']})
    assert hashes(protected)==protected
    folder=OLD/'ROOT_READONLY_WATCH/2025-05-01_RMP_COMPUTATIONAL_ENTRY_OBSERVED_20261010T014857270359'
    event=read(folder/'OBSERVATION.json')
    entry=read(folder/'RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json')
    ledger=read(folder/'NATIVE_RUNTIME_LEDGER.json')
    current=read(OLD/'CURRENT_ORIGINAL_READS/SOURCE36_RUNNING/2025-05-01/NATIVE_RUNTIME_LEDGER.json')
    initial_review=read(OLD/'INDEPENDENT_DOC_REVIEW/SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW.json')
    assert event['event']=='RMP_COMPUTATIONAL_ENTRY_OBSERVED' and event['UTC']=='2026-10-10T01:48:57.271362+00:00'
    assert entry['status']=='ABOUT_TO_DELEGATE' and entry['Native_call_completed'] is False
    assert entry['exact_selected_computational_Method']==0 and entry['actual_parameters']['TimeLimit']==30
    assert entry['source']['execution_SHA']=='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
    for raw in (ledger,current):
        assert raw['inflight']['label']=='ONE_RESTRICTED_MASTER' and raw['inflight']['status']=='IN_FLIGHT'
        assert raw['inflight']['requested_seconds']==30 and raw['inflight']['effective_TimeLimit']==30
        assert not any(c.get('label')=='ONE_RESTRICTED_MASTER' for c in raw['calls'])
        assert raw['Native_ceiling_seconds']==5400 and raw['P2_calls']==0
    assert ledger['inflight']==current['inflight']
    state=read(OLD/'INDEPENDENT_TRANSITION_AUDIT/OBSERVED_EVENT_STATE.json')
    assert state['RMP_pre']=={} and state['RMP_complete']=={}
    assert initial_review['first_RMP_event_observed_in_fixed_capture'] is False
    assert initial_review['current_sequential_reads']['2025-05-01']['actual_RMP_call_observed'] is False
    correction=dict(schema='V42_FIRST_ACTUAL_TRANSITIONS_CAPTURE_SCOPE_CORRECTION_V2',UTC=datetime.now(timezone.utc).isoformat(),
      artifact_consistency_verified=True,scientific_PASS_claimed=False,corrects_original_package_inventory=old_inventory,
      original_scope=['2026-10-10T01:49:09+00:00','2026-10-10T01:49:15+00:00'],
      original_raw_bytes_and_old_inventory_preserved=True,
      initial_documentation_claim_error=dict(
        cause='The package producer checked completed calls only, omitted the Native ledger inflight field, and did not classify new RMP watch events added before capture.',
        affected_files=['README.md','INDEPENDENT_DOC_REVIEW/SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW.json'],
        affected_claims=['No first RMP call/event existed in this capture','first_RMP_event_observed_in_fixed_capture=false',
          'current_sequential_reads/2025-05-01/actual_RMP_call_observed=false'],
        prior_guard_assertions_did_not_fail=True,source_science_or_production_failure=False),
      corrected_fixed_capture_facts=dict(
        root_watch_RMP_entry_observed=True,root_watch_event_UTC=event['UTC'],identity=entry['identity'],
        computational_entry_status='ABOUT_TO_DELEGATE',selected_Method=0,original_per_call_seconds=30,
        Native_ledger_IN_FLIGHT_observed=True,Native_ledger_inflight=ledger['inflight'],
        completed_RMP_Native_call_observed=False,finite_Pi_or_RMP_result_observed=False,
        independent_observer_RMP_event_cursor_still_empty=True,
        Native_backend_optimize_entry_or_completion_proved_by_inflight_alone=False,
        Source36_performance_benefit_or_final_scientific_PASS_observed=False),
      unchanged_transition_facts=dict(source35_all3_PASS=False,source35_all3_status='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED',
        source36_birth_dates=['2025-05-01','2025-05-02','2025-05-10'],observed_retry_streak=[1,2,0],
        May03_at_ordinary_event='READY_VERIFIED_REPAIR priority1000, no new PID'),
      limitations=['This correction reads already captured bytes only; it is not a new current production scan.',
        'The earlier package is immutable. Its raw-copy inventory remains valid, but the identified absence statements must be superseded by this correction.',
        'The two original producer folders are not sealed as whole future directories and can append later events.',
        'ABOUT_TO_DELEGATE plus IN_FLIGHT does not prove finite Pi, completed runtime, performance benefit or scientific certification.'],
      model_constructions=0,Native_optimize_calls=0,checker_replays=0,tests=0,production_mutations=0,Git_mutations=0)
    correction_record=save(OUT/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_CAPTURE_SCOPE_CORRECTION_02.json',correction)
    selections=[(OLD/'SHA_INVENTORY.json','ORIGINAL_PACKAGE/SHA_INVENTORY.json'),
      (OLD/'README.md','ORIGINAL_PACKAGE/README_WITH_SUPERSEDED_RMP_ABSENCE_CLAIM.md'),
      (OLD/'COPY_PROVENANCE.json','ORIGINAL_PACKAGE/COPY_PROVENANCE.json'),
      (OLD/'INDEPENDENT_DOC_REVIEW/package_transitions.py','ORIGINAL_PACKAGE/package_transitions.py'),
      (OLD/'INDEPENDENT_DOC_REVIEW/SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW.json','ORIGINAL_PACKAGE/READONLY_DOC_REVIEW_WITH_SUPERSEDED_RMP_ABSENCE_CLAIM.json'),
      (OLD/'INDEPENDENT_TRANSITION_AUDIT/OBSERVED_EVENT_STATE.json','FIXED_CAPTURE/INDEPENDENT_OBSERVER_EVENT_CURSOR.json'),
      (folder/'OBSERVATION.json','FIXED_CAPTURE/RMP_ROOT_WATCH_OBSERVATION.json'),
      (folder/'RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json','FIXED_CAPTURE/RMP_ABOUT_TO_DELEGATE_ENTRY.json'),
      (folder/'NATIVE_RUNTIME_LEDGER.json','FIXED_CAPTURE/RMP_ROOT_WATCH_NATIVE_LEDGER.json'),
      (folder/'request.json','FIXED_CAPTURE/RMP_REQUEST.json'),
      (OLD/'CURRENT_ORIGINAL_READS/SOURCE36_RUNNING/2025-05-01/NATIVE_RUNTIME_LEDGER.json','FIXED_CAPTURE/LATER_SEQUENTIAL_NATIVE_LEDGER.json'),
      (Path(correction_record['path']),'CORRECTION/SOURCE36_FIRST_ACTUAL_TRANSITIONS_CAPTURE_SCOPE_CORRECTION_02.json'),
      (OUT/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_DOC_PACKAGE_SEAL_VERIFICATION.json','ORIGINAL_PACKAGE/RAW_COPY_SEAL_VERIFICATION_WITH_SUPERSEDED_INTERPRETATION.json'),
      (Path(__file__),'CORRECTION/correct_capture_scope_02.py')]
    DEST.mkdir(parents=True)
    copies=[]
    for source,relative in selections:
        dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
        a,b=rec(source),rec(dest);assert all(a[k]==b[k] for k in ('bytes','sha256'))
        copies.append(dict(relative_path=relative,source=a,copy=b))
    (DEST/'README.md').write_bytes(b'''# Correction to the first actual transition capture

Use this correction with SOURCE36_FIRST_ACTUAL_TRANSITIONS. Its original raw
copies and inventory remain unchanged. The earlier absence statements about
the first RMP event/call are superseded: a Root watch event added before the
fixed capture shows May01 RMP ABOUT_TO_DELEGATE, selected Method0 and30 seconds.
Both its saved Native ledger and the later captured ledger show
ONE_RESTRICTED_MASTER IN_FLIGHT. The packaging guard checked completed calls
but omitted inflight and the newly included watch event. This was a document
interpretation error; the actual source event was copied correctly.

The independent observer's saved RMP cursor was still empty. This does not
erase the Root watch event. No completed RMP call/result, finite Pi, repair
performance benefit or final scientific PASS appears in the fixed capture.
IN_FLIGHT alone does not establish actual backend optimize entry or completion.
All original terminal/birth/counter/schema-error evidence remains valid.

This is a correction based only on already captured bytes, with no new current
scan. Original producer folders may append events later. No atomic current
state, final runtime or later Source36 outcome is inferred. Original science,
frozen source trees and every earlier inventory remain unchanged. No Native,
model, scientific checker, test, production mutation or Git command was run.
''')
    (DEST/'.gitattributes').write_bytes(b'* -text\n** -text\n')
    save(DEST/'COPY_PROVENANCE.json',dict(exact_copies=copies,scope='already captured immutable package bytes and external correction only'))
    files={p.relative_to(DEST).as_posix():rec(p) for p in sorted(DEST.rglob('*')) if p.is_file()}
    inv=save(DEST/'SHA_INVENTORY.json',dict(schema='V42_PACKAGE_SHA_INVENTORY_V1',files=files,inventory_self_excluded=True,scientific_PASS_claimed=False))
    assert hashes(old_files)==old_files and hashes(previous)==previous and hashes(protected)==protected
    for relative,ref in files.items():assert rec(DEST/relative)==ref
    result=dict(document_scope_correction_verified=True,original_package_bytes_unchanged=True,
      package=str(DEST),inventory=inv,correction=correction_record,files=len(files)+1,
      payload_bytes=sum(r['bytes'] for r in files.values()),exact_copy_count=len(copies),
      protected_original1007_execution99_frozen35_36_unchanged=True,previous_inventory_count=len(previous),
      Native_optimize_calls=0,model_constructions=0,checker_replays=0,tests=0,production_mutations=0,Git_mutations=0,scientific_PASS_claimed=False)
    result_ref=save(OUT/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_CAPTURE_SCOPE_CORRECTION_02_SEAL_VERIFICATION.json',result)
    print(json.dumps(dict(verification=result_ref,**result)))
if __name__=='__main__':main()
