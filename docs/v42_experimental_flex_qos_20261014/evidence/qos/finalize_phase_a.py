from pathlib import Path
import csv,json,hashlib
BASE=Path(__file__).parent
def read(n):return json.loads((BASE/n).read_text(encoding='utf-8'))
def write(n,v):(BASE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def rec(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
m=read('E0_E1_E2_POLICY_MANIFEST.json')
m['native_domain_count_scope']='EXACT_ORIGINAL_PHYSICAL_STARTS_STATIC_SITES_GPU_MASKS_FOR_STAY'
m['native_migration_expansion_scope']='NOT_ENUMERATED_ASSUMED_CHECKPOINT_NATIVE_OPTIONS_CONTROL_REPLAY_SEPARATE'
m['native_modeling_population']=dict(original_native_jobs=1499,preserved_native_jobs=1499,
    known_issue_receipts=1649,known_issue_receipts_outside_native_modeling_job_set=150,
    original_resources_and_fixed_GPU_background_preserved=True,
    native_source_population_not_reclassified_or_dropped=True,
    all_active_Dday_Known_requests_preserved_in_observation_audit=1546)
m['native_stay_validation']=dict(original_complete_enumerator_E0_count=825572,
    mask_based_E0_count=825572,identical=True,
    endpoint_Options_checked_with_original_full_validate=True,
    GPU_rack_service_hard_windows_budget_history_checks_unchanged=True,
    global_joint_feasibility='NOT_RUN')
for case in m['cases']:
    case['native_migration_blocks']=0 if case['scenario']=='E0' else None
    case['native_migration_transfer_timestamp_options']=0 if case['scenario']=='E0' else None
    case['E0_migration_zero_proof']='ZERO_SHARED_BUDGET_POSITIVE_TRANSFER_RESTART_LOWER_BOUND' if case['scenario']=='E0' else None
write('E0_E1_E2_POLICY_MANIFEST.json',m)
path=BASE/'NATIVE_KNOWN_DOMAIN_AUDIT.csv'
with path.open(encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f));keys=list(rows[0])
for row in rows:
    if row['scenario']!='E0':
        row['migration_blocks']='NOT_RUN';row['migration_transfer_timestamp_options']='NOT_RUN'
with path.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
c=read('SOURCE_VS_ASSUMED_QOS_CONTRACT.json')
c['assumed']['physical_WAN_payload_restart']='ORIGINAL_NATIVE_POSITIVE_COST_RESOURCES_AVAILABLE_EXPANDED_MIGRATION_DOMAIN_NOT_ENUMERATED'
c['assumed']['expanded_native_migration_options']='NOT_RUN_BOUNDED_CONTROL_REPLAY_OWNED_SEPARATELY'
write('SOURCE_VS_ASSUMED_QOS_CONTRACT.json',c)
ko=BASE/'EXPERIMENTAL_FLEX_QOS_POLICY_KO.md'
text=ko.read_text(encoding='utf-8')
text=text.replace('원본 Generator로 local hard-valid 후보를 셌다. 연구용 Checkpoint 가능성은 참여 집단에 가정하되 원래 WAN/Payload/Restart 모델을 함께 적용했다.',
    '원본 physical_starts·static_sites·GPU mask로 local hard-valid STAY 후보를 셌다. E0의 완전한 개별 후보 열거 결과 825,572개와 같은 수를 확인했고, 각 도메인의 양 끝 Option은 원본 validate로 재검증했다. 연구용 Checkpoint 가능성은 참여 집단에 가정하며 원래 WAN/Payload/Restart 모델을 유지한다. 확대된 Native Migration 도메인 열거는 NOT_RUN이며 별도 bounded control replay에서 확인한다.')
table='\n| 정책 | FLEX20 참여 | FLEX30 참여 | FLEX40 참여 |\n|---|---:|---:|---:|\n| E0 추가 연구 계약 | 0 | 0 | 0 |\n| E1 활성 D-day 참여 | 457 | 674 | 890 |\n| E2 활성 D-day 참여 | 457 | 674 | 890 |\n\n활성 2,320개 작업 기준 Job 참여율은 19.6983%·29.0517%·38.3621%다. 같은 Seed와 참여 집단에서 E1/E2의 계약 상한만 달라진다. 이는 계약에 참여한 수이며 실제 실행된 지연·이동 수가 아니다.\n'
text+=table
ko.write_text(text,encoding='utf-8')
manifest=read('QOS_PHASE_A_ARTIFACT_MANIFEST.json')
manifest['artifacts']=[rec(Path(x['path'])) for x in manifest['artifacts']]
manifest['source_stable']=True
manifest['focused_test_receipt']=rec(BASE/'FOCUSED_QOS_TESTS.xml')
manifest['focused_tests']=dict(total=34,experimental_new=22,source_only_existing=12,failures=0,errors=0)
manifest['reproduction_scripts']=[rec(BASE/'phase_a_qos_audit.py'),rec(BASE/'finalize_phase_a.py')]
write('QOS_PHASE_A_ARTIFACT_MANIFEST.json',manifest)
print(json.dumps(dict(artifacts=len(manifest['artifacts']),Native_Optimize_calls=0,Actual_runs=0,AC_calls=0,
    module_source=rec(BASE.parents[1]/'v42_integration/experimental_qos.py')),ensure_ascii=False))
