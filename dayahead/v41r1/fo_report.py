"""Before/after evidence without converting neighborhood bounds to global gaps."""
import re
from datetime import datetime
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require


def report(acceptance):
    acceptance=Path(acceptance);current=read(acceptance)
    require(current['status']=='PASS','REPORT_REQUIRES_COMPLETED_ACCEPTANCE')
    old_root=RUNTIME/'interrupted/2025-05-04_B1_20260907T032537Z_bounded'
    old_stages=read(old_root/'A0/SOLVER_STAGES.json')['stages']
    log=(old_root/'A0/SOLVER.log').read_text(encoding='utf-8',errors='replace')
    logged_times=[float(x) for x in re.findall(r'\s(\d+(?:\.\d+)?)s\s*$',log,re.M)]
    old_start=read(old_root/'DAYAHEAD_STARTED.json')['started_at']
    stopped=datetime.fromisoformat('2026-09-07T03:25:37+00:00')
    wall=(stopped-datetime.fromisoformat(old_start)).total_seconds()
    memory=read(acceptance.parent/'MEMORY_SAMPLES.json')
    compute=read(current['artifacts']['compute']['path'])
    coverage=read(current['artifacts']['coverage']['path'])
    trace=read(Path(current['artifacts']['solver']['path']).parent/'IMPROVEMENT_TRACE.json')
    seed_calls=[c['seconds'] for c in compute['calls'] if c['stage']=='A0_BUILD_VERIFY_SEED_AND_CANDIDATES']
    old=dict(phase_wall_seconds_at_preservation=wall,last_solver_log_seconds=max(logged_times,default=None),
        first_incumbent_seconds=None,first_incumbent_status='NOT_FOUND_IN_PRESERVED_ATTEMPT',
        final_incumbent=old_stages[-1]['incumbent'],last_precise_global_bound=old_stages[-1]['bound'],gap=None,
        peak_process_RSS_bytes=max(s['memory']['process_peak_RAM_bytes'] for s in old_stages),
        status='SUPERSEDED_BY_FIX_AND_OPTIMIZE_COMPUTE_STRATEGY',
        source_log=record(old_root/'A0/SOLVER.log'),source_stages=record(old_root/'A0/SOLVER_STAGES.json'))
    new=dict(optimization_seconds=current['optimization_seconds'],total_wall_with_Fresh_Actual_seconds=current['total_wall_seconds'],
        A0_model_seed_preparation_seconds=sum(seed_calls),first_incumbent_seconds=current['first_incumbent_seconds'],
        final_objective_vector=current['final_objective_vector'],global_bound=None,certified_gap=None,
        peak_whole_acceptance_RSS_bytes=memory['peak_rss'],candidate_count=current['candidate_count'],
        eligible_candidates=coverage['total_eligible_candidates'],visited_candidates=coverage['unique_candidates_ever_opened'],
        rejected_solver_proposals=sum(bool(row.get('candidate_rejection')) for row in trace),
        candidate_coverage_fraction=current['coverage_fraction'],iteration_count=current['iterations'],
        Fresh=current['Fresh'],Actual=current['Actual'],classification=current['classification'],acceptance=record(acceptance))
    value=dict(status='PASS',day='2025-05-04',policy='B1',old_monolithic=old,new_fix_and_optimize=new,
        scientific_candidate_pruning=0,physical_constraint_relaxation=False,
        original_source_and_logs_preserved=True,old_and_new_model_variable_names_order_not_assumed_identical=True,
        historical_global_bound_not_silently_transferred=True,
        interpretation='Verified incumbent availability and finite completion are established. Unchanged objective values are reported honestly; global optimality is not established.')
    output=ROOT/'dayahead/artifacts/v41r1_bounded_compute/PERFORMANCE_COMPARISON.json';write_json(output,value)
    text=(f'# May-04 B1 computational acceptance\n\n'
        f'원래 시도는 보존 시점까지 약 {wall/60:.1f}분 동안 승인된 정수해를 얻지 못했습니다. '
        f'마지막 정확한 전역 하한은 {old["last_precise_global_bound"]:.10f}였습니다.\n\n'
        f'F&O는 검증된 초기해에서 시작해 최적화 예산 {new["optimization_seconds"]:.1f}/1800초를 사용했습니다. '
        f'첫 solver incumbent은 {new["first_incumbent_seconds"]:.3f}초에 확인됐습니다. '
        f'모델 구성과 초기해 검증은 {new["A0_model_seed_preparation_seconds"]:.1f}초이며, '
        f'Fresh·Actual을 포함한 전체 수락 검증 시간은 {new["total_wall_with_Fresh_Actual_seconds"]/60:.1f}분입니다.\n\n'
        f'권위 후보 {new["candidate_count"]:,}개를 유지했고, {new["iteration_count"]}개 부분문제에서 '
        f'탐색 대상 {new["eligible_candidates"]:,}개 중 {new["visited_candidates"]:,}개 '
        f'({new["candidate_coverage_fraction"]*100:.2f}%)를 방문했습니다. '
        f'최종 P1–P5는 {new["final_objective_vector"]}입니다. '
        '전역 최적성 인증은 없으며, 이 실험은 제한 시간 내 실행 가능한 해의 반환을 검증합니다.\n\n'
        'Fresh OpenDSS와 Actual replay 모두 PASS입니다. 원본 실패·중단 기록과 모든 새 반복 기록을 보존했습니다.\n')
    text+=(f'\n| 지표 | 기존 monolithic | 새 F&O |\n|---|---:|---:|\n'
        f'| 전체 phase/수락시험 경과 | {wall/60:.1f}분에서 중단 | {new["total_wall_with_Fresh_Actual_seconds"]/60:.1f}분, Fresh·Actual 포함 |\n'
        f'| 공유 최적화 예산 사용 | 유한 종료 상한 없음 | {new["optimization_seconds"]:.1f}/1800초 |\n'
        f'| 모델 구성·초기해 검증 | 별도 측정 없음 | {new["A0_model_seed_preparation_seconds"]:.1f}초 |\n'
        f'| 첫 solver 정수해 | 발견 못 함 | optimize 진입 후 {new["first_incumbent_seconds"]:.3f}초 |\n'
        f'| P1 incumbent | 없음 | {new["final_objective_vector"][0]:.10f} |\n'
        f'| 유효 전역 하한 | {old["last_precise_global_bound"]:.10f} | 없음 |\n'
        '| 전역 gap | incumbent 부재 | 인증 없음 |\n'
        f'| 관측 메모리 | {old["peak_process_RSS_bytes"]/2**30:.2f} GiB | {new["peak_whole_acceptance_RSS_bytes"]/2**30:.2f} GiB |\n'
        f'| 후보 방문률 | 해당 없음 | {new["candidate_coverage_fraction"]*100:.2f}% |\n'
        f'| 부분문제 수 | 해당 없음 | {new["iteration_count"]} |\n'
        f'| 독립 검사에서 거절한 solver 후보 | 해당 없음 | {new["rejected_solver_proposals"]} |\n\n'
        '메모리는 기존 기록의 OS peak RSS와 새 수락시험 전체의 1초 간격 RSS 표본 최댓값입니다. '
        '후보 방문률은 F&O에서 열 수 있는 결정의 전체 옵션 범위를 기준으로 합니다. '
        '이전 중단 시도의 전역 하한을 새 실행의 인증으로 이전하지 않았습니다.\n')
    output.with_suffix('.md').write_text(text,encoding='utf-8')
    return value


if __name__=='__main__':
    import sys
    report(sys.argv[1])
