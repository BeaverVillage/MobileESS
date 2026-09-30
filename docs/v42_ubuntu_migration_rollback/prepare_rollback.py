"""Seal cancelled migration evidence and prove Windows originals exist before removal."""
import json,csv,zipfile,hashlib,subprocess,os,time
from pathlib import Path
O=Path(__file__).absolute().parent;R=O.parents[1];M=R/'docs/v42_ubuntu_gpu_migration'
L=Path('//wsl.localhost/Ubuntu-MobileESS-D/home/jaewon');LM=L/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration'
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*a):return subprocess.check_output(['git','-C',str(R),*a],text=True,encoding='utf8',errors='replace').strip()
remote=git('ls-remote','origin','refs/heads/codex/v42-root-lp-compression-a1').split()[0]
assert remote=='bbbf0acb7e92f523550c498197d2c7af917112bf'
assert not git('diff','a88879fdb4e6c51dae35656feee90f68ed19ad8f',remote,'--','v42_root','tests')
assert not git('diff','--','v42_root','tests')
dump('ROLLBACK_PREREGISTRATION.json',dict(MIGRATION_CANCELLED_BY_USER=True,CANONICAL_V42_RUNTIME='WINDOWS',delete_only='Migration-created Linux destinations after Windows validation and original-source verification',preexisting_Linux_and_Windows_research='KEEP',VHD_compaction='Verified registry path, WSL shutdown, supported diskpart with genuine percentage stream',production_A1=False,GPU_for_production=False))
dump('MIGRATION_PROCESS_TERMINATION.json',dict(status='ABORTED_BY_USER_ROLLBACK',migration_jobs_stopped=True,terminated_processes=[],reason='Process inspection after cancellation found no remaining migration worker. Prior copy worker and final reference pipeline already returned completion; no further copy or GPU job was launched.',completed_copy_worker_PID=7609,old_pipeline_cell_session=45750,no_unrelated_process_terminated=True))
dump('SCIENTIFIC_WIP_PRESERVATION.json',dict(remote_head=remote,checkpoint='a88879fdb4e6c51dae35656feee90f68ed19ad8f',scientific_source_diff_from_checkpoint='',UNPUSHED_SCIENTIFIC_WORK=0,scientific_WIP_pushed=True,Windows_HEAD=git('rev-parse','HEAD'),branch=git('branch','--show-current'),status=git('status','--porcelain'),log=git('log','-5','--oneline'),remotes=git('remote','-v')))
archive=O/'ABORTED_MIGRATION_EVIDENCE.zip';files=[]
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for label,base in [('Windows_tooling',M),('Ubuntu_evidence',LM)]:
        for p in sorted(base.iterdir()):
            if not p.is_file() or p.suffix=='.patch':continue
            z.write(p,label+'/'+p.name);files.append(dict(path=str(p),archive_member=label+'/'+p.name,bytes=p.stat().st_size,sha256=sha(p)))
dump('EVIDENCE_ARCHIVE_MANIFEST.json',dict(archive=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),files=files))
for n in ('PR102_GPU_ROOT_BENCHMARK.json','PR102_GPU_ROOT.log'):
    data=(LM/n).read_bytes();(O/n).write_bytes(data)
dump('GPU_BENCHMARK_PRESERVATION.json',dict(PASS=True,benchmark='PR102_GPU_ROOT_BENCHMARK.json',log='PR102_GPU_ROOT.log',GPU_seconds=1938.768148653,prior_CPU_seconds=1557.90,selected_for_production=False,numerical_warnings=True,scientific_policy_result=False))
rows=list(csv.DictReader((LM/'IEEE8500_FILE_MANIFEST.csv').open(encoding='utf8')));missing=[];Windows=0;Linux=0
for i,r in enumerate(rows):
    original=r['original']
    if len(original)>2 and original[1]==':':
        p=Path(original);Windows+=1
    else:
        p=L/original.removeprefix('/home/jaewon/');Linux+=1
    if not p.is_file() or p.stat().st_size!=int(r['bytes']):missing.append(dict(path=original,expected_bytes=r['bytes']))
    if i%10000==0:print('ORIGINAL_AUTHORITY_SIZE_CHECK',i,len(rows),flush=True)
assert not missing,missing
dump('IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json',dict(PASS=True,originals_retained=True,Windows_original_files_checked=Windows,Linux_original_or_Git_backed_reference_files_checked=Linux,total_manifest_files=len(rows),manifest_status='Copy stage had finished before cancellation; overall migration ABORTED_BY_USER_ROLLBACK',copied_logical_bytes=sum(int(r['bytes']) for r in rows),size_checks_PASS=True,Windows_IEEE8500_files_deleted=0,missing=missing,full_initial_hash_receipt='ABORTED_MIGRATION_EVIDENCE.zip/Ubuntu_evidence/IEEE8500_FILE_MANIFEST.csv',source_authority='Existing Windows sources; pre-existing Linux references or Git-backed source also retained independently of copied object store'))
print('ROLLBACK_EVIDENCE_AND_ORIGINALS_PASS',Windows,Linux,archive.stat().st_size,flush=True)
