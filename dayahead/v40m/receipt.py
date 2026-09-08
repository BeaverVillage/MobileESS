"""Post-commit verification without embedding a commit's own SHA in itself."""
from .forensic import *

def run():
    commit=git('rev-parse','HEAD');assert commit!=START
    allowed=('dayahead/v40m/','dayahead/artifacts/v40m_authority72_closure/')
    paths=git('diff','--name-only',START,commit).splitlines()
    assert paths and all(p.startswith(allowed) for p in paths)
    files=[]
    for path in paths:
        working=(REPO/path).read_bytes()
        blob=subprocess.check_output(['git','-C',str(REPO),'show',commit+':'+path])
        assert working==blob or working.replace(b'\r\n',b'\n')==blob,path
        files.append({'path':path,'working_SHA256':hashlib.sha256(working).hexdigest(),
            'committed_SHA256':hashlib.sha256(blob).hexdigest(),'CRLF_normalization_only':working!=blob})
    state=read(OUT/'V40M_START_STATE.json');after=protected()
    assert after==state['protected_file_sha256']
    transitions=read(OUT/'V40M_AUTHORITY_TRANSITION_MATRIX.json')
    tests=read(OUT/'V40M_TEST_REPORT.json')
    required=['V40M_START_STATE.json','V40M_72_BLOCKER_IDENTITY.json','V40M_AUTHORITY_SOURCE_CENSUS.json',
        'V40M_AUTHORITY_SEARCH_MANIFEST.json','V40M_72_CASE_AUTHORITY_LEDGER.json','V40M_72_CASE_AUTHORITY_LEDGER.parquet',
        'V40M_PRE_DAY_COMPLETE_EVIDENCE.json','V40M_EXECUTION_SITE_EVIDENCE.json','V40M_AUTHORITY_CONFLICTS.json',
        'V40M_AUTHORITY_MISSING_FINAL.json','V40M_AUTHORITY_TRANSITION_MATRIX.json','V40M_PROTECTED_SCOPE_DIFF.json',
        'V40M_TEST_REPORT.json','V40M_FINAL_REVIEW.md']
    assert all((OUT/name).is_file() for name in required)
    write('V40M_FINAL_COMMIT_RECEIPT.json',{'created_at':now(),'starting_commit':START,'final_research_commit':commit,
        'branch':git('branch','--show-current'),'worktree':str(REPO),'classification':transitions['classification'],
        'final_counts':transitions['new'],'resolved_original_72':transitions['resolved_original_72'],
        'original_72_identity':record(OUT/'V40M_72_BLOCKER_IDENTITY.json'),
        'required_artifacts':[record(OUT/name) for name in required],
        'required_artifact_count_including_this_receipt':15,'committed_files':files,
        'source_and_artifact_only_allowlist_changes':True,'protected_files_reverified':len(after),
        'V40L_namespace_accessed_or_modified':False,'tests':tests,'postcommit_byte_verification':'PASS',
        'receipt_commit_semantics':'This receipt is written after the research commit and may be committed in a child commit. It does not contain its own commit SHA.',
        **HOLDS})
    print('POSTCOMMIT PASS',commit,len(files),'files',len(after),'protected hashes',flush=True)

if __name__=='__main__':run()
