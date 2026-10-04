"""Solver-independent immutable decisions, column ownership and tree bookkeeping."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class BinaryProjection:
    family: str
    mess: int
    time: int
    site_or_arc: str
    terms: tuple  # (local original column index, coefficient)

    def __post_init__(self):
        object.__setattr__(self, 'terms', tuple((int(j), float(w)) for j, w in self.terms))
        if self.family not in ('location', 'movement', 'original_binary'):
            raise ValueError('UNSUPPORTED_BRANCH_FAMILY')
        if self.mess < 0 or self.time < 0 or not self.terms or len({j for j, _ in self.terms}) != len(self.terms):
            raise ValueError('INVALID_ORIGINAL_PROJECTION')
        if any(j < 0 or not math.isfinite(w) or w == 0 for j, w in self.terms):
            raise ValueError('INVALID_ORIGINAL_PROJECTION_TERMS')

    @property
    def order(self):
        return self.family, self.mess, self.time, self.site_or_arc, self.terms

    def value(self, x):
        return math.fsum(x[j] * w for j, w in self.terms)


@dataclass(frozen=True)
class BranchDecision:
    variable: BinaryProjection
    value: int

    def __post_init__(self):
        if type(self.value) is not int or self.value not in (0, 1):
            raise ValueError('BINARY_BRANCH_REQUIRED')

    def compatible(self, mess, x, tolerance=1e-8):
        return mess != self.variable.mess or abs(self.variable.value(x) - self.value) <= tolerance


def select_branch(projections, points, tolerance=1e-8):
    candidates = []
    for p in projections:
        value = p.value(points[p.mess])
        if not math.isfinite(value) or value < -tolerance or value > 1 + tolerance:
            raise ValueError('NON_BINARY_PROJECTION')
        if tolerance < value < 1 - tolerance:
            candidates.append((abs(value - .5), p.order, p))
    return min(candidates, key=lambda item: item[:2])[2] if candidates else None


@dataclass(frozen=True)
class TrajectoryColumn:
    column_id: str
    mess: int
    x: tuple
    a: tuple
    c: float
    sha: str


class ColumnRegistry:
    """Immutable column bytes; provenance is append-only and separate from identity."""

    def __init__(self):
        self._columns = {}
        self.provenance = {}

    @property
    def columns(self):
        return MappingProxyType(self._columns)

    def add(self, mess, x, a, c, node_id):
        from v42_dw_root.models import hash_column
        if mess < 0 or not all(math.isfinite(float(v)) for v in (*x, *a, c)):
            raise ValueError('INVALID_COLUMN')
        sha = hash_column(x, a, c)
        key = f'{mess}:{sha}'  # identical local vectors in different MESS remain distinct
        column = TrajectoryColumn(key, mess, tuple(map(float, x)), tuple(map(float, a)), float(c), sha)
        if key in self._columns and self._columns[key] != column:
            raise ValueError('COLUMN_HASH_COLLISION')
        self._columns.setdefault(key, column)
        history = self.provenance.setdefault(key, [])
        if node_id not in history:
            history.append(node_id)
        return key

    def partition(self, keys, decisions):
        active, inactive = [], []
        for key in keys:
            c = self._columns[key]
            target = active if all(d.compatible(c.mess, c.x) for d in decisions) else inactive
            target.append(key)
        return tuple(active), tuple(inactive)


FATHOM_REASONS = frozenset(('NODE_INFEASIBLE', 'BOUND_DOMINATED', 'INTEGER_PROJECTED_SOLUTION',
                           'PROVEN_NO_IMPROVING_PRICING_AND_INTEGRAL', 'EXPLICIT_FIXTURE_TERMINATION'))


@dataclass
class Node:
    node_id: int
    parent_id: int | None
    depth: int
    decisions: tuple = ()
    inherited_column_ids: tuple = ()
    inactive_column_ids: tuple = ()
    column_ids: tuple = ()
    lower_bound: float | None = None
    rmp_objective: float | None = None
    pricing_status: str = 'NOT_RUN'
    incumbent_association: int | None = None
    fathom_reason: str | None = None
    creation_order: int = 0
    checkpoint_sha: str | None = None
    bound_certificate: dict | None = None
    terminal_certificate: dict | None = None


@dataclass
class NodeResult:
    status: str
    column_ids: tuple = ()
    rmp_objective: float | None = None
    certified_lower_bound: float | None = None
    pricing_closed: bool = False
    points: tuple | None = None
    global_point: tuple | None = None
    infeasibility_proven: bool = False
    certificate: dict = field(default_factory=dict)


class Tree:
    def __init__(self, registry, root_columns=(), tolerance=1e-7):
        self.registry = registry
        self.nodes = {0: Node(0, None, 0, inherited_column_ids=tuple(root_columns), column_ids=tuple(root_columns))}
        self.open_ids = [0]
        self.completed_ids = []
        self.next_id = 1
        self.incumbent = None
        self.tolerance = tolerance

    def ordered_queue(self):
        return sorted(self.open_ids, key=lambda i: (self.nodes[i].lower_bound if self.nodes[i].lower_bound is not None
                                                  else -math.inf, self.nodes[i].depth, i))

    @property
    def global_lb(self):
        if any(n.fathom_reason == 'EXPLICIT_FIXTURE_TERMINATION' for n in self.nodes.values()):
            return None  # an explicitly discarded subtree has no proof coverage
        if not self.open_ids:
            if self.incumbent is None:
                return None
            # Closed leaves may have been fathomed within tolerance. Preserve
            # their certified floors rather than overstating exact zero gap.
            floors = [self.nodes[i].lower_bound for i in self.completed_ids
                      if self.nodes[i].fathom_reason not in (None, 'NODE_INFEASIBLE')]
            if any(v is None for v in floors):
                return None
            return min([self.incumbent['objective'], *floors])
        bounds = [self.nodes[i].lower_bound for i in self.open_ids]
        return None if any(v is None for v in bounds) else min(bounds)

    @property
    def gap(self):
        lb = self.global_lb
        if self.incumbent is None or lb is None:
            return None
        ub = self.incumbent['objective']
        if lb > ub + self.tolerance:
            raise ValueError('BOUND_INTERVAL_CONTRADICTION')
        return max(0., ub - lb) / max(abs(ub), 1e-12)

    def accepted(self, threshold=.005):
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError('INVALID_GAP_THRESHOLD')
        return self.gap is not None and self.gap <= threshold

    def finish(self, node, reason):
        if reason not in FATHOM_REASONS:
            raise ValueError('INVALID_FATHOM_REASON')
        node.fathom_reason = reason
        self.open_ids.remove(node.node_id)
        self.completed_ids.append(node.node_id)

    def split(self, node, variable):
        children = []
        for bit in (0, 1):
            decisions = node.decisions + (BranchDecision(variable, bit),)
            active, inactive = self.registry.partition(node.column_ids, decisions)
            child = Node(self.next_id, node.node_id, node.depth + 1, decisions, active, inactive, active,
                         lower_bound=node.lower_bound, creation_order=self.next_id, bound_certificate=node.bound_certificate)
            self.next_id += 1
            self.nodes[child.node_id] = child
            self.open_ids.append(child.node_id)
            children.append(child)
        self.open_ids.remove(node.node_id)
        self.completed_ids.append(node.node_id)  # internal branch node; no fathom claim
        return children

    def step(self, solver, projections, independent_validator):
        if not self.open_ids:
            return 'FINISHED'
        node = self.nodes[self.ordered_queue()[0]]
        if self.incumbent is not None and node.lower_bound is not None and node.lower_bound >= self.incumbent['objective'] - self.tolerance:
            self.finish(node, 'BOUND_DOMINATED')
            return 'FATHOMED'
        result = solver(node, self.registry)
        for key in result.column_ids:
            if key not in self.registry.columns:
                raise ValueError('UNREGISTERED_NODE_COLUMN')
        active, inactive = self.registry.partition(result.column_ids, node.decisions)
        if inactive:
            raise ValueError('NODE_COLUMN_BRANCH_VIOLATION')
        node.column_ids = active
        node.rmp_objective = result.rmp_objective
        node.pricing_status = result.status
        if result.certified_lower_bound is not None:
            if not math.isfinite(result.certified_lower_bound) or not result.certificate.get('PASS'):
                raise ValueError('UNVERIFIED_LOWER_BOUND')
            if result.rmp_objective is not None and result.certified_lower_bound > result.rmp_objective + self.tolerance:
                raise ValueError('NODE_BOUND_INTERVAL_CONTRADICTION')
            if node.lower_bound is None or result.certified_lower_bound >= node.lower_bound:
                node.lower_bound = result.certified_lower_bound
                node.bound_certificate = dict(result.certificate)
        if result.infeasibility_proven:
            if result.status in ('TIME_LIMIT', 'INTERRUPTED') or not result.certificate.get('PASS'):
                raise ValueError('UNVERIFIED_INFEASIBILITY')
            node.terminal_certificate = dict(result.certificate)
            self.finish(node, 'NODE_INFEASIBLE')
            return 'FATHOMED'
        if result.points is None:
            return 'INCONCLUSIVE'
        variable = select_branch(projections, result.points)
        if variable is None:
            validation = independent_validator(result.points, result.global_point, node.decisions)
            if not validation.get('PASS') or result.rmp_objective is None:
                raise ValueError('INCUMBENT_INDEPENDENT_VALIDATION_FAILED')
            objective = validation['objective']
            if not math.isfinite(objective) or abs(objective - result.rmp_objective) > self.tolerance:
                raise ValueError('INCUMBENT_OBJECTIVE_MISMATCH')
            if self.incumbent is None or objective < self.incumbent['objective'] - self.tolerance:
                self.incumbent = dict(objective=objective, node_id=node.node_id, points=result.points,
                                      global_point=result.global_point, validation=validation)
            node.incumbent_association = self.incumbent['node_id']
            if result.pricing_closed and result.certificate.get('PASS') and node.lower_bound is not None and node.lower_bound >= objective - self.tolerance:
                reason = 'INTEGER_PROJECTED_SOLUTION' if result.certificate.get('integer_original_optimality_proven') else 'PROVEN_NO_IMPROVING_PRICING_AND_INTEGRAL'
                self.finish(node, reason)
                return 'FATHOMED'
            return 'INCONCLUSIVE'
        if not result.pricing_closed:
            return 'INCONCLUSIVE'
        if not result.certificate.get('PASS') or node.lower_bound is None:
            raise ValueError('UNVERIFIED_PRICING_CLOSURE')
        self.split(node, variable)
        return 'BRANCHED'

    def run(self, solver, projections, independent_validator, max_steps=100):
        for _ in range(max_steps):
            if not self.open_ids:
                return 'FINISHED'
            if self.step(solver, projections, independent_validator) == 'INCONCLUSIVE':
                return 'INCONCLUSIVE'
        return 'EXPLICIT_FIXTURE_STEP_LIMIT'  # leaves remain open; never a proof

    def save(self, path, scientific_sha, code_sha):
        nodes = []
        for i in sorted(self.nodes):
            n = self.nodes[i]
            record = asdict(n)
            record.pop('checkpoint_sha')
            n.checkpoint_sha = digest(record)
            nodes.append(dict(record, checkpoint_sha=n.checkpoint_sha))
        payload = dict(version=1, scientific_sha=scientific_sha, code_sha=code_sha, nodes=nodes,
                       registry=[asdict(c) for c in self.registry.columns.values()], provenance=self.registry.provenance,
                       queue=self.ordered_queue(), completed=self.completed_ids, next_id=self.next_id,
                       incumbent=self.incumbent, global_lb=self.global_lb, tolerance=self.tolerance)
        envelope = dict(payload=payload, sha=digest(payload))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical(envelope))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return envelope['sha']

    @classmethod
    def load(cls, path, scientific_sha, code_sha, column_validator, projections, independent_validator, bound_validator):
        envelope = json.loads(Path(path).read_text(encoding='utf8'))
        p = envelope['payload']
        if envelope['sha'] != digest(p) or p['version'] != 1 or p['scientific_sha'] != scientific_sha or p['code_sha'] != code_sha:
            raise ValueError('CHECKPOINT_IDENTITY_MISMATCH')
        registry = ColumnRegistry()
        for c in p['registry']:
            if not column_validator(c['mess'], c['x'], c['a'], c['c']):
                raise ValueError('CHECKPOINT_COLUMN_INVALID')
            key = registry.add(c['mess'], c['x'], c['a'], c['c'], -1)
            if key != c['column_id'] or registry.columns[key].sha != c['sha']:
                raise ValueError('CHECKPOINT_COLUMN_HASH_MISMATCH')
        if len(registry.columns) != len(p['registry']):
            raise ValueError('CHECKPOINT_DUPLICATE_COLUMN')
        registry.provenance = p['provenance']
        if set(registry.provenance) != set(registry.columns):
            raise ValueError('CHECKPOINT_PROVENANCE_MISMATCH')
        tree = cls(registry, tolerance=p['tolerance'])
        tree.nodes = {}
        allowed = set(projections)
        for record in p['nodes']:
            raw = dict(record)
            sha = raw.pop('checkpoint_sha')
            if sha != digest(raw):
                raise ValueError('CHECKPOINT_NODE_HASH_MISMATCH')
            decisions = tuple(BranchDecision(BinaryProjection(**d['variable']), d['value']) for d in raw['decisions'])
            if any(d.variable not in allowed for d in decisions):
                raise ValueError('CHECKPOINT_BRANCH_DOMAIN_MISMATCH')
            raw['decisions'] = decisions
            for key in ('inherited_column_ids', 'inactive_column_ids', 'column_ids'):
                raw[key] = tuple(raw[key])
                if any(k not in registry.columns for k in raw[key]):
                    raise ValueError('CHECKPOINT_MISSING_COLUMN')
            if registry.partition(raw['column_ids'], decisions)[1]:
                raise ValueError('CHECKPOINT_INCOMPATIBLE_COLUMN')
            node = Node(**raw, checkpoint_sha=sha)
            if any(v is not None and not math.isfinite(v) for v in (node.lower_bound, node.rmp_objective)) or node.fathom_reason not in FATHOM_REASONS | {None}:
                raise ValueError('CHECKPOINT_NODE_STATUS_INVALID')
            if node.node_id in tree.nodes:
                raise ValueError('CHECKPOINT_DUPLICATE_NODE')
            tree.nodes[node.node_id] = node
        tree.open_ids = p['queue']
        tree.completed_ids = p['completed']
        tree.next_id = p['next_id']
        tree.incumbent = p['incumbent']
        if len(set(tree.open_ids + tree.completed_ids)) != len(tree.open_ids + tree.completed_ids) or set(tree.open_ids + tree.completed_ids) != set(tree.nodes):
            raise ValueError('CHECKPOINT_QUEUE_PARTITION_MISMATCH')
        if tree.next_id != max(tree.nodes) + 1 or tree.open_ids != tree.ordered_queue() or p['global_lb'] != tree.global_lb:
            raise ValueError('CHECKPOINT_BOOKKEEPING_MISMATCH')
        for n in tree.nodes.values():
            if n.parent_id is not None:
                parent = tree.nodes.get(n.parent_id)
                if parent is None or n.depth != parent.depth + 1 or n.decisions[:-1] != parent.decisions:
                    raise ValueError('CHECKPOINT_TREE_MISMATCH')
                active, inactive = registry.partition(parent.column_ids, n.decisions)
                if set(n.inherited_column_ids) != set(active) or set(n.inactive_column_ids) != set(inactive):
                    raise ValueError('CHECKPOINT_INHERITANCE_MISMATCH')
                if parent.lower_bound is not None and (n.lower_bound is None or n.lower_bound < parent.lower_bound):
                    raise ValueError('CHECKPOINT_INHERITED_BOUND_MISMATCH')
            if n.node_id in tree.open_ids and n.fathom_reason is not None:
                raise ValueError('CHECKPOINT_OPEN_FATHOMED_NODE')
            if n.lower_bound is not None:
                certificate = n.bound_certificate or {}
                origin = tree.nodes.get(certificate.get('node_id'))
                ancestors, cursor = set(), n
                while cursor is not None and cursor.node_id not in ancestors:
                    ancestors.add(cursor.node_id)
                    cursor = tree.nodes.get(cursor.parent_id)
                if origin is None or origin.node_id not in ancestors or not bound_validator(n.lower_bound, certificate, origin.decisions):
                    raise ValueError('CHECKPOINT_BOUND_CERTIFICATE_INVALID')
            if n.fathom_reason == 'NODE_INFEASIBLE' and not (n.terminal_certificate or {}).get('PASS'):
                raise ValueError('CHECKPOINT_INFEASIBILITY_CERTIFICATE_MISSING')
            children = [c for c in tree.nodes.values() if c.parent_id == n.node_id]
            if children and (len(children) != 2 or children[0].decisions[-1].variable != children[1].decisions[-1].variable or
                             {c.decisions[-1].value for c in children} != {0, 1} or n.node_id in tree.open_ids or n.fathom_reason is not None):
                raise ValueError('CHECKPOINT_BRANCH_PARTITION_MISMATCH')
            if n.node_id in tree.completed_ids and not children and n.fathom_reason is None:
                raise ValueError('CHECKPOINT_UNEXPLAINED_COMPLETION')
        if any(any(i not in tree.nodes for i in origins) for origins in registry.provenance.values()):
            raise ValueError('CHECKPOINT_PROVENANCE_NODE_MISSING')
        if tree.incumbent is not None:
            incumbent = tree.incumbent
            node = tree.nodes.get(incumbent['node_id'])
            if node is None:
                raise ValueError('CHECKPOINT_INCUMBENT_NODE_MISSING')
            validation = independent_validator(incumbent['points'], incumbent['global_point'], node.decisions)
            if not validation.get('PASS') or abs(validation['objective'] - incumbent['objective']) > tree.tolerance:
                raise ValueError('CHECKPOINT_INCUMBENT_INVALID')
            incumbent['validation'] = validation
        return tree
