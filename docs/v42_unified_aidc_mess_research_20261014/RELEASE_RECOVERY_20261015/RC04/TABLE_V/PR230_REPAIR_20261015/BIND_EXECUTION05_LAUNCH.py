"""Bind the direct human May01 fresh-run instruction after verified fixes.

This writes launch documents only. The official production CLI executes them.
No May02-31 or representative-canary authorization is issued here.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration').is_dir())
sys.path.insert(0,str(ROOT))
from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record
from v42_integration.table_v_campaign import SCHEMA,_launch_gate
from v42_integration.table_v_launch import release_identity
from v42_integration.table_v_run import budget,verify_adapters


def read(path):return json.loads(Path(path).read_text(encoding='utf8-sig'))


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False)
    return file_record(path)


def main():
    fix=Path(__file__).resolve().parent;base=fix.parent;output=base/'EXECUTION05'
    verify_adapters(output)
    dw_path=fix/'DW_NATIVE0_04/NATIVE0_DW_PREFLIGHT_RESULT.json'
    dw=read(dw_path)
    if dw.get('status')!='PASS' or dw.get('Native_calls')!=0:
        raise PermissionError('CURRENT_FULL_TO_DW_NATIVE0_PREFLIGHT_MUST_PASS_FIRST')
    regression_path=fix/'REGRESSION06/RESULTS.json';regression=read(regression_path)
    if (regression.get('status')!='PASS' or regression.get('Native_optimize_calls')!=0
            or regression.get('failures') or regression.get('skipped')):
        raise PermissionError('FINAL_EXISTING_AND_NEW_REGRESSIONS_MUST_ALL_PASS_FIRST')
    month_path=fix/'EXECUTOR_REBIND_FINAL02/FINAL_EXECUTOR_REBIND.json';month=read(month_path)
    if (month.get('status')!='PASS_FINAL_SOURCE_NATIVE0_124_CASES' or month.get('case_count')!=124
            or not month.get('all_final_source_bytes_equal') or any(month.get('operations',{}).values())):
        raise PermissionError('FINAL_NATIVE0_124_CASE_SOURCE_REBIND_REQUIRED')
    if any(file_record(r['path'])!=r for r in month['pinned_final_source']):
        raise PermissionError('FINAL_NATIVE0_124_REBIND_SOURCE_CHANGED')
    current=release_identity()
    if current['release_git_sha']=='a23ccf80bb82e2a59f38fc58923dbcc707cf3a9a':
        raise PermissionError('FIXES_MUST_BE_COMMITTED_AND_PUSHED_BEFORE_LAUNCH')
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],cwd=ROOT,text=True).split()
    if not remote or remote[0]!=current['release_git_sha']:
        raise PermissionError('EXISTING_PR230_BRANCH_REMOTE_SHA_MUST_MATCH_CURRENT_RELEASE')
    manifest=read(output/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')
    expected=dict(day='2025-05-01',source_sha=manifest['source_sha'],source_identity=manifest['identity'])
    if dw.get('source_identity')!=expected['source_identity']:
        raise PermissionError('PREFLIGHT_AND_FRESH_RUN_MUST_USE_SAME_SCIENTIFIC_CASE')
    authorities={};ledgers={};documents={}
    for kind in ('PLANNING','K48'):
        checked=budget(output,kind)
        if checked.used()!=0. or not checked.authorization.get('fresh_native_cycle') or checked.calls:
            raise PermissionError('FRESH_NATIVE_CYCLE_MUST_BEGIN_AT_LITERAL_ZERO_WITHOUT_OLD_CALLS')
        authorities[kind]=file_record(output/(kind+'_AUTHORIZATION.json'))
        documents[kind]=checked.authorization;ledgers[kind]=str(checked.path)
    for arm in ('B1','B2','B3'):
        if (output/arm).exists():raise FileExistsError('FRESH_ARM_MUST_NOT_REUSE_AN_EXISTING_ATTEMPT')
    plan=dict(schema=SCHEMA,dates=['2025-05-01'],run_arms=['B1','B2','B3'],execution_scope='MAY01_VALIDATION',
        Worker=1,Threads=1,P2_calls=0,R2='HOLD',automatic_start=False,actual_slots=96,
        execution_roots={'2025-05-01':str(output)},case_bindings={'2025-05-01':expected},
        policy_bindings={'2025-05-01':digest(manifest['science_derivation']['policy'])},
        budget_authorizations={'2025-05-01':authorities},
        prelaunch_evidence=dict(DW_native0=file_record(dw_path),regression=file_record(regression_path),
            month_native0=file_record(month_path)),May02_31_launch_approved=False,**current)
    plan_record=write(output/'PRODUCTION_LAUNCH_PLAN.json',plan)
    approval=dict(schema='TABLE_V_EXPLICIT_RELEASE_LAUNCH_APPROVAL_V1',approved=True,
        human_approval_reference=dict(
            execution_order='응 작업 끝났으면 5월1일 B1 B2 B3 돌려. B0은 pass되었으니 B1부터 시작해. B1 처음부터 실행해.',
            explicit_fresh_Native_override='아니야. Native도 0초로 해야지. 모든 걸 처음부터 B1 돌려야돼.'),
        approved_plan_sha=digest(plan),dates=plan['dates'],execution_scope=plan['execution_scope'],
        approved_release_sha=current['release_sha'],approved_release_git_sha=current['release_git_sha'],
        approved_policy_bindings_sha=digest(plan['policy_bindings']),
        approved_budget_bindings_sha=digest(plan['budget_authorizations']))
    record=write(output/'HUMAN_LAUNCH_AUTHORIZATION.json',approval)
    gate=dict(launch_authorization=record)
    write(output/'PRODUCTION_LAUNCH_GATE.json',gate)
    write(output/'PRODUCTION_BUDGET_AUTHORIZATIONS.json',{'2025-05-01':documents})
    write(output/'PRODUCTION_BUDGET_LEDGERS.json',{'2025-05-01':ledgers})
    _launch_gate(plan,gate)
    write(output/'PRODUCTION_LAUNCH_BINDING.json',dict(status='PASS_AUTHORIZED_NOT_YET_EXECUTED',
        plan=plan_record,approval=record,Native_calls=0,initial_current_cycle_native_seconds=0.,
        source_release_sha=current['release_sha'],release_git_sha=current['release_git_sha'],
        run_arms=plan['run_arms'],B0_preserved_excluded=True,May02_31_launch_approved=False))
    print('PASS May01 B1/B2/B3 release bound; fresh Native=0; no solver launched',flush=True)


if __name__=='__main__':main()
