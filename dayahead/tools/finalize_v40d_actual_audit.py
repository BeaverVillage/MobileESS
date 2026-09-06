"""Seal a blocked Actual preflight without manufacturing performance results."""
from __future__ import annotations
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location('actual_audit', Path(__file__).with_name('audit_v40d_actual_replay.py'))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
R, O, C = audit.REPO, audit.OUT, audit.CAMPAIGN


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def final_identity_verification():
    fields=ast.parse((R/'dayahead/v40a/invariants.py').read_text(encoding='utf-8'))
    mobility=next(ast.literal_eval(n.value) for n in fields.body if isinstance(n,ast.Assign)
      and any(isinstance(t,ast.Name) and t.id=='MOBILITY_FIELDS' for t in n.targets))
    rows=[]
    for day in audit.DAYS:
        p=C/'days'/day/'B3';payload=audit.read(p/'FINAL_JOINT_DECISION_PAYLOAD.json')
        joint=dict(payload['joint_decision']);expected=joint.pop('FINAL_JOINT_DECISION_SHA')
        assert canonical_sha(joint)==expected
        assert canonical_sha(sorted(payload['AIDC_decision'],key=lambda r:r['job_uid']))==joint['FINAL_AIDC_DECISION_SHA']
        trajectory=sorted(payload['MESS_trajectory'],key=lambda r:(r['mess_id'],r['slot']))
        assert canonical_sha([{k:r[k] for k in mobility} for r in trajectory])==joint['FINAL_MESS_ROUTE_SHA']
        pq_fields=('mess_id','slot','p_kw','q_kvar','battery_energy_kwh','soc_fraction')
        assert canonical_sha([{k:r[k] for k in pq_fields} for r in trajectory])==joint['FINAL_MESS_PQ_SHA']
        saved=pd.read_parquet(p/'FINAL_MESS_COMPLETE_TRAJECTORY.parquet').sort_values(['mess_id','slot'])
        assert saved[['mess_id','slot']].to_records(index=False).tolist()==[(r['mess_id'],r['slot']) for r in trajectory]
        for field in pq_fields[2:]:assert np.array_equal(saved[field].to_numpy(),np.array([r[field] for r in trajectory]))
        terminal=audit.read(p/'COOPT_TERMINAL_AUDIT.json');assert terminal['status']=='PASS'
        report=audit.read(p/'postfreeze/POSTFREEZE_VERIFICATION.json')
        assert report['status']=='PASS' and report['FINAL_JOINT_DECISION_SHA']==expected
        last=report['rounds'][-1];assert last['joint_sha256']==expected and not last['summary']['physical_violation']
        rows.append({'day':day,'status':'PASS','recomputed_final_joint_SHA':expected,'executed_round':last['round'],
                     'final_PQ_parquet_matches_payload':True,'terminal':'PASS'})
    result={'status':'PASS','rows':rows,'scope':'Independently recomputed B3 AIDC/route/PQ/joint identities and last accepted AC round; no solver invoked'}
    audit.write('V40D_FINAL_EXECUTED_SHA_RECALCULATION.json',result)
    return result


