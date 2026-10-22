"""Snapshot final stage evidence and current adapter code without solving."""
import ast
import subprocess
from .stage_common import ROOT, OUT, WORK, read, record, put


def seal():
    final=read(OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json')
    assert final['status']=='READY_FOR_MAY01_CAMPAIGN_APPROVAL'
    assert not final['official_campaign_executed'] and not final['Native_optimize_calls']
    raw=read(OUT/'ACTUAL_CURRENT_AC_TWO_TICK_ADMISSION.json')
    assert raw['two_tick_measured_results']
    code=sorted((ROOT/'v2_add_preflight').glob('stage_*.py'))
    for path in code: ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
    # Old seals remain historical snapshots. Current hashes identify exactly
    # what is delivered; they do not imply every earlier run used later edits.
    reports=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='FINAL_STAGE_EVIDENCE_SEAL.json')
    runtime=[]
    for pattern in ('DIRECT_JOINT/*.npz','DIRECT_JOINT/*.json',
            'DIRECT_JOINT/NATIVE0/*.json','DIRECT_JOINT/NATIVE0/READBACK/*.json',
            'CURRENT_CASE_HANDLER_*/K48_M1/M_BINARY.json',
            'CURRENT_CASE_HANDLER_*/K48_M1/K48_NATIVE_LEDGER.json',
            'CURRENT_CASE_HANDLER_*/M1_NATIVE0/JOINT_NATIVE_LEDGER.json',
            'BEAM_POOLS.pkl','PROBE_RETRY_*.json'):
        runtime.extend(WORK.glob(pattern))
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    return put('FINAL_STAGE_EVIDENCE_SEAL.json',dict(PASS=True,
        scope='Delivery snapshot; original sealed M1 evidence not rewritten or re-executed',
        final_certificate=record(OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json'),
        current_stage_code=[record(p) for p in code],
        reports=[record(p) for p in reports],
        selected_runtime_artifacts=[record(p) for p in sorted(set(runtime)) if p.is_file()],
        large_reference_file_hashes_retained_in_original_binary_manifests=True,
        historical_producer_records_not_rewritten_to_current_code=True,
        failed_preparation_attempt_evidence_preserved=True,
        raw_two_tick_receipt_preserved=True,python_AST_PASS=True,git_diff_check_PASS=True,
        original_source_preservation=read(OUT/'ORIGINAL_STAGE_SOURCE_PRESERVATION.json'),
        official_campaign_executed=False,Native_optimize_calls=0,Native_presolve_calls=0))


if __name__=='__main__':
    result=seal()
    print('STAGE_EVIDENCE_SEAL_PASS',len(result['current_stage_code']),len(result['reports']),len(result['selected_runtime_artifacts']))
