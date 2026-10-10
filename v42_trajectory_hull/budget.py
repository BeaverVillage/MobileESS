"""One consumed research token and actual cumulative native accounting."""
from pathlib import Path
from time import perf_counter
import json
import math


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


class Budget:
    def __init__(self, output):
        self.output = Path(output).resolve()
        if self.output.drive.upper() != 'D:':
            raise ValueError('RESEARCH_D_DRIVE_REQUIRED')
        self.output.mkdir(parents=True, exist_ok=True)
        with (self.output/'ONCE.json').open('x', encoding='utf-8') as f:
            json.dump({'native_ceiling':600, 'threads':1, 'no_rerun':True}, f)
        self.calls = []
        self.build_seconds = 0.
        self.certificate_seconds = 0.

    @property
    def used(self):
        return sum(c['Runtime'] for c in self.calls)

    def optimize(self, model, label, limit):
        import gurobipy as gp
        seconds = min(float(limit), 600.-self.used)
        if not math.isfinite(seconds) or seconds <= .05:
            raise TimeoutError('RESEARCH_NATIVE_BUDGET_CONSUMED')
        model.Params.Threads = 1
        model.Params.TimeLimit = seconds
        model.Params.FeasibilityTol = 1e-8
        model.Params.OptimalityTol = 1e-8
        model.Params.IntFeasTol = 1e-8
        model.Params.OutputFlag = 1
        model.Params.LogToConsole = 0
        model.Params.LogFile = str(self.output/f'{len(self.calls):03d}_{label}.log')
        row = dict(label=label, TimeLimit=seconds, Threads=1, state='IN_FLIGHT')
        write(self.output/'LEDGER.json', dict(calls=self.calls, inflight=row,
                                            measured_native_seconds=self.used))
        begin = perf_counter()
        try:
            model.optimize()
        finally:
            runtime = float(model.Runtime)
            if not math.isfinite(runtime) or runtime < 0:
                raise RuntimeError('UNKNOWN_NATIVE_RUNTIME_QUARANTINE')
            row.update(Runtime=runtime, optimize_wall=perf_counter()-begin,
                       Status=int(model.Status), SolCount=int(model.SolCount),
                       IterCount=float(model.IterCount), state='FINISHED')
            self.calls.append(row)
            write(self.output/'LEDGER.json', dict(calls=self.calls, inflight=None,
                                                measured_native_seconds=self.used,
                                                allocated_native_ceiling=600,
                                                native_overshoot=max(0., self.used-600.)))
        return row