def shared_source_identity(data):
    traffic=data['categories']['traffic']
    sources=[traffic['link_order'],*traffic['geometry_sources']]
    manifest=[{'role':role,'bytes':e['bytes'],'sha256':e['sha256']} for role,e in zip(
      ('link_order','service_nodes','physical_edge_catalog','elevated_network'),sources)]
    graph_sha=audit.digest(manifest)
    order=pd.read_csv(traffic['link_order']['path']).sort_values('tensor_index').reduced_link_id.astype(str).tolist()
    parent=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2')
    source=parent/'tmp/c12_exact_sources_repo_cleanup/c12_exact_sources/v2038_parent/Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference'
    static={name:audit.evidence(path) for name,path in {
      'feeder':source/'opendss_assets/IEEE123Master.dss',
      'line_ratings':source/'opendss_assets/Generated_Planning_Line_Ratings_u080.dss',
      'runtime_adapter':source/'power_v70_p4f_contract/opendss_runtime_adapter.json',
      'phase_PV':source/'power_v70_p4f_contract/Generated_PhasePV.dss',
      'C1':R/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json',
      'CENTER':R/'dayahead/v39a/contracts.py',
      'mobility_physics':R/'pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json'}.items()}
    assert all(v['exists'] for v in static.values())
    assert static['feeder']['sha256']=='cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969'
    rows=[]
    for day,tr in zip(audit.DAYS,traffic['days']):
        forecast=R/f'dayahead/cache/v37_may_locked_final/traffic/shared/traffic/{day}/TRAFFIC_FORECAST.npz'
        with np.load(forecast,allow_pickle=False) as f:meta=json.loads(str(f['metadata']))
        assert meta['link_ids']==order and meta['graph_sha']==graph_sha
        declared=audit.read(C/'days'/day/'B3/D1_TRAFFIC_AUTHORITY.json')
        assert declared['road_graph_SHA']==graph_sha
        binding={'day':day,'timezone':'AEST_FIXED_UTC_PLUS_10','traffic_source_SHA':tr['source']['sha256'],
          'traffic_ordered_values_SHA':tr['ordered_values_SHA'],'link_order_SHA':traffic['link_order']['sha256'],
          'road_graph_SHA':graph_sha,'demand_source_SHA':data['categories']['demand']['source']['sha256'],
          'pv_source_SHA':data['categories']['pv']['source']['sha256'],
          'weather_source_SHA':data['categories']['weather']['source']['sha256'],
          'weather_decoded_SHA':data['categories']['weather']['derived']['sha256'],
          'static_sources':{k:v['sha256'] for k,v in static.items()},
          'demand_alignment':'15-minute interval-end sampling','PV_alignment':'30-minute measurement repeated twice',
          'weather_alignment':'hourly observed data time interpolation to quarter-hour starts'}
        same=audit.digest(binding)
        rows.append({'day':day,'status':'PASS','source_binding':binding,'case_source_bindings':{c:same for c in audit.CASES},
          'frozen_forecast_link_order_match':True,'actual_case_execution_binding':'NOT_RUN'})
    result={'status':'PASS','scope':'PREFLIGHT_SHARED_SOURCE_BINDING_ONLY_NOT_EXECUTED_CASE_FAIRNESS_CERTIFICATE',
      'days':rows,'static_sources':static,'actual_cases_executed':0}
    audit.write('V40D_SAME_DAY_ACTUAL_EXOGENOUS_IDENTITY.json',result)
    return result


def final_preservation():
    protected=audit.read(O/'V40D_PROTECTED_PLANNING_MANIFEST.json')['files']
    sources=audit.read(O/'V40D_AUDIT_SOURCE_MANIFEST.json')['files']
    expected={**protected,**sources}
    def check(item):
        path,ev=item;current=audit.sha(path)
        return None if current==ev['sha256'] else {'path':path,'expected':ev['sha256'],'actual':current}
    with ThreadPoolExecutor(max_workers=4) as pool:changed=[r for r in pool.map(check,expected.items()) if r]
    assert not changed,changed
    result={'status':'PASS','protected_Planning_Fresh_result_files':len(protected),
      'result_and_source_files_checked':len(expected),'changed_files':changed,
      'old_result_files_changed':0,'production_source_files_changed':0,
      'scope':'All files referenced by accepted 124 case certificates plus read authority sources. Existing unrelated dirty worktree files were preserved.'}
    audit.write('V40D_FINAL_INTEGRITY_AUDIT.json',result);return result


