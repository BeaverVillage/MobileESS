"""Small immutable postprocess of RC02 complete physical-time diagnostics."""
from pathlib import Path
import csv
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record
from v42_integration.rc02_voltage_audit import write_new

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/VOLTAGE'
RUN=OUT/'ASOF_E0_E3_01'
OLD=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'


def main():
    results={label:read(RUN/(label+'_SUMMARY.json')) for label in ('E0','E1','E2','E3')}
    cell_stats={}
    for label in results:
        with (RUN/(label+'_VOLTAGE_VIOLATION_CELLS.csv')).open(encoding='utf-8',newline='') as stream:
            cells=list(csv.DictReader(stream))
        cell_stats[label]=dict(count=len(cells),all_on_or_after_May01=all(r['before_May01_begin']=='False' for r in cells),
            all_positive_physical_hold=all(float(r['physical_hold_seconds'])>0 for r in cells),
            min_positive_physical_hold_seconds=min(float(r['physical_hold_seconds']) for r in cells),
            first={k:cells[0][k] for k in ('local_time_AEST','native_seconds','node','voltage_pu','event_kind',
                 'physical_hold_seconds','control_iterations','electrical_iterations')},
            cell_ledger=record(RUN/(label+'_VOLTAGE_VIOLATION_CELLS.csv')))
    eq=read(RUN/'RC01_E2_SAME_INPUT_PHYSICAL_SVR_EQUIVALENCE.json')
    e2,e3=[read(RUN/(label+'_STEP_INDEX.json')) for label in ('E2','E3')]
    e2e3_same=all((a['native_seconds'],a['physical_sha'],a['SVR_sha'])==
        (b['native_seconds'],b['physical_sha'],b['SVR_sha']) for a,b in zip(e2,e3)) and len(e2)==len(e3)
    report=dict(schema='RC02_VOLTAGE_GATE_A_CAUSAL_DIAGNOSIS_V1',status='PHYSICAL_FAIL',
        gate_A='CAUSE_CLASSIFIED_PHYSICAL_FAIL_NOT_REPAIRED',Gate_B_canary_PASS=False,
        scope='PR223_FIXED_M2_WITH_ORIGINAL_COMMONCLOCK_ASOF_900S_OBSERVED_AVERAGE_PQ',
        physical_time_vs_iterations=dict(conclusion='REAL_NATIVE_PHYSICAL_TIME_SAMPLES_NOT_INTERNAL_ITERATION_ROWS',
            observer_runs_after_converged_SolveSnap_and_all_due_controls=True,
            native_seconds='Hour()*3600+Seconds()',internal_iteration_counts_are_not_seconds=True,
            every_failed_voltage_cell_has_positive_hold_until_next_native_solve=True,
            all_violations_inside_May01_evaluation=True,pre_May01_failed_cells=0),
        experiments={label:dict(steps=r['measured_substeps'],bad_steps=r['violating_substeps'],
            bad_cells=r['voltage_violation_cells'],minimum_pu=r['voltage_min_pu'],maximum_pu=r['voltage_max_pu'],
            all16_slot_last_solve_PASS=all(s['PASS'] for s in r['last_solve_per_slot']),
            wall_seconds=r['total_wall_seconds'],cells=cell_stats[label]) for label,r in results.items()},
        E2_reproduces_RC01_all_physical_and_SVR_SHA=eq['status']=='PASS',E3_exactly_E2=e2e3_same,
        implementation_audit=dict(tap_reset_each_slot=False,queue_reset_or_restoration=False,
            duplicate_prefix_inside_a_single_engine=False,
            independent_candidates_fresh_compile_and_replay_is_explicit=True,
            input_mapping_changes_control_state=False,original_parameters_verified_every_substep=True,
            native_clock_900_seconds_and_chronological_queue=True,
            boundary_due_controls_sample_new_inputs=True,
            source_compile_initial_tap_mode_queue_verified=True),
        causal_conclusion=dict(new_Unknown_or_presite_is_necessary_cause=False,
            initial_Running_plus_background_fixed_MESS_original_AUTO_already_violate=True,
            fixed_MESS_Q_steps_and_AUTO_delays_consistent_with_extrema=True,
            Q_only_is_proven_unique_cause=False,
            evidence_Q_steps=record(OLD/'FIXED_M2_Q_STEP_AND_CONTROL_EVIDENCE.json'),
            perturbative_Q_or_delay_repair_experiment_run=False),
        scope_distinctions=dict(current_candidate='EXACT_INSTANT_RUNNING_GPU_PLUS_CANDIDATE_AND_CAUSAL_PREFIX',
            present_ablation='OBSERVED_COMPLETED_900S_OCCUPANCY_AVERAGE_ORIGINAL_C1_ASOF_EXOGENOUS',
            offline_Fresh='REALIZED_INTERVAL_END_SETTLED_SAMPLES',
            asof_and_offline_exogenous_or_tap_trajectories_equal_claimed=False,
            new_instantaneous_event_resolved_continuous_occupancy_certificate=False,
            final_settled_PASS_does_not_erase_substep_FAIL=True),
        permitted_resolution=dict(existing_AUTO_restores_settled_last_solve=True,
            existing_Actual_new_job_admission_alone_cannot_guarantee_safe_initial_Running_or_fixed_MESS_transition=True,
            current_scope_has_no_authority_to_interrupt_Running_or_change_fixed_MESS=True,
            physical_constraints_relaxed=False,controls_Delay_TapDelay_band_or_Q_modified=False,
            minimum_next_steps=['APPROVED_FULL_A1_M1_A2_M2_WITH_SAME_ORIGINAL_SUBSTEP_PHYSICAL_VALIDATION_AND_STAGE_BUDGET',
                'IF_STILL_UNSAFE_EXPLICIT_NEW_SAFE_TRANSITION_INITIALIZATION_OR_ACTUATOR_CONTRACT_BEFORE_ACTIVATION'],
            no_automatic_Heavy_solver_or_Full96_or_campaign_admission=True),
        evidence=[record(RUN/'E0_E1_E2_E3_DIAGNOSIS.json'),record(RUN/'COMMON_INPUTS.json'),
            record(RUN/'RC01_E2_SAME_INPUT_PHYSICAL_SVR_EQUIVALENCE.json')],
        source=record(__file__),Native_calls=0,P2_calls=0,Source7_and_RC01_unchanged=True)
    write_new(OUT/'VOLTAGE_GATE_A_CAUSE_AND_MINIMUM_CONTRACT.json',report)
    text='''# RC02 Gate A 전압 원인 판정

**현재 판정은 PHYSICAL_FAIL이다.** RC01와 같은 평균 Actual 점유·Original C1·as-of 외생 입력 및 고정 PR223 M2 운전으로 모든 원본 Native 물리 시각을 다시 측정했다. E2의 145개 시각, 전체 물리 SHA와 SVR SHA가 RC01와 정확히 일치했다.

| 실험 | Native 시각 | 위반 시각/셀 | 최소/최대 pu |
|---|---:|---:|---:|
| E0 초기 RUNNING 324개만 | 137 | 22 / 79 | 0.91734645 / 1.07952340 |
| E1 + 실제 Known 시작 640개 | 148 | 32 / 96 | 0.92048258 / 1.08383024 |
| E2 + 기본 Unknown 시작 25개 | 145 | 32 / 100 | 0.92034853 / 1.08365737 |
| E3 + 실제 Pre-site 변경 0개 | 145 | 32 / 100 | 0.92034853 / 1.08365737 |

위반은 전부 May01 00:00 이후 평가 구간 내부이며, 각 셀은 다음 물리 Solve까지 양의 실제 유지시간을 가진다. Native Hour/Seconds를 시간으로 사용했다. ControlIterations/Iterations는 별도 기록이며 초로 환산하지 않았다. 모든 실험에서 16개 슬롯의 마지막 Solve가 정상인 사실은 슬롯 내부 위반을 지우지 않는다.

슬롯 사이 Tap·Queue 리셋, 입력 매핑의 제어 상태 변경, 한 엔진 내 중복 Prefix, 시간 역행은 발견되지 않았다. 원본 7 RegControl과 11 SVR의 제어 파라미터를 각 물리 시각마다 검증했다. 고정 MESS 24개 서비스 사이트 P/Q, Delay/TapDelay/LDC/밴드, 0.95~1.05 전압 한계는 바꾸지 않았다.

초기 RUNNING만 남긴 E0도 실패하므로 신규 Unknown이나 Pre-site가 필수 원인은 아니다. 초기 운전상태·배경·고정 MESS 명령과 원본 AUTO 제어 지연의 조합에서 발생하는 물리 위반이다. 기존 STA01의 Q ±392.314 kvar 전환과 극값은 일치하지만, Q만의 단독 인과성을 확정하거나 Q-only Repair를 실행하지 않았다.

현재 Actual은 새 시작을 거절할 수 있지만 기존 RUNNING을 무단 중단하거나 고정 MESS 명령을 바꿀 권한이 없다. 따라서 현재 계약 안에서 전압 안전을 해결했다고 주장할 수 없다. 다음 허용 조치는 별도 예산을 가진 원본 A1→M1→A2→M2와 모든 Native substep 물리 검증이다. 그래도 불안전하면 안전한 초기화·전이 또는 추가 제어 계약을 별도로 승인해야 한다. 현재 Gate B/Full96/캠페인 PASS는 없다.

이 실험은 900초 관측 점유 적분의 조건부 원인 분리이다. 현재 후보의 순간 GPU 검사, 실제 실현 외생 자료의 구간 말 Fresh, 초단위 Job 이벤트를 모두 반영한 연속 운전 인증과 혼합하지 않는다. 전체 셀별 시각/PQ/배경과 full Tap·RegControl·Queue 근거는 CSV 및 gzip 원장에 연결되어 있다.
'''
    with (OUT/'VOLTAGE_GATE_A_CAUSE_KO.md').open('x',encoding='utf-8') as stream:stream.write(text)
    print(report['status'],cell_stats['E2']['count'],e2e3_same)


if __name__=='__main__':main()
