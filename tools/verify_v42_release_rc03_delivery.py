"""Verify published RC03 Git bytes, immutable originals and lossless Raw.

This is a read-only delivery audit. It never starts Native, AC or Actual.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.policy import digest

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC03'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    path=RC/'SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json';freeze=read(path)
    assert freeze['candidate_sha']==digest({k:v for k,v in freeze.items() if k!='candidate_sha'})
    assert freeze['final_Release_Freeze'] is False
    assert freeze['state']=='CANDIDATE_PENDING_CURRENT_D0_FULL96_AND_NEW_NATIVE_APPROVAL'
    index_record=freeze['artifact_index'];assert file_record(index_record['path'])==index_record
    index=read(index_record['path'])
    for record in freeze['protected_local_original_records']:
        assert file_record(record['path'])==record
    records=freeze['source_files']+freeze['protected_original_records']+index['committed_records']
    records += [file_record(path),index_record]
    checked={}
    for record in records:
        name=record['path']
        if name in checked:
            assert checked[name]==record;continue
        assert file_record(name)==record
        relative=Path(name).resolve().relative_to(ROOT).as_posix()
        raw=subprocess.check_output(['git','show','HEAD:'+relative],cwd=ROOT)
        assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256']
        checked[name]=record
    for record in freeze['protected_original_records']:
        relative=Path(record['path']).resolve().relative_to(ROOT).as_posix()
        old=subprocess.check_output(['git','show',freeze['parent_RC01_commit']+':'+relative],cwd=ROOT)
        assert len(old)==record['bytes'] and hashlib.sha256(old).hexdigest()==record['sha256']
    regression=read(RC/'REGRESSION/RESULTS.json')
    assert regression['status']=='PASS' and regression['baseline_IDs_preserved']==682
    assert regression['actual_Native_calls']==0 and not regression['failures'] and not regression['skipped']
    # Hashes above bind the actual committed gzip bytes; streaming roundtrip
    # validation also confirms all preserved local plain originals.
    result=subprocess.run([sys.executable,str(ROOT/'tools/package_v42_release_rc03_evidence.py'),'--verify'],
        cwd=ROOT,text=True,capture_output=True,check=True)
    lossless=json.loads(result.stdout)
    assert lossless['status']=='PASS_LOSSLESS_RECOVERY' and not lossless['originals_deleted']
    print(json.dumps(dict(status='PASS_COMMITTED_RC03_SOURCE_EVIDENCE_AND_LOSSLESS_RAW',
        HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        checked_Git_and_current_files=len(checked),protected_original_files=len(freeze['protected_original_records']),
        regression_tests=regression['tests'],baseline_IDs_preserved=682,
        candidate_sha=freeze['candidate_sha'],final_Release_Freeze=False,
        lossless=lossless,Native_calls=0,AC_calls=0,Actual_runs=0),indent=2))


if __name__=='__main__':main()
