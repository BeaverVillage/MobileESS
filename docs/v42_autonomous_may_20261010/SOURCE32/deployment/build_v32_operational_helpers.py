"""Prepare separate Source32 helper files; immutable prior sources stay intact."""
from pathlib import Path
import ast,json
folder=Path('D:/v42_may_restart_20261010_02/autonomous')
names=('freeze_sparse_v31.py','smoke_sparse_v31.py','prepare_verified_v31_zero_start_retries.py')
for name in names:
    original=(folder/name).read_text(encoding='utf-8')
    text=original.replace('v31','v32').replace('V31','V32').replace('Source31','Source32').replace('SOURCE31','SOURCE32').replace('v42run31','v42run32')
    if name.startswith('prepare_'):
        old='Verified eligible same-attempt original F1 basis delegated with Method0/LPWarmStart2 to Native presolve after observed Source30 fullLP300-cap/SolCount0; computational candidate performance pending.'
        new='Verified canonical CLI dispatch retains exact original ReceiptDateBudget class/delegate identities after reproduced Source30 duplicate-module RMP entry failure, and eligible same-attempt F1 basis uses Method0/LPWarmStart2 after Source30 fullLP300-cap/SolCount0. Computational performance and complete date PASS pending.'
        assert old in text;text=text.replace(old,new)
    ast.parse(text)
    target=folder/name.replace('v31','v32');assert not target.exists()
    target.write_text(text,encoding='utf-8')
print(json.dumps(dict(PASS=True,created=[n.replace('v31','v32') for n in names],Native_calls=0,models=0)))
