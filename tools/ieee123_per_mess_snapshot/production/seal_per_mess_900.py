"""Fail-closed preproduction gate and complete before/after scientific hashes."""
import sys,time,ast
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W))
from v41r4_windows_paths import install_long_file_operations
install_long_file_operations()
from fast_prepare import read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_900_namespace import OUT,RUN,ACTUAL
from v41r4_per_mess_budget import CONTRACT,CONTRACT_SHA
E=R/'manifests/per_mess_900s'
before=read(E/'SCIENTIFIC_AND_REUSE_BEFORE.json');assert before['status']=='PASS'
differences=[]
for row in before['files']:
    current=record(row['path'])
    if current!=row:differences.append(dict(before=row,after=current))
write_json(E/'SCIENTIFIC_HASH_PRESERVATION.json',dict(status='PASS' if not differences else 'FAIL',
    files=len(before['files']),differences=differences,checked_at=time.time(),
    note='Scientific code, mapping, PCC, electrical authority, workload, traffic, physical/objective/ranking coefficients byte-exact'))
assert not differences,differences[:3]
checks=['REGRESSION.json','FLEET_LOOP_INTEGRATION.json','REAL_CERTIFICATE_CONVERSION.json',
    'SCIENTIFIC_HASH_PRESERVATION.json','CHECK_B2_PASS.json','CHECK_B3_PASS.json','CHECK_B1_PASS.json','CHECK_ACTUAL_PASS.json']
checks += ['may05_physics_fix/REAL_REJECTION_REGRESSION.json','may05_physics_fix/RECOVERY_REGRESSION.json']
for name in checks:assert read(E/name)['status']=='PASS',name
files=[*W.glob('v41r4_900_*.py'),W/'v41r4_per_mess_budget.py',R/'entry_per_mess_900.py']
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'))
value=dict(status='IEEE123_MESS_PER_VEHICLE_15MIN_BUDGET_PASS',at=time.time(),
    contract=CONTRACT,runtime_budget_contract_SHA=CONTRACT_SHA,runtime_files=[record(p) for p in files],
    independent_display_files=[record(R/'monitor_per_mess_900.ps1')],
    evidence=[record(E/name) for name in checks],scientific_files_unchanged=len(before['files']),
    output=str(RUN),actual_output=str(ACTUAL),day_workers=4,Gurobi_threads=4,
    B0='REUSE_ALL_31_PLANNING_FRESH; REUSE_COMPLETED_ACTUAL; RUN_ONLY_MISSING_ACTUAL',
    B1='REUSE_MAY01_08; NEW_MAY09_31_AS_USER_CLARIFIED; COMPLETE_MISSING_ACTUAL',
    B2='NEW_DECISIONS_MAY01_31',B3='B1_A0_REUSE; M1_ONCE_NEW; A1_MF_FRESH_ACTUAL_NEW',
    old_search_decisions_reused=False,old_candidate_cache_imported=False,
    old_IEEE123_workers_stopped=read(E/'TERMINATION_COMPLETE.json'),
    unequal_B3_B2_objectives_not_a_stop_condition=True)
write_json(OUT/'IEEE123_MESS_PER_VEHICLE_15MIN_BUDGET_PASS.json',value)
write_json(E/'IEEE123_MESS_PER_VEHICLE_15MIN_BUDGET_PASS.json',value)
print(value['status'],CONTRACT_SHA,flush=True)
