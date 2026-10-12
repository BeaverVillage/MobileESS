"""Integer-equivalent node-flow representation of the literal window physics.

All literal arcs and physical rows remain. Only arc types become continuous;
binary throughput nodes restore one integer internal route. Past-boundary
parallel entry alternatives have identical physical columns and admit an
integer representative. No solver import, Native call, or Full96 construction.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.time_decomposed_lb.resources import digest, read, write
from tools.time_decomposed_lb.window_audit import replay
from tools.critical_grid_cg.verify import axis, digests, npz, require

DOCS = ROOT / "docs/v42_b2_time_decomposed_global_lb"
LITERAL = DOCS / "window_native0"
OUT = DOCS / "window_compact_native0"
SAVED = Path(r"D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output")
SOURCE18R = "497609b46faa14ea7e32a9483a333ab32fd264ef"
UNITS = ("MESS01", "MESS02", "MESS03", "MESS04")


def signature(csc, column):
    begin, end = csc.indptr[column:column+2]
    return tuple((int(row), float(value).hex()) for row, value in zip(csc.indices[begin:end], csc.data[begin:end]))


def build():
    begin = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    require(not (OUT / "COMPACT_WINDOW_NATIVE0.json").exists(), "COMPACT_PACKET_ALREADY_SEALED")
    literal = read(LITERAL / "WINDOW_NATIVE0_DESIGN.json")
    require(literal["PASS"] and literal["window"] == [88, 96] and literal["original_FULL_to_window_physical_projection_proved"], "LITERAL_AUTHORITY")
    for name, expected in literal["file_sha256"].items():
        require(digest(LITERAL / name)["sha256"] == expected, "LITERAL_PACKET_DRIFT:"+name)
    identity = read(SAVED / "SCIENTIFIC_CASE_IDENTITY.json")
    require(digest(SAVED / "SCIENTIFIC_CASE_IDENTITY.json")["sha256"] == literal["source_records"][str(SAVED / "SCIENTIFIC_CASE_IDENTITY.json")], "ROUTE_GRAPH_AUTHORITY_DRIFT")
    require(identity["case_sha"] == literal["case_sha"], "CASE_AUTHORITY")
    graph = identity["physical_prescreen_authority"]["proof"]["arcs"]
    sites = identity["physical_prescreen_authority"]["proof"]["sites"]
    require(len(sites) == 24 and len(set(sites)) == 24, "ACTUAL_SITE_AXIS")
    code_path = "v42_supercompact/formulation.py"
    source_blob = subprocess.check_output(["git", "show", f"{SOURCE18R}:{code_path}"], cwd=ROOT)
    require(source_blob == (ROOT / code_path).read_bytes(), "SOURCE18R_NODE_FLOW_PRIMARY_CODE_CHANGED")
    (OUT / "SOURCE18R_NODE_FLOW_FORMULATION.py.txt").write_bytes(source_blob)
    code_text = source_blob.decode("utf-8")
    require("types[j]='B' if k in parallel else 'C'" in code_text
            and "node_activity_link" in code_text, "SOURCE_NODE_FLOW_POLICY_NOT_RECOGNIZED")
    A = sparse.load_npz(LITERAL / "WINDOW_PHYSICS_A.npz").tocsr()
    d = npz(LITERAL / "WINDOW_PHYSICS_DATA.npz")
    warm = npz(LITERAL / "WINDOW_PHYSICS_U4.npz")["x"]
    msha, dsha = digests(A, d)
    require(msha == literal["physical_matrix_sha256"] and dsha == literal["physical_domain_sha256"], "LITERAL_NATIVE_DOMAIN_DRIFT")
    require(A.shape == (17608, 18576) and A.nnz == 98752, "LITERAL_CENSUS")
    names = list(map(str, d["names"]))
    csc = A.tocsc(); csc.sort_indices()
    arc_columns = {}
    per_unit_arcs = defaultdict(list)
    node_in, node_out = defaultdict(list), defaultdict(list)
    internal_groups = defaultdict(list)
    past_entry_groups = defaultdict(list)
    metadata = []
    for column, name in enumerate(names):
        family, coordinates = axis(name)
        if family != "arc":
            continue
        unit, k = coordinates[0], int(coordinates[1])
        origin, depart, destination, connect, route = graph[k]
        require(unit in UNITS and origin in sites and destination in sites and 0 <= depart < connect <= 96
                and depart < 96 and connect > 88, "RETAINED_ARC_TIME_GRAPH")
        require(d["vtypes"][column] == "B" and d["lb"][column] == 0 and d["ub"][column] == 1
                and d["c"][column] == 0, "LITERAL_ARC_TYPE_BOUND_OBJECTIVE")
        arc_columns[unit, k] = column
        per_unit_arcs[unit].append(column)
        node_in[unit, destination, connect].append(column)
        node_out[unit, origin, depart].append(column)
        item = dict(column=column, name=name, unit=unit, original_arc=k, origin=origin, depart=depart,
                    destination=destination, connect=connect, route=route)
        metadata.append(item)
        if depart >= 88:
            internal_groups[unit, origin, depart, destination, connect].append(item)
        else:
            past_entry_groups[unit, destination, connect].append(item)
    require(len(arc_columns) == 16204, "ACTUAL_LITERAL_ARC_COUNT")
    parallel_internal = [dict(key=list(key), arcs=items) for key, items in internal_groups.items() if len(items) > 1]
    require(not parallel_internal, "PARALLEL_INTERNAL_ROUTE_REQUIRES_RETAINED_BINARY_SELECTORS")
    entry_receipts = []
    allowed_support = {"window_flow", "window_free_entry", "window_free_exit"}
    for key, items in sorted(past_entry_groups.items()):
        exemplar = signature(csc, items[0]["column"])
        support = [str(d["row_names"][row]) for row, _value in exemplar]
        families = [name.split("[", 1)[0] for name in support]
        require(set(families) <= allowed_support, "PAST_ENTRY_ARC_COUPLES_TO_INTERNAL_ENERGY_OR_PQ")
        require("window_free_entry" in families, "PAST_ENTRY_MISSING_ENTRY_CUT")
        require(all(signature(csc, item["column"]) == exemplar for item in items), "PAST_ENTRY_PARALLEL_COLUMNS_NOT_IDENTICAL")
        entry_receipts.append(dict(key=list(key), columns=[item["column"] for item in items],
            original_arcs=[item["original_arc"] for item in items], cardinality=len(items),
            representative_column=items[0]["column"], exact_literal_column_signature=[list(pair) for pair in exemplar],
            row_names=support, original_departures=[item["depart"] for item in items],
            identical_physical_columns=True, no_internal_energy_or_power_support=True))
    old_columns = len(names)
    node_receipts = []
    rr, cc, vv = [], [], []
    for unit in UNITS:
        for time_slot in range(88, 97):
            for site in sites:
                key = (unit, site, time_slot)
                incident = node_out[key] if time_slot == 88 else node_in[key]
                column = old_columns + len(node_receipts)
                name = f"node_activity[{unit},{site},{time_slot}]"
                require(name not in names, "NODE_NAME_COLLISION")
                row = len(node_receipts)
                rr.append(row); cc.append(column); vv.append(1.)
                for arc_column in sorted(incident):
                    rr.append(row); cc.append(arc_column); vv.append(-1.)
                value = float(sum(warm[j] for j in incident))
                require(value in (0., 1.), "U4_NODE_THROUGHPUT_NOT_INTEGER")
                node_receipts.append(dict(key=list(key), column=column, name=name,
                    row=A.shape[0]+row, direction="outgoing" if time_slot == 88 else "incoming",
                    literal_arc_columns=sorted(incident), original_arcs=[int(axis(names[j])[1][1]) for j in sorted(incident)],
                    value_from_literal_U4=value,
                    Source18r_name_convention="v42_supercompact.formulation.Compact node_activity[unit,site,time]",
                    local_column_axis_is_new_window_axis=True,
                    original_C2_column_index_not_claimed=True,
                    incoming_equals_Source_outgoing_at_interior_by_preserved_flow=time_slot in range(89,96)))
    require(len(node_receipts) == 864, "COMPLETE_SITE_TIME_NODE_AXIS")
    links = sparse.csr_matrix((vv, (rr, cc)), shape=(len(node_receipts), old_columns+len(node_receipts)))
    W = sparse.vstack([sparse.hstack([A, sparse.csr_matrix((A.shape[0],len(node_receipts)))], format="csr"), links], format="csr")
    W.sort_indices()
    packet = {key: value.copy() for key, value in d.items()}
    types = packet["vtypes"].copy()
    types[list(arc_columns.values())] = "C"
    packet.update(names=np.r_[d["names"], [item["name"] for item in node_receipts]],
                  lb=np.r_[d["lb"], np.zeros(len(node_receipts))], ub=np.r_[d["ub"], np.ones(len(node_receipts))],
                  vtypes=np.r_[types, np.full(len(node_receipts), "B")], c=np.r_[d["c"], np.zeros(len(node_receipts))],
                  rhs=np.r_[d["rhs"], np.zeros(len(node_receipts))], senses=np.r_[d["senses"], np.full(len(node_receipts), "=")],
                  row_names=np.r_[d["row_names"], ["window_node_activity_link["+",".join(map(str,item["key"]))+"]" for item in node_receipts]])
    x = np.r_[warm, [item["value_from_literal_U4"] for item in node_receipts]]
    rep = replay(W, packet, x)
    require(all(value == 0 for value in rep.values()), "COMPACT_ORIGINAL_U4_LIFT")
    joined_csc = W.tocsc(); joined_csc.sort_indices()
    for item in entry_receipts:
        columns = item["columns"]
        template = signature(joined_csc, columns[0])
        require(all(signature(joined_csc, column) == template for column in columns), "ADDED_NODE_LINK_BREAKS_ENTRY_COLUMN_EQUIVALENCE")
        item["exact_compact_column_signature"] = [list(pair) for pair in template]
        item["identical_after_added_node_links"] = True
    require(np.array_equal(W[:A.shape[0], :old_columns].data, A.data)
            and np.array_equal(W[:A.shape[0], :old_columns].indices, A.indices)
            and np.array_equal(W[:A.shape[0], :old_columns].indptr, A.indptr), "ORIGINAL_LITERAL_ROWS_MODIFIED")
    sparse.save_npz(OUT / "WINDOW_PHYSICS_A.npz", W)
    np.savez_compressed(OUT / "WINDOW_PHYSICS_DATA.npz", **packet)
    np.savez_compressed(OUT / "WINDOW_PHYSICS_U4.npz", x=x)
    mapping = dict(schema="V42_COMPACT_WINDOW_MAPPING_V1", PASS=True, window=[88,96],
        original_literal_columns=old_columns, original_literal_rows=A.shape[0],
        retained_all_literal_arc_columns=True, relaxed_arc_columns=sorted(arc_columns.values()),
        arc_metadata=metadata, added_nodes=node_receipts, past_entry_groups=entry_receipts,
        internal_parallel_arcs=parallel_internal, internal_endpoint_group_count=len(internal_groups),
        past_entry_arc_count=sum(item["cardinality"] for item in entry_receipts),
        past_entry_group_count=len(entry_receipts),
        past_entry_parallel_group_count=sum(item["cardinality"] > 1 for item in entry_receipts),
        source_primary_code=dict(path=code_path, git_revision=SOURCE18R,
                                 git_blob_oid=subprocess.check_output(["git", "rev-parse", f"{SOURCE18R}:{code_path}"], cwd=ROOT).decode().strip(),
                                 sha256=hashlib.sha256(source_blob).hexdigest()),
        no_original_C2_alias_or_local_column_index_assumed=True)
    write(OUT / "COMPACT_WINDOW_MAPPING.json", mapping)
    dimensions = dict(rows=W.shape[0], columns=W.shape[1], binary=int(np.count_nonzero(packet["vtypes"] == "B")), nnz=int(W.nnz))
    require(dimensions["binary"] == 896, "EXPECTED_COMPACT_BINARY_CENSUS")
    wmsha, wdsha = digests(W, packet)
    receipt = dict(schema="V42_COMPACT_WINDOW_PHYSICAL_NATIVE0_V1", PASS=True, window=[88,96],
        source18r=SOURCE18R, case_sha=literal["case_sha"], Native_optimize_calls=0, Gurobi_imported=False,
        FULL96_model_reconstructed=False, FULL_CSR_loaded=False,
        representation="Continuous retained literal route arcs plus complete Binary node-throughput and original Binary charge_mode",
        literal_physical_authority=digest(LITERAL / "WINDOW_NATIVE0_DESIGN.json"),
        integer_equivalent_under_physical_projection=True,
        exact_literal_arc_coordinate_equality_claimed=False,
        reason_for_boundary_coordinate_scope="Only multiple past-boundary entries into one identical(site,connect) may remain fractional. They have identical complete physical column support and are replaced by one original entry arc without changing internal route, node, power, SOC, mode, grid, rho or objective. Raw boundary-entry identities themselves need not match.",
        original_FULL_to_window_physical_projection_proved=True,
        all_crossing_arcs_preserved=True, boundary_locations_free=True, boundary_SOC_original_box_only=True,
        original_terminal_SOC_not_imposed=True, departure_debit_timing_original=True,
        entry_transit_power_zero_until_original_connect=True, exit_arcs_and_future_outside_activity_not_restricted=True,
        physical_dimensions=dimensions, original_u4_physical_lift=rep,
        physical_matrix_sha256=wmsha, physical_domain_sha256=wdsha,
        raw_original_window_grid_row_counts=literal["raw_original_window_grid_row_counts"],
        minimum_complete_rows=W.shape[0]+sum(literal["raw_original_window_grid_row_counts"].values()),
        complete_window_model_constructed=False, all_window_grid_coefficients_eliminated_and_validated=False,
        safety_gates=dict(binary_cap=dimensions["binary"] <= 1500,
                          minimum_rows_cap=W.shape[0]+sum(literal["raw_original_window_grid_row_counts"].values()) <= 100000,
                          partial_physics_nnz_cap=W.nnz <= 1500000),
        Window_Native_authorized=False, Window_Optimize_calls=0,
        independent_integer_equivalence_required_before_native=True,
        classification="COMPACT_WINDOW_PHYSICAL_NATIVE0_PENDING_INDEPENDENT_PROOF",
        source_records=literal["source_records"],
        file_sha256={name:digest(OUT/name)["sha256"] for name in ("WINDOW_PHYSICS_A.npz", "WINDOW_PHYSICS_DATA.npz", "WINDOW_PHYSICS_U4.npz", "COMPACT_WINDOW_MAPPING.json", "SOURCE18R_NODE_FLOW_FORMULATION.py.txt")},
        proof="Every original binary path lifts to Binary node throughput. Conversely nonnegative continuous unit flow with free-entry1 and all node throughput0/1 has exactly one visited site/time chain. Earliest arrival (or88 outgoing) consumes full entry mass; strict time DAG and unique inside endpoint arc force every internal route/stay arc to0/1 inductively. Only past-entry parallel alternatives to the same first(site,connect) can mix; their stored complete physical columns are identical with no window energy or P/Q coefficient, so choosing one keeps all physical rows unchanged. Common power/SOC/mode/internal route and any slot grid objective are identical between literal and compact formulations.",
        wall_seconds=time.perf_counter()-begin)
    write(OUT / "COMPACT_WINDOW_NATIVE0.json", receipt)
    write(OUT / "WINDOW_NATIVE0_DESIGN.json", receipt)
    text = f"""# Window Binary 규모 및 정수 동등성

