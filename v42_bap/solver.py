"""Bounded opt-in node CG with Phase I and one sequential native solver."""

from dataclasses import dataclass, field
from copy import copy
import os
from pathlib import Path
import tempfile
import time
import threading

import gurobipy as gp
import numpy as np

from .adapter import restrict_pricing, accept_column, node_bound
from .state import NodeResult, digest
from v42_dw_root.models import Master, build
from v42_dw_root.run import exact_rc
from v42_integrated.matrix import arrays, audit

_OPTIMIZE_LOCK = threading.Lock()


@dataclass
class ToyGuard:
    max_vars: int = 10000
    max_rows: int = 20000
    wall_seconds: float = 30.
    receipts: list = field(default_factory=list)

    def __post_init__(self):
        if not 0 < self.max_vars <= 10000 or not 0 < self.max_rows <= 20000 or not 0 < self.wall_seconds <= 30:
            raise ValueError('LANE_B_HARD_RESOURCE_LIMIT')

    def check(self, model):
        model.update()
        if model.NumVars > self.max_vars or model.NumConstrs > self.max_rows:
            raise RuntimeError('STOP_OVERSIZE_FIXTURE')

    def optimize(self, model, label):
        self.check(model)
        model.Params.Threads = 1
        model.Params.TimeLimit = min(25., self.wall_seconds)
        model.Params.OutputFlag = 0
        model.Params.LogToConsole = 0
        # Advisory Lane-B process lock, distinct from Lane A's resource gates.
        lock_path = Path(tempfile.gettempdir()) / 'MobileESS_LANE_B_TOY_SOLVER.lock'
        with _OPTIMIZE_LOCK, lock_path.open('a+b') as stream:
            stream.seek(0)
            stream.write(b'0')
            stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            start = time.perf_counter()
            try:
                model.optimize()
            finally:
                wall = time.perf_counter() - start
                self.receipts.append(dict(label=label, vars=model.NumVars, rows=model.NumConstrs,
                                          threads=1, concurrent_lane_b_solver_processes=1, wall_seconds=wall,
                                          status=model.Status, time_limit=model.Params.TimeLimit))
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
                if os.environ.get('BAP_TOY_RECEIPT_FILE'):
                    import json
                    with Path(os.environ['BAP_TOY_RECEIPT_FILE']).open('a', encoding='utf8') as receipt_file:
                        receipt_file.write(json.dumps(self.receipts[-1], allow_nan=False) + '\n')
            if wall > self.wall_seconds:
                raise RuntimeError('STOP_TOY_WALL_EXCEEDED')


class BoundedMaster(Master):
    """Existing D-W sparse transport/add interface, generalized unit count."""

    def __init__(self, problem, phase):
        self.A = problem.global_A
        self.d = dict(problem.global_d)
        if phase:
            self.d.update(objective=np.zeros_like(self.d['objective']), constant=np.array(0.))
        self.model = build(self.A, self.d, 'BAP_TOY_PHASE_I' if phase else 'BAP_TOY_RMP')
        self.z = self.model.getVars()
        self.coupling = self.model.getConstrs()
        self.conv = [self.model.addConstr(gp.LinExpr() == 1, name=f'BAP_convexity[{m}]') for m in range(len(problem.blocks))]
        self.lambdas, self.column_data, self.artificials = [], [], []
        self.phase = phase
        if phase:
            for row, sense in zip(self.coupling + self.conv, list(self.d['sense']) + ['='] * len(self.conv)):
                for sign in ([1., -1.] if sense == '=' else [-1.] if sense == '<' else [1.]):
                    self.artificials.append(self.model.addVar(lb=0, obj=1., column=gp.Column([sign], [row]), name='BAP_phase_I_slack'))
        self.model.update()

    def add(self, m, x, a, c, key):
        super().add(m, x, a, 0. if self.phase else c, key)

    def checked(self):
        A, d = arrays(self.model)
        point = np.asarray(self.model.getAttr('X'))
        return audit(A, d, point, tolerance=1e-8)['PASS'] and self.model.DualVio <= 1e-8

    def projection(self, count):
        points = []
        for m in range(count):
            columns = [(v.X, c['x']) for v, c in zip(self.lambdas, self.column_data) if c['unit'] == m]
            if not columns:
                raise ValueError('MISSING_CONVEXITY_BLOCK')
            points.append(tuple(sum((weight * x for weight, x in columns), np.zeros_like(columns[0][1]))))
        return tuple(points), tuple(float(v.X) for v in self.z)


