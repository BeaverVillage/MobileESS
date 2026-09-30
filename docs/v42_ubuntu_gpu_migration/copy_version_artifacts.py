import csv,hashlib,json,shutil
from pathlib import Path
H=Path.home();O=H/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration';WIN=Path('/mnt/d/ChatGPT/Mobile ESS 2/v42_root_lp_compression_pr/docs/v42_ubuntu_gpu_migration');objects=H/'mobileess_data/frozen_authority/version_objects';objects.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((WIN/'V42_VERSION_ARTIFACT_MIGRATION.csv').open(encoding='utf8')));seen=set();copied=0
for row in rows:
    p=row['source'].replace('\\','/');src=Path('/mnt/'+p[0].lower()+p[2:]);obj=objects/row['sha256']
    if row['sha256'] not in seen:
        if not obj.exists():shutil.copy2(src,obj);copied+=int(row['bytes'])
        with obj.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        assert actual==row['sha256'];assert obj.stat().st_size==int(row['bytes']);seen.add(actual)
    dest=Path(row['destination']);dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():dest.symlink_to(obj)
    row.update(ubuntu_sha256=row['sha256'],hash_pass=True)
with (O/'V42_VERSION_ARTIFACT_MIGRATION.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('VERSION_ARTIFACTS_PRESERVED',len(rows),'copied_bytes',copied)
