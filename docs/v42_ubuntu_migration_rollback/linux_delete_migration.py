"""Remove only proven new Linux copies after Windows gates; no traversal of source targets."""
import os,csv,json,shutil,stat,hashlib,subprocess,time
from pathlib import Path
H=Path.home();O=Path('/mnt/d/ChatGPT/Mobile ESS 2/v42_root_lp_compression_pr/docs/v42_ubuntu_migration_rollback')
def read(n):return json.loads((O/n).read_text(encoding='utf-8-sig'))
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
assert read('WINDOWS_V42_VALIDATION.json')['PASS'] and read('WINDOWS_PR102_STRUCTURE_COMPARISON.json')['PASS']
assert read('IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json')['PASS'] and read('SCIENTIFIC_WIP_PRESERVATION.json')['UNPUSHED_SCIENTIFIC_WORK']==0
allowed={'mobileess_research/IEEE8500','mobileess_data','mobileess_research/V42_PR102_evidence','mobileess_worktrees/pr102','mobileess_worktrees/root_lp_compression','codex_mobileess_workspace/MobileESS','mobileess_envs/v42_cpu','mobileess_envs/v42_gpu','mobileess_tools/gurobi_cli','.local/bin/mobileess-v42','.local/bin/gurobi_cl'}
rows=list(csv.DictReader((O/'UBUNTU_MIGRATION_DELETE_MANIFEST.csv').open()));deleted=[]
for row in rows:
    p=Path(row['path']);relative=p.relative_to(H).as_posix()
    assert relative in allowed or (p.parent==H/'mobileess_worktrees' and p.name.startswith(('V42_ROOT_LP','PR102_GPU_ROOT','V42_EXACT_'))),p
    assert row['classification']=='MIGRATION_CREATED_DELETE' and p.exists() and not p.is_symlink() and p.resolve()==p
    total=0;count=0;links=0
    items=[p] if p.is_file() else (Path(folder)/n for folder,dirs,names in os.walk(p,followlinks=False) for n in names)
    for q in items:
        s=q.lstat()
        if stat.S_ISREG(s.st_mode):total+=s.st_size;count+=1
        elif stat.S_ISLNK(s.st_mode):links+=1
    assert total==int(row['logical_regular_file_bytes']) and count==int(row['regular_files']),(p,total,count,row)
    row['delete_approved']=True
    print('DELETE_CONFIRMED_MIGRATION_COPY',p,total,flush=True)
    if p.is_dir():shutil.rmtree(p)
    else:p.unlink()
    assert not p.exists();deleted.append(dict(path=str(p),logical_regular_file_bytes_deleted=total,regular_files_deleted=count,symlinks_removed=links,verified_absent=True))
    dump('UBUNTU_MIGRATION_DELETION_RECEIPT.json',dict(deleted=deleted,logical_regular_file_bytes_deleted=sum(r['logical_regular_file_bytes_deleted'] for r in deleted),preexisting_roots_deleted=False,Windows_originals_deleted=0))
with (O/'UBUNTU_MIGRATION_DELETE_MANIFEST.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
ieee=next(r for r in deleted if r['path']==str(H/'mobileess_research/IEEE8500'))
dump('UBUNTU_IEEE8500_DELETION_RECEIPT.json',dict(PASS=True,status='ABORTED_BY_USER_ROLLBACK',copy_removed=True,logical_regular_file_bytes_deleted=ieee['logical_regular_file_bytes_deleted'],objects_and_symlink_store_removed=True,Windows_originals_retained=True,Windows_IEEE8500_files_deleted=0,prior_manifest_files=read('IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json')['total_manifest_files']))
baseline=read('PREEXISTING_UBUNTU_BASELINE.json')
for row in baseline['representative_hashes']:
    p=Path(row['path']);assert p.is_file() and p.stat().st_size==row['bytes']
    with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
for p in baseline['keep_roots']:assert Path(p).is_dir()
subprocess.run(['sync'],check=True)
free=read('WSL_FREE_SPACE_BEFORE_AFTER.json');s=os.statvfs('/');free.update(after_deletion=subprocess.check_output(['df','-B1','/'],text=True),after_statvfs=dict(block_size=s.f_frsize,total_blocks=s.f_blocks,free_blocks=s.f_bfree,available_blocks=s.f_bavail),logical_regular_file_bytes_deleted=sum(r['logical_regular_file_bytes_deleted'] for r in deleted))
dump('WSL_FREE_SPACE_BEFORE_AFTER.json',free)
print('ALL_CONFIRMED_MIGRATION_COPIES_REMOVED',sum(r['logical_regular_file_bytes_deleted'] for r in deleted),flush=True)
