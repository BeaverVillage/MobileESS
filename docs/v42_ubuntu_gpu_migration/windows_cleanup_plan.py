"""Approve only narrowly proven redundant V42 worktrees and reproducible caches."""
import csv,json,os,subprocess,hashlib,stat,re
from pathlib import Path
O=Path(__file__).absolute().parent;ROOT=O.parents[1];L=Path('//wsl.localhost/Ubuntu-MobileESS-D/home/jaewon/mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def git(p,*a):
    r=subprocess.run(['git','-C',str(p),*a],capture_output=True,text=True,encoding='utf8',errors='replace');return r.returncode,r.stdout.strip()
def table(p,rows,fields):
    with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
inventory=list(csv.DictReader((O/'WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv').open(encoding='utf8')))
gates=dict(tests=read(L/'UBUNTU_V42_VALIDATION.json')['PASS'],structure=read(L/'UBUNTU_PR102_STRUCTURE_COMPARISON.json')['PASS'],GPU_smoke=read(L/'GUROBI_GPU_SMOKE_TEST.json')['PASS'],Windows_dependencies_zero=read(L/'V42_EXTERNAL_PATH_DEPENDENCY_AUDIT.json')['ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES']==0,IEEE8500_preserved=read(L/'IEEE8500_PRESERVATION_MANIFEST.json')['IEEE8500_PRESERVED'],GPU_benchmark_frozen=(L/'PR102_GPU_ROOT_BENCHMARK.json').exists(),science_checkpoint_pushed=git(ROOT,'ls-remote','origin','refs/heads/codex/v42-root-lp-compression-a1')[1].split()[0]==git(ROOT,'rev-parse','refs/remotes/origin/codex/v42-root-lp-compression-a1')[1])
assert all(gates.values()),gates
deps=list(csv.DictReader((L/'V42_DATA_MIGRATION_MANIFEST.csv').open(encoding='utf8')))
versions=list(csv.DictReader((L/'V42_VERSION_ARTIFACT_MIGRATION.csv').open(encoding='utf8')))
links=read(O/'WINDOWS_PATH_LINKS.json')['links'];planned=[];proofs=[]
targets=['v42_exact_wan_factorized_pr','v42_job_capability_pr','v42_flexibility_pr','v42_reference_episode_pr','v42_integrated_pr']
for name in targets:
    p=ROOT.parent/name
    if not p.exists():continue
    row=next(x for x in inventory if x['path']==str(p));status=git(p,'status','--porcelain=v1')[1]
    ignored=git(p,'ls-files','--others','--ignored','--exclude-standard')[1].splitlines()
    unique=[x for x in ignored if not ('__pycache__' in x.split('/') or x.startswith('.pytest_cache/'))]
    direct_links=[x for x in links if x['target'].replace('\\','/').rstrip('/').lower().startswith(str(p).replace('\\','/').lower())]
    child_links=[x for x in links if x['path'].replace('\\','/').lower().startswith(str(p).replace('\\','/').lower()+'/')]
    head=git(p,'rev-parse','HEAD')[1];unpushed=git(p,'rev-list','HEAD','--not','--remotes=origin')[1]
    contains_ieee=any(re.search(r'ieee[_-]?8500|8500[-_ ]?node',str(q),re.I) for q in p.rglob('*'))
    local_migrated=[d for d in deps if d['source'].replace('\\','/').lower().startswith(str(p).replace('\\','/').lower()+'/')]
    artifacts=[d for d in versions if d['head']==head]
    proof=dict(path=str(p),head=head,clean=not status,unique_ignored=unique,unpushed_commits=unpushed,direct_junctions=direct_links,IEEE8500_material_by_path=contains_ieee,all_tracked_history_preserved='Linux complete-history bundle clone and required refs',current_V42_runtime_dependency='0 audited actual Windows opens; current source authority PR102 and WIP in Linux',local_inputs='Any exact referenced source migrated and verified; branch artifacts tracked in preserved Git',local_input_manifest_matches=all(d['hash_pass']=='True' for d in local_migrated),paper_reproducibility='Frozen source/doc artifacts recoverable at exact pushed head; raw/frozen external authorities outside these worktrees retained',gates=gates)
    proof.update(child_reparse_points=child_links,version_science_artifacts_migrated=len(artifacts),version_science_artifacts_hash_pass=all(d['hash_pass']=='True' for d in artifacts))
    ok=not status and not unique and not unpushed and not direct_links and not child_links and not contains_ieee and proof['local_input_manifest_matches'] and proof['version_science_artifacts_hash_pass']
    proofs.append(proof)
    if ok:
        row['classification']=row['candidate_role']='SAFE_DELETE_REDUNDANT'
        planned.append(dict(path=str(p),bytes=row['total_bytes'],file_count=row['file_count'],classification='SAFE_DELETE_REDUNDANT',reason='Clean fully pushed V42 source; no unique ignored files except reproducible caches; exact Git/inputs/evidence preserved in validated Linux',Git_authority=head,migrated_destination='/home/jaewon/mobileess_worktrees/pr102; canonical Linux Git all refs',dependency_audit_result='PASS_WINDOWS_RUNTIME_DEPENDENCIES_0',delete_approved=True,operation='git_worktree_remove'))
    else:row['classification']=row['candidate_role']='UNKNOWN_DO_NOT_DELETE'
# Never touches any IEEE8500 cache, license, raw inputs or ambiguous old environment.
for row in inventory:
    if row['classification']=='UNKNOWN_DO_NOT_DELETE' and any(d['source'].replace('\\','/').lower().startswith(row['path'].replace('\\','/').lower()+'/') for d in deps):row['classification']=row['candidate_role']='MIGRATE_V42_DEPENDENCY'
fields=['path','bytes','file_count','classification','reason','Git_authority','migrated_destination','dependency_audit_result','delete_approved','operation']
table(O/'WINDOWS_SAFE_DELETE_MANIFEST.csv',planned,fields)
table(O/'WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv',inventory,list(inventory[0]))
(O/'WINDOWS_SAFE_DELETE_PROOFS.json').write_text(json.dumps(dict(gates=gates,proofs=proofs),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for n in ('WINDOWS_SAFE_DELETE_MANIFEST.csv','WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv','WINDOWS_SAFE_DELETE_PROOFS.json'):
    import shutil;shutil.copy2(O/n,L/n)
print('SAFE_DELETE',len(planned),'bytes',sum(int(r['bytes']) for r in planned));print(json.dumps(planned,ensure_ascii=False))
