"""Revise an uncommitted research contract without resetting historical usage."""
from pathlib import Path
import argparse
import json
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.unified_contract import REPORT,load_contracts
from v42_integration.m_engine import _write,file_record
from tools.freeze_v42_unified_contracts import main as freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reason',required=True)
    args=parser.parse_args()
    manifest=load_contracts();ledger_path=REPORT/'UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf8'))
    if ledger.get('inflight'):raise RuntimeError('UNRECONCILED_NATIVE_CONTRACT_REVISION_FORBIDDEN')
    revisions=ledger.setdefault('contract_revisions',[])
    archive=REPORT/'CONTRACT_HISTORY'/f'REVISION_{len(revisions)+1:02d}_BEFORE'
    archive.mkdir(parents=True,exist_ok=False)
    for name in list(manifest['contract_file_shas'])+['SHARED_SOURCE_CASE_MANIFEST.json']:
        shutil.copyfile(REPORT/name,archive/name)
    previous=dict(ledger['identity']);before_calls=json.loads(json.dumps(ledger['calls']))
    # Restore exact per-call historical lineage from the existing immutable
    # result; a changed top-level session is never the historical solve Case.
    s1_path=REPORT/'MESS_2X5_FIRST_FULL_RESULT.json'
    if s1_path.exists():
        s1=json.loads(s1_path.read_text(encoding='utf8'))
        for call in ledger['calls']:
            if call.get('label')=='MESS:S1:EXACT_REDUCED' and not call.get('stage_context'):
                call['stage_context']=dict(unified_bindings=s1['shared_bindings'],
                    reduced_case_sha=s1['reduced_case_sha'],numeric_scope='HISTORICAL_DIAGNOSTIC_AIDC_ANCHOR',
                    lineage_restored_from_existing_result=file_record(s1_path),cost_unchanged=True)
                call['session_identity']=dict(science_sha=s1['shared_bindings']['science_sha'],
                    case_sha=s1['shared_bindings']['case_sha'],session=previous['session'])
    freeze();current=load_contracts()
    ledger['identity']=dict(previous,science_sha=current['bindings']['science_sha'],case_sha=current['bindings']['case_sha'])
    row=dict(reason=args.reason,previous_identity=previous,current_identity=ledger['identity'],
        old_contract_archive=str(archive),Native_usage_reset=False,all_existing_calls_preserved=True,
        used_conservative_seconds=ledger['conservative_solve_seconds'],
        historical_case_results_transferred=False,prior_calls_before_lineage_annotation=before_calls)
    revisions.append(row)
    _write(ledger_path,ledger)
    _write(REPORT/'CONTRACT_REVISION_AUDIT.json',dict(revisions=revisions))


if __name__=='__main__':main()
