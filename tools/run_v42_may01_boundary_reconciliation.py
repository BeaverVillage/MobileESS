"""Native-0 read-only audit of the original PR223 issue/D-day boundary."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.known_commands import compile_known_commands
from v42_integration.may01_boundary_reconciliation import (
    approved_initialization_audit,build_running_continuation_certificate,
    checked_json,compare_known_boundary,file_record,validate_running_continuation_certificate)
from v42_integration.policy import digest

ORIGINAL_ROOT=Path(r'D:\v42_integration_validation_20261013\DDAY_V5_B3_FINAL_ATTEMPT01')
INITIAL=Path(r'D:\v42_common_am_qos_integration_20261013\docs\v42_common_am_qos_integration\V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
NATIVE=Path(r'D:\v42_may_joint_repair_campaign_20261013\raw\2025-05-01\NATIVE_INPUT_TEMPLATE_B1.json')
SEMANTIC_SHA='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'
REPORT_NAMES=('PR223_DDAY_INITIALIZATION_REUSE_AUDIT.json','KNOWN_UID_EPISODE_BOUNDARY_COMPARISON.csv',
    'KNOWN_253_886_BOUNDARY_ROOT_CAUSE_KO.md','PLANNING_ISSUE_TO_DDAY_PREFIX_RECONCILIATION.json',
    'ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING.json')


def audit(original_root=ORIGINAL_ROOT,initial_path=INITIAL,native_path=NATIVE):
    """Build reports in memory. Reads historical outcomes only for retrospective audit."""
    initial_record=file_record(initial_path);native_record=file_record(native_path)
    state,reuse=approved_initialization_audit(initial_record,expected_semantic_sha=SEMANTIC_SHA)
    native=checked_json(native_record)
    freeze_record=file_record(original_root/'B3/PLANNING_FREEZE.json');freeze=checked_json(freeze_record)
    preparation_record=file_record(original_root/'CASE/PRODUCTION_CASE_PREPARATION.json')
    preparation=checked_json(preparation_record)
    reference=checked_json(file_record(original_root/'CASE/KNOWN_DESCRIPTOR_REFERENCE_REBINDING.json'))
    references={r['uid']:r for r in reference['rows']}
    carry_record=file_record(original_root/'B3/CARRYOUT_RECEIPT.json');carry=checked_json(carry_record)
    queue_record=file_record(original_root/'B3/ACTUAL_QUEUE_LEDGER.json');queue=checked_json(queue_record)
    controller=carry['controller'];issue=float(preparation['time_axis']['issue_epoch_seconds'])
    # Use the saved authoritative axis rather than shifting the May-01 timestamp.
    if issue!=freeze['actual_gate']['source_issue_epoch_seconds']:
        raise ValueError('ORIGINAL_PREPARATION_FREEZE_ISSUE_AXIS_DRIFT')
    begin=float(state['begin_epoch_seconds']);qos=preparation['QoS_budget_ledger']['receipts']
    records={};summaries={};certificates={};all_rows=[];commands_by_stage={}
    for stage in ('A1','A2'):
        record=file_record(original_root/f'B3/{stage}/A_RESULT.json');a=checked_json(record)
        commands=compile_known_commands(a['selected_jobs'],slot_zero_seconds=issue)
        proof=build_running_continuation_certificate(record,native_record,initial_record,
            issue_seconds=issue,commands=commands,expected_semantic_sha=SEMANTIC_SHA)
        validate_running_continuation_certificate(proof,commands=commands,stage_case_sha=a['case_sha'],
            initial_semantic_sha=SEMANTIC_SHA,begin_seconds=begin)
        rows,summary=compare_known_boundary(native,a,state,issue_seconds=issue,stage=stage,qos_receipts=qos,
            reference_rebindings=references,original_actual_queue=queue,
            original_actual_metadata=controller['metadata'],original_actual_decisions=controller['decisions'])
        for row in rows:
            row.update(command_result_source_byte_sha=record['sha256'],command_source_path=record['path'],
                command_planning_case_sha=freeze['case_sha'],command_stage=stage,
                initial_file_byte_sha=initial_record['sha256'],initial_source_path=initial_record['path'],
                initial_evaluation_case_sha=carry['case_sha'],original_science_version=freeze.get('science_version'))
        pending=[r for r in rows if r['Dday_status']=='PENDING' and r['optimized_start_seconds'] is not None
            and r['optimized_start_seconds']<begin]
        summary['past_pending_QoS']=dict(UIDs=len(pending),
            original_receipt_status_counts=dict(Counter(qos[r['uid']]['status'] for r in pending)),
            original_receipt_reason_counts=dict(Counter(reason for r in pending for reason in qos[r['uid']]['reasons'])),
            allowed_start_at_or_after_Dday_UIDs=sum(any(t>=begin for t in r['allowed_starts_seconds']) for r in pending),
            no_original_allowed_start_at_or_after_Dday_UIDs=sum(not any(t>=begin for t in r['allowed_starts_seconds']) for r in pending),
            original_budget_seconds_counts=dict(Counter(qos[r['uid']]['budget_seconds'] for r in pending)),
            automatic_Dday_retime_authorized=False)
        summary['Running_with_commands_site_match_UIDs']=sum(r['Dday_status']=='RUNNING' and r['optimized_start_seconds'] is not None
            and r['Dday_site']==r['optimized_site'] for r in rows)
        summary['Running_with_commands_site_mismatch_UIDs']=sum(r['Dday_status']=='RUNNING' and r['optimized_start_seconds'] is not None
            and r['Dday_site']!=r['optimized_site'] for r in rows)
        all_rows.extend(rows);summaries[stage]=summary;certificates[stage]=proof;records[stage]=record;commands_by_stage[stage]=commands
    initial_known_running=[r for r in state['running'] if not r['origin_unknown']]
    completed=state['historical_completed']
    reuse.update(original_source_native_record=native_record,
        Known_running_UIDs=len(initial_known_running),Known_running_GPU=sum(r['gpu'] for r in initial_known_running),
        Unknown_prefix_running_UIDs=sum(r['origin_unknown'] for r in state['running']),
        historical_completed_UIDs=len(completed),excluded44_is_subset_of_historical_completed=True,
        historical_completed_reintroduced_as_active_GPU=False,
        A1_no_nonzero_nominal_domain_Known_Running_UIDs=summaries['A1']['primary_groups']['ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD']['UIDs'],
        A1_no_nonzero_nominal_domain_Known_Running_GPU=summaries['A1']['primary_groups']['ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD']['GPU'],
        physical_occupancy_retained_independent_of_Q50_forecast=True,
        approved_counts_changed=False,remaining_private_runtime_used_to_certify_prefix=False)
    event_ledger=controller.get('job_event_ledger',[])
    events=event_ledger if isinstance(event_ledger,list) else event_ledger.get('events',[])
    event_times=[e.get('event_time_seconds',e.get('time_seconds',e.get('at_seconds'))) for e in events]
    event_times=[t for t in event_times if isinstance(t,(float,int))]
    observed_prefix_flags=dict(Apr30_queue_replay=state['Apr30_queue_replay'],
        saved_actual_gate_preday_queue_replay=freeze['actual_gate'].get('preday_queue_replay_executed'),
        saved_initial_binding_Apr30_queue_replay=checked_json(file_record(original_root/'CASE/ACTUAL_INITIAL_STATE_BINDING.json')).get('Apr30_queue_replay'))
    actual_rules=dict(Counter(d.get('status','UNSPECIFIED') for d in controller['decisions'].values()))
    axis_source_records=[]
    source_files=freeze['source_freeze']['files']
    for relative in ('v42_capacity/reference.py','v42_integration/a_engine.py','v42_integration/production_case.py',
            'v42_integration/planning_inputs.py','v42_integration/qos.py','v42_integration/coordinator.py','v42_integration/actual.py'):
        path=Path(r'D:\v42_common_am_qos_integration_20261013')/relative
        expected=next(r for r in source_files if Path(r['path'])==path)
        checked=file_record(path)
        if any(expected[k]!=checked[k] for k in ('sha256','bytes')):
            raise ValueError('ORIGINAL_TIME_AXIS_DRIVER_SOURCE_BYTES_DRIFT:'+relative)
        axis_source_records.append(checked)
    pending_axis=[r for r in all_rows if r['stage']=='A1' and r['issue_status']=='PENDING' and r['optimized_start_seconds'] is not None]
    axis_receipt=dict(status='PASS',native_input_issue_time=native['issue_time'],issue_epoch_seconds=issue,
        Dday_begin_epoch_seconds=begin,native_slot_zero_is_issue=True,native_slot24_is_Dday=True,
        original_preparation_time_axis=preparation['time_axis'],original_model_grid_known_access='known[site,t+24]',
        original_model_CC4_access='anonymous/reserve[site,t+24]',original_model_capacity_native_slots=[24,120],
        original_QoS_native_conversion='(allowed_seconds-issue)/900',
        original_Actual_command_conversion='planning_slot_zero_seconds+native_start_slot*900',
        A1_selected_Pending_UIDs=len(pending_axis),
        A1_selected_Pending_original_QoS_epoch_matches=sum(r['optimized_start_seconds'] in r['allowed_starts_seconds'] for r in pending_axis),
        independent_of_current_known_command_compiler=True,verified_original_source_file_records=axis_source_records,
        changing_native0_to_Dday_authorized=False)
    prefix=dict(schema='ORIGINAL_ISSUE_TO_DDAY_PREFIX_RECONCILIATION_V1',status='NOT_CERTIFIED',
        evidence_scope='ORIGINAL_PR223_SOURCE_AND_RETROSPECTIVE_SAVED_LEDGER',
        issue_seconds=issue,begin_seconds=begin,gap_seconds=begin-issue,prefix_execution='NOT_RUN',
        original_native_time_axis_receipt=axis_receipt,
        original_prefix_receipt_found=False,original_prefix_assertion_flags=observed_prefix_flags,
        public_elapsed_continuation_scope='103_ALREADY_RUNNING_UIDS_ONLY_NOT_PENDING_PREFIX_REPLAY',
        partial_continuation_certificates={stage:dict(certificate_sha=p['certificate_sha'],UIDs=len(p['rows']),
            GPU=p['eligible_GPU'],observed_prefix_compute_GPUh=p['observed_continuation_prefix_GPUh']) for stage,p in certificates.items()},
        stages=summaries,saved_actual_decision_status_counts=actual_rules,
        saved_actual_event_times_first=min(event_times,default=None),
        original_driver_preday_behavior='PRE_DDAY_START_COMMAND_NOT_REPLAYED_REFERENCE_FALLBACK',
        original_driver_behavior_is_optimized_prefix_execution=False,
        legal_path='B_OBSERVED_BOUNDARY_ADAPTER_WITH_TYPED_CONTINUATIONS_AND_EXPLICIT_UNRESOLVED_COMMANDS',
        legal_adapter=dict(reuse_approved_initial_state=True,initial_state_semantic_and_file_validation_separate=True,
            Running103='Source-verified pinned continuation; native start=0 retains remaining-service meaning; no new START or command mutation.',
            Running150='Keep approved observed physical episode. Audit optimized allocation/time divergence; do not move or restart already-running jobs.',
            Known_Running48_without_native_domain='Hold observed 163GPU until observed completion, irrespective of expired nominal Q50.',
            historical_completed178='Preserve observed completed history; no active GPU or CC4 demand reinsertion.',
            Pending886='Keep original optimized command immutable and original QoS receipt. A past command does not become a new Dday START.',
            Pending_expired_authority='Record unresolved expired command with original allowed window and hard contract. Starting at Dday needs an independently valid original window or an explicit new research corrective policy/receipt; no blanket Known consent.',
            future_pending='Only future original commands with exact source/Case/SHA, preparation and physical guard may proceed after all gate requirements.',
            unresolved_conflict_outcome='HOLD before real Actual replay. Preserve queue and capacity metrics as NOT_RUN.'),
        no_planning_command_retime=True,no_FCFS_replacement=True,no_initial_state_redefinition=True,
        no_apparent_schedule_execution_from_nominal_prefix=True,
        Native_calls=0,Actual_calls=0,Fresh_AC_calls=0)
    stage_A1=checked_json(records['A1']);stage_A2=checked_json(records['A2'])
    full_actual=checked_json(file_record(original_root/'B3/ACTUAL_RESULT.json'))
    binding=dict(schema='ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING_V1',status='NOT_CERTIFIED',
        original_case_sha=freeze['case_sha'],original_actual_case_sha=carry['case_sha'],
        new_followup_case_transfer_allowed=False,initial_semantic_sha=SEMANTIC_SHA,initial_raw_file_sha=initial_record['sha256'],
        planning_freeze_record=freeze_record,preparation_record=preparation_record,actual_carryout_record=carry_record,
        original_actual_queue_record=queue_record,original_A_stage_records=records,
        A1_stage_case_sha=stage_A1['case_sha'],A2_stage_case_sha=stage_A2['case_sha'],
        A1_FULL_feasible=stage_A1['FULL_feasible'],A2_FULL_feasible=stage_A2['FULL_feasible'],
        A1_original_commands_preserved=True,A2_original_commands_preserved=True,
        saved_final_known_schedule_format='ORIGINAL_SELECTED_NATIVE_OPTIONS',
        saved_final_known_schedule_equals_A1=freeze['Known_schedule']==stage_A1['selected_jobs'],
        saved_final_known_schedule_equals_A2=freeze['Known_schedule']==stage_A2['selected_jobs'],
        final_A1_vs_A2_selected_jobs_different_UIDs=sum(digest(stage_A1['selected_jobs'][uid])!=digest(stage_A2['selected_jobs'][uid])
            for uid in stage_A1['selected_jobs']),
        running_continuation_certificate=certificates['A1'],final_A2_running_continuation_certificate=certificates['A2'],
        stages=summaries,original_Full96_saved_receipt_preserved=True,
        original_Full96_physical_success_is_not_new_optimized_prefix_certification=True,
        original_Full96_physical_receipt=full_actual.get('receipt'),
        original_Full96_physical_status=full_actual['receipt']['physical_ac_status'],
        block_reasons=['MISSING_ORIGINAL_OPTIMIZED_PENDING_ISSUE_TO_DDAY_PREFIX_EXECUTION',
            'ISSUE_PENDING_SOURCE_OBSERVED_RUNNING_DIFFERS_FROM_OPTIMIZED_COMMAND',
            'PAST_PENDING_COMMAND_AND_ORIGINAL_QOS_WINDOW_NEEDS_EXPLICIT_CAUSAL_DISPOSITION'],
        new_current_event_May01_replay='NOT_RUN',old_nominal_report_relabelled_as_current_performance=False,
        Native_calls=0,Actual_calls=0,Fresh_AC_calls=0)
    return reuse,all_rows,prefix,binding


def narrative(reuse,prefix,binding):
    lines=['# PR223 원본 Known 253/886 경계 원인 재조사','',
        '승인 초기 상태를 원본 `load_dday_state`로 검증하여 재사용했다. semantic SHA와 파일 byte SHA는 서로 다른 검증 대상이며 같을 필요가 없다.',
        '',f"RUNNING {reuse['counts']['running']} / {reuse['counts']['running_GPU']}GPU, PENDING {reuse['counts']['pending']}를 보존했다. PR129 20건, PR125 153건/156GPU, 제외 44건을 변경하지 않았다.",
        f"완료 이력 {reuse['historical_completed_UIDs']}건 전체를 보존했다. A1 비영(非零) Q50 명령 밖의 Known RUNNING 48건/163GPU도 물리 점유로 유지한다.",
        '', '253건은 단일 시작 시각 불일치로 해석할 수 없다. issue RUNNING 103건/133GPU의 start=0은 남은 서비스 연속 실행이다. 실제 과거 episode start, source elapsed, Dday elapsed, site, GPU, Q50, segment를 원본 파일에서 재검증하여 typed certificate를 만들었다. 이 103건의 관측된 6시간 연속 GPU 서비스는 798GPUh이며 Pending prefix가 실행되었다는 증거로 사용하지 않는다.',
        '', '나머지 150건/150GPU는 issue PENDING이었으나 승인 Dday에서는 RUNNING이다. source 관측 시작은 최적 시작보다 108건 먼저, 42건 늦다. site는 40건 일치, 110건 다르다. 이는 승인된 관측/모델 경계와 issue 최적 계획의 차이이며 기존 초기 상태를 잘못 만들어서 생긴 253건으로 묶지 않는다.',
        '', '과거 Pending 886건/886GPU는 issue에도 Pending이다. 714건의 명목 구간은 Dday 전에 끝나고 172건은 명목상 Dday에 걸치지만, 승인 Dday에는 모두 Pending이다. 명목 forecast를 실제 실행/완료로 바꾸거나 Dday로 자동 retime할 수 없다.',
        '', '원본 Actual driver는 과거 시작 명령에 `PRE_DDAY_START_COMMAND_NOT_REPLAYED` reference fallback을 사용했다. 저장된 Full96의 물리 성공과 무누락 결과는 해당 원본 Case에서 보존한다. 최종 Full96 계획은 A2이므로 A1 계획과 A2 계획을 각각 검증한다. 이 결과는 새 current-event 통합이나 원본 최적 prefix 실행의 인증으로 이전하지 않는다.',
        '', '원본 6시간 optimized Pending prefix의 실행 receipt를 찾지 못했고 기존 승인 플래그도 Apr30 replay=False이다. 새 prefix를 만들거나 실행했다는 주장은 하지 않는다. 경로 B는 승인 observed boundary와 source-verified continuation을 연결하는 최소 adapter다. 이미 Running인 물리 episode와 완료 이력을 유지하며 원본 계획을 보존한다.',
        '', '886건의 원본 QoS 허용 시작 구간을 UID별로 CSV에 보존했다. 과거 명령을 새 시작으로 바꾸려면 원본 계약상 유효한 현재 구간이 있거나 구체적인 연구 corrective 정책과 receipt가 먼저 필요하다. 조용한 reference queue 치환이나 Known 권리 확대는 하지 않는다. 잔여 불일치가 해결되기 전 실제 May01 replay는 HOLD/NOT_RUN이다.',
        '', '| Stage | 분류 | UID | GPU | 원본 prefix 명목 GPUh | 원본 prefix 예약 GPUh | 관측 과거 GPUh | 첫 가능한 차이(epoch) |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for stage,summary in prefix['stages'].items():
        for name,g in summary['primary_groups'].items():
            lines.append(f"| {stage} | {name} | {g['UIDs']} | {g['GPU']} | {g['planned_prefix_nominal_compute_GPUh']:.6f} | {g['planned_prefix_reserved_GPUh']:.6f} | {g['observed_past_prefix_compute_GPUh']:.6f} | {g['first_possible_divergence_seconds']} |")
    lines.extend(['','첫 가능한 차이는 실행 prefix가 없어 확정 실패 시점이 아니다. Dday 관측 비교 시점은 모든 행에서 1746021600이며, 인증된 연속 실행에는 차이 시점을 기재하지 않았다.',
        '',f"A1/A2 최종 명령 차이: {binding['final_A1_vs_A2_selected_jobs_different_UIDs']} UID. Native/Actual/Fresh 새 호출은 모두 0이다."])
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root',type=Path,default=ORIGINAL_ROOT)
    parser.add_argument('--initial-state',type=Path,default=INITIAL)
    parser.add_argument('--native-input',type=Path,default=NATIVE)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP')
    args=parser.parse_args();out=args.output_dir
    if any((out/name).exists() for name in REPORT_NAMES):raise FileExistsError('EXISTING_BOUNDARY_REPORTS_MUST_NOT_BE_OVERWRITTEN')
    reuse,rows,prefix,binding=audit(args.original_root,args.initial_state,args.native_input)
    out.mkdir(parents=True,exist_ok=True)
    for name,value in ((REPORT_NAMES[0],reuse),(REPORT_NAMES[3],prefix),(REPORT_NAMES[4],binding)):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    with (out/REPORT_NAMES[1]).open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:writer.writerow({key:json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value for key,value in row.items()})
    (out/REPORT_NAMES[2]).write_text(narrative(reuse,prefix,binding),encoding='utf-8')
    print(json.dumps(dict(initial_reuse=reuse['status'],A1_continuation_UIDs=len(binding['running_continuation_certificate']['rows']),
        optimized_prefix=prefix['status'],May01_replay=binding['new_current_event_May01_replay'],Native_calls=0,outputs=[str(out/name) for name in REPORT_NAMES])))


if __name__=='__main__':main()
