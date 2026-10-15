"""Case-explicit PR222 incumbent admission and Exact Direct four-MESS Joint.

The direct substitution is the verified PR220/221 formulation: retain every
source row as A_source T z, replace only route incidence coordinates by binary
one-hot complete paths, and retain all original charge modes/P/Q/SOC. This
module never imports the archived research adapters or changes RAW_REL.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from copy import copy
from dataclasses import asdict, is_dataclass
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse
from .preparation_profile import measure, profile_joint, profile_component

ENGINE_VERSION = "PR222_CASE_EXPLICIT_EXACT_DIRECT_JOINT_V1"
PR222_SHA = "12594e281bb89611331950f11f775a2612d3cb48"
# Exact tools/u4_primal_alns/pilot.py PARAMS used by PR222's Direct worker.
APPROVED_JOINT_PARAMETERS = dict(Threads=1, FeasibilityTol=1e-9, OptimalityTol=1e-9,
    IntFeasTol=1e-8, MIPGap=.005, Method=2, MIPFocus=1, NumericFocus=3,
    ScaleFlag=2, Seed=0, MIPGapAbs=1e-10)


class _BudgetAdapter:
    """Only adapt calling convention; costs remain in one original ledger."""
    def __init__(self, parent, limit=1800.):
        self.parent = parent
        self.initial_used = float(parent.used())
        self.limit = float(limit)

    def remaining(self):
        return max(0., min(self.parent.remaining(), self.limit - self.used()))

    def used(self):
        return max(0., float(self.parent.used()) - self.initial_used)

    @property
    def calls(self):
        return getattr(self.parent, "calls", getattr(self.parent, "document", {}).get("calls", []))

    def cost(self, *args, **kwargs):
        return self.parent.cost(*args, **kwargs) if hasattr(self.parent, "cost") else nullcontext()

    def native_optimize(self, model, callback=None, *, component="UB", track="M", label="", requested_seconds=None):
        requested_seconds = min(float(requested_seconds), self.remaining())
        if hasattr(self.parent, "solve"):
            return self.parent.solve(model, label=track + ":" + label,
                                     cap=requested_seconds, callback=callback)
        return self.parent.native_optimize(model, callback, component=component, track=track,
                                           label=label, requested_seconds=requested_seconds)

    def record_external(self, *args, **kwargs):
        return self.parent.record_external(*args, **kwargs)


def _json_value(value):
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Fraction):
        return str(value)
    return value


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(_json_value(value), ensure_ascii=False,
                                   indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_record(path):
    path = Path(path).resolve()
    hasher = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            hasher.update(chunk)
    return dict(path=str(path), sha256=hasher.hexdigest(), bytes=path.stat().st_size)


def vector_sha(point):
    return sha256(np.ascontiguousarray(point, dtype="<f8").tobytes()).hexdigest()


def matrix_sha(matrix):
    matrix = matrix.tocsr()
    h = sha256(np.asarray(matrix.shape, dtype="<i8").tobytes())
    for value in (matrix.indptr, matrix.indices, matrix.data):
        h.update(value.dtype.str.encode("ascii"))
        h.update(np.ascontiguousarray(value).tobytes())
    return h.hexdigest()


def domain_sha(domain):
    h = sha256()
    for key in sorted(domain):
        value = np.asarray(domain[key])
        h.update(key.encode())
        h.update(value.dtype.str.encode())
        h.update(np.asarray(value.shape, dtype="<i8").tobytes())
        h.update(value.tobytes())
    return h.hexdigest()


def binding(case):
    """Numeric problem, hard physical inputs and QoS/AIDC anchor identity."""
    sites, initial, arcs, battery, *_ = case.graph
    route = dict(sites=list(sites), initial=initial,
                 arcs=[(a[:4], None if a[-1] is None else vars(a[-1])) for a in arcs],
                 battery=vars(battery))
    digest = sha256(json.dumps(_json_value(route), sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    identity = getattr(case, "identity", {})
    bundle = getattr(case, "bundle", {})
    return dict(case_sha=case.case_sha,stage=identity.get('stage'),
                source_sha=identity.get('D0_source_sha',identity.get('source_sha')),
                science_sha=identity.get('science_sha'),
                day=bundle.get("day", identity.get("day")),
                arm=identity.get("arm", bundle.get("arm")),
                original_matrix_sha=matrix_sha(case.original_A),
                original_domain_sha=domain_sha(case.original_d),
                selected_matrix_sha=matrix_sha(case.A), selected_domain_sha=domain_sha(case.d),
                route_contract_sha=digest,
                aidc_anchor=identity.get("aidc_anchor", identity.get("AIDC_anchor")),
                qos_sha=identity.get("qos_sha", identity.get("QOS_SHA")),
                physical_contract_sha=identity.get("physical_contract_sha"))


def _exact_objective(domain, point):
    return Fraction(float(domain["constant"])) + sum(
        (Fraction(float(domain["objective"][j])) * Fraction(float(point[j]))
         for j in np.flatnonzero(domain["objective"])), Fraction(0))


@profile_component('M_ORIGINAL_FULL_REPLAY')
def strict_full(case, path, evidence=None):
    """Unmodified check_ub FULL/physical validator, without historical ROOT IO.

    Raw packets contain only point. Route metadata belongs to separate files.
    The literal integer gate and exact objective transport match PR222's
    final_verify._strict_ub; no clipping/rounding/repair is permitted.
    """
    from v42_m1_research.check_ub import validate_candidate
    with np.load(path, allow_pickle=False) as packet:
        if packet.files != ["point"]:
            raise ValueError("RAW_POINT_PACKET_AXIS_DRIFT")
        point = packet["point"].copy()
    if point.dtype != np.dtype("float64") or point.shape != (case.A.shape[1],) or not np.isfinite(point).all():
        raise ValueError("RAW_POINT_AXIS_OR_FINITE_DRIFT")
    original = case.lift(point)
    for domain, values in ((case.d, point), (case.original_d, original)):
        discrete = values[domain["types"] != "C"]
        binary = values[domain["types"] == "B"]
        if not np.all(discrete == np.rint(discrete)) or not np.isin(binary, (0., 1.)).all():
            raise ValueError("RAW_LITERAL_INTEGER_GATE")
    replay = validate_candidate(case, point)
    exact = _exact_objective(case.d, point)
    if not replay.get("PASS") or exact != _exact_objective(case.original_d, original):
        raise ValueError("CURRENT_ORIGINAL_FULL_REPLAY_REJECTED")
    displayed = float(exact)
    if Fraction(displayed) < exact:
        displayed = float(np.nextafter(displayed, np.inf))
    return dict(PASS=True, exact_Global_UB=str(exact), Global_UB=displayed,
                point_path=str(Path(path).resolve()), point_file_sha256=file_record(path)["sha256"],
                point_vector_sha256=vector_sha(point),
                strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
                original_matrix_and_96_slot_physical_replay=replay, Native_optimize_calls=0)


class PathGraph:
    """Original PR220 DAG closure, with explicit current named bounds."""
    def __init__(self, case):
        self.case, self.arcs, self.origins = case, case.graph[2], case.graph[1]
        self.horizon = max(a[3] for a in self.arcs)
        self.stay = {(a[0], a[1]): k for k, a in enumerate(self.arcs) if a[-1] is None}
        self.outgoing = defaultdict(list)
        for k, arc in enumerate(self.arcs):
            self.outgoing[arc[:2]].append(k)
        named = {str(name): j for j, name in enumerate(case.original_d["names"])}
        self.available = {u: {k for k in range(len(self.arcs))
                              if (j := named.get(f"arc[{u},{k}]")) is not None
                              and case.original_d["upper"][j] >= 1.} for u in self.origins}

    def validate(self, unit, path):
        site, tick = self.origins[unit], 0
        if not path:
            raise ValueError("EMPTY_ORIGINAL_ROUTE")
        for k in path:
            if k not in self.available[unit]:
                raise ValueError("ORIGINAL_ARC_DOMAIN_REJECTED")
            arc = self.arcs[k]
            if arc[:2] != (site, tick) or not tick < arc[3] <= self.horizon:
                raise ValueError("ORIGINAL_ROUTE_FLOW_OR_ETA")
            if arc[-1] is not None:
                arc[-1].validate(self.horizon)
            site, tick = arc[2:4]
        if tick != self.horizon:
            raise ValueError("INCOMPLETE_ORIGINAL_PATH")
        return True

    def complete(self, unit, moves=()):
        site, tick, path = self.origins[unit], 0, []
        for k in moves:
            arc = self.arcs[k]
            if arc[-1] is None or arc[0] != site or arc[1] < tick:
                raise ValueError("INVALID_MOVE_SEQUENCE")
            path.extend(self.stay[site, t] for t in range(tick, arc[1]))
            path.append(k)
            site, tick = arc[2:4]
        path.extend(self.stay[site, t] for t in range(tick, self.horizon))
        self.validate(unit, path)
        return path

    def paths(self, point):
        original = self.case.lift(point)
        named = {str(name): j for j, name in enumerate(self.case.original_d["names"])}
        result = {}
        for unit, origin in self.origins.items():
            selected = {self.arcs[k][:2]: k for k in self.available[unit]
                        if original[named[f"arc[{unit},{k}]"]] == 1.}
            site, tick, path = origin, 0, []
            while tick < self.horizon:
                k = selected[site, tick]
                path.append(k)
                site, tick = self.arcs[k][2:4]
            self.validate(unit, path)
            result[unit] = path
        return result

    def moving(self, point):
        return any(self.arcs[k][-1] is not None for path in self.paths(point).values() for k in path)


def _certificate_matches(case, point, certificate):
    replay = certificate.get("original_matrix_and_96_slot_physical_replay", {})
    return (certificate.get("PASS") is True and replay.get("PASS") is True
            and replay.get("case_sha") == case.case_sha
            and certificate.get("strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact") is True
            and certificate.get("point_vector_sha256") == vector_sha(point)
            and Fraction(certificate["exact_Global_UB"]) == _exact_objective(case.d, point))


class IncumbentBank:
    """Exact-case global and moving best remain distinct from pool ObjVal."""
    def __init__(self, case):
        self.case, self.graph, self.best, self.best_moving = case, PathGraph(case), None, None

    def offer(self, point, certificate):
        if not _certificate_matches(self.case, point, certificate):
            raise ValueError("CURRENT_RAW_FULL_CERTIFICATE_REQUIRED")
        item = (np.asarray(point).copy(), dict(certificate))
        if self.best is None or Fraction(certificate["exact_Global_UB"]) < Fraction(self.best[1]["exact_Global_UB"]):
            self.best = item
        if self.graph.moving(point) and (self.best_moving is None or
                Fraction(certificate["exact_Global_UB"]) < Fraction(self.best_moving[1]["exact_Global_UB"])):
            self.best_moving = item

    def fields(self):
        return dict(BEST_GLOBAL_UB=None if self.best is None else self.best[1]["Global_UB"],
                    BEST_MOVING_FEASIBLE_UB=None if self.best_moving is None else self.best_moving[1]["Global_UB"])

    def save(self, folder, case_binding):
        Path(folder).mkdir(parents=True,exist_ok=True)
        records = []
        for label, item in (("GLOBAL", self.best), ("MOVING", self.best_moving)):
            if item is None:
                continue
            point, certificate = item
            path = Path(folder) / f"BEST_{label}_INCUMBENT.npz"
            np.savez_compressed(path, point=point)
            _write(path.with_suffix(".REPLAY.json"), dict(certificate, point_path=str(path),
                    point_file_sha256=file_record(path)["sha256"]))
            records.append(dict(origin="CASE_FULL_BANK_" + label, binding=case_binding, raw=file_record(path)))
        _write(Path(folder) / "SAME_CASE_INCUMBENT_REGISTRY.json", records)
        return records


def admit_registry(case, records, folder, validator, case_binding):
    accepted, receipts = [], []
    for ordinal, entry in enumerate(records or []):
        row = dict(origin=entry.get("origin"), admitted=False)
        try:
            if entry["binding"] != case_binding:
                raise ValueError("DATE_ANCHOR_QOS_OR_NUMERIC_PHYSICAL_CONTRACT_MISMATCH")
            record = file_record(entry["raw"]["path"])
            if record != entry["raw"]:
                raise ValueError("RAW_BYTES_DRIFT")
            with np.load(record["path"], allow_pickle=False) as packet:
                if packet.files != ["point"]:
                    raise ValueError("RAW_POINT_PACKET_AXIS_DRIFT")
                point = packet["point"].copy()
            certificate = _validate(case, point, Path(folder) / f"INHERITED_{ordinal:03d}.npz", validator)
            if certificate is None:
                raise ValueError("CURRENT_ORIGINAL_FULL_REPLAY_REJECTED")
            accepted.append((point, certificate))
            row.update(admitted=True, UB=certificate["Global_UB"], source=record)
        except (ValueError, KeyError, OSError) as exc:
            row["reason"] = str(exc)
        receipts.append(row)
    _write(Path(folder) / "CASE_INCUMBENT_ADMISSION.json", dict(binding=case_binding, records=receipts,
                                                               Native_optimize_calls=0))
    return accepted


def _validate(case, point, path, validator):
    if point is None:
        return None
    point = np.asarray(point, dtype=np.float64)
    if point.shape != (case.A.shape[1],) or not np.isfinite(point).all():
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, point=point)
    try:
        certificate = validator(case, path, {})
        if not _certificate_matches(case, point, certificate):
            raise ValueError("CURRENT_RAW_FULL_CERTIFICATE_REQUIRED")
        _write(path.with_suffix(".REPLAY.json"), certificate)
        return certificate
    except ValueError as exc:
        _write(path.with_suffix(".REPLAY.json"), dict(PASS=False, error=str(exc), case_sha=case.case_sha))
        return None


def pin_pools(case, point, bank, candidate_pools=None):
    """Pin complete verified paths and STAY without requiring a MOVE choice."""
    graph = bank.graph
    current = graph.paths(point)
    pool = {}
    for unit in sorted(graph.origins):
        paths, seen = [], set()
        def add(path):
            path = list(path)
            graph.validate(unit, path)
            signature = tuple(path)
            if signature not in seen:
                seen.add(signature)
                paths.append(path)
        add(current[unit])
        add(graph.complete(unit))
        if bank.best_moving is not None:
            add(graph.paths(bank.best_moving[0])[unit])
        for path in (candidate_pools or {}).get(unit, []):
            add(path)
        pool[unit] = paths
    return pool


@profile_joint
def direct_joint(case, point, pools):
    """PR221 Exact Direct substitution with current axes and no global context."""
    graph = PathGraph(case)
    units = sorted(graph.origins)
    if set(pools) != set(units):
        raise ValueError("ALL_MESS_POOL_REQUIRED")
    center = graph.paths(point)
    cache_key = (matrix_sha(case.A), domain_sha(case.d),
                 matrix_sha(case.original_A), domain_sha(case.original_d),
                 file_record(__file__)['sha256'], binding(case)['route_contract_sha'])
    cache = getattr(case, '_direct_static_cache', None)
    cache_hit = cache is not None and cache['key'] == cache_key
    if not cache_hit:
        route = np.asarray([j for j, name in enumerate(map(str, case.d["names"]))
                            if name.startswith(("route_flow[", "arc[", "node_activity["))], dtype=int)
        keep = np.setdiff1d(np.arange(case.A.shape[1]), route, assume_unique=True)
        if not len(route) or np.any(case.d["objective"][route] != 0):
            raise ValueError("ORIGINAL_ROUTE_COORDINATE_OR_OBJECTIVE_DRIFT")
        grouped = {u: [int(j) for j in route if str(case.d["names"][j]).split("[", 1)[1].split(",")[0] == u]
                   for u in units}
        if sum(map(len, grouped.values())) != len(route):
            raise ValueError("ORIGINAL_ROUTE_UNIT_AXIS_DRIFT")
        cache = dict(key=cache_key, route=route, keep=keep, grouped=grouped, path_products={})
        case._direct_static_cache = cache
    route, keep, grouped = cache['route'], cache['keep'], cache['grouped']
    rows, columns, coefficients, axis, selections = list(map(int, keep)), list(range(len(keep))), [1.] * len(keep), [], []
    for unit in units:
        if center[unit] not in pools[unit] or graph.complete(unit) not in pools[unit]:
            raise ValueError("COMPLETE_CENTER_AND_STAY_REQUIRED")
        if len({tuple(path) for path in pools[unit]}) != len(pools[unit]):
            raise ValueError("DUPLICATE_POOL_PATH")
        for ordinal, path in enumerate(pools[unit]):
            graph.validate(unit, path)
            selected = set(path)
            vertices = {graph.arcs[k][:2] for k in path} | {(graph.arcs[path[-1]][2], graph.horizon)}
            col = len(keep) + len(axis)
            for j in grouped[unit]:
                family, text = str(case.d["names"][j]).split("[", 1)
                fields = text[:-1].split(",")
                value = (int(fields[1]) in selected if family in ("route_flow", "arc")
                         else (fields[1], int(fields[2])) in vertices)
                if not case.d["lower"][j] <= float(value) <= case.d["upper"][j]:
                    raise ValueError("PATH_OUTSIDE_SELECTED_ORIGINAL_DOMAIN")
                if value:
                    rows.append(j)
                    columns.append(col)
                    coefficients.append(1.)
            axis.append(dict(unit=unit, ordinal=ordinal, path=list(path), name=f"lambda[{unit},{ordinal}]"))
            selections.append(float(path == center[unit]))
    lift = sparse.csr_matrix((coefficients, (rows, columns)), shape=(case.A.shape[1], len(keep) + len(axis)))
    product = (case.A @ lift).tocsr()
    product.eliminate_zeros()
    product.sort_indices()
    if (product[:, :len(keep)] != case.A[:, keep]).nnz:
        raise ValueError("DIRECT_NONROUTE_SOURCE_COLUMN_DRIFT")
    checked = 0
    for ordinal in range(len(axis)):
        path_columns = lift[:, len(keep) + ordinal].tocoo().row
        path_key = (axis[ordinal]['unit'], tuple(axis[ordinal]['path']))
        exact = cache['path_products'].get(path_key)
        if exact is None:
            source = case.A[:, path_columns].tocoo()
            exact = defaultdict(Fraction)
            for row, value in zip(source.row, source.data):
                exact[int(row)] += Fraction(float(value))
            exact = {r:v for r,v in exact.items() if v}
            cache['path_products'][path_key] = exact
        observed = product[:, len(keep) + ordinal].tocoo()
        if exact != {int(r): Fraction(float(v)) for r,v in zip(observed.row,observed.data)}:
            raise ValueError('SPARSE_PRODUCT_NOT_EXACT_DYADIC')
        checked += len(exact)
    one = sparse.csr_matrix(([1.] * len(axis), ([units.index(a["unit"]) for a in axis],
                             [len(keep) + i for i in range(len(axis))])), shape=(len(units), lift.shape[1]))
    A = sparse.vstack((product, one), format="csr")
    d = dict(names=np.r_[case.d["names"][keep], np.asarray([a["name"] for a in axis])],
             rhs=np.r_[case.d["rhs"], np.ones(len(units))],
             sense=np.r_[case.d["sense"], np.asarray(["="] * len(units))],
             lower=np.r_[case.d["lower"][keep], np.zeros(len(axis))],
             upper=np.r_[case.d["upper"][keep], np.ones(len(axis))],
             types=np.r_[case.d["types"][keep], np.asarray(["B"] * len(axis))],
             objective=np.r_[case.d["objective"][keep], np.zeros(len(axis))],
             constant=np.asarray(case.d["constant"]).copy(),
             row_names=np.r_[case.d["row_names"], np.asarray(["route_pool_one[" + u + "]" for u in units])])
    start = np.r_[point[keep], selections]
    if not np.array_equal(lift @ start, point) or not np.array_equal(one @ start, np.ones(len(units))):
        raise ValueError("UNCHANGED_RAW_START_NOT_RESTORED")
    original_modes = int(sum(str(name).startswith("charge_mode[") for name in case.d["names"]))
    retained_modes = int(sum(str(name).startswith("charge_mode[") for name in d["names"]))
    if original_modes != retained_modes or np.count_nonzero(d["types"] == "B") != original_modes + len(axis):
        raise ValueError("JOINT_ORIGINAL_CHARGE_MODE_AUTHORITY_DRIFT")
    proof = dict(PASS=True, restricted_to_FULL_inclusion=True, restricted_equals_FULL_not_claimed=True,
                 original_source_rows_semantically_preserved=case.A.shape[0],
                 original_source_RHS_Sense_objective_unmodified=True, static_cache_hit=cache_hit,
                 static_cache_key=list(cache_key), dynamic_links_and_start_reverified=True,
                 exact_dyadic_lambda_row_coefficients_checked=checked,
                 no_physical_nonroute_columns_removed=True, original_charge_modes_retained=retained_modes,
                 lambda_axis=axis, keep_columns=keep.tolist(), removed_route_columns=route.tolist(),
                 source_matrix_sha=matrix_sha(case.A), source_domain_sha=domain_sha(case.d),
                 compact_matrix_sha=matrix_sha(A), compact_domain_sha=domain_sha(d), lift_sha=matrix_sha(lift),
                 unchanged_raw_Start_restored=True, point_vector_sha256=vector_sha(point),
                 no_MOVE_forcing=True, restricted_ObjBound_is_Global_LB=False)
    return A, d, lift, start, proof


def _native_joint(case, budget, packet, folder, seconds, native0=False):
    """Native readback, real Optimize and literal inverse-mapped captures."""
    import gurobipy as gp
    A, d, lift, start, proof = packet
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    parent=budget
    while hasattr(parent,'parent'):parent=parent.parent
    if hasattr(parent,'worker_lock'):
        from .table_v_resources import admit_resources
        admit_resources(parent,phase='M_JOINT_PREBUILD')
    model = gp.Model(ENGINE_VERSION)
    captures, messages, errors = [], [], []
    result = dict(executed=False, Native_optimize_calls=0, Native_Runtime=0., native0=native0,
                  current_pool_ObjVal=None, restricted_ObjBound_is_Global_LB=False,
                  global_gap_certified=False)
    try:
        params = dict(APPROVED_JOINT_PARAMETERS, LogFile=str(folder / "NATIVE_GUROBI.log"))
        for key, value in params.items():
            setattr(model.Params, key, value)
        with measure(folder,'M_NATIVE_MODEL_READBACK'):
            x = model.addMVar(A.shape[1], lb=d["lower"], ub=d["upper"], vtype=d["types"], obj=d["objective"])
            x.VarName = d["names"].tolist()
            x.Start = start
            model.ObjCon = float(d["constant"])
            rows = model.addMConstr(A, x, d["sense"], d["rhs"])
            rows.ConstrName = d["row_names"].tolist()
            model.update()
            checks = dict(CSR_exact=matrix_sha(model.getA().tocsr()) == matrix_sha(A),
                          RHS_exact=np.array_equal(model.getAttr("RHS"), d["rhs"]),
                          Sense_exact=np.array_equal(model.getAttr("Sense"), d["sense"]),
                          bounds_exact=np.array_equal(x.LB, d["lower"]) and np.array_equal(x.UB, d["upper"]),
                          types_exact=np.array_equal(x.VType, d["types"]),
                          objective_exact=np.array_equal(x.Obj, d["objective"]) and model.ObjCon == float(d["constant"]),
                          Start_exact=np.array_equal(x.Start, start),
                          literal_inverse_Start_exact=np.array_equal(lift @ x.Start, lift @ start))
            if not all(checks.values()):
                raise ValueError("COMMON_M_NATIVE_READBACK_DRIFT")
            _write(folder / "NATIVE_READBACK.json", dict(PASS=True, checks=checks, Optimize_calls=0))
        def capture(values, objective, discovery):
            values = np.asarray(values, dtype=np.float64)
            K = len(proof["keep_columns"])
            if not np.isin(values[K:], (0., 1.)).all():
                errors.append("NONLITERAL_LAMBDA_CAPTURE_NOT_ADMITTED")
                return
            # Route selection is metadata, never another Raw packet array.
            captures.append(dict(point=np.asarray(lift @ values).ravel(), native_point=values,
                                 route_selection=values[K:].tolist(), ObjVal=float(objective), discovery=discovery))
        def callback(m, where):
            try:
                if where == gp.GRB.Callback.MESSAGE:
                    message = m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if "start" in message.lower():
                        messages.append(message.strip())
                elif where == gp.GRB.Callback.MIPSOL:
                    capture(m.cbGetSolution(x), m.cbGet(gp.GRB.Callback.MIPSOL_OBJ),
                            m.cbGet(gp.GRB.Callback.RUNTIME))
            except Exception as exc:
                errors.append(repr(exc))
                m.terminate()
        if not native0:
            effective = min(float(seconds), float(budget.remaining()))
            if not math.isfinite(effective) or effective <= 0:
                raise TimeoutError("INTEGRATION_SOLVE_BUDGET_EXHAUSTED")
            model.Params.TimeLimit = effective
            result.update(executed=True, Native_optimize_calls=1)
            budget.native_optimize(model, callback, component="UB", track="M_PR222_JOINT",
                                   label=folder.name, requested_seconds=effective)
            result.update(Native_Runtime=float(model.Runtime), native_status=int(model.Status),
                          SolCount=int(model.SolCount), TimeLimit=effective)
            if model.SolCount:
                result["current_pool_ObjVal"] = float(model.ObjVal)
                result["restricted_ObjBound_diagnostic"] = float(model.ObjBound)
                capture(x.X, model.ObjVal, model.Runtime)
        result.update(start_processing=dict(attribute_readback=True, Optimize_entered=not native0,
                      messages=messages, classification=_start_classification(messages, result, float(d["objective"] @ start + d["constant"]))),
                      callback_errors=errors, capture_count=len(captures))
        _write(folder / "NATIVE_CALL.json", result)
        return result, captures
    except Exception as exc:
        result["error"] = repr(exc)
        if result["executed"]:
            try:
                result["Native_Runtime"] = float(model.Runtime)
            except Exception:
                result["Native_Runtime"] = None
        for i,candidate in enumerate(captures):
            np.savez_compressed(folder/f'RECOVERABLE_CAPTURE_{i:03d}.npz',point=candidate['point'])
        result['recoverable_captures']=[file_record(folder/f'RECOVERABLE_CAPTURE_{i:03d}.npz') for i in range(len(captures))]
        _write(folder / "NATIVE_CALL.json", result)
        raise
    finally:
        model.dispose()


def _start_classification(messages, result, start_ub):
    if not result.get("executed"):
        return "ATTRIBUTE_READBACK_ONLY"
    text = "\n".join(messages).lower()
    if "violates constraint" in text or "infeasible" in text:
        return "REJECTED_REQUIRES_LOG_REVIEW"
    if "loaded user mip start" in text or "produced solution" in text:
        return "ACCEPTED_DURING_OPTIMIZE"
    if "did not produce a new incumbent" in text:
        objective = result.get("current_pool_ObjVal")
        return ("NO_NEW_INCUMBENT_EQUAL_OR_BETTER_PRESENT" if objective is not None and objective <= start_ub + 1e-8
                else "NO_NEW_INCUMBENT_CAUSE_NOT_ESTABLISHED")
    return "PROCESSING_NOT_ESTABLISHED_FROM_LOG"


def export_plan(case, point):
    """Full immutable physical MESS anchor from original names, for A2/Actual."""
    graph = PathGraph(case)
    original = case.lift(point)
    values = dict(zip(map(str, case.original_d['names']), map(float, original)))
    units, sites, H = sorted(graph.origins), list(case.graph[0]), graph.horizon
    paths = graph.paths(point)
    P, Q, mode, soc = {}, {}, {}, {}
    connected = {u: [None] * H for u in units}
    moves = []
    for unit in units:
        for k in paths[unit]:
            arc = graph.arcs[k]
            if arc[-1] is None:
                connected[unit][arc[1]] = arc[0]
            else:
                moves.append(dict(unit=unit, arc=k, source=arc[0], depart_slot=arc[1],
                    destination=arc[2], arrival_slot=arc[-1].arrive, connection_slot=arc[3],
                    energy_kWh=float(arc[-1].energy_kwh), route_id=arc[-1].route_id,
                    route_authority_sha256=arc[-1].authority_sha256))
        P[unit] = [sum(values.get(f"Pdis[{unit},{site},{t}]", 0.) -
                       values.get(f"Pch[{unit},{site},{t}]", 0.) for site in sites) for t in range(H)]
        Q[unit] = [sum(values.get(f"Q[{unit},{site},{t}]", 0.) for site in sites) for t in range(H)]
        mode[unit] = [values[f"charge_mode[{unit},{t}]"] for t in range(H)]
        soc[unit] = [values[f"SOC[{unit},{t}]"] for t in range(H+1)]
    site_P = {site: [sum(values.get(f"Pdis[{unit},{site},{t}]", 0.) -
                         values.get(f"Pch[{unit},{site},{t}]", 0.) for unit in units) for t in range(H)] for site in sites}
    site_Q = {site: [sum(values.get(f"Q[{unit},{site},{t}]", 0.) for unit in units) for t in range(H)] for site in sites}
    plan = dict(schema="V42_FULL_MESS_PHYSICAL_ANCHOR_V1", case_sha=case.case_sha,
                point_vector_sha256=vector_sha(point), original_point_vector_sha256=vector_sha(original),
                route_paths=paths, initial_sites=graph.origins, connection_site=connected, moves=moves,
                P_kW=P, Q_kvar=Q, Mode=mode, SOC_kWh=soc,
                site_P_kW=site_P, site_Q_kvar=site_Q, time_axis=list(range(H)),
                dt_seconds=case.graph[3].dt_hours * 3600.,
                P_sign="POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch",
                Q_sign="ORIGINAL_Q_VARIABLE_SIGN", all_physical_inputs_fixed=True,
                case_binding=binding(case), optimization_global_B3_proof=False)
    # Shared A/M coordinator consumes these complete physical aliases.
    plan.update(routes=paths, P_by_site=site_P, Q_by_site=site_Q, SOC=soc)
    payload = json.dumps(_json_value(plan), sort_keys=True, separators=(",", ":"), allow_nan=False)
    plan["sha256"] = sha256(payload.encode()).hexdigest()
    from .a_engine import digest
    plan["plan_sha"] = digest(plan)
    _write(Path(getattr(case,'mess_execution_folder',case.output/'COMMON_M_PR222')) / 'FULL_MESS_PHYSICAL_ANCHOR.json', plan)
    return plan


def optimize_mess(case, initial_point, incumbent_registry, budget):
    """Shared B2/M1/M2 core. Arm/stage only identify explicit fixed inputs.

    Case fields: output, strict_validator (optional), candidate_pools or
    candidate_generator(case,point,bank,budget), joint_solver (fixture only),
    plan_exporter, cold_initializer. The default cold initializer is the
    established common initializer, never the former U4 optimizer fallback.
    """
    began = perf_counter()
    budget = _BudgetAdapter(budget, getattr(case, "mess_stage_budget_seconds", 1800.))
    case = copy(case)
    case.output = Path(case.output).resolve()
    case.output.mkdir(parents=True, exist_ok=True)
    subdir=getattr(case,'mess_execution_subdir','COMMON_M_PR222')
    if subdir not in ('COMMON_M_PR222','COOPERATIVE_SEED/COMMON_M_PR222','COOPERATIVE_SEARCH/COMMON_M_PR222'):
        raise ValueError('OFFICIAL_MESS_EXECUTION_CHILD_REQUIRED')
    folder = case.output / subdir
    folder.mkdir(parents=True,exist_ok=False)
    case.mess_execution_folder=folder
    validator = getattr(case, "strict_validator", strict_full)
    key = binding(case)
    bank = IncumbentBank(case)
    admission_order = []
    certificate = _validate(case, initial_point, folder / "CALLER_INITIAL_POINT.npz", validator)
    admission_order.append(dict(source="CALLER_INITIAL_POINT", admitted=certificate is not None))
    if certificate is not None:
        bank.offer(initial_point, certificate)
    records = (json.loads(Path(incumbent_registry).read_text(encoding="utf-8-sig"))
               if isinstance(incumbent_registry, (str, Path)) else incumbent_registry)
    for point, certificate in admit_registry(case, records, folder, validator, key):
        bank.offer(point, certificate)
    cold_used = bank.best is None
    cold_invoked = cold_used and budget.remaining() > 0
    cold_history = []
    if cold_invoked:
        initializer = getattr(case, "cold_initializer", None)
        if initializer is None:
            from v42_common_mess.engine import _initialize
            from v42_common_mess.budget import StageBudget
            case.point = None
            point, certificate, cold_history = _initialize(case, StageBudget(budget), validator, None,
                                                          APPROVED_JOINT_PARAMETERS)
        else:
            point, certificate, cold_history = initializer(case, budget, validator)
        if point is not None:
            # Cold results are replayed here, regardless of producer certificate.
            certificate = _validate(case, point, folder / "COLD_INITIAL_POINT.npz", validator)
            if certificate is not None:
                bank.offer(point, certificate)
    admission_order.append(dict(source="COLD_INITIALIZER", invoked=cold_invoked,
                                admitted=cold_used and bank.best is not None))
    native, captures, pools, proof = None, [], None, None
    initial_ub = bank.fields()["BEST_GLOBAL_UB"]
    adaptive = dict(history=[],joint_calls=0,unique_pools=0,stop_reason='NO_FULL_SEED_OR_NATIVE_BUDGET')
    if bank.best is not None:
        from .m_adaptive import run
        native, adaptive = run(case, bank, budget, folder, validator)
    registry = bank.save(folder, key)
    feasible = bank.best is not None
    plan = None
    if feasible and getattr(case, "plan_exporter", None) is not None:
        plan = case.plan_exporter(case, bank.best[0])
    result = dict(engine_version=ENGINE_VERSION, PR222_source_sha=PR222_SHA,
                  arm=key["arm"], stage=getattr(case, "identity", {}).get("stage"), day=key["day"],
                  case_sha=case.case_sha, binding=key, PASS=feasible, feasible_accepted=feasible,
                  execution_completion=bool(native and native.get("executed") and not native.get("fixture_backend")
                                            and not native.get("error")),
                  FULL_validated=feasible, global_gap_certified=False, certified_Global_LB=None,
                  gap_status="NOT_CERTIFIED", global_B3_gap_claimed=False,
                  cold_initializer_used=cold_invoked, cold_history=cold_history,
                  historical_witness_supplied=bool(records), initial_verified_UB=initial_ub,
                  current_pool_ObjVal=None if native is None else native.get("current_pool_ObjVal"),
                  **bank.fields(), native_call=native, adaptive_search=adaptive, incumbent_registry=registry,
                  admission_order=admission_order, mess=plan,
                  P2_calls=0, AIDC_optimization_calls=0, LB_optimizer_calls=0,
                  solver_threads=1, wall_seconds=perf_counter() - began,
                  stage_solve_seconds=budget.used(), operational_stage_budget_seconds=1800.,
                  status="FULL_FEASIBLE" if feasible else "NO_FEASIBLE_WITHIN_BUDGET",
                  cold_start_performance="NOT_ESTABLISHED" if cold_used else "NOT_TESTED_WARM_REGRESSION",
                  full_beam_scoring_connection=bool(getattr(case, "candidate_generator", None)))
    _write(folder / "M_STAGE_RESULT.json", result)
    return result, None if not feasible else bank.best[0].copy()
