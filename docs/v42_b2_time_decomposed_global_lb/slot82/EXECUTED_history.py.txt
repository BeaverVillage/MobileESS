"""Primary Git-source comparison and unexecuted selective-integrality census."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/v42_b2_time_decomposed_global_lb"
sys.path.insert(0, str(ROOT))
from tools.time_decomposed_lb.resources import digest, read, write

HISTORY = {
    111: ("501fec79dd402e9f1770c5a403a787ebf452cc3f", [
        "v42_window/grid.py", "v42_window/oracle.py", "v42_window/universal.py",
        "docs/v42_m1_multitime_global_epigraph/W7_FORMULATION.md",
        "docs/v42_m1_multitime_global_epigraph/W7_MATRIX_CENSUS.json",
        "docs/v42_m1_multitime_global_epigraph/W7_UNIVERSAL_STOP_CERTIFICATE.json",
    ]),
    169: ("599d9ea67f6c348bfed9d1a594dc0d1eb3fd2768", [
        "docs/v42_m1_gap_rootcause_20261007/trajectory_hull.py",
        "docs/v42_m1_gap_rootcause_20261007/selective_blocks.py",
        "docs/v42_m1_gap_rootcause_20261007/EXACT_LOCAL_HULL_PROOF_KO.md",
        "docs/v42_m1_gap_rootcause_20261007/SELECTIVE_INTEGRALITY_RESULTS.csv",
        "docs/v42_m1_gap_rootcause_20261007/ROOT_GAP_ATTRIBUTION_CONCLUSION.json",
    ]),
    182: ("d541a9d15a03c4a6f8dbc1906a57c7486e9700e3", [
        "docs/v42_m1_joint_formulation_20261008/formulations.py",
        "docs/v42_m1_joint_formulation_20261008/VALIDITY_PROOF_KO.md",
        "docs/v42_m1_joint_formulation_20261008/A_MODEL_CENSUS.json",
        "docs/v42_m1_joint_formulation_20261008/B_MODEL_CENSUS.json",
        "docs/v42_m1_joint_formulation_20261008/ROOT_COMPARISON.csv",
    ]),
}


def git_bytes(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def primary_history():
    records = []
    for pr, (head, files) in HISTORY.items():
        metadata = json.loads(subprocess.check_output(["gh", "pr", "view", str(pr), "--repo", "BeaverVillage/MobileESS", "--json", "headRefOid,title,url"], cwd=ROOT))
        assert metadata["headRefOid"] == head
        primary = []
        for path in files:
            blob = git_bytes("show", f"{head}:{path}")
            copy = DOCS / "historical_primary" / f"PR{pr}" / Path(path).name
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(blob)
            primary.append(dict(original_path=path, git_revision=head,
                                git_blob_oid=git_bytes("rev-parse", f"{head}:{path}").decode().strip(),
                                bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                                saved_copy=copy.relative_to(ROOT).as_posix(),
                                url=f"https://github.com/BeaverVillage/MobileESS/blob/{head}/{path}"))
        records.append(dict(PR=pr, metadata=metadata, primary_code_and_proofs=primary))
    result = dict(schema="V42_TIME_DECOMPOSITION_PRIMARY_HISTORY_V1", PASS=True,
                  scope="Primary Git code/proofs and fixed PR-head metadata only. Copied Python is source evidence and is never imported or executed.",
                  records=records, Native_calls=0, old_results_promoted_as_current=False,
                  original_scientific_sources_unchanged=True)
    write(DOCS / "HISTORICAL_WINDOW_JOINT_AUDIT.json", result)
    text = """# 과거 Window·Joint 연구와 현재 파일럿의 차이

현재 실험은 Source18r PR207, B2 May01 원본 Case authority를 고정하고, 슬롯75/82/94에서 네 차량의 Binary 접속·Mode/PQ/PCS와 해당 시간의 원본 전체 Grid Security를 보존하는 작은 MILP다. Route·SOC·Rebound의 시간 간 결합은 사영을 포함하도록 완화한다. 현재 결과는 오직 이번 실험의 독립 인증 Bound로만 판정한다.

