"""Freeze a reviewable candidate and exact scoped delivery paths, not release.

Call only after measurements, regression and lossless packaging are complete.
The generated stage list excludes preserved large plain Raw and unrelated work.
"""
from pathlib import Path
import fnmatch
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest
from v42_integration.release_p1_acceptance import saved_a1

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
RC=BASE/'RC03';FREEZE=RC/'SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json'
INDEX=RC/'DELIVERY_ARTIFACT_INDEX.json'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    if FREEZE.exists() or INDEX.exists():raise FileExistsError('CANDIDATE_AND_DELIVERY_INDEX_MUST_NOT_OVERWRITE')
    regression=read(RC/'REGRESSION/RESULTS.json')
    if regression['status']!='PASS' or regression['baseline_IDs_preserved']!=682:
        raise ValueError('COMPLETE_PRESERVED_REGRESSION_REQUIRED')
    report=(RC/'FINAL_REVIEW_KO.md').read_text(encoding='utf8')
    if '_TO_BE_INSERTED_' in report:raise ValueError('FINAL_REVIEW_PENDING_FIELDS_REMAIN')
    package=read(RC/'EVIDENCE_DELIVERY/COMPRESSED_EVIDENCE_MANIFEST.json')
    if package['status']!='PASS_LOSSLESS_PACKAGING' or package['originals_deleted']:
        raise ValueError('PRESERVED_LOSSLESS_PACKAGE_REQUIRED')
    excluded=set(package['git_plain_large_raw_excluded'])
    patterns=('v42_integration/release_*.py','v42_integration/rc02_*.py','v42_integration/research_presite_*.py',
        'tests/test_v42_release_*.py','tests/test_v42_rc02_*.py','tests/test_v42_research_presite_*.py',
        'tools/*v42_release*.py','tools/*v42_rc02*.py','tools/*v42_rc03*.py',
        'tools/*v42_research*.py','tools/*v42_literature*.py','tools/*v42_production_campaign.py','tools/*v42_campaign_presite*.py')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    sources=sorted({'.gitattributes',*(p for p in untracked if any(fnmatch.fnmatchcase(p,pattern) for pattern in patterns))})
    assert len(sources)>30
    source_records=[file_record(ROOT/p) for p in sources]
    documents=[]
    for directory in ('RC02','RC03'):
        for path in sorted((BASE/directory).rglob('*')):
            if not path.is_file() or path in (INDEX,FREEZE):continue
            relative=path.relative_to(ROOT).as_posix()
            if relative in excluded:continue
            if path.stat().st_size>=100_000_000:raise ValueError('GIT_OBJECT_TOO_LARGE:'+relative)
            documents.append(relative)
    all_paths=sorted(set(sources+documents))
    _write(INDEX,dict(schema='V42_RC02_RC03_EXACT_COMMITTED_ARTIFACT_INDEX_V1',
        committed_records=[file_record(ROOT/p) for p in all_paths],
        preserved_plain_Raw_excluded=sorted(excluded),unrelated_untracked_work_included=False,
        Native_calls=0,Actual_runs=0,AC_calls=0))
    old=read(BASE/'RC01/SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json')
    a1=saved_a1();executed=read(BASE/'RC01/A1_P1_120/EXECUTED_ADAPTER_SOURCE.json')
    protected=old['files']+executed['frozen_planning_Source13']
    protected += [file_record(ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'),
        file_record(BASE/'RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json')]
    protected=list({r['path']:r for r in protected}.values())
    local_originals=a1['immutable_records']
    if any(file_record(r['path'])!=r for r in protected+local_originals):
        raise ValueError('ORIGINAL_SOURCE_LEDGER_OR_A1_SUCCESS_BYTES_DRIFT')
    policy=read(RC/'RELEASE_POLICY_CANDIDATE.json')
    freeze=dict(schema='V42_RELEASE_RECOVERY_RC03_SOURCE_POLICY_SCIENCE_CANDIDATE_V1',
        state='CANDIDATE_PENDING_CURRENT_D0_FULL96_AND_NEW_NATIVE_APPROVAL',final_Release_Freeze=False,
        parent_RC01_commit='6a12d503a9d0984888b3b1e0c7c804fb7bf693ea',
        branch='codex/v42-trajectory-tracking-may01-20261014',Draft_PR=230,
        source_files=source_records,source_sha=digest(source_records),
        policy=file_record(RC/'RELEASE_POLICY_CANDIDATE.json'),policy_sha=digest(policy),
        literature_facts=file_record(RC/'LITERATURE/LITERATURE_FACTS.json'),
        all31_R1_contract_preparation=file_record(RC/'CAMPAIGN_R1_CONTRACTS/MAY31_R1_CONTRACT_PREPARATION.json'),
        protected_original_records=protected,protected_local_original_records=local_originals,
        artifact_index=file_record(INDEX),regression=file_record(RC/'REGRESSION/RESULTS.json'),
        lossless_package=file_record(RC/'EVIDENCE_DELIVERY/COMPRESSED_EVIDENCE_MANIFEST.json'),
        current_D0_M1_A2_M2='NOT_RUN_NEW_NATIVE_APPROVAL_REQUIRED',current_D0_Full96='NOT_RUN',
        current_K48_Global_LB=None,May31_campaign='NOT_RUN',
        ASOF_substep_diagnostic_used_as_official_veto=False,Native_calls_this_freeze=0,P2_calls=0)
    freeze['candidate_sha']=digest(freeze);_write(FREEZE,freeze)
    paths=sorted(set(all_paths+[INDEX.relative_to(ROOT).as_posix(),FREEZE.relative_to(ROOT).as_posix()]))
    stage=ROOT/'runtime/RC03_DELIVERY_STAGE_PATHS.txt';stage.parent.mkdir(parents=True,exist_ok=True)
    stage.write_text('\n'.join(paths)+'\n',encoding='utf8')
    print(json.dumps(dict(status='FROZEN_CANDIDATE_NOT_RELEASE',candidate_sha=freeze['candidate_sha'],
        source_files=len(source_records),delivery_files=len(paths),preserved_plain_raw=len(excluded),
        exact_stage_path_file=str(stage),final_Release_Freeze=False,Native_calls=0),indent=2))


if __name__=='__main__':main()
