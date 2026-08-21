#!/usr/bin/env python3
"""Exact radial-grid condensation utilities for Conversation A R25D / A4.

This module is deliberately solver-agnostic.  It proves/constructs two exact
projections used by the BUILD7C planning model:

1) static-subtree condensation: any feeder subtree containing no possible
   decision-dependent IDC/MESS injection has decision-independent branch flow,
   so its FP/FQ variables, balance rows, and line-circle QCP rows can be
   replaced by constants plus fail-closed constant thermal checks;
2) voltage-state projection: retain dU only on decision-skeleton LINE nodes.
   Fixed-ratio transformer dU states and all static-subtree dU states are affine
   functions of one retained ancestor dU (or the anchored root constant), so
   their voltage limits are propagated exactly into retained-variable bounds.

No topology, hard limit, objective, or Fresh Exact OpenDSS certificate is
changed by these transformations.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, MutableMapping, Sequence, Tuple, Any
import math

LINE = "LINE"
TX = "TRANSFORMER_FIXED_RATIO"

@dataclass(frozen=True)
class ProjectionTopology:
    nodes: tuple[str, ...]
    root: str
    parent: Mapping[str, str]
    children: Mapping[str, tuple[str, ...]]
    edge_kind: Mapping[str, str]
    depth: Mapping[str, int]
    decision_nodes: frozenset[str]
    skeleton: frozenset[str]
    static_nodes: frozenset[str]
    static_roots: tuple[str, ...]
    skeleton_line_nodes: tuple[str, ...]
    skeleton_transformer_nodes: tuple[str, ...]
    static_line_nodes: tuple[str, ...]
    static_transformer_nodes: tuple[str, ...]
    retained_voltage_nodes: tuple[str, ...]

    def audit(self) -> dict[str, Any]:
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.nodes) - 1,
            "decision_injection_node_count": len(self.decision_nodes),
            "decision_skeleton_node_count": len(self.skeleton),
            "static_node_count": len(self.static_nodes),
            "static_root_count": len(self.static_roots),
            "skeleton_line_node_count": len(self.skeleton_line_nodes),
            "skeleton_transformer_node_count": len(self.skeleton_transformer_nodes),
            "static_line_node_count": len(self.static_line_nodes),
            "static_transformer_node_count": len(self.static_transformer_nodes),
            "retained_voltage_variable_nodes_per_h": len(self.retained_voltage_nodes),
            "root_voltage_is_constant": True,
        }


def _children_from_parent(nodes: Sequence[str], root: str, parent: Mapping[str, str]) -> Dict[str, tuple[str, ...]]:
    ch: MutableMapping[str, list[str]] = defaultdict(list)
    for n in nodes:
        if n == root:
            continue
        if n not in parent:
            raise ValueError(f"missing parent for nonroot node {n}")
        ch[parent[n]].append(n)
    return {n: tuple(ch.get(n, ())) for n in nodes}


def _depths(nodes: Sequence[str], root: str, parent: Mapping[str, str]) -> Dict[str, int]:
    d = {root: 0}
    pending = set(nodes) - {root}
    while pending:
        progressed = False
        for n in tuple(pending):
            p = parent.get(n)
            if p in d:
                d[n] = d[p] + 1
                pending.remove(n)
                progressed = True
        if not progressed:
            raise ValueError(f"topology is not a rooted tree; unresolved={sorted(pending)[:8]}")
    return d


def build_projection_topology(
    nodes: Sequence[str],
    root: str,
    parent: Mapping[str, str],
    edge_kind: Mapping[str, str],
    decision_nodes: Iterable[str],
) -> ProjectionTopology:
    nodes = tuple(str(x).lower() for x in nodes)
    root = str(root).lower()
    node_set = set(nodes)
    if root not in node_set:
        raise ValueError("root absent from node axis")
    par = {str(k).lower(): str(v).lower() for k, v in parent.items()}
    ek = {str(k).lower(): str(v) for k, v in edge_kind.items()}
    dec = frozenset(str(x).lower() for x in decision_nodes)
    if not dec <= node_set:
        raise ValueError(f"decision nodes absent from topology: {sorted(dec-node_set)}")
    children = _children_from_parent(nodes, root, par)
    depth = _depths(nodes, root, par)
    for n in nodes:
        if n == root:
            continue
        if ek.get(n) not in {LINE, TX}:
            raise ValueError(f"unsupported edge kind for {n}: {ek.get(n)!r}")

    skeleton = {root}
    for q in dec:
        n = q
        while True:
            skeleton.add(n)
            if n == root:
                break
            n = par[n]
    skeleton = frozenset(skeleton)
    static_nodes = frozenset(node_set - skeleton)
    static_roots = tuple(sorted((n for n in static_nodes if par[n] in skeleton), key=lambda n: (depth[n], n)))

    # Fail closed if any static node can reach a decision node; by construction this
    # must be impossible, but this explicit test protects future topology changes.
    for n in static_nodes:
        stack = [n]
        while stack:
            u = stack.pop()
            if u in dec:
                raise ValueError(f"static subtree contains decision injection node {u}")
            stack.extend(children[u])

    sk_line = tuple(sorted((n for n in skeleton if n != root and ek[n] == LINE), key=lambda n: (depth[n], n)))
    sk_tx = tuple(sorted((n for n in skeleton if n != root and ek[n] == TX), key=lambda n: (depth[n], n)))
    st_line = tuple(sorted((n for n in static_nodes if ek[n] == LINE), key=lambda n: (depth[n], n)))
    st_tx = tuple(sorted((n for n in static_nodes if ek[n] == TX), key=lambda n: (depth[n], n)))

    # Root dU is an anchored constant.  Only decision-skeleton LINE nodes need a
    # voltage decision variable; transformer and static-subtree dU states project.
    retained = sk_line
    return ProjectionTopology(
        nodes=nodes,
        root=root,
        parent=par,
        children=children,
        edge_kind=ek,
        depth=depth,
        decision_nodes=dec,
        skeleton=skeleton,
        static_nodes=static_nodes,
        static_roots=static_roots,
        skeleton_line_nodes=sk_line,
        skeleton_transformer_nodes=sk_tx,
        static_line_nodes=st_line,
        static_transformer_nodes=st_tx,
        retained_voltage_nodes=retained,
    )


def condense_static_subtree_flows(
    topo: ProjectionTopology,
    own_p_static: Mapping[str, float],
    own_q_static: Mapping[str, float],
) -> tuple[Dict[str, float], Dict[str, float]]:
    """Return exact branch FP/FQ constants for every static node.

    `own_*_static` may contain all nodes; entries outside the static set are ignored.
    """
    fp = {n: float(own_p_static.get(n, 0.0)) for n in topo.static_nodes}
    fq = {n: float(own_q_static.get(n, 0.0)) for n in topo.static_nodes}
    for n in sorted(topo.static_nodes, key=lambda u: topo.depth[u], reverse=True):
        p = topo.parent[n]
        if p in topo.static_nodes:
            fp[p] += fp[n]
            fq[p] += fq[n]
    return fp, fq


def skeleton_balance_child_terms(
    topo: ProjectionTopology,
    node: str,
    static_fp: Mapping[str, float],
    static_fq: Mapping[str, float],
) -> tuple[tuple[str, ...], float, float]:
    """Return skeleton children and exact constant static-child contributions."""
    dyn = []
    cp = cq = 0.0
    for c in topo.children[node]:
        if c in topo.skeleton:
            dyn.append(c)
        else:
            # A direct static child is necessarily a static-subtree root.
            cp += float(static_fp[c])
            cq += float(static_fq[c])
    return tuple(dyn), cp, cq


def build_voltage_affine_map(
    topo: ProjectionTopology,
    edge_r_ohm: Mapping[str, float],
    edge_x_ohm: Mapping[str, float],
    ratio2: Mapping[str, float],
    static_fp: Mapping[str, float],
    static_fq: Mapping[str, float],
    ref_fp: Mapping[str, float],
    ref_fq: Mapping[str, float],
) -> Dict[str, tuple[str | None, float, float]]:
    """Map every node dU to anchor/scale/offset.

    For retained LINE node n: dU_n = 1*dU_n + 0.
    For the root: dU_root = 0.
    For projected nodes: dU_n = scale*dU_anchor + offset.

    Static LINE offsets use their exact decision-independent branch FP/FQ.
    """
    amap: Dict[str, tuple[str | None, float, float]] = {topo.root: (None, 0.0, 0.0)}
    for n in sorted((u for u in topo.nodes if u != topo.root), key=lambda u: topo.depth[u]):
        if n in topo.retained_voltage_nodes:
            amap[n] = (n, 1.0, 0.0)
            continue
        p = topo.parent[n]
        if p not in amap:
            raise ValueError(f"parent voltage map missing for {n}")
        a, s, b = amap[p]
        k = topo.edge_kind[n]
        if k == TX:
            rr = float(ratio2[n])
            if not math.isfinite(rr) or rr <= 0.0:
                raise ValueError(f"invalid fixed-ratio coefficient for {n}: {rr}")
            amap[n] = (a, rr * s, rr * b)
        elif k == LINE:
            if n not in topo.static_nodes:
                raise ValueError(f"non-retained decision-skeleton LINE unexpectedly projected: {n}")
            drop = 0.002 * (
                float(edge_r_ohm[n]) * (float(static_fp[n]) - float(ref_fp[n]))
                + float(edge_x_ohm[n]) * (float(static_fq[n]) - float(ref_fq[n]))
            )
            amap[n] = (a, s, b - drop)
        else:
            raise ValueError(f"unsupported edge kind {k}")
    return amap


def propagate_projected_voltage_bounds(
    topo: ProjectionTopology,
    affine_map: Mapping[str, tuple[str | None, float, float]],
    voltage_dev_bounds: Mapping[str, tuple[float, float]],
    tol: float = 1e-10,
) -> tuple[Dict[str, tuple[float, float]], list[dict[str, Any]]]:
    """Exactly propagate all node voltage limits to retained dU variable bounds.

    Each eliminated voltage state is affine in one retained anchor.  Because all
    fixed transformer ratio^2 coefficients are positive, its two-sided hard limit
    is exactly another interval on the anchor.  Intersecting all such intervals
    therefore introduces no relaxation or restriction beyond the original limits.
    """
    out = {n: (-math.inf, math.inf) for n in topo.retained_voltage_nodes}
    checks: list[dict[str, Any]] = []
    for n in topo.nodes:
        if n not in voltage_dev_bounds:
            raise ValueError(f"missing voltage-deviation bound for {n}")
        lo, hi = map(float, voltage_dev_bounds[n])
        if lo > hi:
            raise ValueError(f"invalid voltage bounds for {n}: {lo}>{hi}")
        a, s, b = affine_map[n]
        if a is None:
            ok = (b >= lo - tol and b <= hi + tol)
            checks.append({"node": n, "anchor": None, "constant_deviation": b, "lb": lo, "ub": hi, "pass": ok})
            if not ok:
                raise ValueError(f"projected constant voltage violates hard bound at {n}: {b} not in [{lo},{hi}]")
            continue
        if not math.isfinite(s) or s <= 0.0:
            raise ValueError(f"nonpositive affine voltage scale at {n}: {s}")
        ilb = (lo - b) / s
        iub = (hi - b) / s
        oldlo, oldhi = out[a]
        nlo, nhi = max(oldlo, ilb), min(oldhi, iub)
        if nlo > nhi + tol:
            raise ValueError(f"projected voltage-bound intersection empty for anchor {a} because of node {n}")
        out[a] = (nlo, nhi)
        checks.append({"node": n, "anchor": a, "scale": s, "offset": b, "implied_anchor_lb": ilb, "implied_anchor_ub": iub, "intersection_lb": nlo, "intersection_ub": nhi, "pass": True})
    return out, checks


def static_line_thermal_checks(
    topo: ProjectionTopology,
    static_fp: Mapping[str, float],
    static_fq: Mapping[str, float],
    line_limit: Mapping[tuple[str, str], float],
    tol: float = 1e-9,
) -> list[dict[str, Any]]:
    rows = []
    for n in topo.static_line_nodes:
        p = topo.parent[n]
        if (p, n) not in line_limit:
            raise ValueError(f"missing thermal limit for static LINE {p}->{n}")
        lim = float(line_limit[(p, n)])
        fp, fq = float(static_fp[n]), float(static_fq[n])
        ratio = math.hypot(fp, fq) / lim if lim > 0 else math.inf
        ok = fp * fp + fq * fq <= lim * lim + tol * max(1.0, lim * lim)
        rows.append({"parent": p, "child": n, "FP_kW": fp, "FQ_kvar": fq, "limit_kVA": lim, "loading_ratio": ratio, "pass": ok})
        if not ok:
            raise ValueError(f"decision-independent static line thermal violation {p}->{n}: ratio={ratio}")
    return rows


def structural_reduction_counts(topo: ProjectionTopology, horizon: int) -> dict[str, int]:
    H = int(horizon)
    if H <= 0:
        raise ValueError("horizon must be positive")
    static = len(topo.static_nodes)
    static_line = len(topo.static_line_nodes)
    # R24 had FP/FQ on every nonroot node and dU on every node (root fixed by bounds).
    # A4 retains FP/FQ only on the decision skeleton, and dU only on skeleton LINE nodes.
    flow_vars_removed = 2 * static * H
    flow_balance_rows_removed = 2 * static * H
    voltage_vars_removed = (len(topo.nodes) - len(topo.retained_voltage_nodes)) * H
    # R24 has one voltage recursion equality for every nonroot node.
    voltage_rows_removed = ((len(topo.nodes) - 1) - len(topo.skeleton_line_nodes)) * H
    line_qcp_removed = static_line * H
    return {
        "FP_FQ_continuous_variables_removed": flow_vars_removed,
        "P_Q_balance_equalities_removed": flow_balance_rows_removed,
        "dU_continuous_variables_removed": voltage_vars_removed,
        "voltage_recursion_equalities_removed": voltage_rows_removed,
        "line_circle_QCP_constraints_removed_by_constant_precheck": line_qcp_removed,
        "total_continuous_variables_removed_structural": flow_vars_removed + voltage_vars_removed,
        "total_linear_equalities_removed_structural": flow_balance_rows_removed + voltage_rows_removed,
    }
