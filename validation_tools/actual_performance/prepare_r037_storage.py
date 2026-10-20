"""Prepare the reviewed storage layout without dispatching a scientific case."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r037 import operations as op
from v44.common import read,record,verify,atomic,now

def main():
    root=Path('D:/MobileESS_V44/development')
    proof=root/'R037_CHUNK_PROBES_20261018b/RESULT.json'
    regressions=root/'R037_REGRESSIONS_20261018.xml'
    assert read(proof)['PASS'] and len(read(proof)['checks'])==6
    suites=ET.parse(regressions).getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites)==196
    assert all(int(s.attrib['failures'])+int(s.attrib['errors'])==0 for s in suites)
    assert read(op.OPS/'STOP_AUTONOMY.json')['user_dispatch_pause'] is True
    monitors=[]
    for stem in ('collect_watchdog','audit_active_revision'):
        source=op.OPS/(stem+'_r036.py');target=op.OPS/(stem+'_r037.py')
        assert not target.exists()
        text=source.read_text(encoding='utf-8').replace("'v44_recovery_r035','v44_recovery_r036'", "'v44_recovery_r035','v44_recovery_r036','v44_recovery_r037'")
        if stem=='audit_active_revision':
            insertion="if revision=='v44_recovery_r037':\n    value.update(active_row_shared_storage_authorization=record(module.AMENDMENT),active_row_shared_storage_source_sha=digest(module.sources()),raw_layout='V44_EXACT_RAW_ROW_CHUNKS_V1',physical_checks_removed=0)\n"
            text=text.replace('if pending:\n    handover=',insertion+'if pending:\n    handover=')
        target.write_text(text,encoding='utf-8');monitors.append(record(target))
    validation=op.OPS/'R037_CHANGE_AND_VALIDATION.json'
    measurements=[]
    for row in read(proof)['checks']:
        if row['step']=='changed_candidate':
            counts=row['details']['lightweight']['storage_counts']
            measurements.append(dict(arm=row['arm'],tested_prefix_slots=32,
                complete_original_raw_bytes=counts['logical_raw_bytes'],
                new_chunk_and_manifest_bytes=counts['new_compressed_bytes']+counts['manifest_bytes'],
                new_chunks=counts['new_chunks'],shared_rows=counts['reused_chunks'],
                original_complete_raw_restored_byte_exact=True))
    atomic(validation,dict(UTC=now(),PASS=True,tests=196,regressions=record(regressions),
        differential_probe_evidence=record(proof),sources=op.sources(),measurements=measurements,
        storage=dict(layout='CONTENT_ADDRESSED_ZLIB_ROWS_WITH_PER_CANDIDATE_MANIFEST',
            historical_rows_stored_once=True,trajectory_token_factored_out_losslessly=True,
            changed_physical_rows_stored_once_per_exact_content=True,
            original_complete_raw_SHA_and_length_retained=True,independent_Fresh_format_unchanged=True),
        physics_checks_removed=0,native_solves_removed=0,
        existing_raw_paths_or_receipts_rewritten=False,prepared_only=True,
        activation_requires_explicit_user_resume=True,whole_Actual_speedup_measured=False))
    atomic(op.AMENDMENT,dict(UTC=now(),policy=op.POLICY,user_authorized=True,
        user_instruction='저장되는 것들 중 필요 없는 것들 저장하지 말라하고 중복 저장되지 않게 해야 하고. 저장하는 구조도 수정해야 할 것 같은데?',
        wait_instruction='5월 2일 B3 끝나면 다음 날짜 실행하지 말고 대기 해봐.',
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),
        validation=record(validation),monitoring_sources=monitors,
        scope='PREPARE_FUTURE_STORAGE_ONLY_NO_NEW_DATE_UNTIL_EXPLICIT_USER_RESUME'))
    op.validate()
    try:op.require_user_resume()
    except PermissionError:pass
    else:raise AssertionError('USER_DISPATCH_HOLD_MUST_BLOCK_R037')
    request=read(op.OPS/'requests/2025-05-02_B3_attempt015.json')
    with op.install():
        candidate=op.base.decorate(dict(request),read(op.PERMIT));op.authorize(candidate);verify(candidate['sources'])
    verify(request['sources'])
    handoff=read(op.OPS/'CURRENT_HANDOFF.json')
    handoff.update(UTC=now(),prepared_storage_revision='v44_recovery_r037',
        prepared_storage_entry=op.ENTRY,prepared_storage_authorization=record(op.AMENDMENT),
        prepared_storage_validation=record(validation),user_dispatch_pause=True,
        next='Finish May02 B3 and Fresh; clean exact duplicate copies; WAIT. r037 row-shared storage is prepared and validated, with explicit user resume required before any new date.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',handoff)
    atomic(root/'R037_PREPARED_20261018.json',dict(UTC=now(),PASS=True,prepared_revision='v44_recovery_r037',
        active_revision=handoff['active_revision'],pending_revision=handoff['pending_revision'],
        tests=196,user_hold_verified=True,next_date_dispatched=False,measurements=measurements,
        authorization=record(op.AMENDMENT),validation=record(validation)))
    print(dict(PASS=True,prepared_only=True,next_date_dispatched=False,tests=196,measurements=measurements))

if __name__=='__main__':main()
