"""Public saved-point membership comparison; never transfers FULL authority."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'v42_integration').is_dir())
POLICY=HERE.parent/'EXECUTION01/INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json'
BASIC=REPO/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/A1_P1_120/A1_P1_RESULT.json'

def record(path):
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)

before=[record(p) for p in (POLICY,BASIC)]
policy,basic=[json.loads(p.read_text(encoding='utf-8-sig')) for p in (POLICY,BASIC)]
rows=[]
for d in policy['domain_mask']:
    uid=d['uid'];selected=basic['selected_jobs'][uid]
    receipt=policy['known_issued_receipts'][uid]
    reference=policy['known_observed_records'][uid]
    begin=basic['D0_issue_seconds']
    restored=([24] if d['state']=='RUNNING' else [24+round((x-begin)/900)
        for x in receipt['allowed_starts_seconds'] if begin<=x<begin+86400])
    reasons=[]
    if selected['start'] not in restored:reasons.append('OUTSIDE_NEW_E1_RECEIPT')
    if selected['start'] not in d['allowed_native_starts']:reasons.append('OUTSIDE_FAILED_COMPILER')
    if selected['initial_site'] not in d['initial_sites']:reasons.append('OUTSIDE_INITIAL_SITE_COMPATIBILITY')
    if reasons:
        rows.append(dict(uid=uid,state=d['state'],gpu=d['source_hard_contract']['gpu'],
            participant=d['participant'],basic_start=selected['start'],new_causal_reference=d['reference_native_slot'],
            new_budget_seconds=d['budget_seconds'],basic_site=selected['initial_site'],reasons=reasons,
            source_hard_release=d['source_hard_contract']['release_seconds'],
            source_hard_earliest=d['source_hard_contract']['hard_earliest_start_seconds'],
            source_hard_latest=d['source_hard_contract']['hard_latest_start_seconds'],
            source_completion_deadline=d['source_hard_contract']['completion_deadline_seconds']))
assert before==[record(p) for p in (POLICY,BASIC)]
out=dict(schema='TABLE_V_BASIC_POINT_PUBLIC_E1_MEMBERSHIP_DIAGNOSTIC_V1',
    evidence_scope='CROSS_CASE_DOMAIN_DIAGNOSTIC_NOT_FULL_REPLAY_OR_FEASIBILITY_AUTHORITY',
    Basic_source_identity=basic['source_identity'],new_E1_case_sha=policy['case_sha'],
    selected_UIDs_compared=len(policy['domain_mask']),
    outside_new_E1_receipt_UIDs=sum('OUTSIDE_NEW_E1_RECEIPT' in r['reasons'] for r in rows),
    outside_failed_compiler_UIDs=sum('OUTSIDE_FAILED_COMPILER' in r['reasons'] for r in rows),
    outside_initial_site_compatibility_UIDs=sum('OUTSIDE_INITIAL_SITE_COMPATIBILITY' in r['reasons'] for r in rows),
    interpretation='Basic 85500-window FULL point is not automatically feasible under the new original E1 receipt windows. This membership diagnostic does not prove E1 infeasibility.',
    domain_difference_rows=rows,source_records=before,analysis_source=record(Path(__file__)),
    Gurobi_imports=0,Native_calls=0,model_builds=0,presolve=0,IIS=0,private_future_reads=0)
with (HERE/'BASIC_POINT_E1_DOMAIN_MEMBERSHIP_DIAGNOSTIC.json').open('x',encoding='utf-8') as stream:
    json.dump(out,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('domain_difference_rows','source_records','analysis_source')}))