|과거 연구|실제 수학적 영역|이번 파일럿과의 차이|
|---|---|---|
|PR111 W7|슬롯40–46의 Grid만 남겼으나 네 차량의96슬롯 Route/SOC/terminal physics는 모두 유지한 연속완화. G1/G2/G3 조건부 W7 LP와 별도 feasible-upper 증인으로 전체 조건부 셀을 감사했다.|이번 Snapshot은 실제 Binary 접속/Mode를 유지하고 시간 간 물리를 완화한다. 조건부 epigraph 계수를 만들거나 기존 default와 합산하지 않고, 세 개의 독립 MILP Global Bound를 max로 결합한다.|
|PR169 local trajectory hull|MESS04의69–72 국소 경로149,817개·mode word16개를 유한 disjunction으로 convexify. 자유 boundary SOC와 경계를 가로지르는 원본 이동 arc를 포함하고, 원래96슬롯 C3A 행을 모두 남겼다. 이후 다른 MESS/여러 hull 및 별도 Selective Integrality를 진단했다.|새 Snapshot은 hull EF를 추가하지 않는다. 조건부 Window는 원본96슬롯 문제의 보수적인 사영 완화로 설계하며, full C3A 위에 수백만 private EF 열을 쌓지 않는다. Boundary 출발 debit/진입 transit/free SOC 증명은 같은 물리적 위험을 감사하지만, 과거 결과를 현재 Source18r 인증으로 재사용하지 않는다.|
|PR182 공동 fleet/time/grid EF|76–79의 두 차량 occupancy-count9개 disjunction, 또는 네 차량8개 Boolean selector에 원본 grid/SOC/route rows를 곱한 RLT와 cross-selector symmetry. 모든 원본96슬롯 행을 유지하고 원래 정수 projection의 양방향 동등성을 증명했다.|이번 Snapshot/Window는 의도적인 하한용 사영 완화이며 원본 정수 projection과 동등하다고 주장하지 않는다. 최대256/1,500 Binary 및 행·NNZ 안전상한으로 작은 실제 정수 MILP의 실용성을 측정한다.|

PR111의 W7 feasible-upper 증인은 해당 조건부 창의 최적값이 inherited default보다 약함을 증명했으며 Full 문제의 LB가 아니다. 과거 upper_max0.3441896824와 당시 default0.5722125039는 현재 B2 수치로 옮기지 않는다. 당시 사전 선정 창 밖 슬롯89가 중요했으므로 한 약한 창으로 모든 시간 분해를 기각할 수 없다는 점만 연구 설계에 반영한다.

PR169의100/200개 선택 Binary 실험과192개 cross-master는 그 당시 Source에서 인증 Global LB 개선0이었다. 이 관측은 이번300개 Binary 후보의 성능을 증명하지 않는다. PR169는 실제 UB 개선도 관측했으나, 현재 U4 UB 엔진을 변경하는 근거로 사용하지 않는다.

PR182 A/B는 각각 추가133,254/225,952개 연속 열, 추가312,931/1,001,388행이었다. 두 ROOT LP는600초 예산에서 TIME_LIMIT였으며 미완료 point/raw bound를 신규 Global LB로 승격하지 않았다. 이번 연구는 이러한 full-horizon EF 계산비용을 재현하지 않고 Snapshot 최대3×30초 및 조건부 Window 최대120초만 허용한다.

