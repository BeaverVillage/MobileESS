"""Seal only this May01 preparation's files; never alter old archives."""
import subprocess
from datetime import datetime,timezone
import psutil
from .may01_common import *

def run():
    init();p=psutil.Process();owned=[];protected=[]
    for q in psutil.process_iter(['name','cmdline']):
        c=q.info['cmdline'] or []
        if q.pid in (p.pid,p.ppid()):continue
        if '-m' in c and any(s.startswith('v2_add_preflight.may01_') for s in c):owned.append(dict(pid=q.pid,command=c))
        elif 'python' in (q.info['name'] or '').lower():protected.append(dict(pid=q.pid,command=c))
    assert not owned
    put('MAY01_RESOURCE_CLOSURE.json',dict(unfinished_owned_processes=owned,other_python_read_only_snapshot=protected,
        available_RAM_bytes=psutil.virtual_memory().available,Native_optimizer_calls=0,workers_forced_to_stop=0,
        RSS_limit_GiB=4,system_reserve_GiB=5,original_workers_ledgers_campaigns_changed=False))
    changed=subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    assert all(n.startswith(('docs/v2_add/may01/','v2_add_preflight/may01_')) for n in changed)
    put('MAY01_SOURCE_AND_PRIOR_EVIDENCE_PRESERVATION.json',dict(base=BASE,original_source=SOURCE,
        all_existing_tracked_files_unchanged=True,method='Initial clean HEAD verified; all subsequent changed paths restricted to new May01 namespace',
        changed_paths=changed,May02_to_07_new_executions=0,source_beta_ratings_objective_algorithms_changed=False,
        new_candidate_winding_parameters='Explicit source-equivalent IDC research hardware candidate; original DY/field cases preserved'))
    files=list(RUN.rglob('*'))
    for folder in (RUNTIME/'phase2').glob('CORRECTION_MAY01_*'):
        if folder.is_dir():files.extend(folder.rglob('*'))
    records=[record(q) for q in sorted(set(files)) if q.is_file()]
    put('MAY01_OWNED_RUNTIME_ARCHIVE.json',dict(root=str(RUN),files=len(records),bytes=sum(r['bytes'] for r in records),
        records=records,old_runtime_files_overwritten=False,large_arrays_in_Runtime=True,
        fixed_M1_reference='Prior FULL96_MATRIX_PORT_PACK, separately sealed in REFERENCE_FULL_MATRIX_SEAL.json'))
    required=['MAY01_VOLTAGE_ROOT_CAUSE_KO.md','MAY01_SVR_HARDWARE_COMPARISON.csv',
        'MAY01_ALL24_PORT_VOLTAGE_CERTIFICATION.json','MAY01_MESS_PQ_TIME_SECURITY.json','FULL_CONSTRAINT_FAMILY_CENSUS.csv',
        'PRESCREENING_PROOF_AND_REMOVED_ROWS.csv','COMPACT_FORMULATION_EQUIVALENCE.json','BEFORE_AFTER_MODEL_SIZE.csv',
        'FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json','MESS8_COMPACT_NATIVE0_BUILD_REPORT.json',
        'MAY01_B0_B1_B2_B3_STAGE_READINESS.json','FINAL_MAY01_PRESTART_REVIEW_KO.md','FINAL_MAY01_PRESTART_GO_NO_GO.json']
    assert all((OUT/n).is_file() for n in required)
    paths=[q for q in OUT.iterdir() if q.is_file() and q.name!='MAY01_EVIDENCE_SHA256_MANIFEST.json']
    paths+=list((ROOT/'v2_add_preflight').glob('may01_*.py'))
    put('MAY01_EVIDENCE_SHA256_MANIFEST.json',dict(UTC=datetime.now(timezone.utc).isoformat(),base=BASE,
        required_deliverables=required,files=[record(q) for q in sorted(paths)],excludes_own_manifest=True,
        source_version='V2_add',PR=236))
    print('SEALED',len(records),'Runtime files',sum(r['bytes'] for r in records),'bytes',flush=True)

if __name__=='__main__':run()
