"""Fresh Native-cycle preparation under the latest direct human instruction."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration').is_dir())
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.table_v_flex_planning import require_flex_case
from v42_integration.table_v_run import prepare,budget

base=Path(__file__).resolve().parent.parent
output=base/'EXECUTION05'
source=base/'EXECUTION03/INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json'
manifest=require_flex_case(json.loads(source.read_text(encoding='utf8')))
expected=dict(day='2025-05-01',source_sha=manifest['source_sha'],source_identity=manifest['identity'])
latest='아니야. Native도 0초로 해야지. 모든 걸 처음부터 B1 돌려야돼.'
order='응 작업 끝났으면 5월1일 B1 B2 B3 돌려. B0은 pass되었으니 B1부터 시작해. B1 처음부터 실행해.'
authorizations={}
for name in ('PLANNING','K48'):
    old=base/'EXECUTION02'/(name+'_AUTHORIZATION.json')
    ledger=base/'EXECUTION02'/(name+'_NATIVE_LEDGER.json')
    auth=deepcopy(json.loads(old.read_text(encoding='utf8')))
    auth.update(authorization_id='USER_EXPLICIT_FRESH_TABLE_V_MAY01_EXECUTION05_'+name,
        authorized_ledger_path=str(output/(name+'_NATIVE_LEDGER.json')),source_cases=[expected],
        carry_forward_ledgers=[],prior_arm_stage_costs_reset=True,
        human_approval_reference=dict(previous_stage_caps=file_record(old),latest_direct_user_instruction=latest,
            preceding_direct_user_execution_order=order),
        fresh_native_cycle=dict(schema='TABLE_V_EXPLICIT_FRESH_NATIVE_CYCLE_V1',approved=True,
            cycle_id='USER_FRESH_MAY01_EXECUTION05_'+name,start_native_seconds=0.,
            human_approval_reference=dict(latest_direct_user_instruction=latest,execution_order=order),
            archived_native_ledgers=[file_record(ledger)],reuse_previous_solution_or_bound=False))
    authorizations[name]=auth
context=prepare(output,day='2025-05-01',carry_forward_native_ledgers=(),authorizations=authorizations)
baseline=base/'EXECUTION02/B0/ARM_OUTCOME.json'
_write(output/'PRESERVED_B0_BASELINE.json',dict(outcome=file_record(baseline),
    original_source_freeze=file_record(base/'EXECUTION02/EXECUTION_SOURCE_FREEZE.json'),
    baseline_preserved=True,rerun_requested=False,current_release_recertified=False))
main=budget(output,'PLANNING');k48=budget(output,'K48')
assert main.used()==k48.used()==0.
_write(output/'FRESH_CYCLE_INITIAL_RECEIPT.json',dict(status='PREPARED_NOT_LAUNCHED',Native_calls=0,
    current_cycle_native_seconds=main.used(),K48_current_cycle_native_seconds=k48.used(),B1_A1_cap_seconds=5400.,
    archived_native_seconds_excluded_from_current_cycle=main.document['archived_native_seconds_excluded_from_current_cycle'],
    historical_ledgers_read_only=main.historical,source_case=expected,
    previous_point_bound_or_DW_certificate_imported=False,run_arms=['B1','B2','B3'],
    latest_direct_user_instruction=latest))
print(json.dumps(dict(status='PREPARED_FRESH_NATIVE0',output=str(output),Native_calls=0,
    B1_A1_cap_seconds=5400.,current_cycle_native_seconds=main.used())),flush=True)