코드·증명·원시 결과 CSV의 exact Git blob OID/SHA256 및 보존 사본은 HISTORICAL_WINDOW_JOINT_AUDIT.json과 historical_primary에 있다. 사본 Python 파일은 실행·import하지 않았다. Native 호출0회, 기존 Source/결과 변경0회다.
"""
    (DOCS / "HISTORICAL_WINDOW_JOINT_AUDIT_KO.md").write_text(text, encoding="utf-8")
    return result


def selective_proposal():
    base = ROOT / "docs/v42_b2_root_lp_tightening/base"
    with np.load(base / "LP_DATA.npz", allow_pickle=False) as z:
        names, lower, upper = z["names"].copy(), z["lb"].copy(), z["ub"].copy()
        rows, columns = len(z["row_names"]), len(names)
    with np.load(base / "LP_ORIGINAL_BINARY.npz", allow_pickle=False) as z:
        original_binary = z["columns"].copy()
    with np.load(base / "LP_POINT.npz", allow_pickle=False) as z:
        reference = z["x"].copy()
    slots = (75, 82, 94)
    selected = []
    for raw_column in original_binary:
        column = int(raw_column)
        name = str(names[column])
        if name.split("[", 1)[0] not in {"node_activity", "charge_mode"}:
            continue
        slot = int(name.rsplit(",", 1)[-1][:-1])
        if slot not in slots:
            continue
        assert lower[column] == 0 and upper[column] == 1
        selected.append(dict(column=column, name=name, slot=slot,
                             family=name.split("[", 1)[0], unit=name.split("[", 1)[1].split(",", 1)[0],
                             saved_BASE_LP_value=float(reference[column]),
                             saved_BASE_LP_fractional=abs(float(reference[column])-round(float(reference[column]))) > 1e-8))
    families = Counter(row["family"] for row in selected)
    per_slot = Counter(row["slot"] for row in selected)
    census = read(base / "NATIVE0.json")["dimensions"]
    assert rows == census["rows"] and columns == census["columns"]
    assert len(original_binary) == 9322 and len(selected) == 300
    result = dict(schema="V42_TIME_DECOMPOSITION_SELECTIVE_INTEGRALITY_PROPOSAL_V1", PASS=True,
                  Native_optimize_calls=0, model_builds=0, actual_Solver_execution_authorized=False,
                  critical_slots=list(slots), slots_reselected_after_results=False,
                  source18r="497609b46faa14ea7e32a9483a333ab32fd264ef", parent_PR214="40ab888b884255e76fd6c89fd01933570b60c242",
                  original_binary_count=len(original_binary), selected_binary_count=len(selected),
                  selected_family_count=dict(families), selected_per_slot_count=dict(per_slot),
                  relaxed_remaining_original_binary_count=len(original_binary)-len(selected),
                  saved_BASE_fractional_selected_count=sum(row["saved_BASE_LP_fractional"] for row in selected),
                  expected_model_size=dict(rows=rows, columns=columns, nnz=census["nnz"], binary=len(selected), additional_rows=0, additional_columns=0),
                  selected=selected,
                  inclusion="F_FULL_integer projected through existing K48 authority is contained in F_K48_selective, which is contained in F_K48_LP. Only 300 original node_activity/charge_mode types revert C->B; every stored K48 row/RHS/sense/bound/objective,96-slot Route/SOC/PCS/grid row and alias contract remains unchanged. Any certified selective MILP Global Bound is therefore a valid FULL Global LB; the model incumbent is never a FULL UB.",
                  priority="Separate follow-up only after reviewing current Snapshot/Window evidence; lower priority than this capped pilot. It preserves time coupling but retains full244,265-column/143,308-row K48 resource burden, so fewer Binary does not prove cheap ROOT or material gain. PR169's nonmaterial oldSource tests are a caution, not a current impossibility proof.",
                  evidence=[digest(base / name) for name in ("LP_DATA.npz", "LP_ORIGINAL_BINARY.npz", "LP_POINT.npz", "NATIVE0.json")],
                  no_future_gain_or_resource_safety_assumed=True)
    write(DOCS / "SELECTIVE_INTEGRALITY_PROPOSAL.json", result)
    text = f"""# Selective Integrality 후속 후보 — 실행0회

Critical slot을 현재 사전등록과 동일한0-based75/82/94로 고정한다. 기존 저장K48 축·원래 Binary 목록에서 실제로 센 후보는300개다: node_activity288개, charge_mode12개이며 각 슬롯100개다. 나머지9,022개 원래 Binary는 연속완화한다. 선택한 변수의 bounds는 모두 원본[0,1]이다. Saved BASE LP에서 선택300개 중{result['saved_BASE_fractional_selected_count']}개가 fractional이지만, 이는 성능 개선의 인증이 아니다.

새 행/열은0개다. 예상 크기는143,308행/244,265열/{census['nnz']:,} NNZ/300 Binary다. Route/SOC/PCS/원래K48 계통행 및96슬롯 전체를 그대로 유지한다. 현재 작업에서는 모델을 다시 만들거나 Native를 호출하지 않았다.

원본 FULL 정수 가능해의 검증된K48 사영은 모든 선택 Binary를 만족한다. 선택하지 않은 Binary의[0,1] 연속완화는 가능영역을 넓힌다. 따라서 F_FULL_integer→F_K48_selective⊆F_K48_LP의 포함관계가 성립하며, 향후 검증된 Global Solver Bound만 FULL 하한으로 옮길 수 있다. Selective incumbent는 FULL UB 또는Actual PASS가 아니다.

실험 우선순위는 이번 Snapshot·Window 결과를 확인한 뒤 별도 승인 대상으로 보류한다. 이 후보는 시간 결합을 보존하지만 기존 대규모K48 연속 행렬을 유지하므로 Binary300개만으로 ROOT 시간·RAM 감소를 보장하지 않는다. 과거PR169100/200개 Binary의 하한 개선0은 다른 Source의 관측이며 현재 Source18r의 불가능성 증명이 아니다. 가중치 반복·제약 반복·자동 추가 Solve를 개발하지 않는다.
"""
    (DOCS / "SELECTIVE_INTEGRALITY_PROPOSAL_KO.md").write_text(text, encoding="utf-8")
    return result


if __name__ == "__main__":
    history = primary_history()
    proposal = selective_proposal()
    print(json.dumps(dict(history_PASS=history["PASS"], primary_records=len(history["records"]),
                          selected_binary_count=proposal["selected_binary_count"], expected_model_size=proposal["expected_model_size"], Native_calls=0), ensure_ascii=False))
