"""Persistent column append prototype. No old basis import or reuse policy."""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math
import time

from .contracts import canonical, digest


@dataclass(frozen=True)
class RMPRows:
    names: tuple
    rhs: tuple
    senses: tuple
    objective_constant: float = 0.

    def __post_init__(self):
        for key in ('names', 'rhs', 'senses'):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        if not len(self.names) == len(self.rhs) == len(self.senses):
            raise ValueError('Row axis mismatch')
        if len(set(self.names)) != len(self.names) or any(s not in ('<', '=', '>') for s in self.senses):
            raise ValueError('Invalid row identity')
        if not all(math.isfinite(v) for v in (*self.rhs, self.objective_constant)):
            raise ValueError('Nonfinite row authority')


@dataclass(frozen=True)
class RMPColumn:
    name: str
    coefficients: tuple
    objective: float
    lower: float = 0.
    upper: float = 1e100

    def __post_init__(self):
        object.__setattr__(self, 'coefficients', tuple(float(v) for v in self.coefficients))
        if not all(math.isfinite(v) for v in (*self.coefficients, self.objective, self.lower, self.upper)):
            raise ValueError('Nonfinite column authority')
        if self.lower > self.upper:
            raise ValueError('Invalid bounds')


class PersistentRMP:
    """Retain only model construction; reset solution state before EVERY optimize.

    LPWarmStart=0 and Model.reset(0) deliberately disable old basis/start reuse.
    No VBasis/CBasis is read, written, exported, imported, or selected here.
    The registry remains authoritative and reconstructs the model after restart.
    """
    def __init__(self, rows, columns=(), time_limit=5., environment=None):
        import gurobipy as gp
        if not 0 < time_limit <= 30:
            raise ValueError('Lane C fixture cap must be <=30 seconds')
        self.rows = rows
        self.registry = []
        self.variables = []
        self.model = gp.Model('DW_RUNTIME_RMP', env=environment)
        for key, value in dict(OutputFlag=0, Threads=1, TimeLimit=time_limit, Method=1,
                               LPWarmStart=0, FeasibilityTol=1e-8, OptimalityTol=1e-8).items():
            self.model.setParam(key, value)
        self.model.ObjCon = rows.objective_constant
        self.constraints = [self.model.addLConstr(gp.LinExpr(), sense, rhs, name)
                            for name, sense, rhs in zip(rows.names, rows.senses, rows.rhs)]
        self.model.update()
        self.append(columns)

    def append(self, columns):
        import gurobipy as gp
        columns = tuple(columns)
        names = [c.name for c in self.registry] + [c.name for c in columns]
        if len(set(names)) != len(names) or any(len(c.coefficients) != len(self.constraints) for c in columns):
            raise ValueError('Column registry/row axis mismatch')
        started = time.perf_counter()
        for c in columns:
            pairs = [(v, row) for v, row in zip(c.coefficients, self.constraints) if v != 0]
            native = gp.Column([p[0] for p in pairs], [p[1] for p in pairs])
            self.variables.append(self.model.addVar(lb=c.lower, ub=c.upper, obj=c.objective,
                                                   name=c.name, column=native))
            self.registry.append(c)
        self.model.update()
        return time.perf_counter() - started

    def identity(self):
        self.model.update()
        matrix = self.model.getA().tocsr()
        return dict(row_count=self.model.NumConstrs, column_count=self.model.NumVars,
                    nnz=self.model.NumNZs, matrix=matrix.toarray().tolist(),
                    row_names=self.model.getAttr('ConstrName'), names=self.model.getAttr('VarName'),
                    rhs=self.model.getAttr('RHS'), senses=self.model.getAttr('Sense'),
                    bounds=[(lo if math.isfinite(lo) else '-INF', hi if math.isfinite(hi) else 'INF')
                            for lo, hi in zip(self.model.getAttr('LB'), self.model.getAttr('UB'))],
                    objective_coefficients=self.model.getAttr('Obj'), objective_constant=self.model.ObjCon,
                    model_sense=self.model.ModelSense, types=self.model.getAttr('VType'))

    def solve(self):
        self.model.reset(0)
        start = time.perf_counter()
        self.model.optimize()
        elapsed = time.perf_counter() - start
        if self.model.Status != 2:
            raise RuntimeError('Toy RMP did not reach OPTIMAL: ' + str(self.model.Status))
        return dict(status=int(self.model.Status), objective=float(self.model.ObjVal),
                    solution=self.model.getAttr('X'), duals=self.model.getAttr('Pi'),
                    optimize_seconds=elapsed, native_runtime_seconds=float(self.model.Runtime),
                    warm_basis_selected=False, LPWarmStart=0,
                    solution_state_reset=True, native_internal_state_policy='reset(0) before every solve')

    def checkpoint(self, path):
        data = dict(schema_version=1, rows=asdict(self.rows), columns=[asdict(c) for c in self.registry])
        wrapper = dict(registry=data, registry_SHA=digest(data))
        p = Path(path)
        temp = p.with_suffix(p.suffix + '.tmp')
        temp.write_text(canonical(wrapper) + '\n', encoding='utf8', newline='\n')
        temp.replace(p)

    @classmethod
    def restart(cls, path, **kwargs):
        wrapper = json.loads(Path(path).read_text(encoding='utf8'))
        data = wrapper['registry']
        if wrapper['registry_SHA'] != digest(data) or data['schema_version'] != 1:
            raise ValueError('Checkpoint registry SHA mismatch')
        return cls(RMPRows(**data['rows']), [RMPColumn(**c) for c in data['columns']], **kwargs)

    def close(self):
        self.model.dispose()


def build_rmp(rows, columns, flags, persistent=None, **kwargs):
    """Default path rebuilds; opt-in path requires append-only exact-prefix registry."""
    columns = tuple(columns)
    if not flags.DW_PERSISTENT_RMP or persistent is None:
        return PersistentRMP(rows, columns, **kwargs)
    if rows != persistent.rows or columns[:len(persistent.registry)] != tuple(persistent.registry):
        raise ValueError('Persistent RMP authority changed: reconstruct from disk')
    persistent.append(columns[len(persistent.registry):])
    return persistent