원래16,236 Binary 창은 PR209의 literal arc-Binary 차량 영역에서 잘라낸 표현이다. 96슬롯K48의9,322 Binary는 Source18r의 기존 node-activity compact/C2/C3A 표현이다. 시간 범위 차이만으로 Binary 수를 비교하면 서로 다른 표현을 혼동한다.

사전등록창[88,96)의 literal16,204 arc 열은 모두 남긴다. 그 type만[0,1] 연속으로 바꾸고, 실제24개 site·4대·88..96의864개 node-throughput Binary와 원래32개 mode Binary를 유지한다. 총896 Binary이며 실제 물리 크기는{dimensions['rows']:,}행/{dimensions['columns']:,}열/{dimensions['nnz']:,} NNZ다. 계통행을 포함한 최소 행 수는{receipt['minimum_complete_rows']:,}이다. 원래 physical row/RHS/sense/Bounds/SOC/PQ/PCS를 삭제·변경하지 않았다.

Source18r의 v42_supercompact.formulation.Compact는 route_flow를 연속으로 바꾸고 Binary node_activity와 원본 flow equality를 유지한다. 진짜 parallel endpoint arc가 있으면 selector Binary를 유지하는 정책이다. 현재 창의 모든 내부 endpoint group은 실제 검사에서 유일하다. 과거 경계를 넘어 들어오는 arc는 {mapping['past_entry_arc_count']:,}개이며, 같은 최초 연결(site,time) 그룹은 실제 저장된 창 행렬에서 동일한 열이다. 이 열에는 창 내부 이동에너지·P/Q 항이 없다. 이번 작업은 Source18r의 기존 개념을 창의 자유 경계에 적용한 재표현이며 새 strengthening이 아니다.

