"""Verify the committed RC01 source seals, ledgers and packaged evidence."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.unified_contract import digest

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def main():
    freeze=read(OUT/'SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json')
    assert digest({k:v for k,v in freeze.items() if k!='candidate_sha'})==freeze['candidate_sha']
    assert freeze['state']=='FREEZE_CANDIDATE_PENDING_INTEGRATED_VALIDATION' and not freeze['final_Release_Freeze']
    gates=read(OUT/'RELEASE_GATES.json');assert gates['status']=='CAMPAIGN_BLOCKED_WITH_EXACT_REASONS'
    assert not gates['automatic_start'] and gates['final_release_sha'] is None
    assert read(OUT/'REGRESSION/RESULTS.json')['status']=='PASS'
    checked=0
    for r in freeze['files']:
        assert file_record(r['path'])==r
        rel=Path(r['path']).relative_to(ROOT).as_posix()
        data=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
        assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'];checked+=1
    p1=read(OUT/'A1_P1_120/EXECUTED_ADAPTER_SOURCE.json')
    assert all(file_record(r['path'])==r for r in p1['files']+p1['frozen_planning_Source13'])
    canonical=ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    assert file_record(canonical)['sha256']=='96dafdd5a0f261e2446d66de8070d604c588a8cbf8bfd9e4960f5c20730deadc'
    ledger=read(OUT/'A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json')
    assert ledger['authorization_consumed'] and len(ledger['calls'])==1 and ledger['inflight'] is None
    subprocess.run([sys.executable,str(ROOT/'tools/package_v42_release_evidence.py'),'--verify'],cwd=ROOT,check=True)
    excluded=set(read(OUT/'COMPRESSED_EVIDENCE_MANIFEST.json')['git_plain_large_raw_excluded'])
    artifacts=0
    for p in sorted(OUT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(ROOT).as_posix()
        if rel in excluded:continue
        data=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
        r=file_record(p)
        assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'];artifacts+=1
    print(json.dumps(dict(status='PASS_COMMITTED_SOURCE_AND_EVIDENCE',HEAD=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),checked_new_source_files=checked,
        checked_committed_artifacts=artifacts,
        candidate_sha=freeze['candidate_sha'],final_Release_Freeze=False,Native_calls_this_verification=0),indent=2))

if __name__=='__main__':main()
