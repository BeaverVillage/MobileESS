"""Build the blocked authority audit without importing an optimizer or AC engine."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import subprocess

from .contracts import BASE, QUANTILES, authority_gate, feasibility_labels

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_april_b0_voltage_margin_calibration'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def table(name, fields, rows=()):
    with (OUT/name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def cite(path, needle):
    lines = (ROOT/path).read_text(encoding='utf-8').splitlines()
    line = next(i+1 for i, value in enumerate(lines) if needle in value)
    return dict(path=path, line=line, excerpt=lines[line-1], sha256=sha(ROOT/path),
                base_git_blob=git('rev-parse', BASE+':'+path).strip())


def main():
    require_head = git('rev-parse', 'HEAD').strip()
    if require_head != BASE:
        raise ValueError('Audit must be generated before the first new commit at exact PR117 head')
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = []
    for row in git('ls-tree', '-r', BASE).splitlines():
        meta, path = row.split('\t', 1)
        mode, kind, oid = meta.split()
        inventory.append(dict(path=path, mode=mode, kind=kind, git_blob=oid))
    table('PR117_TRACKED_OBJECTS.csv', ('path', 'mode', 'kind', 'git_blob'), inventory)
    dump('PR117_BASE_RECEIPT.json', dict(repository='BeaverVillage/MobileESS', PR=117, exact_head=BASE,
         base_branch='codex/v42-mess-benders-v2-fullscale-loop',
         new_branch='codex/v42-april-b0-voltage-margin-calibration',
         base_tree=git('rev-parse', BASE+'^{tree}').strip(), tracked_files=len(inventory),
         inventory_sha256=sha(OUT/'PR117_TRACKED_OBJECTS.csv'),
         preservation_method='Original Git blobs plus no inherited tracked-file diff. No May result values parsed for calibration.',
         parallel_branches_modified=False))

    # Complete implementation search, excluding tests and reports that contain historical outcomes.
    files = [r['path'] for r in inventory if r['path'].endswith('.py')
             and not r['path'].startswith(('tests/', 'contract_tests/')) and not r['path'].endswith('/report.py')]
    hits = []
    for path in files:
        for i, line in enumerate((ROOT/path).read_text(encoding='utf-8-sig').splitlines(), 1):
            if 'B0' in line or 'b0' in line:
                hits.append(dict(path=path, line=i, text=line))
    dump('B0_SOURCE_SEARCH.json', dict(base_head=BASE, implementation_files_scanned=files, matches=hits,
         exclusion='tests, contract_tests, report.py; historical scientific result artifacts not scanned',
         raw_april_inputs_opened=False, May_result_values_used=False))

    cc = cite('docs/v42_ts_cc4_temporal_refinement/CC4_SCHEDULABLE_SERVICE_CONTRACT.md', 'unchanged B0/C0')
    lp = cite('docs/v42_ts_cc4_temporal_refinement/CC4_SCHEDULABLE_SERVICE_CONTRACT.md', 'LP witness is not an executable placement')
    causal = cite('v42_native/providers.py', 'FUTURE_RUNTIME_FEATURE')
    unknown = cite('docs/v42_native_integration_mess_milp/EVENT_ACTUAL_CONTROL_CONTRACT.md', 'Missing provider')
    frozen = cite('v42_native/actual.py', 'def require_frozen_replay')
    ac = cite('docs/v42_native_integration_mess_milp/EVENT_ACTUAL_CONTROL_CONTRACT.md', 'not an OpenDSS producer')
    scope = cite('v42_native/coordinator.py', "for stage in ('A1','M1','A2','M2')")
    raw = cite('docs/v42_native_integration_mess_milp/NATIVE_SOURCE_AUTHORITY_AUDIT.md', '2025-04-01')
    mess = cite('v42_native/mess.py', 'def ')
    findings = [
        dict(id='A', subject='Exact B0 definition', status='NOT_ESTABLISHED', evidence=[cc, lp, scope],
             finding='B0/C0 denotes inherited aggregate forecast authority here. It does not define the operational B0 Planning/Actual baseline. No complete B0 policy is present in the searched PR117 implementations.'),
        dict(id='B', subject='April B0 planning schedule generation', status='NOT_ESTABLISHED', evidence=[scope, lp, raw],
             finding='Generic A1/M1/A2/M2 adapters and historical April source pointers are not an April B0 frozen-schedule producer. No authoritative April B0 policy binding or schedule artifact was located.'),
        dict(id='C', subject='Known/unknown workload authority', status='PARTIAL_GENERIC_ONLY', evidence=[cc, unknown, causal],
             finding='Causal generic interfaces exist. No B0-specific known-job decision and realized-arrival policy has been frozen. Anonymous allocation cannot be promoted.'),
        dict(id='D', subject='B0 MESS/AIDC decision authority', status='NOT_ESTABLISHED', evidence=[mess, scope, lp],
             finding='Native device model code is not a B0 decision-policy receipt. Do not assume a zero-MESS or fixed CC4 B0 definition.'),
        dict(id='E', subject='B0 D-Day frozen replay authority', status='PARTIAL_GENERIC_ONLY', evidence=[frozen, ac, unknown],
             finding='Immutable replay and Fresh AC validation are validators, not a B0 realized replay producer or a complete B0 schedule policy.'),
        dict(id='F', subject='B0 Actual input mapping', status='NOT_ESTABLISHED', evidence=[raw, unknown, ac],
             finding='Historical grid/weather pointers are present, but no April B0 forecast/Actual causal mapping is bound in the exact base. Target April year, timezone and complete paired source coverage are unverified.'),
        dict(id='G', subject='Final B0 schedule SHA/provenance', status='MISSING', evidence=[frozen, lp],
             finding='No April B0 authoritative final schedule was located or generated. Schedule SHA is null; neither a diagnostic LP nor a unit fixture substitutes for it.')]
    criteria = {key: False for key in ('planning_policy', 'frozen_schedule_generation', 'dday_replay',
                 'causal_boundary', 'forecast_actual_mapping', 'no_anonymous_promotion', 'no_future_leakage')}
    audit = dict(base_head=BASE, findings=findings, criteria=criteria, criterion_evidence={},
                 scan_receipt='B0_SOURCE_SEARCH.json', final_schedule_sha256=None,
                 no_new_schedule_invented=True, no_anonymous_promotion_performed=True,
                 no_future_data_used=True, qualification='Generic causal safeguards are not evidence that an unbound B0 execution pipeline passes all authority gates.')
    dump('B0_AUTHORITY_AUDIT.json', audit)
    authorization = authority_gate(audit)
    dump('B0_EXECUTION_AUTHORIZATION.json', dict(**authorization, execution_stopped=True,
         B1_substitution=False, optimization_calls=0, OpenDSS_calls=0,
         counts_scope='Scientific experiments; excludes tiny inherited unit-test models',
         reason='B0 policy, April input mapping, and executable frozen Actual replay authority are not established at exact PR117.'))
    if authorization['B0_APRIL_EXECUTION_AUTHORIZED']:
        raise ValueError('This audit-only entry point cannot execute an authorized experiment')

    data_fields = ('day_ahead_load_forecast', 'realized_dday_load', 'day_ahead_PV_forecast',
        'realized_rooftop_PV', 'weather_if_used', 'AIDC_known_state', 'AIDC_realized_arrivals_occupancy',
        'MESS_initial_state', 'network_topology_parameters', 'OpenDSS_source_case')
    sources = [dict(component=k, path=None, date_coverage=None, timezone=None, resolution=None,
                    missing_values=None, duplicate_values=None, sha256=None, causal_availability=None,
                    status='NOT_BOUND_NOT_QUALITY_ASSESSED', reason='B0 authority STOP precedes raw data execution/audit binding.')
               for k in data_fields]
    tracked_raw = [r['path'] for r in inventory if r['path'].lower().endswith(('.dss', '.pkl', '.parquet', '.xlsx'))]
    dump('APRIL_DATA_AUTHORITY.json', dict(PASS=False, status='UNVERIFIED_AFTER_B0_AUTHORITY_STOP',
         authoritative=False, synthetic=False, future_filled=False, target_year=None,
         confirmed_date_coverage=None, confirmed_dates=[], sources=sources,
         tracked_raw_candidate_paths=tracked_raw, historical_April_pointer=raw,
         qualification='No complete paired April B0 input bundle is established. This does not assert that historical local April data do not exist; no reconstruction or synthetic filling was attempted.'))
    dump('PREREGISTRATION.json', dict(base_head=BASE, recorded_UTC=datetime.now(timezone.utc).isoformat(),
         experiment='April B0 voltage security margin calibration', status='BLOCKED_BEFORE_DATE_AUTHORITY',
         target_year=None, frozen_date_window=[], exclusions=[],
         exclusion_rule='Only source-backed missing/duplicate/nonfinite or causal-authority failures, fixed before any optimization or AC. Use all authoritative available April days; no outcome-dependent selection.',
         quantiles=QUANTILES, quantile_method='linear interpolation, sorted samples, index (n-1)*q',
         aggregation=['pointwise', 'day_worst_directional_max'], IID_claim=False,
         primary='S0 physical planning 0.95–1.05 unless authoritative B0 fixed definition requires otherwise',
         sensitivity={'S1':[.9525,1.0475], 'S2':[.955,1.045]},
         voltage_definitions=dict(V_PLAN='Planning surrogate', V_DA_AC='frozen plan + DA forecast, offline Fresh OpenDSS diagnostic',
                                  V_DDAY_AC='same frozen plan + realized D-Day inputs, Fresh OpenDSS'),
         operational_chain=['Day-Ahead Planning','plan freeze','D-Day Actual','Fresh OpenDSS'],
         OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True, DA_AC_operational_gate=False,
         residual_identity='e_total = e_model + e_forecast', identity_absolute_tolerance=1e-12,
         alignment=['date','node','phase','time'], dominance_metric='daily and pooled RMSE, no causal attribution',
         no_plan_change_after_freeze=True, no_Actual_optimization_or_repair=True,
         physical_voltage_band=[.95,1.05], physical_line_transformer_limits_required=True,
         MAY_USED_FOR_CALIBRATION=False, FINAL_MARGIN_ACCEPTED=False,
         candidate_selection='Report all four quantiles at both aggregation levels; choose none in this PR.'))
    table('APRIL_DATE_MANIFEST.csv', ('date','source_sha256','included','exclusion_reason','status'))
    table('APRIL_RESIDUAL_ALL.csv', ('date','node','phase','time','V_PLAN','V_DA_AC','V_DDAY_AC','e_model','e_forecast','e_total','r_up','r_down'))
    table('APRIL_DAY_WORST_STATISTICS.csv', ('date','R_up_day','R_down_day','worst_upper_node_phase_time','worst_lower_node_phase_time'))
    table('VOLTAGE_MARGIN_QUANTILES.csv', ('aggregation','q','delta_up','delta_down','V_lower','V_upper'))
    table('OPTIONAL_BAND_SENSITIVITY.csv', ('date','band','planning_feasible','classification'))
    unavailable = dict(status='NOT_RUN_BLOCKED_B0_ACTUAL_AUTHORITY', sample_count=0,
                       values=None, qualification='No observations; header-only CSVs do not represent zero residuals or feasibility failures.')
    for name in ('APRIL_POINTWISE_STATISTICS.json','MODEL_ERROR_STATISTICS.json',
                 'FORECAST_ERROR_STATISTICS.json','TOTAL_ERROR_STATISTICS.json'):
        dump(name, unavailable)
    dump('VOLTAGE_MARGIN_CANDIDATES.json', dict(**unavailable, candidates=[],
         CALIBRATED_CANDIDATE_ONLY=True, FINAL_MARGIN_ACCEPTED=False))
    dump('CURRENT_005_MARGIN_COMPARISON.json', dict(**unavailable, current_delta_up=.005,
         current_delta_down=.005, empirical_percentile_up=None, empirical_percentile_down=None,
         conservativeness_assessment=None, superiority_claim=False))
    dump('MAY_HOLDOUT_RECEIPT.json', dict(MAY_USED_FOR_CALIBRATION=False, May_experiments=0,
         May_result_values_opened_by_calibration=False, margin_tuning_on_May=False,
         note='Base Git object metadata and semantic source-authority pointers are preserved. Inherited regression tests may inspect legacy evidence solely for consistency; no such values enter this calibration.'))
    dump('RESOURCE_RECEIPT.json', dict(recorded_UTC=datetime.now(timezone.utc).isoformat(),
         cpu_receipt='RESOURCE_CPU.json', process_receipt='RESOURCE_PROCESSES.json',
         optimization_calls=0, OpenDSS_calls=0, M1_heavy_Benders_calls=0,
         counts_scope='Scientific experiments; excludes tiny inherited unit-test models',
         policy='Audit-only STOP. No heavy solve launched; inherited unit/regression checks are separate from scientific experiments.'))
    flags = dict(B0_APRIL_EXECUTION_AUTHORIZED=False, APRIL_CALIBRATION_COMPLETE=False,
                 MAY_USED_FOR_CALIBRATION=False, FINAL_MARGIN_ACCEPTED=False, CALIBRATED_CANDIDATE_ONLY=True,
                 candidate_generated=False, OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True,
                 DA_AC_OPERATIONAL_GATE=False, V42_ARCHITECTURE_CHANGED=False,
                 B1_RUN=False, PROPOSED_RUN=False, M1_HEAVY_OPTIMIZATION_RUN=False,
                 ACTUAL_P_REPAIR=False, ACTUAL_Q_REPAIR=False, ACTUAL_GLOBAL_REOPTIMIZATION=False,
                 **feasibility_labels(None,None))
    dump('FINAL_FLAGS.json', flags)
    dump('FINAL_VERDICT.json', dict(classification='BLOCKED_B0_ACTUAL_AUTHORITY', reason=authorization['reason'] if 'reason' in authorization else 'Missing authoritative B0 Planning/frozen Actual pipeline and April mapping.',
         executed_days=0, confirmed_April_coverage=None, V_PLAN_generated=False,
         V_DA_AC_generated=False, V_DDAY_AC_generated=False, pointwise_quantiles=None,
         day_worst_quantiles=None, S0_feasible_days=None, S2_feasible_days=None,
         DDay_Fresh_AC_physical_pass_days=None, model_vs_forecast_dominance=None,
         MAY_USED_FOR_CALIBRATION=False, FINAL_MARGIN_ACCEPTED=False,
         per_day_directories_created=False, result_qualification='Not run; no numeric estimate or substitute experiment.'))
    (OUT/'NEXT_MODIFICATIONS.md').write_text('''# 다음 작업

1. B0/C0 forecast 이름과 operational B0 baseline을 구분하여 정확한 B0 정책을 저장소 근거로 확정한다. MESS/AIDC 결정, known/unknown 처리, D-Day causal replay, forecast/Actual mapping과 schedule SHA provenance를 동결한다. 임의 fixed CC4 또는 anonymous LP schedule을 만들지 않는다.
2. B0 gate PASS 이후 target April 연도와 전체 paired forecast/realized coverage를 source SHA, timezone, resolution, missing/duplicate, causal availability로 감사한다. 실제 historical source가 있더라도 authority 없이 자동 승격하지 않는다. 전체 사용 가능일과 사전 제외 규칙을 실행 전에 동결한다.
3. resource snapshot 후 authorized S0 plan을 freeze하고 offline DA-AC와 동일 SHA의 D-Day Fresh AC를 실행한다. DA-AC fail은 plan 수정이나 operational gate를 유발하지 않는다. Actual P/Q·route·schedule repair와 재최적화는 금지한다.
4. 정확한 node-phase-time alignment, residual identity, directional residual, 모든 네 quantile의 pointwise/day-worst 통계, daily min/max/violations/worst identities, line/transformer 및 RMSE component dominance를 생성한다. S1/S2는 선택 sensitivity이며 S2 infeasible을 physical infeasible로 표현하지 않는다.
5. April 후보를 동결한 뒤 별도 May holdout validation을 수행한다. 이번 PR에서 May 실행·결과 기반 tuning·margin acceptance를 하지 않는다. B0 authority FAIL을 B1/Proposed로 대체하지 않는다.

현재 verdict는 BLOCKED_B0_ACTUAL_AUTHORITY다. Generic validators, 통계 unit fixture, header-only CSV는 과학 실험 결과가 아니다. 다른 architecture/Benders branch를 수정하지 않았다.
''', encoding='utf-8')
    review()


def review():
    questions = [
        ('왜 April을 calibration으로 선택했는가?', '사용자가 April calibration / May holdout을 사전 지정했다. 결과를 보고 선택하지 않았다.'),
        ('왜 May는 사용하지 않았는가?', 'Out-of-sample holdout을 보존하기 위해 calibration 경로에서 May 결과를 열거나 실행하지 않았다.'),
        ('B0 authority는 무엇인가?', 'PR117의 B0/C0 forecast 인터페이스는 확인되지만 operational B0 정의·Planning·Actual authority는 확정되지 않았다. B0_AUTHORITY_AUDIT.json A–G 참조.'),
        ('B0 Actual authority가 확인됐는가?', '아니오. 일반 frozen replay validator는 있지만 B0 전용 실행 정책과 April Actual mapping이 없다. 따라서 gate FAIL이다.'),
        ('anonymous allocation을 사용했는가?', '과학 실행을 하지 않았고 anonymous LP를 schedule로 승격하지 않았다.'),
        ('future information leakage가 있는가?', '이번 task는 실험과 reconstruction을 하지 않아 future 입력을 사용하지 않았다. 미구현 B0 pipeline의 causal boundary가 검증됐다는 뜻은 아니다.'),
        ('V_PLAN은 무엇인가?', 'Planning surrogate voltage다. 이번 task에서는 생성되지 않았다.'),
        ('V_DA_AC는 무엇인가?', 'Frozen plan과 day-ahead forecast로 Fresh OpenDSS를 실행한 offline calibration diagnostic voltage다. 생성되지 않았다.'),
        ('V_DA_AC가 operational stage인가?', '아니오. 운영 gate로 추가하지 않는다. 진단 실패는 plan 수정의 근거가 아니다.'),
        ('V_DDAY_AC는 무엇인가?', '동일 frozen plan에 realized D-Day inputs를 적용한 Fresh OpenDSS voltage다. 생성되지 않았다.'),
        ('동일 frozen schedule인가?', '실제 schedule이 없어 실행 동일성을 주장할 수 없다. 계약 테스트는 SHA 일치를 강제한다.'),
        ('P/Q repair를 했는가?', '아니오. P/Q·route·known schedule repair와 변경을 모두 금지했다.'),
        ('full reoptimization했는가?', '아니오. Actual global optimization은 금지되고 이번 task optimizer 호출은 0이다.'),
        ('e_model은?', 'V_DA_AC − V_PLAN이다. 관측치가 없어 미산출이다.'),
        ('e_forecast는?', 'V_DDAY_AC − V_DA_AC이다. 관측치가 없어 미산출이다.'),
        ('e_total은?', 'V_DDAY_AC − V_PLAN이다. 관측치가 없어 미산출이다.'),
        ('identity가 성립하는가?', '동일 alignment에서 e_total ≈ e_model + e_forecast를 1e−12 absolute tolerance로 검사한다. Unit fixture만 PASS이며 실제 April identity 검증은 NOT_RUN이다.'),
        ('upper residual은?', 'max(0, V_DDAY_AC − V_PLAN)이다.'),
        ('lower residual은?', 'max(0, V_PLAN − V_DDAY_AC)이다.'),
        ('왜 asymmetric margin을 허용하는가?', '상승·하락 오차의 크기와 분포가 같다는 근거가 없으므로 두 방향을 따로 계산한다.'),
        ('pointwise residual은?', '각 date/node/phase/time 관측치의 directional residual 분포다. Correlated sample을 IID로 주장하지 않는다.'),
        ('day worst residual은?', '하루 내 모든 node-phase-time의 r_up, r_down 각각의 최댓값이다. 하루를 표본 단위로도 보고한다.'),
        ('90% quantile은?', '사전등록 q=.90이며 실제 값은 미산출이다.'),
        ('95% quantile은?', '사전등록 q=.95이며 실제 값은 미산출이다.'),
        ('97.5% quantile은?', '사전등록 q=.975이며 실제 값은 미산출이다.'),
        ('99% quantile은?', '사전등록 q=.99이며 실제 값은 미산출이다. 네 quantile 모두 보고하며 결과로 하나를 선택하지 않는다.'),
        ('current 0.005는 어느 수준인가?', '관측치가 없어 empirical percentile을 산출할 수 없다. 값을 추정하지 않았다.'),
        ('0.005가 너무 큰가?', '판단 불가다. April 잔차와 별도 holdout 검증이 필요하다.'),
        ('0.005가 너무 작은가?', '판단 불가다. 상·하 방향별 pointwise/day-worst 검증이 필요하다.'),
        ('model error와 forecast error 중 무엇이 큰가?', '실제 residual이 없어 미판정이다. 사전등록된 daily/overall RMSE로 비교한다.'),
        ('B0 S0 feasible인가?', 'NOT_RUN / null이다. B0 infeasible로 분류하지 않는다.'),
        ('B0 S2 feasible인가?', 'NOT_RUN / null이다. S2 sensitivity를 실행하지 않았다.'),
        ('S2 fail이면 physical fail인가?', '아니오. S0 feasible/S2 infeasible이면 B0_PHYSICALLY_FEASIBLE=true, B0_ROBUST_MARGIN_FEASIBLE=false로 구분한다.'),
        ('Planning physical band는?', 'Primary S0는 0.95–1.05 pu다. 다만 기존 authoritative B0 fixed definition이 있으면 먼저 따른다.'),
        ('D-Day physical band는?', '0.95–1.05 pu와 line/transformer hard limits다.'),
        ('April physical violation count는?', '미산출이다. 실행 0일을 violation 0으로 표현하지 않는다.'),
        ('worst lower event는?', '관측치가 없어 node/phase/time은 null이다.'),
        ('worst upper event는?', '관측치가 없어 node/phase/time은 null이다.'),
        ('line/transformer violation은?', 'Fresh AC를 실행하지 않아 미측정이다. PASS를 주장하지 않는다.'),
        ('May를 봤는가?', 'Calibration 경로에서는 May scientific output 값을 열지 않았다. Source authority 문서의 경로·Git blob metadata와 inherited regression evidence 점검은 margin fitting과 분리된다.'),
        ('May margin tuning을 했는가?', '아니오. MAY_USED_FOR_CALIBRATION=false다.'),
        ('calibrated candidate band는?', '0.95+delta_down(q), 1.05−delta_up(q)다. 실제 후보는 0개이며 미산출이다.'),
        ('symmetric인가 asymmetric인가?', '두 방향별 값을 허용한다. 실제 April 값이 없으므로 이번 task에서 어느 형태도 추정하지 않는다.'),
        ('final margin을 확정했는가?', '아니오. FINAL_MARGIN_ACCEPTED=false다.'),
        ('왜 아직 확정하면 안 되는가?', 'B0 authority와 April 실행이 먼저 필요하며 April 완료만으로도 최종 확정은 불가하다. 별도 May holdout이 필요하다.'),
        ('다음 May experiment는 무엇인가?', 'Authority와 April 후보를 먼저 확정·동결한 뒤 별도 PR에서 untouched May 입력으로 frozen replay/physical 검증을 한다. 이번 PR에서는 실행하지 않는다.'),
        ('B1/Proposed는 이번에 실행했는가?', '아니오. B0 FAIL의 대체 실험을 하지 않았다.'),
        ('V42 architecture를 변경했는가?', '아니오. 새 namespace만 추가하며 PR117 기존 tracked bytes와 다른 branch를 보존한다.'),
        ('Day-Ahead AC validation을 부활시켰는가?', '아니오. V_DA_AC는 offline diagnostic만 허용한다. Operational chain은 Planning → freeze → D-Day Actual → Fresh OpenDSS다.'),
        ('final verdict는?', 'BLOCKED_B0_ACTUAL_AUTHORITY다. B0_APRIL_EXECUTION_AUTHORIZED=false, 실행 0일, 실제 voltage/residual/quantile은 미산출이다.')]
    text = '# April B0 voltage margin calibration 검토\n\n실험을 authority gate에서 중단했다. 아래 미산출은 실패 수치나 zero residual을 의미하지 않는다.\n\n'
    text += '\n\n'.join(f'**Q{i}. {q}**\n\nA. {a}' for i, (q,a) in enumerate(questions,1))+'\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
