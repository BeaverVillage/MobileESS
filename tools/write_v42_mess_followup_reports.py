"""Write source-scoped MESS follow-up findings from saved receipts, no solver."""
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write, file_record

OUT=ROOT/"docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def csv_write(name, rows):
    with (OUT/name).open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def native_log(path):
    text=Path(path).read_text(encoding="utf8",errors="replace")
    def value(pattern):
        m=re.search(pattern,text)
        return None if m is None else float(m.group(1))
    return dict(Presolve_seconds=value(r"Presolve time: ([\d.]+)s"),
        Root_LP_seconds=value(r"Root relaxation:.*?([\d.]+) seconds"),
        root_barrier_log_reported_cumulative_native_seconds=value(r"Barrier performed.*? in ([\d.]+) seconds"),
        Root_LP_completed=bool(re.search(r"Root relaxation: objective",text)),
        root_log_interrupted=bool(re.search(r"Root relaxation: (interrupted|time limit)",text)),
        log=file_record(path))


def main():
    audit=read(OUT/"ORIGINAL_BEAM_JOINT_COMPRESSION_AUDIT.json")
    pair=read(OUT/"MESS_4X24_NATIVE_COMPARISON.json")
    cert=read(OUT/"JOINT_GRID_COMPRESSION_CERTIFICATE.json")
    native_rows=[]
    logs={}
    for name, run in pair["results"].items():
        p=ROOT/"runtime/FOLLOWUP_ORIGINAL_BEAM_JOINT/NATIVE_PAIR_20S"/name/"NATIVE_GUROBI.log"
        logs[name]=native_log(p)
        compression=0. if name=="ORIGINAL" else cert["compression_total_wall_seconds"]
        validations=pair["original_FULL_capture_validation"][name]
        validation_wall=sum(v["certificate"]["original_matrix_and_96_slot_physical_replay"]["validation_wall_seconds"]
                            for v in validations if v["status"]=="PASS")
        native_wall=run["native_build_readback_solve_capture_wall_seconds"]
        native_rows.append(dict(variant=name,status="DIAGNOSTIC_ONLY",source_sha=pair["identity"]["source_sha"],
            case_sha=pair["identity"]["case_sha"],physical_sha=pair["identity"]["physical_sha"],pool_sha=pair["identity"]["pool_sha"],
            packet_load_seconds=run["packet_load_wall_seconds"], native_build_readback_solve_capture_seconds=native_wall,
            compression_proof_cache_seconds=compression, FULL_raw_replay_seconds=validation_wall,
            measured_same_pool_wall_excluding_shared_packet_creation=native_wall+compression+run["packet_load_wall_seconds"]+validation_wall,
            Native_Runtime=run["Native_Runtime"],Presolve_seconds=logs[name]["Presolve_seconds"],
            Root_LP_seconds=logs[name]["Root_LP_seconds"],
            barrier_log_cumulative_native_seconds=logs[name]["root_barrier_log_reported_cumulative_native_seconds"],
            FULL_UB=run["current_pool_ObjVal"], restricted_bound=run["restricted_ObjBound_diagnostic"],
            total_Beam_generation_and_iteration_wall="NOT_RUN_FIXED_HISTORICAL_POOL",
            Peak_RSS_bytes=pair["peak"]["RSS_bytes"],Peak_private_commit_bytes=pair["peak"]["private_commit_bytes"],
            native_threads=1,workers=1,total_performance_improvement="NOT_CERTIFIED"))
    csv_write("MESS_COMPRESSION_TOTAL_WALL.csv",native_rows)
    _write(OUT/"MESS_NATIVE_LOG_PHASE_AUDIT.json",dict(status="DIAGNOSTIC_ONLY",variants=logs,
        differing_presolve_paths_preserved=True,exact_math_does_not_require_same_solver_search=True,
        barrier_log_seconds_are_cumulative_native_time_not_added_to_presolve_or_root_seconds=True))
    root=read(OUT/"S1_ROOT_FRACTIONALITY.json") if (OUT/"S1_ROOT_FRACTIONALITY.json").exists() else None
    # A completed diagnostic LP is not an exact integer oracle and not a bound
    # for the original four-vehicle unrestricted route domain.
    _write(OUT/"S1_EXACT_ORACLE_STATUS.json",dict(status="NOT_CERTIFIED",
        full_path_integer_oracle_this_followup="NOT_RUN",same_case_integer_optimum=None,
        scope="REDUCED_2_MESS_5_NODE_FULL96_ONLY",original_operational_algorithm_replaced=False,
        root_diagnostic_receipt=None if root is None else file_record(OUT/"S1_ROOT_FRACTIONALITY.json"),
        reason="LIMITED_FOLLOWUP_BUDGET_PRIORITIZED_SAME_POOL_COMPARISON_AND_ROOT_LP;HISTORICAL_BOUNDED_S1_INTEGER_RUN_DID_NOT_CERTIFY_OPTIMUM;NO_NEW_INTEGER_ORACLE_RUN"))
    hull=read(OUT/"GLOBAL_LB_AGGREGATE_MODE_HULL_DIAGNOSTIC.json")
    s1_hull=read(OUT/"S1_AGGREGATE_MODE_HULL_SEPARATION.json")
    s1_effect=read(OUT/"S1_MODE_HULL_LP_COMPARISON.json")
    s1_gate=read(OUT/"S1_MODE_HULL_VALIDITY_GATE.json")
    _write(OUT/"GLOBAL_LB_METHOD_VALIDITY.json",dict(status="DIAGNOSTIC_ONLY",
        selected_candidate="AGGREGATE_SITE_POWER_ROUTE_BINARY_MODE_INTEGER_HULL",
        symbolic_integer_validity="PASS",
        integer_validity_theorem=hull["integer_validity_theorem"],
        independent_original_source_row_validity="PASS",source_validity_scope="S1_ONLY",
        Original_4x24_independent_source_row_validity="NOT_CERTIFIED",cuts_adopted=0,
        historical_PR227_4X24_root_robust_violations=hull["robustly_violated_count"],
        historical_PR227_root_diagnostic=file_record(OUT/"GLOBAL_LB_AGGREGATE_MODE_HULL_DIAGNOSTIC.json"),
        S1_root_diagnostic=None if root is None else file_record(OUT/"S1_ROOT_FRACTIONALITY.json"),
        S1_source_integer_validity=file_record(OUT/"S1_MODE_HULL_VALIDITY_GATE.json"),
        source_power_limit_kW=s1_gate["power_limit_kW"],S1_root_robustly_violated=s1_hull["robustly_violated_count"],
        S1_diagnostic_LP_valid_cuts_applied=s1_effect["new_valid_cuts_applied"],
        S1_baseline_LP_objective=root["lp_objective"],S1_strengthened_LP_objective=s1_effect["lp_objective"],
        S1_LP_increase=s1_effect["LP_objective_increase"],S1_material_LB_improvement=False,
        S1_LP_comparison=file_record(OUT/"S1_MODE_HULL_LP_COMPARISON.json"),
        S1_unchanged_objective_continuous_mode_reselection_witness=file_record(OUT/"S1_MODE_RESELECTION_LP_WITNESS.json"),
        weaker_600kW_history=file_record(OUT/"GLOBAL_LB_WEAKER_600KW_DIAGNOSTIC_HISTORY.json"),
        strengthened_original_global_LB=None,K48_improvement="NOT_RUN",
        requires_before_adoption=["Actual same-case root LP row separation", "Original unrestricted integer route/connection/mode row audit",
            "Exact outward row transport", "Certified complete global LP dual bound", "Same-source K48 numerical increase", "Resource cost audit"],
        PR227_failure_not_repeated=True, PR227_failure="Stabilized Lagrangian no material LB gain; multi-period integer support0 violated cuts",
        restricted_master_or_Beam_ObjBound_is_Global_LB=False, S1_bound_transferred_to_original4x24=False,
        method_activated=False,Native_optimize_calls=0))
    csv_write("ORIGINAL_4X24_UB_LB_GAP.csv",[dict(status="PASS",scope="HISTORICAL_EXACT_CASE_ONLY",
        source_git="497609b46faa14ea7e32a9483a333ab32fd264ef",case_sha="34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292",
        objective="min_original_rho_max",FULL_moving_UB=.5398310226338695,K48_Global_LB=.46498486997548166,
        Global_gap_percent=100*(.5398310226338695-.46498486997548166)/.5398310226338695,
        new_FULL_UB_improvement=0.,new_certified_Global_LB=None,new_case_numeric_transfer=False,
        original_joint_restricted_bound=.5398310226338695,compressed_joint_restricted_bound=.28940049108548904,
        restricted_bound_scope="SAME_BEAM_POOL_ONLY_NOT_GLOBAL")])
    csv_write("BEAM_DIVERSITY_UB_RESULTS.csv",[
        dict(variant="ORIGINAL_BEAM_FIXED_PR221_POOL",status="PASS",case_sha=pair["identity"]["case_sha"],
            optimized_vehicles=4,candidate_nodes=24,slots=96,FULL_UB=.5398310226338695,new_UB_gain=0.,
            node_time_exploration="FIXED_HISTORICAL_POOL",actual_new_search="NOT_RUN"),
        dict(variant="ORIGINAL_BEAM_PLUS_EXACT_COMPRESSION",status="PASS",case_sha=pair["identity"]["case_sha"],
            optimized_vehicles=4,candidate_nodes=24,slots=96,FULL_UB=.5398310226338695,new_UB_gain=0.,
            node_time_exploration="IDENTICAL_FIXED_POOL",actual_new_search="NOT_RUN"),
        dict(variant="DIVERSIFIED_BEAM_PLUS_EXACT_COMPRESSION",status="NOT_RUN",case_sha=pair["identity"]["case_sha"],
            optimized_vehicles=4,candidate_nodes=24,slots=96,FULL_UB=None,new_UB_gain=None,
            node_time_exploration="NATIVE0_FIXTURE_ONLY_ALL4_VEHICLES_DESTINATION_TIME_MOVE_CLASSES",actual_new_search="NOT_RUN")])
    text=(
        "원래 Adaptive Beam → 4-MESS Joint MILP → Original FULL Validation → Incumbent Registry를 보존했다. "
        "PR220/221/222/227의 원본 계통·경로·384 Charge Mode·SOC·P/Q 구조와 역사적 Moving UB를 변경하지 않았다.\n\n"
        "15. 원래 PR221 INITIAL_1001 동일 4대·24노드·96슬롯 Direct Joint를 정확히 압축했다(PASS). "
        "변수137,635와 이진416은 그대로이며715,600행→685,819행,7,008,176NNZ→6,961,847NNZ다. "
        "기존 보수적 Box만 사용한 첫 시도는 삭제0행이었다. 보존된 Connection 부등식과 Helper 등식에서 "
        "외향 반올림한 유효 Bound를 증명한 뒤29,781 Grid 행을 삭제했다. Solver 변수 Bound는 변경하지 않았다. "
        "같은 제한 Pool의 Integer/LP 가능영역·목적·Raw Lift·MIP Start 동등성과 Original FULL 포함성을 분리했다. "
        "제한 Pool이 전체 Original Domain과 같다는 주장은 없다.\n\n"
        "16. 계산 성능 개선은 확인하지 못했다(NOT_CERTIFIED). 원본 Native19.089초/측정 Joint Wall22.887초, "
        "압축 Native20.229초/Joint Wall24.085초에 압축·증명·캐시 비용9.243초가 추가됐다. "
        "원본은 같은 Pool에서 Presolve 후 Optimal, 압축은 TimeLimit에 도달했다. 정확한 수학적 동등성은 "
        "같은 Presolve/Branch 경로를 보장하지 않는다. 전체 새 Beam 생성·반복 Wall은 NOT_RUN이며 기본 설정에 채택하지 않는다.\n\n"
        "17. 새 FULL UB 개선은0이다. 양쪽 모두0.5398310226338695이며 실제 Native Capture의 Original FULL "
        "계통·경로·SOC·PCS·Mode Replay가 PASS다. 기존 검증 Moving Incumbent는 보호하고 Registry 수정은0이다. "
        "PR221 Benchmark Start는 PR220 원시 벡터와 bit-identical하지 않으나 같은 목적과3-MOVE 경로를 보존하며 "
        "차이 최대6.384e-10인 연속 좌표도 수정 없이 각각 Replay했다.\n\n"
        "18. 별도 실험용 Diversity Admission은 네 차량에 동일 Pool Budget을 적용하고STAY/검증 Incumbent를 "
        "고정하며 목적지·이동시각·Single/Multiple MOVE를 균형 있게 입장시킨다. "
        "기존 Signed Multi-Critical P/Q·SOC·PCS·여행 서비스 손실·Rebound Score의 네 차량 결합을 사용한다. "
        "Fixture 회귀는 PASS이며 실제 새4×24 Signed Search와 동일 예산 Solver 비교는 NOT_RUN이다. "
        "충분한 실제 충전소 탐색 또는 더 좋은 UB를 주장하지 않는다.\n\n"
        "19. S1 연속 LP 진단과 정수 Oracle은 별개다. 최신 상태는S1_ROOT_FRACTIONALITY.json에 기록한다. "
        "원래30초 S1 MIP는 Root가 중단되어 분수 Route/Mode 개수를 관측하지 못했다. "
        "이번 실제 S1 LP는13.254초에 Optimal, 수치 목적0.6090630116056528이다. "
        "원본 행 잔차4.894e-13 및 Bound 잔차0에서 분수 Arc4,307개/Mode192개, "
        "복수 위치 점유187개 차량·슬롯, 동시 충방전192개 차량·슬롯을 실제 관측했다. "
        "위치+이동중 점유 질량과 SOC Balance는 보존되지만, 분수 차량의 여러 노드 전력 운전은 정수 물리 실행이 아니다. "
        "같은 S1 정수 가능 UB0.6412659669740282와의 차이0.03220295536837536을 정수 최적 Gap으로 부르지 않는다.\n\n"
        "20. K48보다 높은 인증 Global LB는 얻지 못했다. 기존0.46498486997548166을 원래 동일 Case에서만 보존한다. "
        "PR227 Lagrangian/다기간 Route-SOC 무개선 이력을 보존했다. 새 Aggregate Mode Hull 후보는 정수 "
        "단일 위치와 Binary Mode에서ΣPch≤Pmax·Mode 및ΣPdis≤Pmax·(1−Mode)를 증명하며, "
        "원래 Pmax300kW에서 역사적 실제4×24 Root109개 및 실제 S1 Root35개 강한 위반을 진단했다. "
        "처음 사용한 약한600kW 진단97건도 수정 이력으로 보존하고 원래 Pmax라고 부르지 않는다. "
        "S1 원본960 Flow/2 Terminal/1,866 Connection/1,866 Mode 행의 정확한 계수와 DAG를 "
        "독립 검증한 후384 유효 Cut을 제한된 S1 LP에만 추가했다. "
        "12.309초에 Optimal 목적0.6090630116727263, 증가6.707e-11로 수치 잡음이며 실질 개선0이다. "
        "총 충방전이 모든 슬롯에서300kW 이하라 Mode만 다시 선택하면 모든 Cut을 만족하는 같은 목적의 "
        "새 LP Witness가 존재함을 모든 원본 행과 함께 확인했다. 저장 Raw·Route/P/Q/SOC는 수정하지 않았다. "
        "분수 Mode의 현재 값 위반만으로 LB 개선이 따라오지 않는 원인을 규명했다. "
        "이 Cut을 운영 모델에 채택하지 않으며4×24 강화 Global LB는 NOT_RUN이다.\n\n"
        "21. 원본 제한 Pool ObjBound0.539831 및 압축 제한 ObjBound0.289400은 모두 Global LB가 아니다. "
        "S1 축소 Bound를4×24 Global LB로 이전하지 않는다. 원래 같은 Case의 Global Gap13.864737209%를 유지한다.\n\n"
        "동결 가능: 검증 Incumbent 보존, 동일 Pool의 Integer/LP 삭제 증명, 정확한 Raw Lift/Native Readback/"
        "FULL Replay, Source/Case/Physical/Pool SHA 기반 오염 거부. 압축·Diversity·Mode Hull은 실험용 기본 비활성이다. "
        "계산 성능·새 Beam UB·강화 Global LB·S1 정수 Oracle은 미검증 상태이며 May 캠페인 확대 근거로 쓰지 않는다.\n"
    )
    (OUT/"MESS_FINAL_REVIEW_KO.md").write_text(text,encoding="utf8")
    print(json.dumps(dict(status="PASS",reports_written=7,Native_optimize_calls=0)))


if __name__=="__main__":
    main()
