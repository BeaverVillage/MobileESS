"""Preserve V41R1 and copy its accepted, uncommitted source into this worktree."""
from pathlib import Path
import hashlib,json,shutil,subprocess,os

OLD=Path('D:/codex_mobileess_workspace/MobileESS_v41r1_premay_voltage_security_margin')
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'dayahead/artifacts/v41r2_780gpu_capacity_rebase'
OUT.mkdir(parents=True,exist_ok=True)
def record(p):
    with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p.resolve()),sha256=h,bytes=p.stat().st_size)
def write(p,v):
    data=(json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode()
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_bytes(data);os.replace(tmp,p)
    assert p.read_bytes()==data

if not (OUT/'V41R1_PRESERVATION.json').exists():
    source=[]
    for folder in ['dayahead','tests']:
        for p in (OLD/folder).rglob('*.py'):
            if set(p.parts)&{'__pycache__','artifacts','cache','original_source'}: continue
            target=ROOT/p.relative_to(OLD);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
            saved=OUT/'original_source'/p.relative_to(OLD);saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,saved)
            source.append(dict(original=record(p),preserved=record(saved)))
    refs={str(p.resolve()):record(p) for p in (OLD/'dayahead/artifacts/v41r1_first_improvement').rglob('*') if p.is_file()}
    freeze=json.loads((OLD/'dayahead/artifacts/v41r1_first_improvement/V41R1_FIRST_IMPROVEMENT_FREEZE.json').read_text())
    for r in freeze['files']:
        p=Path(r['path']); actual=record(p);assert actual==r,(str(p),actual,r)
        refs[str(p.resolve())]=actual
    for folder in ['inputs/2025-05-04','e/20250504','actual_inputs/2025-05-04']:
        for p in (OLD/'frozen_artifacts/v41r1_migration'/folder).rglob('*'):
            if p.is_file():refs[str(p.resolve())]=record(p)
    write(OUT/'V41R1_PRESERVATION.json',dict(transition='V41R1_624GPU -> V41R2_780GPU_CAPACITY_REBASE',
        source=source,frozen_files=list(refs.values()),old_root=str(OLD),new_root=str(ROOT),
        old_git_status=subprocess.check_output(['git','-C',str(OLD),'status','--porcelain'],text=True),
        git_HEAD=subprocess.check_output(['git','-C',str(OLD),'rev-parse','HEAD'],text=True).strip(),Full_May='HOLD'))
    shutil.copyfile('C:/Users/kjw39/.codex/attachments/0ebe4dff-a908-4bb1-82f0-95d7bce26577/pasted-text.txt',OUT/'USER_REQUEST.txt')
    for name in ['bins.parquet','runtime_history.parquet','mature_work_jobs.parquet','CAUSAL_INPUT_RECEIPT.json','H4_AUTHORITY.json','H4_CAP_POOL.json']:
        source=OLD/'frozen_artifacts/v41r1_migration/inputs/2025-05-04'/name
        target=ROOT/'frozen_artifacts/v41r2_780/inputs/2025-05-04'/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    print('PRESERVATION_PASS',len(refs),flush=True)