class NodeCG:
    """Original full local domain + exact branch rows; restricted feasibility
    uses Phase I. RMP infeasibility alone is NEVER a node-infeasibility proof.
    There is intentionally no production launch path in this lane.
    """

    def __init__(self, problem, guard, max_iterations=100):
        self.problem, self.guard, self.max_iterations = problem, guard, max_iterations
        self.pricing_audits = []

    def __call__(self, node, registry):
        active, _ = registry.partition(node.column_ids, node.decisions)
        keys = list(active)
        # No scientific inputs are loaded here. Limits are checked before copy.
        proxies = []
        try:
            for m, b in enumerate(self.problem.blocks):
                proxies.append(restrict_pricing(b, m, node.decisions, self.guard))
            for phase in (True, False):
                for iteration in range(self.max_iterations):
                    master = BoundedMaster(self.problem, phase)
                    try:
                        for key in keys:
                            c = registry.columns[key]
                            master.add(c.mess, np.asarray(c.x), np.asarray(c.a), c.c, key)
                        self.guard.optimize(master.model, f'node{node.node_id}/phase{int(phase)}/rmp{iteration}')
                        if master.model.Status != gp.GRB.OPTIMAL or not master.checked():
                            return NodeResult('RMP_INCONCLUSIVE', tuple(keys))
                        pi = np.asarray([r.Pi for r in master.coupling])
                        alpha = np.asarray([r.Pi for r in master.conv])
                        dual_sha = digest(dict(pi=pi.tolist(), alpha=alpha.tolist(), node=node.node_id, phase=phase))
                        bounds, added = [], False
                        for m, proxy in enumerate(proxies):
                            proxy.d = dict(self.problem.blocks[m].d)
                            if phase:
                                proxy.d['objective'] = np.zeros_like(proxy.d['objective'])
                            proxy.price(pi, alpha[m])  # existing verified convention
                            self.guard.optimize(proxy.model, f'node{node.node_id}/phase{int(phase)}/price{iteration}/{m}')
                            if proxy.model.Status == gp.GRB.INFEASIBLE:
                                return NodeResult('FULL_LOCAL_DOMAIN_INFEASIBLE', tuple(keys), infeasibility_proven=True,
                                                  certificate=dict(PASS=True, exact_branch_local_infeasibility=True, dual_sha=dual_sha))
                            valid_bound = proxy.model.Status in (gp.GRB.OPTIMAL, gp.GRB.TIME_LIMIT, gp.GRB.INTERRUPTED) and np.isfinite(proxy.model.ObjBound) and abs(proxy.model.ObjBound) < 1e90
                            bounds.append(float(proxy.model.ObjBound) if valid_bound else None)
                            if proxy.model.SolCount:
                                x = np.asarray(proxy.model.getAttr('X'))
                                # Original binaries must be exact, no rounding/repair.
                                key, rc = accept_column(self.problem.blocks[m], m, proxy, x, node.decisions, pi, alpha[m],
                                                        proxy.model.ObjVal, registry, node.node_id)
                                exhaustive = self.problem.pricing_min(m, node.decisions, proxy.d['objective'] - proxy.B.T @ pi, alpha[m])
                                if proxy.model.Status == gp.GRB.OPTIMAL and abs(rc - exhaustive) > 1e-8:
                                    raise ValueError('NATIVE_PRICING_ENUMERATION_MISMATCH')
                                self.pricing_audits.append(dict(node=node.node_id, mess=m, phase=phase, dual_sha=dual_sha,
                                                               rc=rc, exhaustive_min=exhaustive, PASS=True))
                                if rc < -1e-8 and key not in keys:
                                    keys.append(key)
                                    added = True
                        lb, proof = None, {}
                        if all(v is not None for v in bounds):
                            lb, proof = node_bound(master.A, master.d, pi, alpha, bounds)
                            proof.update(dual_sha=dual_sha, node_id=node.node_id, phase=phase, pi=pi.tolist(), alpha=alpha.tolist(), pricing_bounds=bounds)
                        if phase and master.model.ObjVal <= 1e-8:
                            break  # feasible original RMP; begin objective pricing
                        if phase and lb is not None and lb > 1e-8:
                            return NodeResult('PHASE_I_PROVEN_INFEASIBLE', tuple(keys), infeasibility_proven=True, certificate=proof)
                        closed = all(v is not None and v >= -1e-8 for v in bounds)
                        if not phase and not added:
                            points, global_point = master.projection(len(proxies))
                            return NodeResult('PRICING_CLOSED' if closed else 'PRICING_INCONCLUSIVE', tuple(keys), master.model.ObjVal,
                                              lb, closed, points, global_point, certificate=proof)
                        if not added:
                            return NodeResult('PHASE_I_INCONCLUSIVE', tuple(keys))
                    finally:
                        master.model.dispose()
                else:
                    return NodeResult('CG_ITERATION_LIMIT', tuple(keys))
            return NodeResult('CG_INCONCLUSIVE', tuple(keys))
        finally:
            for proxy in proxies:
                proxy.model.dispose()
