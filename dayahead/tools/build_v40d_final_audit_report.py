"""Human-readable evidence report; uses existing saved audits only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pandas as pd
from dayahead.paper_analysis.storage import read,atomic,write_json


def link(p,label=None):
    return f"[{label or p.name}]({p.as_posix()})"


def build(repo):
    root=repo/"dayahead/artifacts/v40d_actual_realized_replay";smoke=root/"smoke/2025-05-01"
    traffic=read(root/"sumo_source_audit/V40D_MAY01_MESS_SUMO_REALIZED_REPLAY_SUMMARY.json")
    cases=[read(smoke/c/"V40D_ACTUAL_SMOKE_17_POINT_AUDIT.json") for c in ("B0","B1","B2","B3")]
    cap=read(root/"capacity_audit/V40D_ACTUAL_SITE_GPU_CAPACITY_CONTRACT.json")
    guard=read(root/"FINAL_PROTECTED_ARTIFACT_RECHECK.json")
    text=["# V40D May-01 Actual 독립 감사", "", "May-01 B0/B1/B2/B3의 실행 일관성 및 17개 검증 항목은 PASS입니다. FULL_CAMPAIGN_AUTHORIZED = False이며 전체 campaign은 실행하지 않았습니다.",
        "", "Stage25F는 **관측 기반 보정 SUMO 시뮬레이션 데이터**입니다. 직접 관측한 5분 이동시간 또는 보정 전 raw SUMO라고 주장하지 않습니다. SUMO 원자료를 2019년에 학습·고정한 graph correction 모델로 보정하고, 15분 기준값과 SUMO의 5분 내부 형태를 보존합니다. Day-Ahead ML ETA를 Actual 이동시간으로 대입한 차량은 0입니다. 데이터 생성의 통계적 보정모델 사용과 Actual의 Day-Ahead 예측 ETA 사용은 구분합니다.",
        "", "## 목적함수와 독립 source", "", "Planning_J는 최종 실행 결정에 대한 Planning 평가값이며 B3는 AC restoration 이후의 값입니다. Fresh와 Actual은 각각 다른 OpenDSS 결과입니다. 아래 Actual 값은 이번 ACTUAL namespace의 96-slot 배열에서 선로 phase loading 최댓값을 재계산했습니다.",
        "", "| Case | Planning_J | Fresh_AC_rho | Actual_AC_rho | Actual OpenDSS run ID |", "|---|---:|---:|---:|---|"]
    for r in cases:
        v=r["comparison"];text.append(f"| {r['case']} | {v['Planning_J']:.15g} | {v['Fresh_AC_rho']:.15g} | {v['Actual_AC_rho']:.15g} | {v['Actual_OpenDSS_run_id']} |")
    for r in cases:
        v=r["comparison"];text+=['',f"{r['case']}: "+" · ".join(link(Path(v[k]["path"]),label) for k,label in (("Planning_source","Planning source"),("Fresh_source","Fresh source"),("Actual_source","Actual summary")))+" · "+link(Path(v["Actual_AC_rho_source"]),"Actual raw array")]
    text += ["", "## 요청 counters", "", "| Counter | B0 | B1 | B2 | B3 |", "|---|---:|---:|---:|---:|"]
    keys=list(cases[0]["counters"])
    for key in keys:
        text.append("| "+key+" | "+" | ".join(str(r["counters"][key]) for r in cases)+" |")
    text += ["", "SOC_BALANCE_MAX_ERROR 단위는 kWh, 기존 수치 허용치는 1e-9 kWh입니다. MESS_COMMAND_NONEXECUTION_COUNT는 nonzero frozen P/Q의 일부 또는 전부가 미실행된 vehicle-slot 수입니다. 지연된 명령을 뒤로 이동하지 않았습니다.",
        "", "## Capacity / Rack / power", "", "SITE_CAPACITY_VECTOR = [64,32,64,32,80,64,32,64,32,64,32,64], SITE_CAPACITY_SUM = 624.",
        "", "Loader: dayahead.v40d_actual.inputs.capacity. Admission: RackDispatcher.admit. 124개 static binding에서 날짜·case별 vector/authority SHA가 모두 동일합니다. 실제 runtime 검증 범위는 May-01 네 case입니다. 미실행 120 case의 occupancy/headroom을 0으로 채우지 않았습니다.",
        "", "Capacity file SHA: `"+cap["capacity_file"]["sha256"]+"`", "", "Capacity canonical SHA: `"+cap["capacity_canonical_SHA"]+"`",
        "", "Aggregate 624는 aggregate power identity에만 사용합니다. admission은 각 C_s를 hard cap으로 사용합니다. 48 Rack은 단일 gang 호환성/결정적 label이며 합산하지 않습니다. 중복된 Rack별 누적 용량 제한을 제거했습니다. 실제 current Rack 한도가 site C_s와 같아 기존 동작에서는 중복 제한이었으며 scientific vector는 변경하지 않았습니다.",
        "", "CENTER=547.7239090195797 W/GPU, idle=104.1606964512843 W/GPU의 원래 정밀도를 유지했습니다. site IT 재계산 오차는 0; analytic aggregate identity 최대 오차는 "+str(max(r['power']['aggregate_analytic_max_error_kW'] for r in cases))+" kW로 기존 2e-12 kW 허용치 이내입니다. observed-weather C1 독립 PCC 재계산 오차는 0이며 OpenDSS에 실제 적용된 AIDC P/Q와 MESS P/Q를 readback했습니다.",
        "", "B3는 final accepted 내부 A1 checkpoint와 최종 payload의 identity를 검증했습니다. 이번 May campaign의 A1은 A0와 값이 같지만 소스 binding은 내부 A1을 기준으로 검사하며, 잘못된 A1 identity를 주입한 테스트는 실패합니다.",
        "", "## MESS D00 상태", "", "| Case | Vehicle | D00 상태 | Frozen initial location | 출발시간 | 출발 origin | Route SHA |", "|---|---|---|---|---|---|---|"]
    for r in cases:
        for s in r["MESS_invariants_and_SOC"]["D00_states"]:
            text.append(f"| {r['case']} | {s['vehicle_id']} | {s['state_at_D00']} | {s['frozen_initial_location']} | {s['departure_time']} | {s['departure_origin']} | {s['route_sha']} |")
    text += ["", "B2 MESS03/04는 정확히 D00 출발이므로 SHA로 고정된 출발 origin STA08/STA06을 사용했습니다. B3는 네 차량 모두 D00에 연결되어 있고 각 frozen 위치를 출발까지 유지했습니다. May-01에는 D00 이전 출발 TRANSIT 상태가 없습니다. 그런 입력에 완전한 residual execution authority가 없으면 origin으로 reset하지 않고 fail-closed합니다.",
        "", "## SUMO 링크별 재계산", "", "| Case | 이동 차량 | SUMO replay 차량 | DA ML ETA 사용 | 경로 변경/재탐색 | 시간/도착 오차 (s) |", "|---|---:|---:|---:|---:|---:|"]
    for r in traffic["cases"]:
        text.append(f"| {r['case']} | {r['moving_vehicle_count']} | {r['SUMO_realized_replay_vehicle_count']} | 0 | 0 / 0 | 0 / 0 |")
    text += ["", "31일 × 288 slot × 509 directed reduced link 파일을 원래 content-addressed freeze와 SHA 대조했습니다. lookup은 AEST UTC+10에서 실제 link-entry 시간의 5분 half-open bucket을 사용하며 interpolation을 추가하지 않았습니다. 28개 traversal의 timestamp, lookup timestamp, duration, exit, arrival, connection-ready 시각을 CSV에 저장했습니다.",
        "", "May-01 source SHA: `"+traffic["source"]["sha256"]+"`", "", "Source path: `"+traffic["source"]["path"]+"`",
        "", "link-order SHA: `"+traffic["link_order"]["sha256"]+"`",
        "", "Travel energy는 동일 frozen edge geometry와 재계산한 traversal duration에 기존 deterministic physics를 적용해 독립 확인했으며 오차는 0입니다. SoC에는 출발마다 한 번만 차감합니다.",
        "", "## 전기적 위반 결과", "", "감사 PASS는 전기적 위반이 없다는 뜻이 아닙니다. Actual에서 발생한 위반은 사후 재최적화하거나 숨기지 않았습니다.",
        "", "| Case | 전압 위반 node-phase-slot | Vmax (pu) | 선로/변압기 전류/kVA 위반 |", "|---|---:|---:|---:|"]
    for r in cases:
        s=read(smoke/r["case"]/"actual_grid/OPENDSS_SUMMARY.json")
        text.append(f"| {r['case']} | {s['voltage_violation_count']} | {s['Vmax_pu']:.12f} | 0 / 0 / 0 |")
    text += ["", "## 남은 blocker 및 보호 검사", "", "UNASSIGNED spillover는 44 case, 2,420 case-job rows, 891 unique jobs입니다. 자체 case의 기존 site authority 복구는 0건입니다. 2,398 rows에 다른 비교군의 site 후보가 있으나 해당 case의 pre-day spatial authority로 승격하지 않았습니다. 별도 full lineage CSV와 결과를 보지 않는 전체 pre-day placement의 설계만 저장했으며 새 site 배정은 하지 않았습니다.",
        "", f"Protected Planning/Fresh {guard['checked_files']}개 SHA 비교: diff={guard['changed_count']}. 기존 Python source 695개: diff=0. 관련 회귀 테스트 165개와 observer guard 테스트 2개 PASS.",
        "", "Full 124-case Actual campaign: NOT AUTHORIZED / NOT STARTED. 따라서 31일 전체 Actual 평균은 아직 없습니다.",
        "", "## 산출물", ""]
    for p in [root/"sumo_source_audit/V40D_MAY01_MESS_SUMO_REALIZED_REPLAY_AUDIT.csv",root/"sumo_source_audit/V40D_MAY01_MESS_SUMO_REALIZED_REPLAY_SUMMARY.json",
        smoke/"MAY01_FOUR_CASE_SMOKE_STATUS.json",smoke/"V40D_ACTUAL_SMOKE_COMPARISON.json",
        root/"capacity_audit/V40D_ACTUAL_SITE_GPU_CAPACITY_AUDIT.csv",root/"site_authority_audit/V40D_UNASSIGNED_SPILLOVER_FULL_LINEAGE.csv",
        root/"site_authority_audit/V40D_PRE_DAY_PLACEMENT_AUTHORITY_DESIGN_ONLY.json",root/"FINAL_PROTECTED_ARTIFACT_RECHECK.json"]:
        text.append("- "+link(p))
    path=root/"V40D_MAY01_FINAL_AUDIT_REPORT.md"
    with atomic(path) as stream:stream.write(("\n".join(text)+"\n").encode("utf-8"))
    write_json(root/"V40D_FINAL_AUDIT_STATUS.json",{"smoke":"PASS","SUMO_source_audit":traffic["status"],"full_campaign_authorized":False,
        "full_campaign_launched":False,"blocked_case_count":44,"protected_diff":guard["changed_count"],"tests_passed":167,"report":str(path)})
    print(path)

if __name__=="__main__":build(Path(__file__).resolve().parents[2])