def main():
    data=audit.read(O/'V40D_ACTUAL_DATA_PREFLIGHT.json');decisions=audit.read(O/'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')
    assert data['status']=='PASS' and decisions['status']=='PASS'
    assert decisions['verified_case_count']==124
    execution=final_identity_verification();print('FINAL_JOINT_SHA_RECOMPUTED',len(execution['rows']),flush=True)
    identity=shared_source_identity(data);print('SAME_DAY_SOURCE_IDENTITY',identity['status'],flush=True)
    workload=data['categories']['workload']
    blockers=[{
      'id':'AIDC_INDIVIDUAL_JOB_ACTUAL_EXECUTION_AUTHORITY_UNDEFINED',
      'type':'MISSING_ACCEPTED_SCIENTIFIC_EXECUTION_CONTRACT_NOT_MISSING_RAW_DATA',
      'affected_dates':list(audit.DAYS),'affected_cases':list(audit.CASES),
      'required_source_or_file':'An accepted V40A-compatible job-level Actual execution contract/function; no such source was identified in the preserved V16/V28/V29/V39/V40 execution chain.',
      'required_fields_or_rules':['PENDING: frozen DA start/site plus observed total duration versus fixed-slot reserved-service cap',
       'RUNNING: observed remaining service at D-1 issue/counterfactual initial state; never restart full observed duration at slot zero',
       'Behavior if realized duration crosses frozen service end, target-day boundary, or exceeds frozen site/gang capacity',
       'Shortfall/backlog/completion semantics without new site/start choices or reoptimization'],
      'existing_different_rule':'V28R2 replay_workload executes min(DA cohort/rack/slot service, available backlog, remaining capacity). Its input is a 15x48x96 service tensor, not per-job gang schedules.',
      'why_not_reusable_unchanged':'V40A freezes individual jobs and non-additive Rack compatibility labels. Reconstructing old cohort/rack reservation capacities or substituting full observed durations would introduce a new scientific execution rule.',
      'current_identity_only_source':'dayahead/v39d/actual.py:validate_actual_fixed_replay; deterministic_rack_assignment uses already supplied intervals.',
      'decision_needed':'Provide an existing accepted per-job execution authority or explicitly define/freeze a new one before replay. No formula adopted by this audit.'}]
    audit.write('V40D_MISSING_ACTUAL_AUTHORITY_REQUEST.json',{'status':'FAIL_CLOSED','campaign_launched':False,
      'missing_raw_files':[],'missing_raw_dates':[],'missing_raw_fields':[],
      'blockers':blockers,'data_preflight':'PASS','decision_binding':'PASS',
      'next_step':'Resolve the execution authority, then freeze the runnable contract; deterministic smoke remains 2025-05-01 if prerequisites pass.'})
    contract={'status':'FAIL_CLOSED_NOT_FROZEN','campaign_execution_allowed':False,'contract_SHA':None,
      'draft_content_SHA':audit.digest(blockers),'method_SHA':audit.METHOD_SHA,
      'accepted_executed_decision':'Final post-restoration AIDC/route/PQ identity, never pre-restoration MF',
      'AIDC_Actual':{'status':'UNRESOLVED','blocker_id':blockers[0]['id'],'observed_duration_formula_adopted':False},
      'MESS_Actual':{'selected_route':'V33M3 replay_committed_move; fixed departure, destination and link sequence',
        'link_time':'final_tt_sec at realized link-entry slot5; fail when required entry data unavailable',
        'energy':'PFR longitudinal physics with selected route geometry and realized elapsed seconds',
        'command_rule':'Preserve V28R2 connected/PCS/SoC gating, no command shifting or substitute',
        'adapter_status':'NOT_IMPLEMENTED_BECAUSE_JOB_EXECUTION_GATE_FAILED'},
      'grid_PV_weather':{'sources':'31/31 source-completeness evidence in V40D_ACTUAL_DATA_PREFLIGHT.json',
        'demand':'VIC1 DISPATCHREGIONSUM TOTALDEMAND at 15-min ends, inherited sampling',
        'PV':'VIC1 ROOFTOP_PV_ACTUAL MEASUREMENT, each 30-min average duplicated into 15-min intervals',
        'weather':'NOAA observed station 94866099999, accepted QC and inherited time interpolation',
        'C1':'Use current exact_c1_pcc_kw and current CENTER site-power constants exactly once; no extra normalization/refit',
        'native_control':'Inherited engine fixes planned tap/cap states per slot; no autonomous control redesign proposed'},
      'objective':'max(abs(phase-line current)/same frozen phase-line ampacity); transformer metrics separate',
      'reoptimization_calls_allowed':0,'route_change_calls_allowed':0,'physical_violation_policy':'Record outcome; no Actual optimization repair',
      'smoke':{'status':'NOT_RUN','deterministic_date':'2025-05-01','selection':'Earliest May date; no Actual objective inspected'},
      'missing_scientific_rules':blockers[0]['required_fields_or_rules']}
    audit.write('V40D_ACTUAL_REPLAY_CONTRACT.json',contract)
    integrity=final_preservation();print('PRESERVATION',integrity['result_and_source_files_checked'],flush=True)
    tests={'status':'PASS_AUDIT_VALIDATIONS_ONLY','source_completeness':'PASS_ALL_31_DAYS',
      'frozen_decision_certificate_hash_test':'PASS_124_CASES','B3_joint_component_recalculation':'PASS_31_CASES',
      'same_day_exogenous_source_binding':'PASS_31_DAYS_PREFLIGHT_ONLY','inherited_function_lookup':'PASS',
      'source_result_preservation':'PASS','actual_smoke':'NOT_RUN_BLOCKED',
      'zero_optimizer_call_assertion_during_actual':'NOT_RUN_NO_ACTUAL_EXECUTION',
      'zero_route_change_assertion_during_actual':'NOT_RUN_NO_ACTUAL_EXECUTION',
      'Actual_OpenDSS_objective_recalculation':'NOT_RUN','Actual_output_schema_test':'NOT_RUN',
      'Actual_cases_executed':0,'audit_calls_to_optimizers':0,'audit_calls_to_OpenDSS':0}
    audit.write('V40D_TEST_REPORT.json',tests)
    block='''V40D_ACTUAL_AUTHORITY_AUDIT = FAIL
V40D_ACTUAL_DATA_PREFLIGHT = PASS
ACTUAL_DAYS_COMPLETE = 0/31
ACTUAL_CASES_COMPLETE = 0/124
B0_ACTUAL_COMPLETE = 0/31
B1_ACTUAL_COMPLETE = 0/31
B2_ACTUAL_COMPLETE = 0/31
B3_ACTUAL_COMPLETE = 0/31
ACTUAL_AIDC_REOPTIMIZATION_CALLS = 0
ACTUAL_MESS_ROUTE_SEARCH_CALLS = 0
ACTUAL_ROUTE_CHANGE_CALLS = 0
ACTUAL_A1_CALLS = 0
ACTUAL_MF_CALLS = 0
ACTUAL_SAME_DAY_EXOGENOUS_IDENTITY = PASS
ACTUAL_FINAL_JOINT_SHA_BINDING = PASS
B0_MEAN_J_ACTUAL = NOT_RUN
B1_MEAN_J_ACTUAL = NOT_RUN
B2_MEAN_J_ACTUAL = NOT_RUN
B3_MEAN_J_ACTUAL = NOT_RUN
B3_VS_B2_MEAN_ACTUAL_DELTA = NOT_RUN
B3_VS_B2_ACTUAL_WIN_TIE_LOSS = NOT_RUN
B3_VS_B2_PAIRED_95CI = NOT_RUN
B3_VS_B2_WILCOXON_P = NOT_RUN
ACTUAL_VOLTAGE_VIOLATIONS_TOTAL = NOT_RUN
ACTUAL_LINE_VIOLATIONS_TOTAL = NOT_RUN
ACTUAL_TRANSFORMER_CURRENT_VIOLATIONS_TOTAL = NOT_RUN
ACTUAL_TRANSFORMER_KVA_VIOLATIONS_TOTAL = NOT_RUN
MAY_RESULT_BASED_TUNING = 0
PLANNING_DECISIONS_CHANGED_FOR_ACTUAL = NO
FRESH_RESULTS_OVERWRITTEN = NO
OLD_RESULTS_CHANGED = 0
GLOBAL_JOINT_OPTIMALITY_CLAIM = NO
push = NO
PR = NO
'''
    (O/'V40D_FINAL_STATUS.txt').write_text(block,encoding='utf-8')
    report=f'''# V40D Actual realized replay — preflight blocked

새 Actual 캠페인은 실행하지 않았다. 요청서 3·5A·21절의 실행 규칙 확인 게이트가 실패했다. 데이터와 동결 결정은 확인했지만, 개별 작업의 관측 실행시간을 V40A의 동결 일정에 적용할 승인된 실행 규칙은 발견되지 않았다.

| 검사 | 결과 |
|---|---|
| SUMO realized final_tt_sec | 31/31일, 매일 288 × 509 = 146,592행; 누락·중복·비유한 값 없음 |
| 실제 수요 | VIC1 DISPATCHREGIONSUM, 31/31일; 5분 원본과 15분 끝점 선택 검사 PASS |
| 실제 rooftop PV | VIC1 ACTUAL MEASUREMENT, 31/31일; 30분→15분 에너지 보존 PASS |
| 관측 기상 | NOAA Melbourne 94866099999, 31/31일; C1 필요 필드와 보간 검사 PASS |
| Kestrel 관측 | 고유 {workload['unique_frozen_jobs']:,}개 동결 작업, 날짜별 {sum(d['frozen_job_count'] for d in workload['days']):,}개 작업 행; 실제 시작·종료·양의 실행시간 및 GPU 일치 PASS |
| 최종 동결 결정 | 124/124 인증서와 참조 파일 확인; B2는 생산 로더와 동일하게 B0 AIDC 결정에 연결 |
| B3 실행 결정 | 31/31 AIDC/route/PQ/joint SHA 독립 재계산, 최종 수락 AC round와 final P/Q 일치 |
| 기존 결과 보존 | 인증서 참조 {integrity['protected_Planning_Fresh_result_files']:,}개 파일 변경 0; 결과·소스 {integrity['result_and_source_files_checked']:,}개 재대조 |

V28R2의 `replay_workload`는 코호트·Rack·시간별 예약 서비스량에 대해 `min(DA 서비스, backlog, 남은 용량)`을 실행한다. 입력은 15 × 48 × 96 서비스 텐서다. V40A는 개별 gang 작업과 비가산 Rack 호환성 라벨을 사용하므로 이 방식의 용량·예약을 복원해 그대로 넣을 수 없다. V39D/V39E의 Actual 함수는 이미 주어진 계획 구간과 SHA를 검사하며 관측 종료시간으로 실행 구간을 만드는 함수가 아니다.

따라서 `frozen start + observed duration` 공식을 임의로 채택하지 않았다. PENDING의 전체 실행시간, RUNNING의 잔여 실행시간, 예약 종료 초과·용량 충돌 시 shortfall/backlog 처리에 대한 기존 승인된 per-job 규칙이 필요하다. 이 audit에서는 새로운 규칙이나 사이트·시작시각을 만들지 않았다.

계획 기간 밖에서 끝나는 B3 작업에 UNASSIGNED 사이트가 존재함도 확인했다. 추가 원본 대조에서 이들 RUNNING 작업이 실측상 운영일로 넘어오는 사례는 0건이었다. 따라서 이것을 관측된 오류나 별도 데이터 누락으로 보고하지 않는다. 미래의 실행 계약은 이런 경계 처리도 명확히 해야 한다.

수요는 상속 구현의 15분 끝점 샘플링이며 15분 평균으로 바꾸지 않았다. PV는 각 30분 관측 평균을 두 번 적용하며 forecast나 fallback을 사용하지 않았다. SUMO는 관측 기반으로 보정된 시뮬레이션 travel time으로, 직접 측정된 5분 교통값이라고 주장하지 않는다. 기상은 GFS가 아닌 NOAA 관측이다.

`V40D_ACTUAL_REPLAY_CONTRACT.json`은 **FAIL_CLOSED_NOT_FROZEN**인 검토용 초안이며 runnable contract SHA가 없다. `V40D_MISSING_ACTUAL_AUTHORITY_REQUEST.json`은 빠진 데이터 파일이 아닌 실행 규칙의 정확한 범위를 기록한다. smoke 날짜는 게이트 해소 후 가장 이른 2025-05-01로 정했으며 실행은 하지 않았다. Actual 결과·차이·통계·인과 해석은 전부 NOT_RUN이다. Daily/aggregate 성능 표를 만들어 빈 값을 결과로 표시하지 않았다.

아래 exogenous identity PASS는 **31일 사전 source binding 검사**이고, final joint binding PASS는 **Actual 입력으로 사용할 동결 결정의 검사**이다. 어느 것도 Actual 124개 실행 완료를 의미하지 않는다. 무최적화·무경로변경 카운터의 0은 캠페인 자체가 실행되지 않았다는 뜻이며 smoke 검증 통과를 주장하지 않는다.

실행 가능 재생 계약이 확보되면 계약 동결 → 5월 1일 smoke → 무최적화·경로 불변·목적함수 재계산·출력 스키마 검사 → 최대 4 날짜 작업의 전체 캠페인 순서로 재개한다. Planning을 재실행할 필요는 발견되지 않았다.

```text
{block}```
'''
    (O/'V40D_FINAL_REVIEW.md').write_text(report,encoding='utf-8')
    (O/'V40D_PLANNING_FRESH_ACTUAL_ATTRIBUTION.md').write_text(
      '# Actual attribution — NOT_RUN\n\nActual execution is blocked by the missing per-job execution authority. No J_ACTUAL exists. Improvement survival, B3-vs-B2 Actual ranking, paired statistics, and Actual attribution cannot be calculated. Optional A1 counterfactual: NOT_RUN. See V40D_FINAL_REVIEW.md.\n',encoding='utf-8')
    files={p.name:{'sha256':audit.sha(p),'bytes':p.stat().st_size} for p in O.iterdir() if p.is_file() and p.name!='V40D_ARTIFACT_SHA256.json'}
    audit.write('V40D_ARTIFACT_SHA256.json',{'files':files,'audit_code':audit.evidence(Path(audit.__file__)),'finalizer_code':audit.evidence(Path(__file__))})
    print(block)


if __name__=='__main__':main()
