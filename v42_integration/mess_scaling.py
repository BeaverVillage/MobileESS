"""Source-bound FULL96 MESS scaling, original physical rows and bounded pilots.

The reduced problem keeps four physical vehicles. Only selected vehicles have
decision variables; the others retain the literal P/Q/SOC/STAY source witness.
Route-pool bounds are diagnostics. Only the unrestricted reduced MILP can
supply a REDUCED_CASE_GLOBAL bound, never an original 4x24 global bound.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import csv
import gzip
import json
import math
import re

import numpy as np

from .unified_contract import REPORT, BINDING_FIELDS, digest, load_contracts, require_bindings
from .m_engine import _write, file_record, vector_sha

STAGES = {"S1": (2, 5), "S2": (2, 8), "S3": (2, 12), "S4": (2, 24),
          "S5": (4, 5), "S6": (4, 12), "S7": (4, 24)}
ACTIVE_TWO = ("MESS01", "MESS03")
SELECTION_RULE = "INITIAL_LOCATIONS_THEN_COLOCATED_AIDC_AND_FEEDER_CORRIDOR_DIVERSITY_V1"
TWO_ORDER = ("STA01", "STA08", "IDC01", "IDC11", "STA12", "STA06", "IDC02", "IDC05",
             "STA02", "STA03", "IDC08", "IDC12", "IDC03", "IDC04", "IDC06", "IDC07",
             "IDC09", "IDC10", "STA04", "STA05", "STA07", "STA09", "STA10", "STA11")
FOUR_ORDER = ("STA01", "STA12", "STA08", "STA06", "IDC01", "IDC11", "IDC02", "IDC05",
              "STA02", "STA03", "IDC08", "IDC12", "IDC03", "IDC04", "IDC06", "IDC07",
              "IDC09", "IDC10", "STA04", "STA05", "STA07", "STA09", "STA10", "STA11")
DEFAULT_MAPPING = Path("C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/tmp/"
    "c12_exact_sources_repo_cleanup/c12_exact_sources/v2038_parent/"
    "Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference/"
    "power_v70_p4f_contract/service_node_electrical_mapping_v1.csv")
DEFAULT_STAY = Path(__file__).resolve().parents[1] / (
    "docs/v42_common_am_qos_integration/receipts/DDAY_V5_FINAL/"
    "DDAY_V5_B3_FINAL_ATTEMPT01/B3/M1/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json")


def checked(receipt):
    actual = file_record(receipt["path"])
    if any(actual[k] != receipt[k] for k in ("sha256", "bytes")):
        raise ValueError("MESS_ORIGINAL_SOURCE_BYTE_DRIFT:" + receipt["path"])
    return Path(actual["path"])


def load_routes(bundle):
    """Return original record-indexed routes; retain road transit link chains."""
    table = json.loads(gzip.decompress(checked(bundle["route_table"]).read_bytes()))
    sites = tuple(table["service_ids"])
    if len(sites) != 24 or len(set(sites)) != 24:
        raise ValueError("MESS_ORIGINAL_24_UNIQUE_SERVICE_SITES_REQUIRED")
    if len(bundle["initial_MESS_sites"]) != 4 or any(
            s not in sites for s in bundle["initial_MESS_sites"].values()):
        raise ValueError("MESS_ORIGINAL_FOUR_INITIAL_VEHICLES_REQUIRED")
    from v42_native.mess import RouteArc, Battery
    battery = Battery(**bundle["battery"])
    battery.validate()
    routes, excluded = [], defaultdict(int)
    for i, row in enumerate(table["routes"]):
        if row["traffic_forecast_sha"] != bundle["traffic_forecast_sha"]:
            raise ValueError("MESS_SAME_DAY_TRAFFIC_FORECAST_SHA_DRIFT")
        s, d, t = row["origin_service_id"], row["destination_service_id"], row["departure_slot_15"]
        if s not in sites or d not in sites:
            raise ValueError("MESS_NONEXISTENT_SOURCE_SERVICE_SITE")
        if s == d:
            excluded["SAME_SITE_USES_STAY"] += 1
            continue
        arrive, connect = t + row["travel_slots_15min"], t + row["connection_ready_slots_15min"]
        if not 0 <= t < arrive <= connect < 96:
            excluded["ORIGINAL_ROUTEARC_OUTSIDE_HORIZON"] += 1
            continue
        if not row["route_link_ids"]:
            raise ValueError("MESS_ORIGINAL_ROAD_LINK_CHAIN_REQUIRED")
        route = RouteArc(f"{s}:{d}:{t}", s, d, t, arrive, connect,
                         row["energy_safe_kwh"], digest(row))
        route.validate(96)
        routes.append((i, route, row))
    return sites, tuple(routes), battery, dict(excluded)


def audit_original_sites(bundle, *, electrical_certificate, mapping=DEFAULT_MAPPING,
                         coefficients=None):
    """Actual source IDs, IEEE123 hosts, road nodes and original compatibility."""
    certificate = json.loads(checked(electrical_certificate).read_text(encoding="utf8"))
    reference = certificate["input_identity"]["identity"]["inputs"]["service_PCC_mapping"]
    mapping_record = file_record(mapping)
    if mapping_record["sha256"] != reference["sha256"] or mapping_record["bytes"] != reference["bytes"]:
        raise ValueError("MESS_ELECTRICAL_MAPPING_CERTIFICATE_SHA_DRIFT")
    sites, routes, battery, excluded = load_routes(bundle)
    with Path(mapping).open(encoding="utf-8-sig", newline="") as stream:
        rows = {r["service_node_id"]: r for r in csv.DictReader(stream)}
    if set(rows) != set(sites):
        raise ValueError("MESS_ROUTE_ELECTRICAL_MAPPING_SITE_SET_DRIFT")
    traffic_nodes, road_links = {}, set()
    for _, route, row in routes:
        for site, node in ((route.source, row["road_origin_node"]),
                           (route.destination, row["road_destination_node"])):
            if site in traffic_nodes and traffic_nodes[site] != node:
                raise ValueError("MESS_SITE_ROAD_LOCATION_DRIFT")
            traffic_nodes[site] = node
        road_links.update(row["route_link_ids"])
    result = []
    for site in sites:
        row = rows[site]
        sensitivity = dict(status="NOT_READ", original_signs_preserved=True)
        if coefficients is not None:
            p_name, q_name = f"mess_p_kw[{site}]", f"mess_q_kvar[{site}]"
            indices = [(c.control_names.index(p_name), c.control_names.index(q_name)) for c in coefficients]
            profile = np.concatenate([np.asarray(c.current_matrix)[[p, q]].ravel()
                                      for c, (p, q) in zip(coefficients, indices)])
            sensitivity = dict(status="READ_ORIGINAL_SIGNED_FULL96", P_control=p_name, Q_control=q_name,
                vector_sha=vector_sha(profile), signed_min=float(profile.min()), signed_max=float(profile.max()),
                source_coefficient_shas=sorted({c.coefficient_sha256 for c in coefficients}),
                original_signs_preserved=True, ranking_or_bound_claim=False)
        result.append(dict(service_id=site, IEEE123_host_bus=row["electrical_host_bus"],
            phases=[1, 2, 3], MESS_PCC_bus="mess_" + site.lower() + "_pcc.1.2.3",
            phase_authority="ORIGINAL_THREE_PHASE_PCC_MAPPING", road_node=traffic_nodes[site],
            AIDC_coexists=row["asset_type"] == "IDC", AIDC_id="A" + site if row["asset_type"] == "IDC" else None,
            connect_and_charge_allowed=float(row["mess_transformer_kva"]) > 0,
            MESS_transformer_kVA=float(row["mess_transformer_kva"]),
            P_limit_kW=battery.p_limit, PCS_kVA=battery.pcs_kva,
            Q_limit="ORIGINAL_PCS16_INNER_POLYGON_WITH_P_NET", electrical_source_distance=int(row["host_source_distance"]),
            traffic_route_records=sum(r.source == site for _, r, _ in routes),
            travel_contract="ORIGINAL_ROAD_LINK_CHAIN_ETA_ENERGY_NO_NEW_DIRECT_ROAD_ARC",
            geographic_coordinates="NOT_PRESENT_IN_CERTIFIED_ROUTE_OR_ELECTRICAL_MAPPING",
            sensitivity=sensitivity))
    return dict(schema="ORIGINAL24_MESS_SITE_AUDIT_V1", PASS=True, source_generated_sites=False,
        service_sites=list(sites), site_count=len(sites), rows=result,
        route_source=bundle["route_table"], mapping_source=mapping_record,
        electrical_certificate=electrical_certificate, accepted_original_route_records=len(routes),
        excluded_records=excluded, road_transit_links=len(road_links), transit_links_are_not_charging_sites=True,
        battery=bundle["battery"], initial_sites=bundle["initial_MESS_sites"],
        AIDC_MESS_separate_resources_and_injections=True, Native_optimize_calls=0)


@dataclass
class ScaleCase:
    stage: str
    sites: tuple
    active: tuple
    inactive: tuple
    initial: dict
    routes: tuple
    route_records: tuple
    battery: object
    stay_plan: dict
    bindings: dict
    case_sha: str
    manifest: dict
    original_sites: tuple
    original_routes: tuple
    original_initial: dict
    expected_stage_bindings: dict
    planning_stage: str = "M1"
    warm_plan: dict | None = None


def validate_stay_physics(stay, sites, routes, battery, initial):
    """Reconstruct and replay all four original physical vehicles, no certificate copy."""
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    if set(stay["initial_sites"]) != set(initial) or stay["initial_sites"] != initial or stay.get("moves"):
        raise ValueError("MESS_FULL_FOUR_SOURCE_STAY_REQUIRED")
    if stay["time_axis"] != list(range(96)) or stay["dt_seconds"] != 900:
        raise ValueError("MESS_SOURCE_STAY_FULL96_REQUIRED")
    names = ["P_kW", "Q_kvar", "SOC_kWh", "Mode", "connection_site"]
    if any(set(stay[k]) != set(initial) for k in names):
        raise ValueError("MESS_SOURCE_STAY_PER_VEHICLE_FIELDS_REQUIRED")
    values, selected = {}, {}
    for unit, origin in initial.items():
        if stay["connection_site"][unit] != [origin] * 96:
            raise ValueError("MESS_INACTIVE_SOURCE_LOCATION_IS_NOT_STAY")
        selected[unit] = [sites.index(origin)*96+t for t in range(96)]
        if stay.get("routes", stay.get("route_paths"))[unit] != selected[unit]:
            raise ValueError("MESS_SOURCE_STAY_ROUTE_INDEX_DRIFT")
        if len(stay["SOC_kWh"][unit]) != 97 or any(len(stay[k][unit]) != 96 for k in names if k != "SOC_kWh"):
            raise ValueError("MESS_SOURCE_STAY_ARRAY_AXIS_DRIFT")
        for t in range(97):
            values[f"SOC[{unit},{t}]"] = float(stay["SOC_kWh"][unit][t])
        if values[f"SOC[{unit},0]"] != battery.initial:
            raise ValueError("MESS_SOURCE_STAY_INITIAL_SOC_DRIFT")
        for t in range(96):
            values[f"charge_mode[{unit},{t}]"] = float(stay["Mode"][unit][t])
            p, q = float(stay["P_kW"][unit][t]), float(stay["Q_kvar"][unit][t])
            for site in sites:
                values[f"Pch[{unit},{site},{t}]"] = max(0., -p) if site == origin else 0.
                values[f"Pdis[{unit},{site},{t}]"] = max(0., p) if site == origin else 0.
                values[f"Q[{unit},{site},{t}]"] = q if site == origin else 0.
    point = dict(values=values, chosen_arcs=selected, mode="MILP", initial_sites=initial)
    physical = validate(point, sites, [r for _, r, _ in routes], battery, 96)
    modes = supplemental_physical(point, sites, battery)
    if not physical["PASS"] or not modes["charge_mode_and_connection_PASS"]:
        raise ValueError("MESS_CURRENT_SOURCE_STAY_PHYSICAL_REPLAY_REJECTED")
    return dict(PASS=True, original_route_SOC_PCS=physical, original_Mode=modes,
        all_four_vehicles_replayed=True, historical_grid_certificate_transferred=False,
        current_grid_revalidation="REQUIRED_IN_PILOT_ORIGINAL_ROWS", Native_optimize_calls=0)


def require_stage_bindings(bindings, expected_stage_bindings=None, *, contracts=REPORT):
    shared=load_contracts(contracts)["bindings"]
    expected=shared if expected_stage_bindings is None else expected_stage_bindings
    require_bindings(bindings,expected)
    for name in BINDING_FIELDS:
        if name not in ("aidc_anchor","mess_anchor") and expected[name]!=shared[name]:
            raise ValueError("MESS_STAGE_COMMON_SOURCE_CONTRACT_DRIFT:"+name)
    return dict(expected)


def build_scale_case(bundle, stage, stay_plan, *, bindings, contracts=REPORT, stay_source=None,
                     expected_stage_bindings=None,planning_stage="M1",warm_plan=None):
    expected=require_stage_bindings(bindings,expected_stage_bindings,contracts=contracts)
    if planning_stage not in ("M1","M2"):
        raise ValueError("MESS_ORIGINAL_PLANNING_STAGE_REQUIRED")
    if stage not in STAGES:
        raise ValueError("MESS_UNKNOWN_SCALING_STAGE")
    sites, routes, battery, excluded = load_routes(bundle)
    count, size = STAGES[stage]
    order = TWO_ORDER if count == 2 else FOUR_ORDER
    if set(order) != set(sites):
        raise ValueError("MESS_FROZEN_SELECTION_SOURCE_SITE_SET_DRIFT")
    selected = order[:size]
    active = ACTIVE_TWO if count == 2 else tuple(sorted(bundle["initial_MESS_sites"]))
    inactive = tuple(u for u in sorted(bundle["initial_MESS_sites"]) if u not in active)
    if any(bundle["initial_MESS_sites"][u] not in selected for u in active):
        raise ValueError("MESS_ACTIVE_INITIAL_SITE_NOT_IN_STAGE")
    replay = validate_stay_physics(stay_plan, sites, routes, battery, bundle["initial_MESS_sites"])
    kept = tuple((i, r, row) for i, r, row in routes if r.source in selected and r.destination in selected)
    if any(not any(r.source == bundle["initial_MESS_sites"][u] for _, r, _ in kept) for u in active):
        raise ValueError("MESS_ACTIVE_UNIT_HAS_NO_ORIGINAL_MOVING_ROUTE")
    specification = dict(stage=stage, slots=96, slot_seconds=900, physical_units=4,
        optimization_units=list(active), inactive_units=list(inactive), charging_sites=list(selected),
        selection_rule=SELECTION_RULE, rule_frozen_before_execution=True,
        selection_rationale=dict(required_initial_sites=True, S1_AIDC_cohosts=["IDC01", "IDC11"],
            S1_different_electrical_corridors=["28", "67", "149", "79", "83"],
            sensitivity_diversity="ORIGINAL_SIGNED_VECTOR_AUDIT;NOT_PERFORMANCE_SELECTION_OR_PRUNING",
            S1_other_vehicle_than_historical_MESS03="MESS01", not_selected_as_neighborhood_of_best_MESS03=True),
        original_route_record_indices=[i for i, _, _ in kept], original_route_source=bundle["route_table"],
        original_battery=bundle["battery"], original_initial_sites=bundle["initial_MESS_sites"],
        inactive_stay_source=stay_source, inactive_stay_plan_sha=digest(stay_plan),
        inactive_current_source_physical_replay=replay, exact_inactive_Q_preserved=True,
        full96_physical_scope=True, original_traffic_network_preserved=True,
        new_direct_road_arcs=0, historical_numeric_LB_transferred=False,
        bindings=bindings, measurement_status="NOT_RUN")
    if expected_stage_bindings is not None:
        specification.update(planning_stage=planning_stage,
            anchor_scope="SUPERVISOR_CURRENT_NATIVE_AIDC_STAGE_BINDINGS",
            prior_MESS_warm_plan_sha=None if warm_plan is None else digest(warm_plan),
            prior_MESS_numeric_UB_LB_transferred=False)
    case_sha = digest(specification)
    specification["reduced_case_sha"] = case_sha
    return ScaleCase(stage, tuple(selected), tuple(active), inactive,
        {u: bundle["initial_MESS_sites"][u] for u in active}, tuple(r for _, r, _ in kept), kept,
        battery, deepcopy(stay_plan), dict(bindings), case_sha, specification,
        sites, tuple(r for _, r, _ in routes), dict(bundle["initial_MESS_sites"]),expected,
        planning_stage,None if warm_plan is None else deepcopy(warm_plan))


def fixed_injections(scale, all_sites):
    """Inactive literal Q, including sites outside the optimized charging set."""
    p, q = {s: np.zeros(96) for s in all_sites}, {s: np.zeros(96) for s in all_sites}
    for unit in scale.inactive:
        for t, site in enumerate(scale.stay_plan["connection_site"][unit]):
            p[site][t] += float(scale.stay_plan["P_kW"][unit][t])
            q[site][t] += float(scale.stay_plan["Q_kvar"][unit][t])
    return p, q


def validate_scale_identity(scale):
    """A stored SHA never grants authority to mutated mutable Python objects."""
    manifest = deepcopy(scale.manifest)
    claimed = manifest.pop("reduced_case_sha", None)
    if claimed != scale.case_sha or digest(manifest) != scale.case_sha:
        raise ValueError("MESS_REDUCED_CASE_MANIFEST_CONTENT_DRIFT")
    if (tuple(manifest["charging_sites"]) != scale.sites or
            tuple(manifest["optimization_units"]) != scale.active or
            tuple(manifest["inactive_units"]) != scale.inactive or
            manifest["bindings"] != scale.bindings or
            manifest["original_initial_sites"] != scale.original_initial or
            manifest["original_battery"] != vars(scale.battery) or
            digest(scale.stay_plan) != manifest["inactive_stay_plan_sha"] or
            scale.initial != {u:scale.original_initial[u] for u in scale.active}):
        raise ValueError("MESS_REDUCED_CASE_MUTABLE_STATE_DRIFT")
    if manifest.get("planning_stage","M1")!=scale.planning_stage or (
            "prior_MESS_warm_plan_sha" in manifest and manifest["prior_MESS_warm_plan_sha"] !=
            (None if scale.warm_plan is None else digest(scale.warm_plan))):
        raise ValueError("MESS_CURRENT_STAGE_WARM_ANCHOR_DRIFT")
    if [i for i,_,_ in scale.route_records] != manifest["original_route_record_indices"] or tuple(
            r for _,r,_ in scale.route_records) != scale.routes:
        raise ValueError("MESS_ORIGINAL_ROUTE_SELECTION_DRIFT")
    for _,route,row in scale.route_records:
        if digest(row) != route.authority_sha256 or (
                row["origin_service_id"],row["destination_service_id"],row["departure_slot_15"],
                row["energy_safe_kwh"]) != (route.source,route.destination,route.depart,route.energy_kwh):
            raise ValueError("MESS_ORIGINAL_ROUTE_RECORD_CONTENT_DRIFT")
    checked(manifest["original_route_source"])
    return dict(PASS=True,reduced_case_sha=scale.case_sha)


def validate_response_coefficients(coefficients, source_receipt, bindings):
    """Compare every in-memory descriptor/array against byte-frozen source NPZ."""
    if not source_receipt or source_receipt["sha256"] != bindings["response_sha"]:
        raise ValueError("MESS_SHARED_RESPONSE_SHA_DRIFT")
    path = checked(source_receipt)
    from .production_case import FIELDS
    if len(coefficients) != 96:
        raise ValueError("MESS_SHARED_RESPONSE_FULL96_REQUIRED")
    with np.load(path,allow_pickle=False) as packet:
        controls,branches = tuple(map(str,packet["control_names"])),tuple(map(str,packet["branch_names"]))
        # A compressed NPZ member decompresses on every __getitem__. Each
        # full96 scientific array is loaded exactly once before slot slicing.
        cached={name:packet[name].copy() for name in FIELDS+("anchor_control",)}
        source_ratings=packet["transformer_ratings"].copy()
        source_denominators=packet["rating_a"].copy()
        for tick,c in enumerate(coefficients):
            if c.slot != tick or c.coefficient_sha256 != bindings["response_sha"] or (
                    tuple(c.control_names),tuple(c.branch_names)) != (controls,branches):
                raise ValueError("MESS_SHARED_RESPONSE_DESCRIPTOR_DRIFT")
            for name in FIELDS:
                if not np.array_equal(np.asarray(getattr(c,name)),cached[name][tick],equal_nan=True):
                    raise ValueError("MESS_SOURCE_RESPONSE_ARRAY_CONTENT_DRIFT:"+name)
            if not np.array_equal(np.asarray(c.anchor),cached["anchor_control"][tick],equal_nan=True):
                raise ValueError("MESS_SOURCE_RESPONSE_ANCHOR_CONTENT_DRIFT")
            # Python None is the explicit source NaN rating representation.
            ratings=np.asarray([np.nan if v is None else float(v) for v in c.transformer_ratings])
            if not np.array_equal(ratings,source_ratings,equal_nan=True):
                raise ValueError("MESS_SOURCE_TRANSFORMER_RATING_DRIFT")
            if not np.array_equal(np.asarray(c.current_denominators_A),source_denominators,equal_nan=True):
                raise ValueError("MESS_SOURCE_NORMALAMPS_DENOMINATOR_DRIFT")
    checked(source_receipt)
    return dict(PASS=True,response_sha=bindings["response_sha"],source=source_receipt,
        in_memory_full96_arrays_rechecked=True)


def validate_pilot_inputs(scale, aidc_anchor, coefficients, coefficient_source):
    from .coordinator import _full_a
    _full_a(aidc_anchor)
    if aidc_anchor["aidc_anchor"] != scale.bindings["aidc_anchor"]:
        raise ValueError("MESS_CURRENT_SHARED_AIDC_ANCHOR_REQUIRED")
    require_stage_bindings(scale.bindings,scale.expected_stage_bindings)
    return dict(PASS=True,scale=validate_scale_identity(scale),
        response=validate_response_coefficients(coefficients,coefficient_source,scale.bindings),
        AIDC_content_digest_revalidated=True)


def validate_grid_authority(authority, *, bundle, electrical_certificate, thermal_receipt,
                            coefficients):
    """All service-transformer current rows and exact current source authorities."""
    if authority.require_all_transformer_currents is not True or authority.frozen is not True:
        raise ValueError("MESS_ALL_ORIGINAL_TRANSFORMER_CURRENT_ROWS_REQUIRED")
    certificate=json.loads(checked(electrical_certificate).read_text(encoding="utf8"))
    thermal=json.loads(checked(thermal_receipt).read_text(encoding="utf8"))
    if certificate.get("schema") != "V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2":
        raise ValueError("MESS_EXACT_11SVR_ELECTRICAL_CERTIFICATE_REQUIRED")
    from .a_engine import digest as native_digest
    expected=(certificate["input_identity"]["identity"]["inputs"]["OpenDSS_master"]["sha256"],
        native_digest(bundle["capacities"]),native_digest(bundle),native_digest(bundle["battery"]))
    actual=(authority.topology_sha,authority.mapping_sha,authority.service_sha,authority.pq_sha)
    if actual != expected:
        raise ValueError("MESS_CURRENT_GRID_AUTHORITY_CONTENT_SHA_DRIFT")
    compiled=thermal["transformer_current_authority_sha256"]
    from v42_pr134_b1.common import digest as compiled_digest
    if (thermal.get("PASS") is not True or compiled_digest(thermal["identity"]) != compiled or
            authority.transformer_current_authority_sha256 != compiled or
            authority.thermal_authority != thermal or
            any(c.transformer_current_authority_sha256 != compiled for c in coefficients)):
        raise ValueError("MESS_CURRENT_COMPILED_TRANSFORMER_AUTHORITY_DRIFT")
    return dict(PASS=True,all_original_transformer_current_rows_required=True,
        electrical_certificate=electrical_certificate,thermal_receipt=thermal_receipt,
        compiled_transformer_current_sha=compiled,source_topology_mapping_service_PQ_sha_exact=True)


def full_vehicle_replay(scale, active_case, point):
    """Inverse-map active route indices and independently replay all four units."""
    from .m_engine import PathGraph
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    sites, routes = scale.original_sites, scale.original_routes
    full_arcs = [(s,t,s,t+1,None) for s in sites for t in range(96)] + [
        (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    def key(a):
        return tuple(a[:4])+(None if a[-1] is None else a[-1].authority_sha256,)
    indices = {key(a):k for k,a in enumerate(full_arcs)}
    graph = PathGraph(active_case)
    active_paths = graph.paths(point)
    named = dict(zip(map(str, active_case.original_d["names"]), map(float, active_case.lift(point))))
    values, chosen = {}, {}
    plan = dict(schema="V42_FULL_MESS_PHYSICAL_ANCHOR_V1",initial_sites=scale.original_initial, time_axis=list(range(96)), dt_seconds=900,
        P_sign="POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch", Q_sign="ORIGINAL_Q_VARIABLE_SIGN",
        P_kW={},Q_kvar={},SOC_kWh={},Mode={},connection_site={},routes={},moves=[],
        shared_bindings=scale.bindings,reduced_case_sha=scale.case_sha,
        physical_units=4, original24_source_route_index_mapping=True)
    for unit, origin in scale.original_initial.items():
        if unit in active_paths:
            chosen[unit] = [indices[key(graph.arcs[k])] for k in active_paths[unit]]
        else:
            chosen[unit] = [sites.index(origin)*96+t for t in range(96)]
        plan["routes"][unit] = chosen[unit]
        connection = [None]*96
        for k in chosen[unit]:
            a = full_arcs[k]
            if a[-1] is None:
                connection[a[1]] = a[0]
            else:
                plan["moves"].append(dict(unit=unit,original_arc=k,source=a[0],depart=a[1],
                    destination=a[2],connect=a[3],route_id=a[-1].route_id,
                    energy_kWh=a[-1].energy_kwh,route_authority_sha256=a[-1].authority_sha256))
        plan["connection_site"][unit] = connection
        plan["P_kW"][unit],plan["Q_kvar"][unit],plan["Mode"][unit],plan["SOC_kWh"][unit] = [],[],[],[]
        for t in range(97):
            soc = named[f"SOC[{unit},{t}]"] if unit in scale.active else float(scale.stay_plan["SOC_kWh"][unit][t])
            values[f"SOC[{unit},{t}]"] = soc
            plan["SOC_kWh"][unit].append(soc)
        for t in range(96):
            mode = named[f"charge_mode[{unit},{t}]"] if unit in scale.active else float(scale.stay_plan["Mode"][unit][t])
            values[f"charge_mode[{unit},{t}]"] = mode
            plan["Mode"][unit].append(mode)
            total_p = total_q = 0.
            for site in sites:
                if unit in scale.active:
                    ch = named.get(f"Pch[{unit},{site},{t}]",0.)
                    dis = named.get(f"Pdis[{unit},{site},{t}]",0.)
                    q = named.get(f"Q[{unit},{site},{t}]",0.)
                else:
                    p = float(scale.stay_plan["P_kW"][unit][t])
                    ch = max(0.,-p) if site == origin else 0.
                    dis = max(0.,p) if site == origin else 0.
                    q = float(scale.stay_plan["Q_kvar"][unit][t]) if site == origin else 0.
                values[f"Pch[{unit},{site},{t}]"],values[f"Pdis[{unit},{site},{t}]"],values[f"Q[{unit},{site},{t}]"] = ch,dis,q
                total_p += dis-ch; total_q += q
            plan["P_kW"][unit].append(total_p); plan["Q_kvar"][unit].append(total_q)
    source = dict(values=values,initial_sites=scale.original_initial,chosen_arcs=chosen,mode="MILP")
    physical = validate(source, sites, routes, scale.battery, 96)
    modes = supplemental_physical(source, sites, scale.battery)
    inactive_exact = all(plan[k][u] == scale.stay_plan[k][u]
        for u in scale.inactive for k in ("P_kW","Q_kvar","SOC_kWh","Mode","connection_site","routes"))
    passed = physical["PASS"] and modes["charge_mode_and_connection_PASS"] and inactive_exact
    replay = dict(PASS=bool(passed), original_four_vehicle_route_SOC_PCS=physical,
        original_Mode=modes,inactive_P_Q_SOC_Mode_location_bit_exact=inactive_exact,
        all_four_vehicles_replayed=True, grid_injections_validated_in_current_original_rows=True,
        Native_optimize_calls=0, historical_grid_certificate_transferred=False)
    if not passed:
        raise ValueError("MESS_COMBINED_ACTIVE_INACTIVE_FOUR_VEHICLE_REPLAY_REJECTED")
    plan["P_by_site"]={s:[sum(plan["P_kW"][u][t] for u in plan["initial_sites"]
        if plan["connection_site"][u][t]==s) for t in range(96)] for s in sites}
    plan["Q_by_site"]={s:[sum(plan["Q_kvar"][u][t] for u in plan["initial_sites"]
        if plan["connection_site"][u][t]==s) for t in range(96)] for s in sites}
    plan["SOC"]=plan["SOC_kWh"]
    plan["all_physical_inputs_fixed"]=True
    from .a_engine import digest as handoff_digest
    plan["plan_sha"] = handoff_digest(plan)
    return replay, plan


def prescreen(scale):
    """Reuse the original forward/backward DAG proof, never prune by score."""
    from v42_native.mess_domain import build_domain
    domain = build_domain(scale.sites, scale.initial, scale.routes, scale.battery, 96)
    proof = domain.receipt()
    if not proof["PASS"]:
        raise ValueError("MESS_ORIGINAL_DAG_PRESCREEN_PROOF_REJECTED")
    return domain, dict(proof, reduced_case_sha=scale.case_sha,
        sensitivity_deletions=0, PCS_SOC_mode_rows_unchanged=True,
        SOC_empty_path_checks_not_fractional_arc_zero_proofs=True)


def beam_paths(scale, *, scorer=None, width=16, max_moves=4):
    """Deterministic diverse original-index route pool; heuristic cuts are explicit."""
    if width < 1 or max_moves < 1:
        raise ValueError("MESS_BEAM_POSITIVE_WIDTH_AND_DEPTH_REQUIRED")
    domain, receipt = prescreen(scale)
    arcs = domain.arcs
    outgoing = defaultdict(list)
    stay = {}
    for k, a in enumerate(arcs):
        outgoing[a[:2]].append(k)
        if a[-1] is None:
            stay[a[:2]] = k
    pools, counters = {}, defaultdict(int)
    for unit in scale.active:
        admissible = set(next(u.retained for u in domain.units if u.mess == unit))
        origin = scale.initial[unit]
        baseline = tuple(stay[origin, t] for t in range(96))
        completed = {baseline: (0., 0.)}
        # Multiple first corridors and MOVE counts survive each round-robin beam.
        initial_energy = Fraction(float(scale.battery.initial))
        minimum, maximum = Fraction(float(scale.battery.minimum)), Fraction(float(scale.battery.maximum))
        terminal = Fraction(float(scale.battery.terminal))
        charge_step = Fraction(float(scale.battery.dt_hours*scale.battery.eta_charge))*Fraction(float(scale.battery.p_limit))
        frontier = {0: [(origin, (), 0, "STAY", initial_energy, 0., 0.)]}
        for tick in range(96):
            groups = defaultdict(list)
            for label in frontier.pop(tick, []):
                groups[label[2], label[3]].append(label)
            kept = []
            while groups and len(kept) < width:
                for key in sorted(list(groups)):
                    group = groups[key]
                    group.sort(key=lambda z: (z[-1], z[-2], z[1]))
                    kept.append(group.pop(0))
                    if not group:
                        del groups[key]
                    if len(kept) >= width:
                        break
            counters["HEURISTIC_BEAM_LABEL_DISCARDS"] += sum(map(len, groups.values()))
            for site, path, moves, corridor, upper_soc, energy, score in kept:
                for k in outgoing[site, tick]:
                    if k not in admissible:
                        counters["PROVEN_STRUCTURAL_ZERO"] += 1
                        continue
                    arc = arcs[k]
                    moving = arc[-1] is not None
                    if moving and moves >= max_moves:
                        counters["HEURISTIC_MOVE_DEPTH_DISCARDS"] += 1
                        continue
                    # Optimistic PCS charging upper bound, safe only as path infeasibility test.
                    cost = float(arc[-1].energy_kwh) if moving else 0.
                    next_soc = upper_soc-Fraction(cost) if moving else min(maximum, upper_soc+charge_step)
                    suffix_upper = min(maximum, next_soc+(96-arc[3])*charge_step)
                    if next_soc < minimum or suffix_upper < terminal:
                        counters["PHYSICAL_PATH_SOC_NECESSARY_REJECTIONS"] += 1
                        continue
                    new_path = path+(k,)
                    new_score = float(scorer(unit, new_path, arcs)) if scorer else energy+cost
                    first = arc[2] if moving and corridor == "STAY" else corridor
                    item = (arc[2], new_path, moves+int(moving), first, next_soc, energy+cost, new_score)
                    if arc[3] == 96:
                        completed[new_path] = (new_score, energy+cost)
                    else:
                        frontier.setdefault(arc[3], []).append(item)
        # Pin STAY and one MOVE per destination independently of beam truncation.
        for k, arc in enumerate(arcs):
            if arc[-1] is None or k not in admissible or arc[0] != origin or arc[1] not in (0, 24, 48, 72):
                continue
            optimistic = initial_energy-Fraction(float(arc[-1].energy_kwh))
            if optimistic < minimum:
                continue
            if optimistic+(96-arc[3])*charge_step < terminal:
                continue
            path = tuple(stay[origin, t] for t in range(arc[1]))+(k,)+tuple(
                stay[arc[2], t] for t in range(arc[3], 96))
            completed[path] = (float(scorer(unit, path, arcs)) if scorer else float(arc[-1].energy_kwh),
                               float(arc[-1].energy_kwh))
        chosen = [baseline]
        families = defaultdict(list)
        for path, scores in completed.items():
            if path == baseline:
                continue
            moves = [arcs[k] for k in path if arcs[k][-1] is not None]
            families[len(moves), moves[0][2] if moves else "STAY"].append((scores, path))
        while families and len(chosen) < max(width, len(scale.sites)):
            for key in sorted(list(families)):
                entries = families[key]
                entries.sort()
                chosen.append(entries.pop(0)[1])
                if not entries:
                    del families[key]
                if len(chosen) >= max(width, len(scale.sites)):
                    break
        pools[unit] = [list(p) for p in chosen]
    return pools, dict(PASS=True, reduced_case_sha=scale.case_sha, Native_optimize_calls=0,
        original_index_arcs_only=True, STAY_pinned=True, scorer="SIGNED_MINIMAX" if scorer else "TRAVEL_ENERGY_DIVERSITY_ONLY",
        score_is_not_bound_or_hard_feasibility=True, heuristic_search_not_full_route_domain=True,
        counters=dict(counters), path_counts={u: len(p) for u, p in pools.items()}, prescreen=receipt)


def source_grid_controls(scale, all_sites, coefficients, aidc_anchor, p, q):
    fixed_p, fixed_q = fixed_injections(scale, all_sites)
    rows = []
    for t, c in enumerate(coefficients):
        row = []
        for name in c.control_names:
            site = name.split("[", 1)[1][:-1]
            if name.startswith("aidc_load_kw["):
                row.append(float(aidc_anchor["AIDC_P_by_site"][site][t]))
            elif name.startswith("mess_p_kw["):
                row.append(p.get((site, t), 0.)+float(fixed_p[site][t]))
            elif name.startswith("mess_q_kvar["):
                row.append(q.get((site, t), 0.)+float(fixed_q[site][t]))
            else:
                raise ValueError("MESS_SOURCE_GRID_UNRECOGNIZED_CONTROL")
        rows.append(row)
    return rows


def model_build_estimate(scale, coefficients):
    """Conservative admission estimate, explicitly not measured build performance."""
    domain, _ = prescreen(scale)
    connected = sum(sum(row[2] for row in u.slots) for u in domain.units)
    arcs = sum(len(u.retained) for u in domain.units)
    native_columns = arcs + connected*3 + len(scale.active)*(96+97) + 1
    grid_rows = sum(2*len(c.voltage_constant) + sum(1 if str(n).lower().startswith("transformer.") else 16
                    for n in c.branch_names) + sum(r is not None for r in c.transformer_ratings)*16 for c in coefficients)
    native_rows = grid_rows + connected*22 + len(scale.active)*(len(scale.sites)*96+99)
    # Python expression/node overhead can dominate sparse numeric storage.
    estimate = max(512*1024**2, native_rows*3072 + native_columns*4096)
    return dict(estimate_only=True, measured_build_status="NOT_RUN", estimated_columns=native_columns,
        estimated_rows=native_rows, estimated_peak_private_bytes=estimate,
        required_available_RAM_bytes=max(8*1024**3, estimate*2),
        full_grid_rows_retained=grid_rows, reduction_changes_route_PQ_domains_not_grid_rows=True)


class _ConstructionDeadline:
    stage = "M1"
    def __init__(self, budget,stage="M1"):
        self.budget = budget
        self.stage=stage
    def check(self):
        if self.budget.remaining() <= 0:
            raise RuntimeError("MESS_SHARED_NATIVE_BUDGET_EXHAUSTED")


def _attr(model, name):
    try:
        value = getattr(model, name)
        return value if not isinstance(value, float) or math.isfinite(value) else None
    except Exception:
        return None


def constructor_summary(receipt):
    """Native.solve updates the optimizer result in place; never embed it in itself."""
    domain=receipt.get("physical_prescreen", {})
    return dict(model_build_seconds=receipt.get("model_build_seconds"),
        model_size_before_solve=deepcopy(receipt.get("model_size_before_solve")),
        route_variable_count=receipt.get("route_variable_count"),
        route_move_arcs=receipt.get("route_move_arcs"),
        reachability_removed=receipt.get("reachability_removed"),
        zero_unreachable_PQ_columns=receipt.get("zero_unreachable_PQ_columns"),
        PCS_mode=receipt.get("PCS_mode"),
        physical_prescreen=dict(PASS=domain.get("PASS"),state_sha=domain.get("state_sha"),
            structural_proof=domain.get("structural_proof"),
            original_constructor_forward_removed_arcs=domain.get("original_constructor_forward_removed_arcs"),
            additional_exact_removed_arcs=domain.get("additional_exact_removed_arcs"),
            additional_SOC_removed_arcs=domain.get("additional_SOC_removed_arcs")))


def affine_support_upper(matrix, lower, upper):
    """Outward enclosure of exact dyadic box support; no tolerance coefficient deletion."""
    matrix=np.asarray(matrix,dtype=float)
    lower,upper=np.asarray(lower,dtype=float),np.asarray(upper,dtype=float)
    if matrix.ndim!=2 or matrix.shape[1]!=len(lower) or lower.shape!=upper.shape or (
            not np.isfinite(matrix).all() or not np.isfinite(lower).all() or
            not np.isfinite(upper).all() or np.any(lower>upper)):
        raise ValueError("MESS_FINITE_OUTER_BOX_SUPPORT_AXIS_REQUIRED")
    out=np.zeros(matrix.shape[0])
    for j in range(matrix.shape[1]):
        endpoint=np.where(matrix[:,j]>=0,upper[j],lower[j])
        term=np.nextafter(matrix[:,j]*endpoint,np.inf)
        out=np.nextafter(out+term,np.inf)
    return out


def _sparse_box_support(row, lower, upper, sense):
    """Upper bound on the exact stored dyadic row over the unchanged box."""
    values=row.data if sense=="<" else -row.data
    endpoint=np.where(values>=0,upper[row.indices],lower[row.indices])
    if not np.isfinite(endpoint[values!=0]).all():
        return np.inf
    total=0.
    for coefficient,end in zip(values,endpoint):
        if coefficient==0:
            continue
        term=np.nextafter(float(coefficient)*float(end),np.inf)
        total=np.nextafter(total+term,np.inf)
    return float(total)


def _csr_box_support_vectorized_exact(A,lower,upper,sense):
    """Same row order and two outward rounds per term as the scalar reference.

    Only independent rows are vectorized: the j-th stored nonzero is processed
    in each row before its j+1-th. No reduce/sum/FMA or coefficient tolerance.
    """
    counts=np.diff(A.indptr);eligible=(sense=="<")|(sense==">")
    support=np.full(A.shape[0],np.inf);support[eligible]=0.
    unbounded=np.zeros(A.shape[0],dtype=bool)
    for j in range(int(counts.max(initial=0))):
        rows=np.flatnonzero(eligible & (counts>j) & ~unbounded)
        positions=A.indptr[rows]+j
        values=np.where(sense[rows]=="<",A.data[positions],-A.data[positions])
        columns=A.indices[positions]
        endpoint=np.where(values>=0,upper[columns],lower[columns])
        nonzero=values!=0.
        bad=nonzero & ~np.isfinite(endpoint)
        unbounded[rows[bad]]=True;support[rows[bad]]=np.inf
        active=nonzero & ~bad
        ids=rows[active]
        with np.errstate(over="ignore",invalid="ignore"):
            term=np.nextafter(values[active]*endpoint[active],np.inf)
            support[ids]=np.nextafter(support[ids]+term,np.inf)
    return support


def compress_native_grid_rows(matrix,rhs,sense,lower,upper,*,support_backend="VECTORIZED_EXACT"):
    """Exact native-CSR removals; every discarded row has a checkable witness.

    No coefficient is thresholded, scaled, or regenerated. Equality rows remain.
    A same-LHS row is implied by the retained tightest native inequality. A box
    removal has an outward dyadic support bound under the ORIGINAL bounds.
    """
    from scipy import sparse
    from .m_engine import matrix_sha,domain_sha
    if not sparse.isspmatrix_csr(matrix) or not matrix.has_canonical_format or matrix.dtype!=np.dtype("float64"):
        raise ValueError("MESS_COMPRESSION_CANONICAL_NATIVE_CSR_REQUIRED_NO_FLOAT_DUPLICATE_FOLDING")
    A=matrix.copy()
    rhs=np.asarray(rhs,float);sense=np.asarray(sense)
    lower=np.asarray(lower,float);upper=np.asarray(upper,float)
    if A.shape!=(len(rhs),len(lower)) or len(sense)!=len(rhs) or lower.shape!=upper.shape or (
            not np.isfinite(A.data).all() or not np.isfinite(rhs).all() or
            np.isnan(lower).any() or np.isnan(upper).any() or np.any(lower>upper)):
        raise ValueError("MESS_COMPRESSION_NATIVE_MATRIX_OR_DOMAIN_DRIFT")
    if support_backend not in ("VECTORIZED_EXACT","SCALAR_REFERENCE"):
        raise ValueError("MESS_COMPRESSION_SUPPORT_BACKEND_REQUIRED")
    if not np.isin(sense,("<",">","=")).all():
        raise ValueError("MESS_COMPRESSION_UNKNOWN_NATIVE_SENSE")
    # Codes: keep, exact duplicate, weaker same-LHS, outward-box, constant-box.
    reason=np.zeros(A.shape[0],dtype=np.uint8)
    representative=np.arange(A.shape[0],dtype=np.int64)
    support=_csr_box_support_vectorized_exact(A,lower,upper,sense) if support_backend=="VECTORIZED_EXACT" else np.full(A.shape[0],np.inf)
    groups=defaultdict(list)
    for i in range(A.shape[0]):
        if sense[i] not in ("<",">"):
            if sense[i]!="=":raise ValueError("MESS_COMPRESSION_UNKNOWN_NATIVE_SENSE")
            continue
        a,b=A.indptr[i:i+2];values=A.data[a:b];indices=A.indices[a:b]
        if support_backend=="SCALAR_REFERENCE":support[i]=_sparse_box_support(A.getrow(i),lower,upper,sense[i])
        bound=rhs[i] if sense[i]=="<" else -rhs[i]
        if support[i]<=bound:
            reason[i]=4 if not np.any(values!=0) else 3
        nonzero=values!=0
        key=(str(sense[i]),indices[nonzero].astype("<i8").tobytes(),
            values[nonzero].astype("<f8",copy=False).tobytes())
        groups[key].append(i)
    for ids in groups.values():
        rep=min(ids,key=lambda i:(rhs[i] if sense[i]=="<" else -rhs[i],i))
        for i in ids:
            if i==rep or reason[i]:continue
            representative[i]=rep
            reason[i]=1 if rhs[i]==rhs[rep] else 2
    keep=np.flatnonzero(reason==0)
    certificate=dict(schema="MESS_EXACT_NATIVE_CSR_GRID_COMPRESSION_V1",PASS=True,
        original_matrix_sha=matrix_sha(A),original_rhs_sense_sha=domain_sha(dict(rhs=rhs,sense=sense)),
        original_bounds_sha=domain_sha(dict(lower=lower,upper=upper)),
        original_rows=A.shape[0],retained_rows=len(keep),original_nonzeros=A.nnz,
        retained_nonzeros=A[keep].nnz,coefficient_epsilon_deletions=0,
        equality_rows_removed=0,variables_or_bounds_changed=False,
        proof_counts={name:int(np.count_nonzero(reason==code)) for code,name in enumerate(
            ("RETAINED","EXACT_DUPLICATE","SAME_LHS_WEAKER_RHS","OUTWARD_BOX","CONSTANT_BOX"))},
        inclusion="original_subset_compressed_by_row_subset;compressed_subset_original_by_each_removal_witness",
        native_matrix_scope="SUPPLIED_STORED_CSR;REAL_NATIVE_LINEAGE_REQUIRES_CAPTURE_RECEIPT")
    return dict(keep=keep,reason=reason,representative=representative,support=support,certificate=certificate)


def verify_native_grid_compression(matrix,rhs,sense,lower,upper,proof):
    """Independent repeat of every removal proof, including representative chains."""
    from scipy import sparse
    if not sparse.isspmatrix_csr(matrix) or not matrix.has_canonical_format or matrix.dtype!=np.dtype("float64"):
        raise ValueError("MESS_COMPRESSION_CANONICAL_NATIVE_CSR_REQUIRED_NO_FLOAT_DUPLICATE_FOLDING")
    A=matrix.copy()
    expected=compress_native_grid_rows(A,rhs,sense,lower,upper)
    if expected["certificate"]!=proof["certificate"]:
        raise ValueError("MESS_COMPRESSION_NATIVE_CERTIFICATE_DRIFT")
    for key in ("keep","reason","representative","support"):
        if not np.array_equal(expected[key],proof[key]):
            raise ValueError("MESS_COMPRESSION_REMOVAL_WITNESS_DRIFT:"+key)
    return dict(PASS=True,all_removed_rows_proven=True,coefficient_epsilon_deletions=0,
        original_integer_feasible_region_preserved=True,original_LP_feasible_region_preserved=True,
        original_objective_and_domains_preserved=True,Native_optimize_calls=0)


def offline_vectorized_proof_benchmark(certificate_path,output,*,slots=96,reference_timing=False):
    """Saved real CSR only; no model/factory/solver/AC or ledger mutation.

    Full96 execution needs Supervisor resource admission. Scalar timing is an
    explicit opt-in; saved scalar proof arrays always provide the exact oracle.
    """
    from scipy import sparse
    from .m_engine import domain_sha
    certificate_path=Path(certificate_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=json.loads(certificate_path.read_text(encoding="utf8"))
    if source.get("FULL96_original_rows_captured") is not True or source.get("slots_captured")!=96 or (
            not 1<=slots<=96 or [row["slot"] for row in source["slots"]]!=list(range(96))):
        raise ValueError("MESS_OFFLINE_PROOF_REAL_FULL96_NATIVE_CAPTURE_REQUIRED")
    with np.load(checked(source["original_native_bounds_types_names_rows"]),allow_pickle=False) as packet:
        domain={key:packet[key].copy() for key in packet.files}
    native_axis_sha=domain_sha({key:domain[key] for key in ("lower","upper","types","names")})
    if native_axis_sha!=source["original_variable_bounds_types_names_sha"]:
        raise ValueError("MESS_OFFLINE_PROOF_ORIGINAL_NATIVE_DOMAIN_AXIS_DRIFT")
    began=perf_counter();per_slot=[];vector_total=scalar_total=0.
    for row in source["slots"][:slots]:
        loaded=perf_counter()
        A=sparse.load_npz(checked(row["original_CSR"])).tocsr()
        with np.load(checked(row["original_row_and_proof_arrays"]),allow_pickle=False) as packet:
            saved={key:packet[key].copy() for key in packet.files}
        read_seconds=perf_counter()-loaded
        scalar_seconds=None
        if reference_timing:
            started=perf_counter()
            scalar=compress_native_grid_rows(A,saved["rhs"],saved["sense"],domain["lower"],domain["upper"],support_backend="SCALAR_REFERENCE")
            scalar_seconds=perf_counter()-started;scalar_total+=scalar_seconds
            for key in ("keep","reason","representative","support"):
                if scalar[key].dtype!=saved[key].dtype or scalar[key].tobytes()!=saved[key].tobytes():
                    raise ValueError("MESS_OFFLINE_SCALAR_CAPTURE_ORACLE_DRIFT:"+key)
            if scalar["certificate"]!=row["certificate"]:raise ValueError("MESS_OFFLINE_SCALAR_CERTIFICATE_DRIFT")
        started=perf_counter()
        vector=compress_native_grid_rows(A,saved["rhs"],saved["sense"],domain["lower"],domain["upper"])
        vector_seconds=perf_counter()-started;vector_total+=vector_seconds
        for key in ("keep","reason","representative","support"):
            if vector[key].dtype!=saved[key].dtype or vector[key].tobytes()!=saved[key].tobytes():
                raise ValueError("MESS_OFFLINE_VECTOR_CAPTURE_BIT_ORACLE_DRIFT:"+key)
        if vector["certificate"]!=row["certificate"]:raise ValueError("MESS_OFFLINE_VECTOR_CERTIFICATE_DRIFT")
        per_slot.append(dict(slot=row["slot"],original_native_CSR=row["original_CSR"],
            saved_scalar_proof_arrays=row["original_row_and_proof_arrays"],native_matrix_sha=row["actual_native_matrix_sha"],
            scalar_reference_seconds=scalar_seconds,vector_proof_seconds=vector_seconds,artifact_read_hash_seconds=read_seconds,
            exact_support_bits_same=True,keep_reason_representative_bits_same=True,certificate_all_hashes_same=True,
            max_row_NNZ=int(np.diff(A.indptr).max(initial=0)),original_rows=A.shape[0],original_NNZ=A.nnz,
            retained_rows=len(vector["keep"]),retained_NNZ=A[vector["keep"]].nnz))
    result=dict(schema="MESS_OFFLINE_EXACT_VECTORIZED_PROOF_BENCHMARK_V1",PASS=True,
        scope="SAVED_REAL_NATIVE_CSR_FULL96" if slots==96 else "SAVED_REAL_NATIVE_CSR_PREFIX_ONLY",
        captured_case_identity=source["identity"],source_compression_certificate=file_record(certificate_path),
        original_native_domain=source["original_native_bounds_types_names_rows"],original_native_domain_axis_sha=native_axis_sha,
        slots_verified=slots,original_rows=sum(row["original_rows"] for row in per_slot),
        original_NNZ=sum(row["original_NNZ"] for row in per_slot),
        retained_rows=sum(row["retained_rows"] for row in per_slot),retained_NNZ=sum(row["retained_NNZ"] for row in per_slot),
        all_saved_scalar_support_keep_reason_representative_bytes_same=True,
        all_native_matrix_rhs_sense_bound_certificate_hashes_same=True,
        vector_proof_compute_seconds=vector_total,scalar_reference_compute_seconds=scalar_total if reference_timing else None,
        proof_kernel_compute_speedup=scalar_total/vector_total if reference_timing and vector_total else None,
        total_wall_seconds=perf_counter()-began,per_slot=per_slot,Native_optimize_calls=0,native_models_created=0,
        AC_calls=0,ledger_created_or_mutated=False,Native_solver_speedup="NOT_MEASURED",
        source_generation_speedup="NOT_MEASURED",original_UB_LB_transferred=False,
        prefix_result_never_promoted_to_full96=slots!=96,
        timing_scope="ONE_PROOF_PASS_SAME_CSR;IO_EXCLUDED_FROM_KERNEL;SCALAR_THEN_VECTOR_IN_SAME_PROCESS",
        previous_322s_three_pass_pipeline_is_not_like_for_like_speedup_baseline=True)
    _write(output/"OFFLINE_EXACT_VECTORIZED_PROOF_RESULT.json",result)
    return result



class NativeGridCompression:
    """Bounded per-slot capture of unchanged add_grid; full native CSR replay.

    The original constructor is called directly through a forwarding model.
    Each slot is first assembled by Gurobi, read back AFTER constant folding,
    and then proved redundant rows are removed. At most one uncompressed slot
    coexists with retained rows. This first exact implementation saves row
    retention memory; generation/readback time must be measured separately.
    """
    def __init__(self,model,coefficients,authority,output,identity,*,probe_slots=None):
        if authority.require_all_transformer_currents is not True:
            raise ValueError("MESS_COMPRESSION_ALL_TRANSFORMER_CURRENT_ROWS_REQUIRED")
        if probe_slots is not None and not 1<=probe_slots<=len(coefficients):
            raise ValueError("MESS_COMPRESSION_PROBE_SLOT_AXIS")
        self.model=model;self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.identity=deepcopy(identity);self.probe_slots=probe_slots
        self.expected=[2*len(c.voltage_constant)+sum(1 if n.lower().startswith("transformer.") else 16
            for n in c.branch_names)+16*sum(r is not None for r in c.transformer_ratings) for c in coefficients]
        self.pending=[];self.slots=[];self.slot=0;self.base=None;self.domain=None
        self.build_started=perf_counter();self.rho=None

    def addVar(self,**kwargs):
        if self.rho is not None or kwargs!=dict(lb=0,ub=1,name="rho_max"):
            raise ValueError("MESS_COMPRESSION_ORIGINAL_RHO_DOMAIN_DRIFT")
        self.rho=self.model.addVar(**kwargs)
        self.model.update()
        from v42_integrated.matrix import arrays
        from scipy import sparse
        self.base,self.domain=arrays(self.model)
        sparse.save_npz(self.output/"ORIGINAL_PHYSICAL_CSR.npz",self.base,compressed=False)
        np.savez(self.output/"ORIGINAL_NATIVE_DOMAIN_BEFORE_OBJECTIVE.npz",**self.domain)
        return self.rho

    def addConstr(self,*args,**kwargs):
        if self.probe_slots is not None and self.slot>=self.probe_slots:
            # Explicit partial Native0 capture only. It can never be optimized.
            return None
        constraint=self.model.addConstr(*args,**kwargs);self.pending.append(constraint)
        if len(self.pending)==self.expected[self.slot]:self._flush()
        elif len(self.pending)>self.expected[self.slot]:
            raise ValueError("MESS_COMPRESSION_SOURCE_ROW_COUNT_DRIFT")
        return constraint

    def _flush(self):
        from scipy import sparse
        from .m_engine import matrix_sha,domain_sha
        self.model.update()
        first=self.pending[0].index;last=self.pending[-1].index+1
        if last-first!=len(self.pending):raise ValueError("MESS_COMPRESSION_NATIVE_ROW_ORDER_DRIFT")
        # getA uses the actual native canonical coefficient/RHS storage.
        current=self.model.getA().tocsr();A=current[first:last].copy();del current
        rhs=np.asarray(self.model.getAttr("RHS",self.pending),float)
        sense=np.asarray(self.model.getAttr("Sense",self.pending))
        names=np.asarray(self.model.getAttr("ConstrName",self.pending))
        lower=np.asarray(self.model.getAttr("LB"),float);upper=np.asarray(self.model.getAttr("UB"),float)
        if not np.array_equal(lower,self.domain["lower"]) or not np.array_equal(upper,self.domain["upper"]):
            raise ValueError("MESS_COMPRESSION_ORIGINAL_NATIVE_BOUNDS_CHANGED")
        proof=compress_native_grid_rows(A,rhs,sense,lower,upper)
        verify=verify_native_grid_compression(A,rhs,sense,lower,upper,proof)
        slot=self.output/f"SLOT_{self.slot:03d}"
        sparse.save_npz(str(slot)+".ORIGINAL_CSR.npz",A,compressed=False)
        np.savez(str(slot)+".ROWS.npz",rhs=rhs,sense=sense,row_names=names,
            keep=proof["keep"],reason=proof["reason"],representative=proof["representative"],support=proof["support"])
        removed=np.flatnonzero(proof["reason"]!=0)
        self.model.remove([self.pending[int(i)] for i in removed]);self.model.update()
        row=dict(slot=self.slot,original_row_offset=self.base.shape[0]+sum(r["original_rows"] for r in self.slots),
            original_rows=len(rhs),retained_rows=len(proof["keep"]),native_nonzeros=A.nnz,
            retained_nonzeros=A[proof["keep"]].nnz,original_CSR=file_record(str(slot)+".ORIGINAL_CSR.npz"),
            original_row_and_proof_arrays=file_record(str(slot)+".ROWS.npz"),
            actual_native_matrix_sha=matrix_sha(A),native_rhs_sense_sha=domain_sha(dict(rhs=rhs,sense=sense)),
            certificate=proof["certificate"],independent_proof_recheck=verify,
            captured_before_removal=True,source_constructor="UNCHANGED_v42_native.grid.add_grid")
        _write(str(slot)+".CERTIFICATE.json",row)
        self.slots.append(row);self.slot+=1;self.pending=[]

    def receipt(self):
        from .m_engine import domain_sha
        complete=len(self.expected)==96 and self.slot==96 and not self.pending
        totals=defaultdict(int)
        for row in self.slots:
            for name,value in row["certificate"]["proof_counts"].items():totals[name]+=value
        return dict(schema="MESS_INCREMENTAL_NATIVE_GRID_COMPRESSION_CAPTURE_V1",identity=self.identity,
            source_constructor=file_record(Path(__file__).resolve().parents[1]/"v42_native/grid.py"),
            FULL96_original_rows_captured=complete,partial_probe_only=not complete,
            slots_captured=self.slot,original_grid_rows=sum(r["original_rows"] for r in self.slots),
            retained_grid_rows=sum(r["retained_rows"] for r in self.slots),
            original_grid_nonzeros=sum(r["native_nonzeros"] for r in self.slots),
            retained_grid_nonzeros=sum(r["retained_nonzeros"] for r in self.slots),
            physical_rows_unchanged=self.base.shape[0],original_variable_bounds_types_names_sha=domain_sha(
                {k:self.domain[k] for k in ("lower","upper","types","names")}),
            original_physical_CSR=file_record(self.output/"ORIGINAL_PHYSICAL_CSR.npz")
                if (self.output/"ORIGINAL_PHYSICAL_CSR.npz").exists() else None,
            original_native_bounds_types_names_rows=file_record(self.output/"ORIGINAL_NATIVE_DOMAIN_BEFORE_OBJECTIVE.npz")
                if (self.output/"ORIGINAL_NATIVE_DOMAIN_BEFORE_OBJECTIVE.npz").exists() else None,
            original_integer_and_LP_feasible_region_preserved=complete,
            candidate_FULL_requires_original_CSR_and_full4_physics=True,
            Native_optimize_calls=0,wall_seconds=perf_counter()-self.build_started,
            generation_strategy="ORIGINAL_NATIVE_ONE_SLOT_THEN_EXACT_REMOVAL;NO_SOURCE_PROJECTION_SUBSTITUTION",
            performance_improvement="NOT_MEASURED",proof_counts=dict(totals),slots=self.slots)

    def original_problem(self,model):
        """Lift identity preserves full original native rows/objective/domains."""
        from scipy import sparse
        from .m_engine import matrix_sha,domain_sha
        from v42_integrated.matrix import arrays
        if len(self.expected)!=96 or self.slot!=96 or self.pending:
            raise ValueError("MESS_COMPRESSION_PARTIAL_CAPTURE_CANNOT_SOLVE_OR_CERTIFY_FULL")
        selected,d=arrays(model)
        for key in ("names","lower","upper","types"):
            if not np.array_equal(d[key],self.domain[key]):
                raise ValueError("MESS_COMPRESSION_NATIVE_COLUMN_AXIS_CHANGED:"+key)
        matrices=[self.base];retained=[self.base]
        rhs=[self.domain["rhs"]];sense=[self.domain["sense"]];names=[self.domain["row_names"]]
        retained_rhs=[self.domain["rhs"]];retained_sense=[self.domain["sense"]];retained_names=[self.domain["row_names"]]
        for row in self.slots:
            A=sparse.load_npz(checked(row["original_CSR"])).tocsr()
            with np.load(checked(row["original_row_and_proof_arrays"]),allow_pickle=False) as packet:
                block={k:packet[k].copy() for k in packet.files}
            proof=dict(keep=block["keep"],reason=block["reason"],representative=block["representative"],
                support=block["support"],certificate=row["certificate"])
            verify_native_grid_compression(A,block["rhs"],block["sense"],d["lower"],d["upper"],proof)
            matrices.append(A);retained.append(A[block["keep"]])
            rhs.append(block["rhs"]);sense.append(block["sense"]);names.append(block["row_names"])
            retained_rhs.append(block["rhs"][block["keep"]]);retained_sense.append(block["sense"][block["keep"]])
            retained_names.append(block["row_names"][block["keep"]])
        original=sparse.vstack(matrices,format="csr")
        expected_selected=sparse.vstack(retained,format="csr")
        if matrix_sha(selected)!=matrix_sha(expected_selected):
            raise ValueError("MESS_COMPRESSION_RETAINED_NATIVE_CSR_BIT_IDENTITY_DRIFT")
        for key,blocks in (("rhs",retained_rhs),("sense",retained_sense),("row_names",retained_names)):
            if not np.array_equal(d[key],np.concatenate(blocks)):
                raise ValueError("MESS_COMPRESSION_RETAINED_NATIVE_ROW_ATTRIBUTES_DRIFT:"+key)
        original_d=dict(d,rhs=np.concatenate(rhs),sense=np.concatenate(sense),row_names=np.concatenate(names))
        receipt=self.receipt();receipt.update(PASS=True,
            actual_selected_matrix_sha=matrix_sha(selected),captured_original_matrix_sha=matrix_sha(original),
            selected_domain_sha=domain_sha(d),original_domain_sha=domain_sha(original_d),
            retained_native_CSR_bit_identity_PASS=True,objective_bounds_types_names_exactly_unchanged=True)
        _write(self.output/"FULL96_COMPRESSION_CERTIFICATE.json",receipt)
        return original,original_d,receipt


def add_grid_exact_compressed(model,coefficients,controls,authority,*,output,identity,probe_slots=None):
    """Opt-in exact native row deletion; original source-grid constructor unchanged."""
    from v42_native.grid import add_grid
    if len(coefficients)!=96 or len(controls)!=96 or any(c.slot!=i for i,c in enumerate(coefficients)):
        raise ValueError("MESS_COMPRESSION_ORIGINAL_FULL96_AXIS_REQUIRED")
    if any(key not in identity or not isinstance(identity[key],str) or len(identity[key])!=64
            for key in BINDING_FIELDS) or any(c.coefficient_sha256!=identity["response_sha"] for c in coefficients):
        raise ValueError("MESS_COMPRESSION_SOURCE_RESPONSE_AND_COMMON_BINDINGS_REQUIRED")
    capture=NativeGridCompression(model,coefficients,authority,output,identity,probe_slots=probe_slots)
    limit=len(coefficients) if probe_slots is None else probe_slots
    rho=add_grid(capture,coefficients[:limit],controls[:limit],authority)
    if capture.pending:raise ValueError("MESS_COMPRESSION_INCOMPLETE_NATIVE_SLOT")
    _write(capture.output/"GRID_CAPTURE_RECEIPT.json",capture.receipt())
    return rho,capture


def compress_existing_native_grid_model(model,coefficients,authority,*,output,identity,grid_first,phase_observer=None):
    """Supervisor-only exact deletion in an already built original SAME model.

    No Optimize/reset, ledger creation, or LB/UB transfer occurs here. Supervisor
    can record the original solve, call this helper, reset and solve with a new
    canonical ledger label; both candidate validators use the returned original
    A/d. This saves a second original full-model build in a measured comparison.
    """
    from scipy import sparse
    from v42_integrated.matrix import arrays
    from .m_engine import matrix_sha,domain_sha
    if len(coefficients)!=96 or any(c.slot!=i for i,c in enumerate(coefficients)) or any(
            key not in identity or not isinstance(identity[key],str) or len(identity[key])!=64
            for key in BINDING_FIELDS) or any(c.coefficient_sha256!=identity["response_sha"] for c in coefficients):
        raise ValueError("MESS_COMPRESSION_SOURCE_RESPONSE_FULL96_AND_BINDINGS_REQUIRED")
    if authority.require_all_transformer_currents is not True:
        raise ValueError("MESS_COMPRESSION_ALL_TRANSFORMER_CURRENT_ROWS_REQUIRED")
    phase=phase_observer or (lambda name:None)
    phase("COMPRESSION_CAPTURE")
    model.update();A,d=arrays(model)
    capture=NativeGridCompression(model,coefficients,authority,output,identity)
    if not isinstance(grid_first,int) or grid_first<0 or grid_first+sum(capture.expected)!=A.shape[0]:
        raise ValueError("MESS_COMPRESSION_ORIGINAL_GRID_MUST_BE_EXACT_FINAL_NATIVE_ROW_BLOCK")
    capture.base=A[:grid_first].copy()
    capture.domain=dict(d,rhs=d["rhs"][:grid_first].copy(),sense=d["sense"][:grid_first].copy(),
        row_names=d["row_names"][:grid_first].copy())
    sparse.save_npz(capture.output/"ORIGINAL_PHYSICAL_CSR.npz",capture.base,compressed=False)
    np.savez(capture.output/"ORIGINAL_NATIVE_DOMAIN_BEFORE_OBJECTIVE.npz",**capture.domain)
    sparse.save_npz(capture.output/"FULL_ORIGINAL_NATIVE_CSR.npz",A,compressed=False)
    np.savez(capture.output/"FULL_ORIGINAL_NATIVE_DOMAIN.npz",**d)
    original_matrix_sha=matrix_sha(A);original_domain_sha=domain_sha(d)
    constraints=model.getConstrs();offset=grid_first;removal_indices=[]
    for slot,c in enumerate(coefficients):
        phase("COMPRESSION_PROOF")
        end=offset+capture.expected[slot];block=A[offset:end].copy()
        rhs=d["rhs"][offset:end];sense=d["sense"][offset:end];names=d["row_names"][offset:end]
        expected_names=[]
        for _ in c.voltage_constant:expected_names.extend(["voltage_lower","voltage_upper"])
        for branch,rating in zip(c.branch_names,c.transformer_ratings):
            expected_names.extend(["transformer_current"] if branch.lower().startswith("transformer.") else ["line_thermal_face"]*16)
            if rating is not None:expected_names.extend(["transformer_kVA"]*16)
        if not np.array_equal(names,np.asarray(expected_names)):
            raise ValueError("MESS_COMPRESSION_ORIGINAL_SOURCE_GRID_ROW_FAMILY_ORDER_DRIFT")
        proof=compress_native_grid_rows(block,rhs,sense,d["lower"],d["upper"])
        verify=verify_native_grid_compression(block,rhs,sense,d["lower"],d["upper"],proof)
        phase("COMPRESSION_ARTIFACT_WRITE")
        path=capture.output/f"SLOT_{slot:03d}"
        sparse.save_npz(str(path)+".ORIGINAL_CSR.npz",block,compressed=False)
        np.savez(str(path)+".ROWS.npz",rhs=rhs,sense=sense,row_names=names,
            keep=proof["keep"],reason=proof["reason"],representative=proof["representative"],support=proof["support"])
        row=dict(slot=slot,original_row_offset=offset,original_rows=len(rhs),
            retained_rows=len(proof["keep"]),native_nonzeros=block.nnz,retained_nonzeros=block[proof["keep"]].nnz,
            original_CSR=file_record(str(path)+".ORIGINAL_CSR.npz"),
            original_row_and_proof_arrays=file_record(str(path)+".ROWS.npz"),
            actual_native_matrix_sha=matrix_sha(block),native_rhs_sense_sha=domain_sha(dict(rhs=rhs,sense=sense)),
            certificate=proof["certificate"],independent_proof_recheck=verify,
            captured_before_removal=True,source_constructor="SUPERVISOR_EXISTING_UNCHANGED_SOURCE_NATIVE_MODEL")
        _write(str(path)+".CERTIFICATE.json",row)
        capture.slots.append(row);capture.slot+=1
        removal_indices.extend(offset+int(i) for i in np.flatnonzero(proof["reason"]!=0))
        offset=end
    # All source-order and row proofs pass before the first native mutation.
    phase("COMPRESSION_NATIVE_REMOVE")
    model.remove([constraints[i] for i in removal_indices])
    model.update()
    phase("COMPRESSION_CSR_RECONSTRUCT_VERIFY")
    original,original_d,receipt=capture.original_problem(model)
    if matrix_sha(original)!=original_matrix_sha or domain_sha(original_d)!=original_domain_sha:
        raise ValueError("MESS_COMPRESSION_EXISTING_ORIGINAL_NATIVE_CASE_IDENTITY_DRIFT")
    receipt.update(generation_strategy="ONE_EXISTING_ORIGINAL_MODEL;PROVEN_ROWS_REMOVED_AFTER_ORIGINAL_CAPTURE",
        original_native_model_rebuilt=False,Native_optimize_calls=0,
        original_full_native_CSR=file_record(capture.output/"FULL_ORIGINAL_NATIVE_CSR.npz"),
        original_full_native_domain=file_record(capture.output/"FULL_ORIGINAL_NATIVE_DOMAIN.npz"),
        fresh_second_optimize_required=True,prior_native_UB_LB_transferred=False)
    _write(capture.output/"FULL96_COMPRESSION_CERTIFICATE.json",receipt)
    selected,selected_d=arrays(model)
    return SimpleNamespace(A=selected,d=selected_d,original_A=original,original_d=original_d,
        lift=lambda point:np.asarray(point).copy(),compression_certificate=receipt)


def projected_grid_rows(coefficient, fixed_control, variable_controls, *, lower_squared=.9025,
                        upper_squared=1.1025):
    """One slot of source-formula affine grid rows in aggregate signed P/Q/rho.

    This compact, matrix-free audit is not a native CSR identity certificate:
    native expression folding can differ in last bits. Any adoption must compare
    these rows with the captured actual native matrix before removing rows.
    """
    c=coefficient;indices=np.asarray(variable_controls,dtype=int);fixed=np.asarray(fixed_control,dtype=float)
    angles=2*np.pi*np.arange(16)/16;cos,sin=np.cos(angles),np.sin(angles)
    v0=c.voltage_constant+c.voltage_matrix.T@fixed
    v=c.voltage_matrix[indices].T
    p0=c.flow_p_constant+c.flow_p_matrix@fixed
    q0=c.flow_q_constant+c.flow_q_matrix@fixed
    pp=c.flow_p_matrix[:,indices];qq=c.flow_q_matrix[:,indices]
    ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
    pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
    raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
    grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
    correction=c.current_matrix.T-grad
    bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
    rows=[np.c_[v,np.zeros(len(v))],np.c_[-v,np.zeros(len(v))]]
    rhs=[upper_squared-v0,v0-lower_squared]
    families=["voltage_upper"]*len(v)+["voltage_lower"]*len(v)
    for k,name in enumerate(c.branch_names):
        if name.lower().startswith("transformer."):
            rows.append(np.r_[c.current_matrix[indices,k],0.][None,:])
            rhs.append(np.array([1.-c.current_constant[k]-c.current_matrix[:,k]@fixed]))
            families.append("transformer_current")
        else:
            a=(cos[:,None]*pp[k]+sin[:,None]*qq[k])/ap[k]+correction[k,indices]
            b=-((cos*p0[k]+sin*q0[k])/ap[k]+correction[k]@(fixed-c.anchor)+bias[k])
            rows.append(np.c_[a,-np.ones(16)]);rhs.append(b)
            families.extend(["line_thermal_face"]*16)
        rating=c.transformer_ratings[k]
        if rating is not None:
            a=cos[:,None]*pp[k]+sin[:,None]*qq[k]
            b=float(rating)*math.cos(math.pi/16)-cos*p0[k]-sin*q0[k]
            rows.append(np.c_[a,np.zeros(16)]);rhs.append(b)
            families.extend(["transformer_kVA"]*16)
    return np.vstack(rows),np.concatenate(rhs),families


def audit_grid_bottleneck(result_path, *, directory=REPORT):
    """Real S1 metadata and streaming source-affine row audit, no native/model build."""
    result_path=Path(result_path);directory=Path(directory)
    result=json.loads(result_path.read_text(encoding="utf8"))
    selection=json.loads((result_path.parent.parent/"S1_SELECTION_AND_SOURCE.json").read_text(encoding="utf8"))
    require_bindings(result["shared_bindings"],selection["bindings"])
    gate=json.loads((result_path.parent/"PILOT_SOURCE_CONTENT_GATE.json").read_text(encoding="utf8"))
    source=gate["response"]["source"];checked(source)
    matrix=json.loads((directory/"MESS_SCALING_CASE_MATRIX.json").read_text(encoding="utf8"))
    spec=next(s for s in matrix["stages"] if s["stage"]=="S1")
    if spec["reduced_case_sha"]!=result["reduced_case_sha"]:
        raise ValueError("MESS_GRID_AUDIT_SAME_REDUCED_CASE_REQUIRED")
    target=json.loads(Path(load_contracts()["historical_reference_file"]["path"]).read_text(encoding="utf8"))
    aidc=json.loads(checked(target["source_A1_artifact"]).read_text(encoding="utf8"))
    from .coordinator import _full_a
    _full_a(aidc)
    stay=json.loads(checked(spec["inactive_stay_source"]).read_text(encoding="utf8"))
    from .production_case import FIELDS
    with np.load(source["path"],allow_pickle=False) as z:
        data={name:z[name].copy() for name in FIELDS+("anchor_control",)}
        controls=tuple(map(str,z["control_names"]));branches=tuple(map(str,z["branch_names"]))
        ratings=tuple(None if np.isnan(v) else float(v) for v in z["transformer_ratings"])
    selected=spec["charging_sites"]
    variable=[controls.index(f"mess_p_kw[{s}]") for s in selected]+[
              controls.index(f"mess_q_kvar[{s}]") for s in selected]
    units=len(spec["optimization_units"])
    p=units*spec["original_battery"]["p_limit"]
    q=units*spec["original_battery"]["pcs_kva"]
    lower=np.r_[-np.full(len(selected),p),-np.full(len(selected),q),0.]
    upper=np.r_[np.full(len(selected),p),np.full(len(selected),q),1.]
    totals=defaultdict(int);family=defaultdict(lambda:defaultdict(int));per_slot=[]
    began=perf_counter()
    for t in range(96):
        fixed=np.zeros(len(controls))
        for j,name in enumerate(controls):
            site=name.split("[",1)[1][:-1]
            if name.startswith("aidc_load_kw["):
                fixed[j]=aidc["AIDC_P_by_site"][site][t]
            elif name.startswith("mess_p_kw["):
                fixed[j]=sum(stay["P_kW"][u][t] for u in spec["inactive_units"] if stay["connection_site"][u][t]==site)
            elif name.startswith("mess_q_kvar["):
                fixed[j]=sum(stay["Q_kvar"][u][t] for u in spec["inactive_units"] if stay["connection_site"][u][t]==site)
        c=SimpleNamespace(**{name:data[name][t] for name in FIELDS},slot=t,
            anchor=data["anchor_control"][t],control_names=controls,branch_names=branches,
            transformer_ratings=ratings)
        W,b,names=projected_grid_rows(c,fixed,variable)
        support=affine_support_upper(W,lower,upper)
        satisfied=support<=b
        constant=np.all(W==0.,axis=1)
        groups=defaultdict(list)
        canonical=np.where(W==0.,0.,W)
        for i,row in enumerate(canonical):
            groups[row.tobytes()].append(i)
        redundant=set();duplicates=dominated=0
        for ids in groups.values():
            minimum=min(ids,key=lambda i:(b[i],i))
            for i in ids:
                if i!=minimum:
                    redundant.add(i)
                    if b[i]==b[minimum]:duplicates+=1
                    else:dominated+=1
        removed=set(map(int,np.flatnonzero(satisfied)))|redundant
        row=dict(slot=t,source_formula_rows=len(b),constant_only=int(constant.sum()),
            box_always_satisfied=int(satisfied.sum()),exact_duplicate=duplicates,
            same_LHS_looser_RHS=dominated,union_candidate_removals=len(removed))
        per_slot.append(row)
        for k,v in row.items():
            if k!="slot":totals[k]+=v
        for i,name in enumerate(names):
            family[name]["rows"]+=1
            family[name]["box_always_satisfied"]+=int(satisfied[i])
            family[name]["constant_only"]+=int(constant[i])
            family[name]["candidate_removals"]+=int(i in removed)
    native=result["model_size"]
    grid=sum(native["constraint_families"][f] for f in family)
    if totals["source_formula_rows"]!=grid or any(family[f]["rows"]!=native["constraint_families"][f] for f in family):
        raise ValueError("MESS_REAL_S1_SOURCE_FORMULA_FAMILY_COUNT_DRIFT")
    audit=dict(schema="MESS_S1_GRID_ROW_BOTTLENECK_SOURCE_AUDIT_V1",PASS=True,
        scope="REAL_SOURCE_FORMULA_AND_NATIVE_METADATA_COUNTS;NOT_NATIVE_CSR_BIT_EQUIVALENCE",
        reduced_case_sha=result["reduced_case_sha"],bindings=result["shared_bindings"],
        source_coefficients=source,original_native_result=file_record(result_path),
        Native_optimize_calls=0,native_model_builds=0,new_S1_matrix_materialized=False,
        working_row_block_shape=[8485,11],streaming_slots=96,wall_seconds=perf_counter()-began,
        native_rows=native["linear_constraints"],native_grid_rows=grid,grid_row_percent=100*grid/native["linear_constraints"],
        original_nonzeros=native["nonzeros"],presolved_nonzeros=result["Presolved_NNZ"],
        nonzero_reduction_percent=100*(1-result["Presolved_NNZ"]/native["nonzeros"]),
        build_wall_seconds=result["build_wall_seconds"],presolve_seconds=result["Presolve_seconds"],
        root_seconds=result["Root_LP_seconds"],root_status=result["Root_LP_status"],
        native_Runtime=result["native_Runtime"],best_FULL_UB=result["BEST_GLOBAL_UB"],
        best_MOVING_FULL_UB=result["BEST_MOVING_FEASIBLE_UB"],reduced_Global_LB=result["Global_LB"],gap=result["gap"],
        source_formula_totals=dict(totals),family=dict(family),per_slot=per_slot,
        candidates_applied_to_solver=False,original_native_CSR_equivalence="NOT_CERTIFIED_ORIGINAL_MATRIX_NOT_PERSISTED",
        coefficient_epsilon_deletions=0,positive_proportional_row_detection="NOT_RUN_REQUIRES_EXACT_RATIONAL_VERIFICATION",
        outer_box=dict(P_per_site=[-p,p],Q_per_site=[-q,q],rho=[0.,1.],
            all_site_boxes_simultaneously_allowed=True,outer_superset_of_original_PCS_and_route_domains=True),
        adoption_gate="CAPTURE_ORIGINAL_NATIVE_CSR_AND_DOMAIN;EXACT_ROW_COMPARISON_AND_OUTWARD_SUPPORT_PROOF;FULL_ORIGINAL_VALIDATOR")
    _write(directory/"MESS_GRID_ROW_BOTTLENECK_NATIVE0_AUDIT.json",audit)
    return audit


class _BenchmarkPhaseSampler:
    """Per-phase sampled peaks; process cumulative peaks are labeled separately."""
    def __init__(self):
        import threading
        self.lock=threading.RLock();self.stop=threading.Event();self.rows={}
        self.name="BUILD";self.started=perf_counter();self.thread=None
    def phase(self,name):
        with self.lock:
            now=perf_counter()
            self.rows.setdefault(self.name,dict(wall_seconds=0.,samples=0))["wall_seconds"]+=now-self.started
            self.name=name;self.started=now
    def sample(self):
        from v42_common_mess.model import memory_observation
        observation=memory_observation()
        with self.lock:
            row=self.rows.setdefault(self.name,dict(wall_seconds=0.,samples=0))
            row["samples"]+=1
            for key in ("RSS_bytes","private_bytes"):
                row["sampled_peak_"+key]=max(row.get("sampled_peak_"+key,0),observation[key])
            row["minimum_available_RAM_bytes"]=min(row.get("minimum_available_RAM_bytes",np.inf),observation["RAM_available"])
            row["cumulative_process_peak_RSS_bytes"]=observation["peak_RSS_bytes"]
            row["cumulative_process_peak_private_commit_bytes"]=observation["peak_private_commit_bytes"]
    def __enter__(self):
        import threading
        self.sample()
        def worker():
            while not self.stop.wait(.25):
                try:self.sample()
                except Exception as exc:
                    with self.lock:self.rows.setdefault("SAMPLING_ERROR",{})["error"]=repr(exc)
                    return
        self.thread=threading.Thread(target=worker,name="MESS_COMPRESSION_PHASE_MEMORY",daemon=True)
        self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(timeout=2);self.sample();self.phase("FINISHED")
    def receipt(self):
        with self.lock:return dict(sample_interval_seconds=.25,peak_scope="SAMPLED_PHASE_PEAK;OS_CUMULATIVE_PEAK_SEPARATE",
            wall_scope="CALLBACK_PHASE_ATTRIBUTION;NATIVE_LOG_TIMINGS_AUTHORITATIVE",phases=deepcopy(self.rows))


def _same_model_compression_benchmark(model,case,scale,coefficients,authority,budget,
        point,warm_certificate,output,seconds,sampler,build_seconds):
    """Two measured solves, independent starts/bounds, exact same original case."""
    import gurobipy as gp
    from .m_engine import strict_full,PathGraph,IncumbentBank,matrix_sha,domain_sha
    from v42_native.solver import assert_milp
    from v42_common_mess.model import memory_observation
    from v42_common_mess.telemetry import root_lp
    from v42_integrated.matrix import arrays
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    original_matrix_sha=matrix_sha(case.original_A);original_domain_sha=domain_sha(case.original_d)
    fair_start_sha=vector_sha(point) if warm_certificate is not None else None
    comparison_id=digest(dict(reduced_case_sha=case.case_sha,original_matrix_sha=original_matrix_sha,
        original_domain_sha=original_domain_sha,fair_start_sha=fair_start_sha,seconds_per_variant=seconds))
    rows=[];winner=None;moving_winner=None;current=case
    base_context=deepcopy(budget.stage_context)
    began=perf_counter()
    def admission(phase):
        sampler.phase(phase)
        if memory_observation()["RAM_available"]<8*1024**3:
            raise RuntimeError("MESS_COMPRESSION_BENCHMARK_MINIMUM_8GB_RAM_GATE:"+phase)
        if budget.remaining()<seconds:
            raise RuntimeError("MESS_COMPRESSION_BENCHMARK_EQUAL_CAP_BUDGET_REQUIRED:"+phase)
        if hasattr(budget,"preflight"):budget.preflight()
    try:
        for variant in ("ORIGINAL","COMPRESSED"):
            folder=output/variant;folder.mkdir(parents=True,exist_ok=True)
            if variant=="COMPRESSED":
                admission("COMPRESSION_ADMISSION")
                grid_rows=sum(2*len(c.voltage_constant)+sum(1 if n.lower().startswith("transformer.") else 16
                    for n in c.branch_names)+16*sum(r is not None for r in c.transformer_ratings) for c in coefficients)
                compressed=compress_existing_native_grid_model(model,coefficients,authority,
                    output=output/"EXACT_PROOF",identity=dict(scale.bindings,reduced_case_sha=scale.case_sha),
                    grid_first=case.original_A.shape[0]-grid_rows,phase_observer=sampler.phase)
                if matrix_sha(compressed.original_A)!=original_matrix_sha or domain_sha(compressed.original_d)!=original_domain_sha:
                    raise ValueError("MESS_COMPRESSION_BENCHMARK_ORIGINAL_CASE_HASH_DRIFT")
                current=SimpleNamespace(**dict(vars(case),A=compressed.A,d=compressed.d,
                    original_A=compressed.original_A,original_d=compressed.original_d,output=folder))
                equivalence=file_record(output/"EXACT_PROOF"/"FULL96_COMPRESSION_CERTIFICATE.json")
            else:
                current=SimpleNamespace(**dict(vars(case),output=folder));equivalence=None
            sampler.phase(variant+":RESET_AND_IDENTICAL_START")
            model.reset(1)  # discard previous solution/search state and all prior MIP starts
            expected_start=point.copy() if fair_start_sha else np.full(current.A.shape[1],gp.GRB.UNDEFINED)
            model.setAttr("Start",model.getVars(),expected_start.tolist())
            model.Params.Threads=1;model.Params.Seed=0;model.Params.MIPGap=.03
            model.Params.FeasibilityTol=1e-9;model.Params.OptimalityTol=1e-9;model.Params.IntFeasTol=1e-8
            model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(folder/"NATIVE_GUROBI.log")
            model.update()
            actual_start=np.asarray(model.getAttr("Start"),dtype=np.float64)
            number_of_starts=_attr(model,"NumStart")
            if not np.array_equal(actual_start,expected_start) or number_of_starts is None:
                raise ValueError("MESS_COMPRESSION_BENCHMARK_IDENTICAL_START_READBACK_DRIFT")
            start_receipt=dict(PASS=True,expected_vector_sha=vector_sha(expected_start),
                actual_vector_sha=vector_sha(actual_start),NumStart=number_of_starts,
                policy="CURRENT_SOURCE_STAY" if fair_start_sha else "NO_START_BOTH_VARIANTS_ALL_UNDEFINED")
            actual_A,actual_d=arrays(model)
            if matrix_sha(actual_A)!=matrix_sha(current.A) or domain_sha(actual_d)!=domain_sha(current.d):
                raise ValueError("MESS_COMPRESSION_BENCHMARK_RESET_CHANGED_NUMERIC_PROBLEM")
            sampler.phase(variant+":INITIAL_FULL_REPLAY")
            bank=IncumbentBank(current)
            if fair_start_sha:
                warm_path=folder/"IDENTICAL_SOURCE_STAY_START.npz";np.savez_compressed(warm_path,point=point)
                warm=strict_full(current,warm_path)
                warm["full_four_vehicle_physical_replay"],_=full_vehicle_replay(scale,current,point)
                bank.offer(point,warm)
            captures=[];events=dict(first_solver_incumbent_seconds=None,root_first_observed_seconds=None,
                root_LB=None,root_fractional_route_columns=None,root_fractional_modes=None,
                presolve_removed_rows=None,presolve_removed_columns=None)
            admission(variant+":NATIVE_ADMISSION")
            budget.stage_context=dict(base_context,comparison_id=comparison_id,comparison_variant=variant,
                grid_compression_mode="ORIGINAL_FULL_ROWS" if variant=="ORIGINAL" else "EXACT_NATIVE_CSR_SAME_MODEL",
                original_matrix_sha=original_matrix_sha,original_domain_sha=original_domain_sha,
                selected_matrix_sha=matrix_sha(current.A),selected_domain_sha=domain_sha(current.d),
                declared_equivalence_certificate=equivalence,identical_start_vector_sha=fair_start_sha,
                actual_Start_readback=start_receipt,
                prior_variant_LB_or_incumbent_given_to_solver=False)
            native_begin=perf_counter();sampler.phase(variant+":NATIVE_BEFORE_CALLBACK")
            def callback(m,where):
                if where==gp.GRB.Callback.PRESOLVE:
                    sampler.phase(variant+":PRESOLVE")
                    events["presolve_removed_rows"]=int(m.cbGet(gp.GRB.Callback.PRE_ROWDEL))
                    events["presolve_removed_columns"]=int(m.cbGet(gp.GRB.Callback.PRE_COLDEL))
                elif where in (gp.GRB.Callback.SIMPLEX,gp.GRB.Callback.BARRIER):sampler.phase(variant+":ROOT_LP")
                elif where==gp.GRB.Callback.MIPSOL:
                    if events["first_solver_incumbent_seconds"] is None:events["first_solver_incumbent_seconds"]=perf_counter()-native_begin
                    if len(captures)<8:captures.append(np.asarray(m.cbGetSolution(m.getVars()),dtype=np.float64))
                elif where==gp.GRB.Callback.MIPNODE:
                    nodes=m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
                    sampler.phase(variant+(":ROOT_CUTS" if nodes==0 else ":BRANCHING"))
                    if nodes==0:
                        if events["root_first_observed_seconds"] is None:events["root_first_observed_seconds"]=perf_counter()-native_begin
                        events["root_LB"]=float(m.cbGet(gp.GRB.Callback.MIPNODE_OBJBND))
                        if m.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL:
                            x=np.asarray(m.cbGetNodeRel(m.getVars()))
                            fractional=(x!=np.rint(x))&(current.d["types"]!="C")
                            events["root_fractional_route_columns"]=int(np.count_nonzero(fractional&np.char.startswith(current.d["names"],"arc[")))
                            events["root_fractional_modes"]=int(np.count_nonzero(fractional&np.char.startswith(current.d["names"],"charge_mode[")))
            native=budget.solve(model,label="MESS:"+scale.stage+":COMPRESSION_BENCH:"+variant,cap=seconds,callback=callback)
            native_wall=perf_counter()-native_begin
            if _attr(model,"SolCount"):captures.append(np.asarray(model.getAttr("X"),dtype=np.float64))
            raw_bound=_attr(model,"ObjBound");status=_attr(model,"Status")
            valid_bound=raw_bound if status in (2,7,8,9,10,11,13,15,16,17) else None
            telemetry=root_lp(folder/"NATIVE_GUROBI.log")
            solver_size=assert_milp(model)
            sampler.phase(variant+":ALL_ORIGINAL_ROWS_AND_FULL4_REPLAY")
            validation_begin=perf_counter();accepted=[];rejected=[];seen=set()
            for index,raw in enumerate(captures):
                sha=vector_sha(raw)
                if sha in seen:continue
                seen.add(sha);path=folder/f"RAW_{index:03d}.npz";np.savez_compressed(path,point=raw)
                try:
                    cert=strict_full(current,path)
                    cert["full_four_vehicle_physical_replay"],_=full_vehicle_replay(scale,current,raw)
                    bank.offer(raw,cert);_write(path.with_suffix(".REPLAY.json"),cert)
                    accepted.append(dict(raw=file_record(path),UB=cert["Global_UB"],moving=PathGraph(current).moving(raw)))
                except ValueError as exc:rejected.append(dict(raw=file_record(path),reason=str(exc)))
            fields=bank.fields();ub=fields["BEST_GLOBAL_UB"]
            bound_rejection=None
            if valid_bound is not None and ub is not None and valid_bound>ub:
                valid_bound=None;bound_rejection="SOLVER_BOUND_EXCEEDS_CURRENT_FULL_UB"
            gap=abs(ub-valid_bound)/abs(ub) if ub not in (None,0) and valid_bound is not None else None
            bank.save(folder,dict(shared=scale.bindings,reduced_case_sha=scale.case_sha,comparison_variant=variant))
            row=dict(variant=variant,reduced_case_sha=scale.case_sha,comparison_id=comparison_id,
                original_matrix_sha=original_matrix_sha,original_domain_sha=original_domain_sha,
                selected_matrix_sha=matrix_sha(current.A),model_size=solver_size,native_receipt=native,
                requested_native_cap=seconds,native_Runtime=_attr(model,"Runtime"),native_Work=_attr(model,"Work"),
                native_wall_seconds=native_wall,native_status=status,B_and_B_nodes=_attr(model,"NodeCount"),
                raw_solver_ObjBound=raw_bound,Global_LB=valid_bound,bound_rejection=bound_rejection,gap=gap,
                initial_start_vector_sha=fair_start_sha,first_variant_solver_incumbent_used_as_second_start=False,
                actual_Start_readback=start_receipt,
                events=events,accepted=accepted,rejected=rejected,full_validation_seconds=perf_counter()-validation_begin,
                after_variant_memory=memory_observation(),declared_equivalence_certificate=equivalence,
                original_ALL_rows_and_full4_vehicle_replay=True,bound_scope="REDUCED_CASE_GLOBAL",**fields,**telemetry)
            _write(folder/"VARIANT_RESULT.json",row);rows.append(row)
            if bank.best is not None and (winner is None or bank.best[1]["Global_UB"]<winner[1]["Global_UB"]):
                winner=(bank.best[0].copy(),bank.best[1],variant)
            if bank.best_moving is not None and (moving_winner is None or bank.best_moving[1]["Global_UB"]<moving_winner[1]["Global_UB"]):
                moving_winner=(bank.best_moving[0].copy(),bank.best_moving[1],variant)
        sampler.phase("FINAL_SAME_CASE_BEST_FULL_REPLAY")
        finalbank=IncumbentBank(current);plan=None;replay=None
        if winner is not None:
            path=output/"BEST_BOTH_VARIANTS_RAW.npz";np.savez_compressed(path,point=winner[0])
            cert=strict_full(current,path);replay,plan=full_vehicle_replay(scale,current,winner[0])
            cert["full_four_vehicle_physical_replay"]=replay;finalbank.offer(winner[0],cert)
            _write(path.with_suffix(".REPLAY.json"),cert)
        if moving_winner is not None:
            path=output/"BEST_MOVING_BOTH_VARIANTS_RAW.npz";np.savez_compressed(path,point=moving_winner[0])
            cert=strict_full(current,path)
            cert["full_four_vehicle_physical_replay"],_=full_vehicle_replay(scale,current,moving_winner[0])
            finalbank.offer(moving_winner[0],cert);_write(path.with_suffix(".REPLAY.json"),cert)
        finalbank.save(output,dict(shared=scale.bindings,reduced_case_sha=scale.case_sha))
        finalfields=finalbank.fields();lb=rows[-1]["Global_LB"];ub=finalfields["BEST_GLOBAL_UB"]
        final_bound_rejection=None
        if lb is not None and ub is not None and lb>ub:
            lb=None;final_bound_rejection="SECOND_SOLVER_BOUND_EXCEEDS_BEST_SAME_CASE_FULL_UB"
        summary=dict(schema="MESS_S1_EXACT_COMPRESSION_SAME_MODEL_BENCHMARK_V1",comparison_id=comparison_id,
            status="REDUCED_FULL_FEASIBLE" if winner is not None else "NO_CURRENT_FULL_FEASIBLE_INCUMBENT",
            SAME_original_numeric_case=True,original_matrix_sha=original_matrix_sha,original_domain_sha=original_domain_sha,
            source_model_build_count=1,build_wall_seconds=build_seconds,model_size=rows[-1]["model_size"],
            variants=rows,Native_optimize_calls=2,native_receipt=rows[-1]["native_receipt"],
            native_Runtime=sum(r["native_Runtime"] or 0. for r in rows),native_Runtime_scope="SUM_OF_TWO_CANONICAL_CALLS",
            solve_wall_seconds=perf_counter()-began,Global_LB=lb,gap=abs(ub-lb)/abs(ub) if ub not in (None,0) and lb is not None else None,
            bound_rejection=final_bound_rejection,numeric_scope=base_context.get("numeric_scope","UNSPECIFIED_CALLER_CONTEXT"),
            integrated_current_A1_M1_certified=False,integrated_four_stage_certified=False,
            FULL_validated=winner is not None,mess=plan,full_four_vehicle_physical_replay=replay,
            BEST_FULL_point_variant=None if winner is None else winner[2],identical_start_vector_sha=fair_start_sha,
            BEST_MOVING_point_variant=None if moving_winner is None else moving_winner[2],
            historical_UB_LB_transferred=False,first_solver_incumbent_given_to_second_solver=False,
            second_solver_bound_is_fresh=True,Original_global_gap_certified=False,Full96_Actual="NOT_RUN",Fresh_AC="NOT_RUN",
            benchmark_phase_memory=sampler.receipt(),after_native_memory=memory_observation(),**finalfields)
        _write(output/"COMPRESSION_BENCHMARK_RESULT.json",summary)
        return summary
    except BaseException as exc:
        _write(output/"COMPARISON_INTERRUPTED.json",dict(error=repr(exc),completed_variants=rows,
            no_automatic_retry=True,comparison_id=comparison_id,phase_memory=sampler.receipt()))
        raise
    finally:budget.stage_context=base_context


def run_original_pilot(scale, *, coefficients, grid_authority, aidc_anchor, all_sites,
                       coefficient_source, physical_bundle, electrical_certificate, thermal_receipt,
                       budget, output, seconds=30., mode="EXACT_REDUCED", native0=False,
                       grid_compression="NONE",compression_probe_slots=None,compare_exact_compression=False):
    """Supervisor only: original MESS physical model plus full source grid rows.

    budget is injected. This function never instantiates, replaces or resets a
    native ledger. All-four source STAY is independently revalidated before the
    current reduced matrix validator admits a warm start or solver candidate.
    """
    if mode not in ("EXACT_REDUCED", "BEAM_JOINT") or not 0 < seconds <= 120:
        raise ValueError("MESS_BOUNDED_SINGLE_PILOT_REQUIRED")
    if budget is None or not hasattr(budget, "solve") or not hasattr(budget, "remaining"):
        raise ValueError("MESS_SUPERVISOR_SHARED_LEDGER_REQUIRED")
    if grid_compression not in ("NONE","EXACT_NATIVE_BLOCK") or (
            grid_compression!="NONE" and mode!="EXACT_REDUCED"):
        raise ValueError("MESS_COMPRESSION_OPT_IN_EXACT_REDUCED_ONLY")
    if compression_probe_slots is not None and (not native0 or grid_compression!="EXACT_NATIVE_BLOCK"):
        raise ValueError("MESS_COMPRESSION_PARTIAL_PROBE_NATIVE0_ONLY")
    if compare_exact_compression and (scale.stage!="S1" or mode!="EXACT_REDUCED" or native0 or
            grid_compression!="NONE" or compression_probe_slots is not None or seconds>30):
        raise ValueError("MESS_COMPRESSION_BENCHMARK_S1_ORIGINAL_EXACT_TWO_EQUAL_BOUNDED_NATIVE_CAPS")
    if compare_exact_compression and budget.remaining()<2*seconds:
        raise RuntimeError("MESS_COMPRESSION_BENCHMARK_TWO_EQUAL_CAPS_BUDGET_REQUIRED")
    from v42_native.mess import solve
    from v42_native.grid import add_grid
    from v42_native.voltage import Stage, voltage_for
    from v42_native.solver import assert_milp
    from v42_integrated.matrix import arrays
    from .m_engine import strict_full, PathGraph, IncumbentBank, pin_pools, direct_joint, _native_joint
    from v42_common_mess.model import memory_observation
    from v42_common_mess.telemetry import root_lp
    from .m_engine import _BudgetAdapter
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/"PILOT_STARTED.json").exists():
        raise RuntimeError("MESS_NO_AUTOMATIC_PILOT_RESTART")
    source_gate=validate_pilot_inputs(scale,aidc_anchor,coefficients,coefficient_source)
    source_gate["grid_authority"]=validate_grid_authority(grid_authority,bundle=physical_bundle,
        electrical_certificate=electrical_certificate,thermal_receipt=thermal_receipt,coefficients=coefficients)
    if tuple(all_sites) != scale.original_sites or physical_bundle["initial_MESS_sites"] != scale.original_initial:
        raise ValueError("MESS_CURRENT_ORIGINAL_24_SITE_FOUR_UNIT_AXIS_DRIFT")
    _write(output/"PILOT_SOURCE_CONTENT_GATE.json",source_gate)
    estimate = model_build_estimate(scale, coefficients)
    _write(output/"MODEL_BUILD_ESTIMATE.json", estimate)
    memory = memory_observation()
    if memory["RAM_available"] < estimate["required_available_RAM_bytes"]:
        raise RuntimeError("MESS_BUILD_RAM_ADMISSION_REJECTED")
    _write(output/"PILOT_STARTED.json", dict(reduced_case_sha=scale.case_sha, mode=mode, Native0=native0,
        native_cap=seconds, shared_ledger_path=str(getattr(budget, "path", "INJECTED")), estimate=estimate))
    controls, result = [], {}
    compression_capture=[]
    before_build = perf_counter()
    stage_enum=Stage(scale.planning_stage)
    authority = replace(grid_authority, stage=stage_enum,
        voltage_lower_squared=voltage_for(stage_enum).lower_squared,
        voltage_upper_squared=voltage_for(stage_enum).upper_squared)
    def grid(model, p, q):
        controls.extend(source_grid_controls(scale, all_sites, coefficients, aidc_anchor, p, q))
        if grid_compression=="NONE":
            rho=add_grid(model, coefficients, controls, authority)
        else:
            rho,capture=add_grid_exact_compressed(model,coefficients,controls,authority,
                output=output/"EXACT_GRID_CAPTURE",identity=dict(scale.bindings,
                    reduced_case_sha=scale.case_sha,planning_stage=scale.planning_stage),
                probe_slots=compression_probe_slots)
            compression_capture.append(capture)
        return [("rho",rho), ("reserve_shortfall", 0.)]
    def optimizer(model, objectives, deadline, incumbent=None, **kwargs):
        import gurobipy as gp
        model.setObjective(objectives[0][1], gp.GRB.MINIMIZE)
        model.update()
        build_elapsed=perf_counter()-before_build
        size = assert_milp(model)
        A, d = arrays(model)
        if compression_probe_slots is not None:
            result.update(status="NATIVE0_PARTIAL_GRID_CAPTURE_ONLY",Native_optimize_calls=0,
                build_wall_seconds=build_elapsed,model_size=size,FULL_validated=False,
                original_grid_FULL96="NOT_BUILT_PARTIAL_PROBE",reduced_case_sha=scale.case_sha,
                shared_bindings=scale.bindings,compression_capture=compression_capture[0].receipt(),
                Global_LB=None,gap=None,performance_comparison="NOT_RUN")
            _write(output/"PARTIAL_GRID_CAPTURE_RESULT.json",result)
            return None,result
        original_A,original_d=A,d
        if compression_capture:
            original_A,original_d,compression_receipt=compression_capture[0].original_problem(model)
            result["exact_grid_compression"]=compression_receipt
        arcs = [(s,t,s,t+1,None) for s in scale.sites for t in range(96)] + [
            (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(scale.routes)]
        identity = dict(scale.bindings, stage=scale.planning_stage,scale_stage=scale.stage,
            physical_contract_sha=scale.bindings["physical_sha"], binary_count=int(np.count_nonzero(d["types"] == "B")),
            numeric_scope="CURRENT_NATIVE_AIDC_STAGE" if scale.manifest.get("anchor_scope") else
                "HISTORICAL_DIAGNOSTIC_AIDC_ANCHOR_CURRENT_REDUCED_PHYSICAL_ROWS",
            original_full4x24_grid_certificate_transferred=False)
        case = SimpleNamespace(A=A, d=d, original_A=original_A, original_d=original_d, lift=lambda x: np.asarray(x).copy(),
            graph=(scale.sites, scale.initial, arcs, scale.battery, {}), identity=identity,
            case_sha=scale.case_sha, output=output, bundle={"day": "2025-05-01"})
        point = np.zeros(A.shape[1], dtype=np.float64)
        candidate_plan=scale.stay_plan if compare_exact_compression or scale.warm_plan is None else scale.warm_plan
        for u in scale.inactive:
            if any(candidate_plan[k][u]!=scale.stay_plan[k][u]
                    for k in ("P_kW","Q_kvar","SOC_kWh","Mode","connection_site","routes")):
                raise ValueError("MESS_STAGE_WARM_PLAN_INACTIVE_SOURCE_DRIFT")
        full_arcs=[(s,t,s,t+1,None) for s in scale.original_sites for t in range(96)]+[
            (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(scale.original_routes)]
        def arc_key(a):return tuple(a[:4])+(None if a[-1] is None else a[-1].authority_sha256,)
        stage_indices={arc_key(a):k for k,a in enumerate(arcs)}
        chosen={u:{stage_indices[arc_key(full_arcs[k])] for k in candidate_plan["routes"][u]} for u in scale.active}
        for j, name in enumerate(map(str, d["names"])):
            if name == "rho_max":
                continue
            family, text = name.split("[", 1)
            fields = text[:-1].split(",")
            u = fields[0]
            if family == "arc":
                point[j] = float(int(fields[1]) in chosen[u])
            elif family == "SOC":
                point[j] = float(candidate_plan["SOC_kWh"][u][int(fields[1])])
            elif family == "charge_mode":
                point[j] = float(candidate_plan["Mode"][u][int(fields[1])])
            elif family in ("Pch", "Pdis", "Q"):
                site, tick = fields[1], int(fields[2])
                connected = site == candidate_plan["connection_site"][u][tick]
                p = float(candidate_plan["P_kW"][u][tick])
                point[j] = (float(candidate_plan["Q_kvar"][u][tick]) if family == "Q" else
                    max(0., -p) if family == "Pch" else max(0., p)) if connected else 0.
            else:
                raise ValueError("MESS_ORIGINAL_NATIVE_VARIABLE_FAMILY_DRIFT:"+family)
        rho = int(np.flatnonzero(d["names"] == "rho_max")[0])
        # Bound the literal stored source thermal rows at the source STAY point.
        original_thermal=np.flatnonzero(np.asarray(original_d["row_names"]) == "line_thermal_face")
        values = original_A[original_thermal] @ point - original_d["rhs"][original_thermal]
        denominator = -original_A[original_thermal, rho].toarray().ravel()
        idx=np.flatnonzero(np.asarray(d["row_names"]) == "line_thermal_face")
        if np.any(denominator <= 0):
            raise ValueError("MESS_ORIGINAL_THERMAL_RHO_SIGN_DRIFT")
        point[rho] = float(np.nextafter(np.max(values/denominator, initial=0.), np.inf))+1e-9
        source = output/"CURRENT_STAY_POINT.npz"
        np.savez_compressed(source, point=point)
        validation_begin=perf_counter()
        try:
            certificate = strict_full(case, source)
            certificate["full_four_vehicle_physical_replay"], _ = full_vehicle_replay(scale,case,point)
        except ValueError as exc:
            certificate = None
            _write(output/"CURRENT_STAY_POINT.REPLAY.json", dict(PASS=False, error=str(exc),
                historical_grid_certificate_transferred=False, current_case_sha=scale.case_sha))
        if certificate is not None:
            _write(output/"CURRENT_STAY_POINT.REPLAY.json", certificate)
        result.update(build_wall_seconds=build_elapsed, model_size=size,
            reduced_case_sha=scale.case_sha, full_source_stay_current_matrix_PASS=certificate is not None,
            current_stay_validation_wall_seconds=perf_counter()-validation_begin,
            first_FULL_validated_UB_seconds=perf_counter()-before_build if certificate is not None else None,
            first_FULL_validated_moving_UB_seconds=None,
            build_memory=memory_observation(), mode=mode, Native_optimize_calls=0,
            Global_LB=None, gap=None, bound_scope="REDUCED_CASE_GLOBAL" if mode == "EXACT_REDUCED" else "RESTRICTED_ROUTE_POOL",
            restricted_bound_is_Global_LB=False, Original_global_gap_certified=False,
            shared_bindings=scale.bindings, inactive_units=scale.inactive,
            inactive_Q_preserved=True, grid_contribution_once=True,
            historical_AIDC_anchor_diagnostic=scale.manifest.get("anchor_scope") is None,
            original_planning_stage=scale.planning_stage,
            warm_candidate_only_prior_UB_LB_transferred=False,
            Full96_Actual="NOT_RUN", Fresh_AC="NOT_RUN")
        result["grid_compression_mode"]=grid_compression
        _write(output/"MODEL_BUILD_RESULT.json", result)
        if native0:
            return None, dict(result, status="NATIVE0_BUILD_READBACK")
        if compare_exact_compression:
            result.update(_same_model_compression_benchmark(model,case,scale,coefficients,authority,budget,
                point,certificate,output/"COMPRESSION_BENCHMARK",seconds,benchmark_sampler[0],build_elapsed))
            result["compare_exact_compression"]=True
            result["gap_target_3_percent"]=result["gap"] is not None and result["gap"]<=.03
            _write(output/"S1_CURRENT_RESULT.json",result)
            return None,result
        bank = IncumbentBank(case)
        if certificate is not None:
            bank.offer(point, certificate)
        native_start = perf_counter()
        events = dict(first_solver_incumbent_seconds=None, presolve_removed_rows=None,
            presolve_removed_columns=None, root_first_observed_seconds=None,
            root_LB=None, root_fractional_route_columns=None, root_fractional_modes=None)
        captures = []
        def callback(m, where):
            if where == gp.GRB.Callback.PRESOLVE:
                events["presolve_removed_rows"] = int(m.cbGet(gp.GRB.Callback.PRE_ROWDEL))
                events["presolve_removed_columns"] = int(m.cbGet(gp.GRB.Callback.PRE_COLDEL))
            elif where == gp.GRB.Callback.MIPSOL:
                if events["first_solver_incumbent_seconds"] is None:
                    events["first_solver_incumbent_seconds"] = perf_counter()-native_start
                # Only bounded raw captures are stored; FULL admission follows Optimize.
                if len(captures) < 8:
                    captures.append(np.asarray(m.cbGetSolution(m.getVars()), dtype=np.float64))
            elif where == gp.GRB.Callback.MIPNODE and m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT) == 0:
                if events["root_first_observed_seconds"] is None:
                    events["root_first_observed_seconds"] = perf_counter()-native_start
                events["root_LB"] = float(m.cbGet(gp.GRB.Callback.MIPNODE_OBJBND))
                if m.cbGet(gp.GRB.Callback.MIPNODE_STATUS) == gp.GRB.OPTIMAL:
                    x = np.asarray(m.cbGetNodeRel(m.getVars()))
                    fractional = (x != np.rint(x)) & (d["types"] != "C")
                    events["root_fractional_route_columns"] = int(np.count_nonzero(fractional & np.char.startswith(d["names"], "arc[")))
                    events["root_fractional_modes"] = int(np.count_nonzero(fractional & np.char.startswith(d["names"], "charge_mode[")))
        if mode == "BEAM_JOINT":
            if certificate is None:
                raise ValueError("MESS_JOINT_REQUIRES_CURRENT_FULL_STAY_WITNESS")
            from .m_candidates import SignedMinimax, pcs_vertices
            # The unchanged native constructor repeats family-only row names.
            # Derive slot axes from its exact insertion order, rather than
            # inventing the qualified names used by the campaign compressor.
            per_slot = []
            dominated = re.compile(r"transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]", re.I)
            for c in coefficients:
                count = 2*len(c.voltage_constant)
                for name, rating in zip(c.branch_names, c.transformer_ratings):
                    if not dominated.fullmatch(name) or authority.require_all_transformer_currents:
                        count += 1 if name.lower().startswith("transformer.") else 16
                    if rating is not None:
                        count += 16
                per_slot.extend([c.slot]*count)
            first_grid = A.shape[0]-len(per_slot)
            if first_grid < 0:
                raise ValueError("MESS_ORIGINAL_GRID_INSERTION_AXIS_DRIFT")
            all_rows = []
            activities = A[idx] @ point-d["rhs"][idx]
            for original_row, residual, scale_co in zip(idx, activities, denominator):
                slot = per_slot[int(original_row)-first_grid]
                loading = float(point[rho]+residual/scale_co)
                all_rows.append((loading, int(original_row), slot))
            selected = {}
            for slot in range(96):
                group = sorted((r for r in all_rows if r[2] == slot), reverse=True)
                if not group:
                    raise ValueError("MESS_EVERY_SLOT_SIGNED_THERMAL_CONTEXT_REQUIRED")
                for r in group[:2]:
                    selected[r[1]] = r
            rows = []
            for loading, i, slot in selected.values():
                a,b = A.indptr[i:i+2]
                rows.append(dict(slot=slot, original_row=i, current_loading=loading,
                    metadata=dict(name="line_thermal_face", original_row=i),
                    coeff={str(d["names"][j]):str(Fraction(float(w))) for j,w in zip(A.indices[a:b], A.data[a:b])},
                    rhs=str(Fraction(float(d["rhs"][i])))))
            context = dict(rows=rows, all_thermal_rows_scanned=len(idx), selected_rows=len(rows),
                signed_coefficients_from_current_original_matrix=True,
                heuristic_shortlist_not_FULL_bound=True)
            scorer = SignedMinimax(case, point, context, pcs_vertices(case))
            base = scorer.graph.paths(point)
            def rank(u, path, _):
                # Partial paths use a legal STAY suffix when they already complete.
                if arcs[path[-1]][3] != 96:
                    return sum(float(arcs[k][-1].energy_kwh) for k in path if arcs[k][-1] is not None)
                paths = dict(base); paths[u] = list(path)
                return scorer.peak(paths)[0]
            pools, beam = beam_paths(scale, scorer=rank)
            pools = pin_pools(case, point, bank, pools)
            _write(output/"BEAM_PATH_AUDIT.json", beam)
            packet = direct_joint(case, point, pools)
            native, raw = _native_joint(case, _BudgetAdapter(budget, seconds), packet,
                output/"JOINT", seconds, native0=False)
            captures.extend(row["point"] for row in raw)
            result["restricted_ObjBound_diagnostic"] = native.get("restricted_ObjBound_diagnostic")
            result["native_receipt"] = native
            result["Native_optimize_calls"] = native["Native_optimize_calls"]
        else:
            model.Params.Threads=1; model.Params.Seed=0; model.Params.MIPGap=.03
            model.Params.FeasibilityTol=1e-9; model.Params.OptimalityTol=1e-9; model.Params.IntFeasTol=1e-8
            model.Params.OutputFlag=1; model.Params.LogToConsole=0
            model.Params.LogFile=str(output/"NATIVE_GUROBI.log")
            if certificate is not None:
                model.setAttr("Start", model.getVars(), point.tolist())
            native = budget.solve(model, label="MESS:"+scale.stage+":EXACT_REDUCED", cap=seconds, callback=callback)
            result["Native_optimize_calls"] = 1
            result["native_receipt"] = native
            if _attr(model, "SolCount"):
                captures.append(np.asarray(model.getAttr("X"), dtype=np.float64))
            candidate_bound = _attr(model, "ObjBound")
            if candidate_bound is not None and _attr(model, "Status") not in (gp.GRB.INFEASIBLE, gp.GRB.UNBOUNDED, gp.GRB.INF_OR_UNBD, gp.GRB.NUMERIC):
                result["Global_LB"] = candidate_bound
            result.update(B_and_B_nodes=_attr(model, "NodeCount"), native_status=_attr(model, "Status"),
                native_Runtime=_attr(model, "Runtime"), native_Work=_attr(model, "Work"))
            result.update(root_lp(output/"NATIVE_GUROBI.log"))
        accepted, rejected, seen = [], [], set()
        for i, raw in enumerate(captures):
            sha = vector_sha(raw)
            if sha in seen:
                continue
            seen.add(sha)
            path = output/f"RAW_{i:03d}.npz"
            np.savez_compressed(path, point=raw)
            try:
                cert = strict_full(case, path)
                cert["full_four_vehicle_physical_replay"], full_plan = full_vehicle_replay(scale,case,raw)
                bank.offer(raw, cert)
                if result["first_FULL_validated_UB_seconds"] is None:
                    result["first_FULL_validated_UB_seconds"]=perf_counter()-before_build
                if PathGraph(case).moving(raw) and result["first_FULL_validated_moving_UB_seconds"] is None:
                    result["first_FULL_validated_moving_UB_seconds"]=perf_counter()-before_build
                _write(path.with_suffix(".REPLAY.json"), cert)
                accepted.append(dict(raw=file_record(path), UB=cert["Global_UB"], moving=PathGraph(case).moving(raw)))
            except ValueError as exc:
                rejected.append(dict(raw=file_record(path), reason=str(exc)))
        result.update(bank.fields(), events=events, accepted=accepted, rejected=rejected,
            solve_wall_seconds=perf_counter()-native_start, after_native_memory=memory_observation())
        ub, lb = result["BEST_GLOBAL_UB"], result["Global_LB"]
        if ub is not None and lb is not None and lb <= ub and ub != 0:
            result["gap"] = abs(ub-lb)/abs(ub)
        elif lb is not None and ub is not None and lb > ub:
            result["Global_LB"] = None
            result["bound_rejection"] = "SOLVER_BOUND_EXCEEDS_CURRENT_FULL_UB"
        result["status"] = "REDUCED_FULL_FEASIBLE" if bank.best is not None else "NO_CURRENT_FULL_FEASIBLE_INCUMBENT"
        result["gap_target_3_percent"] = result["gap"] is not None and result["gap"] <= .03
        bank.save(output, dict(shared=scale.bindings, reduced_case_sha=scale.case_sha))
        if bank.best is not None:
            replay,full_plan = full_vehicle_replay(scale,case,bank.best[0])
            _write(output/"FULL_FOUR_VEHICLE_PHYSICAL_PLAN.json",full_plan)
            _write(output/"FULL_FOUR_VEHICLE_PHYSICAL_REPLAY.json",replay)
            result["full_four_vehicle_physical_replay"] = replay
            result["FULL_validated"]=True
            result["mess"]=full_plan
        else:
            result["FULL_validated"]=False
            result["mess"]=None
        _write(output/"S1_CURRENT_RESULT.json", result)
        return None, result
    prior_context=getattr(budget,"stage_context",None)
    had_context=hasattr(budget,"stage_context")
    budget.stage_context=dict(unified_bindings=dict(scale.bindings),
        reduced_case_sha=scale.case_sha,scale_stage=scale.stage,planning_stage=scale.planning_stage,
        science_sha=scale.bindings["science_sha"],case_sha=scale.bindings["case_sha"],
        physical_sha=scale.bindings["physical_sha"],time_axis_sha=scale.bindings["time_axis_sha"],
        qos_sha=scale.bindings["qos_sha"],aidc_anchor=scale.bindings["aidc_anchor"],
        mess_anchor=scale.bindings["mess_anchor"],response_sha=coefficient_source["sha256"],
        coefficient_source=coefficient_source,
        numeric_scope="CURRENT_NATIVE_AIDC_STAGE" if scale.manifest.get("anchor_scope") else "HISTORICAL_DIAGNOSTIC_AIDC_ANCHOR",
        grid_compression_mode=grid_compression,
        prior_UB_LB_transferred=False)
    benchmark_sampler=[]
    try:
        if compare_exact_compression:
            with _BenchmarkPhaseSampler() as sampler:
                benchmark_sampler.append(sampler)
                _,receipt=solve(scale.planning_stage,_ConstructionDeadline(budget,scale.planning_stage),scale.sites,scale.initial,
                    scale.routes,scale.battery,96,grid,optimizer=optimizer)
            result["benchmark_phase_memory"]=sampler.receipt()
            summary_path=output/"COMPRESSION_BENCHMARK"/"COMPRESSION_BENCHMARK_RESULT.json"
            summary=json.loads(summary_path.read_text(encoding="utf8"))
            summary["benchmark_phase_memory"]=sampler.receipt()
            _write(summary_path,summary)
        else:
            _, receipt = solve(scale.planning_stage, _ConstructionDeadline(budget,scale.planning_stage), scale.sites, scale.initial,
                scale.routes, scale.battery, 96, grid, optimizer=optimizer)
    finally:
        if had_context:budget.stage_context=prior_context
        else:delattr(budget,"stage_context")
    result["original_native_constructor_receipt"] = constructor_summary(receipt)
    # The full prescreen has its separate source proof artifact. Avoid repeating
    # its million-byte slot lists in every result, without losing numeric facts.
    result.pop("physical_prescreen",None)
    _write(output/"S1_CURRENT_RESULT.json", result)
    return result


def validate_captured_a_input_mess(a_case,finalmess,expectedbindings):
    """The captured A input MESS must be the literal input to this M stage."""
    if hasattr(a_case,"unified_bindings"):
        for key in BINDING_FIELDS:
            if key!="aidc_anchor" and a_case.unified_bindings[key]!=expectedbindings[key]:
                raise ValueError("MESS_NATIVE_A_COMMON_BINDINGS_DRIFT:"+key)
    if not isinstance(a_case.grid.fixed_mess,dict) or a_case.grid.fixed_mess.get("plan_sha")!=finalmess["plan_sha"]:
        raise ValueError("MESS_NATIVE_A_CAPTURED_INPUT_MESS_ANCHOR_DRIFT")
    return dict(PASS=True,captured_input_mess_anchor=finalmess["plan_sha"])


def make_stage_pilot_bundle(integration_or_a_case,aidc_result,finalmess,stage,expectedbindings,output):
    """Current native A result to scaled M1/M2; no historical A result lookup."""
    from .coordinator import _full_a
    from .production_case import ProductionPhysicalContext,read,ARCHIVE
    from .partial_canary import SOURCE_DIR
    _full_a(aidc_result)
    require_stage_bindings(expectedbindings,expectedbindings)
    if stage not in ("M1","M2") or aidc_result["aidc_anchor"]!=expectedbindings["aidc_anchor"]:
        raise ValueError("MESS_CURRENT_NATIVE_A_STAGE_ANCHOR_REQUIRED")
    call=aidc_result.get("Native_call",{})
    replay=aidc_result.get("FULL_point_replay",{})
    if call.get("solver")!="GUROBI" or call.get("Native_Runtime") is None or replay.get("PASS") is not True:
        raise ValueError("MESS_CURRENT_NATIVE_A_SOURCE_REPLAY_EVIDENCE_REQUIRED")
    from .a_engine import digest as handoff_digest
    if finalmess.get("plan_sha")!=expectedbindings["mess_anchor"] or handoff_digest(
            {k:v for k,v in finalmess.items() if k!="plan_sha"})!=finalmess.get("plan_sha"):
        raise ValueError("MESS_CURRENT_INPUT_MESS_CONTENT_ANCHOR_REQUIRED")
    output=Path(output)
    if hasattr(integration_or_a_case,"make_a_case"):
        integration=integration_or_a_case
        a_case=integration.make_a_case("B3","A1" if stage=="M1" else "A2",finalmess,output/"A_DESCRIPTORS")
        source_freeze=integration.source_freeze
    else:
        a_case=integration_or_a_case
        source_freeze=getattr(a_case,"source_freeze",read(SOURCE_DIR/"SOURCE_FREEZE_DDAY_GRID_V5.json"))
    if aidc_result.get("case_sha")!=a_case.case_sha or aidc_result.get("stage")!=("A1" if stage=="M1" else "A2"):
        raise ValueError("MESS_NATIVE_A_RESULT_CURRENT_CAPTURED_CASE_STAGE_DRIFT")
    validate_captured_a_input_mess(a_case,finalmess,expectedbindings)
    bundle=a_case.data[0]
    physical=ProductionPhysicalContext(source_freeze,read(ARCHIVE/"CAMPAIGN_MANIFEST.json"),bundle)
    stay=read(DEFAULT_STAY)
    # A previous full4 optimized plan is a candidate only; source OFF anchors
    # lack per-vehicle native arrays and use the current replayed STAY candidate.
    warm=finalmess if all(k in finalmess for k in ("P_kW","Q_kvar","SOC_kWh","connection_site")) else None
    scale=build_scale_case(bundle,"S1",stay,bindings=expectedbindings,
        expected_stage_bindings=expectedbindings,planning_stage=stage,warm_plan=warm,
        stay_source=file_record(DEFAULT_STAY))
    source=physical.certificate["outputs"]["planning_coefficients"]
    validate_pilot_inputs(scale,aidc_result,a_case.grid.coefficients,source)
    validate_grid_authority(a_case.grid.authority,bundle=bundle,electrical_certificate=bundle["electrical_certificate"],
        thermal_receipt=physical.manifest["thermal"],coefficients=a_case.grid.coefficients)
    return dict(scale=scale,aidc_anchor=aidc_result,coefficients=a_case.grid.coefficients,
        coefficient_source=source,grid_authority=a_case.grid.authority,physical_bundle=bundle,
        electrical_certificate=bundle["electrical_certificate"],thermal_receipt=physical.manifest["thermal"],
        physical=physical,all_sites=scale.original_sites,
        prior_UB_LB_transferred=False,current_native_A_full_replay=True)


def full_stay_handoff(stay_source=DEFAULT_STAY):
    """Literal four-unit source STAY with complete aggregated grid aliases."""
    plan=json.loads(Path(stay_source).read_text(encoding="utf8"))
    sites=tuple(plan.get("P_by_site",plan.get("site_P_kW")))
    plan["routes"]=plan["routes"] if "routes" in plan else plan["route_paths"]
    plan["SOC"]=plan["SOC_kWh"]
    plan["P_by_site"]={s:[sum(plan["P_kW"][u][t] for u in plan["initial_sites"]
        if plan["connection_site"][u][t]==s) for t in range(96)] for s in sites}
    plan["Q_by_site"]={s:[sum(plan["Q_kvar"][u][t] for u in plan["initial_sites"]
        if plan["connection_site"][u][t]==s) for t in range(96)] for s in sites}
    plan.pop("plan_sha",None)
    from .a_engine import digest as handoff_digest
    plan["plan_sha"]=handoff_digest(plan)
    return plan


def install_scaled_m_adapter(integration, *, m1_seconds=30.,m2_seconds=30.,mode="EXACT_REDUCED"):
    """Install coordinator make-M/optimizer hooks without a full4x24 model build.

    Supervisor sets integration.initial_mess=full_stay_handoff() and freezes its
    SHA before calling run_arm. A/M budgets stay in the injected common ledger.
    """
    make_a=integration.make_a_case
    state={"latest_a":None,"input_mess":None}
    def capture_a(arm,stage,mess,folder):
        case=make_a(arm,stage,mess,folder)
        case.source_freeze=integration.source_freeze
        state.update(latest_a=case,input_mess=mess)
        return case
    def make_m(arm,stage,aidc,folder):
        if state["latest_a"] is None:
            raise ValueError("MESS_SCALING_REQUIRES_CURRENT_A_CASE_BEFORE_M")
        return SimpleNamespace(identity=dict(aidc_anchor=aidc["aidc_anchor"],stage=stage),
            case_sha=digest(dict(aidc_anchor=aidc["aidc_anchor"],stage=stage)),
            a_case=state["latest_a"],aidc_result=aidc,finalmess=state["input_mess"],
            stage=stage,output=Path(folder))
    def optimizer(mcase,initial,registry,budget):
        if not hasattr(mcase,"unified_bindings"):
            raise ValueError("MESS_SUPERVISOR_STAGE_BINDINGS_REQUIRED")
        prepared=make_stage_pilot_bundle(mcase.a_case,mcase.aidc_result,mcase.finalmess,
            mcase.stage,mcase.unified_bindings,mcase.output)
        keys=("coefficients","grid_authority","aidc_anchor","all_sites","coefficient_source",
            "physical_bundle","electrical_certificate","thermal_receipt")
        with prepared["physical"].physical_scope():
            result=run_original_pilot(prepared["scale"],**{k:prepared[k] for k in keys},
                budget=budget,output=mcase.output/"SCALED_SOURCE_PHYSICAL",mode=mode,
                seconds=m1_seconds if mcase.stage=="M1" else m2_seconds)
        folder=mcase.output/"SCALED_SOURCE_PHYSICAL"
        registry_path=folder/"SAME_CASE_INCUMBENT_REGISTRY.json"
        current_registry=json.loads(registry_path.read_text(encoding="utf8")) if registry_path.exists() else []
        _write(folder/"STAGE_REGISTRY_RESCOPE.json",dict(previous_records=len(registry or []),
            previous_raw_candidate_supplied=initial is not None,previous_UB_LB_transferred=False,
            candidate_source="PRIOR_FULL4_PLAN_FRESH_CURRENT_MATRIX_REPLAY",current_registry=current_registry))
        result.update(engine_version="V42_S1_ORIGINAL_PHYSICAL_CURRENT_STAGE_V1",
            case_sha=prepared["scale"].case_sha,incumbent_registry=current_registry,
            global_gap_certified=False,original4x24_global_LB=None)
        point=None
        if result.get("FULL_validated"):
            with np.load(folder/"BEST_GLOBAL_INCUMBENT.npz",allow_pickle=False) as z:
                point=z["point"].copy()
        _write(mcase.output/"M_STAGE_RESULT.json",result)
        return result,point
    integration.make_a_case=capture_a
    integration.make_m_case=make_m
    integration.unified_m_optimizer=optimizer
    return integration


def prepare_production_pilot(output, *, contracts=REPORT):
    """Lazy original descriptors only; no A/M models, optimization or Actual replay."""
    from .production_case import build_integration_case, read, ARCHIVE
    from .partial_canary import SOURCE_DIR
    from .tracking_canary import HISTORICAL_A1
    output = Path(output)
    integration = build_integration_case(
        source_freeze=read(SOURCE_DIR/"SOURCE_FREEZE_DDAY_GRID_V5.json"),
        strict_stats=SOURCE_DIR/"QOS_EMPIRICAL_STATS_STRICT.json", output=output/"CASE")
    aidc = read(HISTORICAL_A1)
    shared = load_contracts(contracts)
    target_receipt=shared["historical_reference_file"]
    target_path=Path(target_receipt["path"])
    if file_record(target_path)["sha256"] != target_receipt["sha256"]:
        raise ValueError("MESS_HISTORICAL_TARGET_SOURCE_RECEIPT_DRIFT")
    expected_a1=read(target_path)["source_A1_artifact"]
    actual_a1=file_record(HISTORICAL_A1)
    if any(actual_a1[k]!=expected_a1[k] for k in ("sha256","bytes")):
        raise ValueError("MESS_HISTORICAL_A1_SOURCE_BYTES_DRIFT")
    from .coordinator import _full_a
    _full_a(aidc)
    if aidc["aidc_anchor"] != shared["bindings"]["aidc_anchor"]:
        raise ValueError("MESS_HISTORICAL_DIAGNOSTIC_AIDC_ANCHOR_SHA_DRIFT")
    a_case = integration.make_a_case("B3", "A1", integration.initial_mess, output/"A_DESCRIPTORS")
    bundle = a_case.data[0]
    stay = read(DEFAULT_STAY)
    scale = build_scale_case(bundle, "S1", stay, bindings=shared["bindings"],
        contracts=contracts, stay_source=file_record(DEFAULT_STAY))
    audit = audit_original_sites(bundle, electrical_certificate=bundle["electrical_certificate"],
        coefficients=a_case.grid.coefficients)
    # GridAuthority needs the same scoped transformer/11-SVR source receipts.
    from .production_case import ProductionPhysicalContext
    physical = ProductionPhysicalContext(integration.source_freeze, read(ARCHIVE/"CAMPAIGN_MANIFEST.json"), bundle)
    response_source=physical.certificate["outputs"]["planning_coefficients"]
    validate_pilot_inputs(scale,aidc,a_case.grid.coefficients,response_source)
    validate_grid_authority(a_case.grid.authority,bundle=bundle,
        electrical_certificate=bundle["electrical_certificate"],thermal_receipt=physical.manifest["thermal"],
        coefficients=a_case.grid.coefficients)
    return dict(integration=integration, a_case=a_case, scale=scale, audit=audit,
        aidc_anchor=aidc, grid_authority=a_case.grid.authority,
        coefficients=a_case.grid.coefficients,coefficient_source=response_source,
        physical_bundle=bundle,electrical_certificate=bundle["electrical_certificate"],
        thermal_receipt=physical.manifest["thermal"],
        physical=physical, all_sites=tuple(audit["service_sites"]))
