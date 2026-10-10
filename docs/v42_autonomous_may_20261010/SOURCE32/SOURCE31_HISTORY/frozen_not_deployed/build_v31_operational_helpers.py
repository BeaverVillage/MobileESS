"""Create new operational files; preserve all Source30 files verbatim."""
from pathlib import Path
import ast,json

folder=Path('D:/v42_may_restart_20261010_02/autonomous')
names=('freeze_sparse_v30.py','smoke_sparse_v30.py',
       'run_v30_native_denied_regressions.py','prepare_verified_v30_zero_start_retries.py')
for name in names:
    source=(folder/name).read_text(encoding='utf-8')
    updated=source.replace('v30','v31').replace('V30','V31').replace('Source30','Source31')
    if name.startswith('prepare_'):
        updated=updated.replace("expected_unstarted_source=read(root/'B2_V28_ZERO_START_DEPLOYMENT_MANIFEST.json')",
            "expected_unstarted_source=read(root/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')")
        old_reason="Verified same-attempt projection-proof reuse with fresh original bounds/checker per round plus narrowly scoped Presolve0 for the original single30-second RMP call addressing observed presolve/uncrush instability; original fullLP primal basis and120/300/5400 caps, all original matrix/domain/objective/precision/certification preserved."
        new_reason="Verified eligible same-attempt original F1 basis delegated with Method0/LPWarmStart2 to Native presolve after observed Source30 fullLP300-cap/SolCount0; computational candidate performance pending. Existing projection theorem reuse, fresh original bounds/checker, scoped RMP Presolve0 and all original120/300/5400 caps, matrix/domain/objective/precision/certification remain unchanged."
        assert old_reason in updated
        updated=updated.replace(old_reason,new_reason)
    ast.parse(updated)
    target=folder/name.replace('v30','v31')
    assert not target.exists(),target
    target.write_text(updated,encoding='utf-8')
print(json.dumps(dict(PASS=True,created=[name.replace('v30','v31') for name in names],
    production_or_immutable_changes=0,Native_calls=0)))