원본 literal 정수 경로는 node throughput0/1로 직접 lift한다. 반대로 compact의 비음수 flow와 entry mass1, node0/1을 이용하면 최초 visited node가 전체 유량1을 받는다. 모든 내부 endpoint arc가 유일하고 시간이 엄격히 증가하므로 내부 경로는 순서대로0/1이다. 최초 연결 node로 들어오는 과거 boundary arc들만 서로 섞일 수 있으나, 실제 전체 물리 열이 동일하므로 하나의 원래 arc를1로 선택하고 나머지를0으로 두어도 내부 SOC/PQ/mode/경로·모든 슬롯 계통 식·rho와 목적값이 그대로다. 원래 departure debit이88보다 앞선 에너지는 창 밖에서 이미 차감되어 창 energy row에 넣지 않는다.

동등성은 power/SOC/mode/내부 route와 계통·목적에 대한 정수 물리 사영의 동등성이다. 과거 boundary arc 각각의 raw 좌표까지 같다는 주장은 하지 않는다. 원본 FULL→literal window 포함관계와 이 사영 동등성을 결합하면 original FULL 정수 가능해는 compact Window에 포함된다. 창 시작 위치/SOC와 종단SOC를 원래 초기/종단값으로 고정하지 않고, 모든 crossing arc를 유지한다.

실제 endpoint 유일성·boundary column signature·added node links·U4 lift의 독립 verifier PASS와 전체 계통/Native readback/RAM gates 이후에만 한 번의360초 Native 후보로 사용할 수 있다. 이 생성기는 Gurobi import/Optimize/Full96 생성0회다.
"""
    (OUT / "COMPACT_WINDOW_INTEGER_EQUIVALENCE_KO.md").write_text(text, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    result = build()
    print(json.dumps({key:result[key] for key in ("PASS", "classification", "physical_dimensions", "minimum_complete_rows", "wall_seconds")}, ensure_ascii=False))
