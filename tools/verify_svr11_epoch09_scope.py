"""Prove this physical successor preserves every Native/model execution module."""
from pathlib import Path
import sys,json
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
root=Path(r'D:\v42_svr11_may_20261011_09');old=Path(r'D:\v42_svr11_may_20261011_08')
m=verify(root/'CAMPAIGN_MANIFEST.json');origin=read(old/'CAMPAIGN_MANIFEST.json')
changed=sorted(k for k in set(m['execution_sources'])|set(origin['execution_sources']) if m['execution_sources'].get(k)!=origin['execution_sources'].get(k))
assert changed==['v42_svr11/authority.py','v42_svr11/freeze.py','v42_svr11/migration.py','v42_svr11/prepare.py']
assert all(m[k]==origin[k] for k in ('algorithm_version','native_M_limit_seconds','native_A_limit_seconds',
    'Threads','P2_calls','policy_order','worker_counts','FAIL_CONTINUE','original_transformer_current_authority',
    'M_acceptance','M_gap_certificate_required','Actual_reoptimization','Actual_PQ_repair','Planning_taps_copied_to_Actual'))
assert 'model_checkpoint_reuse_contract' not in m and m['previous_equipment_dates_or_models_promoted']==0
a=read(origin['scenario']['path'])['svr']['units'];b=read(m['scenario']['path'])['svr']['units']
fields={'cut_terminal','original_bus_spec','series_orientation','upstream_new_bus','engineering_assumptions'}
assert len(a)==len(b)==11
for x,y in zip(a,b):
    assert x['id']==y['id']
    assert x==y if x['id']!='BUS82' else {k:v for k,v in x.items() if k not in fields}=={k:v for k,v in y.items() if k not in fields}
out=dict(PASS=True,changed_sources=changed,only_one_existing_bank_placement_changed=True,
    Native_and_model_execution_modules_byte_identical=True,policy_budgets_and_constraints_preserved=True,
    old_equipment_physics_or_models_admitted=False,source_SHA=m['execution_SHA'],
    equipment_change_contract=m['equipment_change_contract'],minimum_smoke=read(m['hardware']['path'])['minimum_AC'],UTC=now())
atomic(root/'SOURCE_SCOPE_VERIFICATION.json',out);print(json.dumps(out,ensure_ascii=False))
