"""Create preparation helpers, without executing deployment or queue actions."""
from pathlib import Path
ROOT=Path('D:/v42_may_restart_20261010_02/autonomous')
freeze=(ROOT/'freeze_sparse_v28.py').read_text(encoding='utf-8')
for old,new in [('v42run28','v42run30'),('==96','==98'),('==1108','==1110'),('V28','V30')]:
    freeze=freeze.replace(old,new)
p=ROOT/'freeze_sparse_v30.py';assert not p.exists();p.write_text(freeze,encoding='utf-8')
prepare=(ROOT/'prepare_verified_v28_zero_start_retries.py').read_text(encoding='utf-8')
for old,new in [('v42run28','v42run30'),('V28','V30'),('v28','v30'),('==96','==98')]:
    prepare=prepare.replace(old,new)
old="binding_status='BOUND_TO_IMMUTABLE_V30_CHECKOUT',UTC=now(),"
new="binding_status='BOUND_TO_IMMUTABLE_V30_CHECKOUT',repair_code_root=str(code),UTC=now(),"
assert old in prepare;prepare=prepare.replace(old,new)
old='Verified current-attempt original Native basis transport selects primal Method0/LPWarmStart1 only at the exact original full-LP call, addressing observed Method1 time-cap recurrence while preserving original120/300/5400 budgets, original matrix/domain/objective/precision and independent full certification; prior scoped repairs remain unchanged.'
new='Verified same-attempt projection-proof reuse with fresh original bounds/checker per round plus narrowly scoped Presolve0 for the original single30-second RMP call addressing observed presolve/uncrush instability; original fullLP primal basis and120/300/5400 caps, all original matrix/domain/objective/precision/certification preserved.'
assert old in prepare;prepare=prepare.replace(old,new)
p=ROOT/'prepare_verified_v30_zero_start_retries.py';assert not p.exists();p.write_text(prepare,encoding='utf-8')
print('Created unexecuted future Source30 freeze/binding helpers; no campaign/queue/deployment changes.')
