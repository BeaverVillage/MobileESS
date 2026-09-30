"""Preserve exact science artifacts before removing clean source worktrees."""
import os,subprocess,csv,hashlib,re
from pathlib import Path
O=Path(__file__).absolute().parent;ROOT=O.parents[1]
rows=[];ext={'.parquet','.npz','.npy','.csv','.gz','.pkl','.json','.png','.svg','.pdf','.dss','.txt','.log'}
for name in ('v42_exact_wan_factorized_pr','v42_job_capability_pr','v42_flexibility_pr','v42_reference_episode_pr','v42_integrated_pr'):
    repo=ROOT.parent/name
    head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    tracked=subprocess.check_output(['git','-C',str(repo),'ls-files'],text=True,encoding='utf8').splitlines()
    for rel in tracked:
        p=repo/rel
        if not p.is_file():continue # Non-materialized sparse Git entries remain in exact Linux Git authority.
        if p.suffix.lower() not in ext:continue
        with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        rows.append(dict(source=str(p),relative_path=rel,head=head,bytes=p.stat().st_size,sha256=digest,destination='/home/jaewon/mobileess_data/frozen_authority/version_worktrees/'+head+'/'+rel,ubuntu_sha256='',hash_pass=False))
with (O/'V42_VERSION_ARTIFACT_MIGRATION.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('VERSION_ARTIFACTS',len(rows),'logical_bytes',sum(int(r['bytes']) for r in rows))
