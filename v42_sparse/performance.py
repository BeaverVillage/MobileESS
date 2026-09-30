"""Fail-closed clean Windows CPU performance gate and immutable source receipt."""
import psutil
from v42_root.common import *

ROLLBACK=ROOT.parent/'v42_root_lp_compression_pr/docs/v42_ubuntu_migration_rollback'
def performance_gate():
    def load(name):return json.loads((ROLLBACK/name).read_text(encoding='utf-8-sig'))
    compaction=load('WSL_VHD_COMPACTION_RECEIPT.json')
    if not compaction.get('PASS') or compaction.get('actual_final_percentage')!=100 or compaction.get('exit_code')!=0:raise ValueError('COMPACTION_NOT_COMPLETE')
    attestation=OUT/'USER_ROLLBACK_COMPLETION.json'
    if attestation.exists():
        if not read(attestation).get('performance_authorized_now'):raise ValueError('USER_COMPLETION_NOT_AUTHORIZED')
        for filename in ['WINDOWS_V42_VALIDATION.json','IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json','ROOT_LP_WIP_WINDOWS_RESTORE.json']:
            if not load(filename).get('PASS'):raise ValueError('ROLLBACK_GATE:'+filename)
        if load('WINDOWS_V42_VALIDATION.json').get('canonical_runtime')!='WINDOWS':raise ValueError('WINDOWS_RUNTIME_NOT_CANONICAL')
    else:
        flags=load('FINAL_FLAGS.json')
        for k in ['WINDOWS_V42_RUNTIME_PASS','WINDOWS_IEEE8500_ORIGINAL_PRESERVED','ROOT_LP_COMPRESSION_WIP_RESTORED_ON_WINDOWS']:
            if flags.get(k) is not True:raise ValueError('ROLLBACK_GATE:'+k)
        if flags.get('CANONICAL_V42_RUNTIME')!='WINDOWS' or flags.get('VHD_COMPACTION_ACTUAL_FINAL_PERCENT')!=100:raise ValueError('ROLLBACK_FLAGS_NOT_COMPLETE')
        if not (ROLLBACK/'FINAL_REVIEW_KO.md').exists() or not (ROLLBACK/'FINAL_VERDICT.json').exists():raise ValueError('FINAL_ROLLBACK_REPORT_NOT_COMPLETE')
    busy=[];own_chain={psutil.Process().pid,*[p.pid for p in psutil.Process().parents()]}
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            if p.pid in own_chain:continue
            name=(p.info['name'] or '').lower();cmd=' '.join(p.info['cmdline'] or [])
            if name=='diskpart.exe' or (name in ('python.exe','pwsh.exe','powershell.exe') and any(s in cmd for s in ['guarded_compact','finalize_rollback.py','rollback_validation','rollback_worker'])):busy.append(p.info)
        except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    if busy:raise ValueError('ROLLBACK_IO_ACTIVE:'+str(busy))
    evidence={name:sha(ROLLBACK/name) for name in ['FINAL_FLAGS.json','FINAL_REVIEW_KO.md','WINDOWS_V42_VALIDATION.json','IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json','ROOT_LP_WIP_WINDOWS_RESTORE.json'] if (ROLLBACK/name).exists()}
    return dict(PASS=True,checked_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),canonical='WINDOWS',GPU=False,rollback_evidence=evidence,user_completion_sha256=sha(attestation) if attestation.exists() else None,compaction_receipt_sha256=sha(ROLLBACK/'WSL_VHD_COMPACTION_RECEIPT.json'),diskpart_active=False,known_rollback_workers_active=False)

def source_freeze():
    frozen();manifest=read(OUT/'SOURCE_MANIFEST.json')
    for row in manifest['sources']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('SOURCE_DRIFT:'+row['path'])
    if sha(OUT/'PREREGISTRATION.json')!=manifest['preregistration_sha256']:raise ValueError('PREREGISTRATION_DRIFT')
    d=read(OUT/'FORMULATION_EXACTNESS.json')
    if not d['PASS'] or any(sha(ROOT/p)!=h for p,h in d['source_sha256'].items()):raise ValueError('EXACTNESS_SOURCE_DRIFT')
    d=read(OUT/'NATIVE_REAL_EQUIVALENCE.json')
    if not d['PASS'] or any(sha(ROOT/p)!=h for p,h in d['source_sha256'].items()):raise ValueError('NATIVE_EQUIVALENCE_SOURCE_DRIFT')
    performance_gate()
