"""Passive fill-in parsing shared by canaries, full stages and speed receipts."""
import re
from .telemetry import StressTelemetry


def fill_in_metrics(log):
    def match(pattern, convert=float):
        value = re.search(pattern, log, re.MULTILINE)
        if value is None:
            return None
        try:
            return convert(value.group(1).replace(',', ''))
        except ValueError:
            return None
    # Gurobi prints scientific notation for factor nnz and memory units.
    return dict(ordering_seconds=match(r'Ordering time:\s*([\d.]+)s'),
        factor_nnz=match(r'Factor NZ\s*:\s*([\deE+.,-]+)'),
        factor_memory_printed=match(r'Factor NZ[^\n]*\(roughly\s*([\d.]+)\s*(?:MB|GB)', float),
        factor_memory_unit=match(r'Factor NZ[^\n]*\(roughly\s*[\d.]+\s*(MB|GB)', str),
        factor_operations=match(r'Factor Ops\s*:\s*([\deE+.,-]+)'),
        barrier_iterations=match(r'Barrier solved model in\s*(\d+) iterations', int),
        barrier_seconds=match(r'Barrier solved model in\s*\d+ iterations and\s*([\d.]+) seconds'),
        crossover_seconds=match(r'Crossover time:\s*([\d.]+) seconds'),
        root_completed=True if ('Root relaxation: objective ' in log or 'Optimal objective ' in log) else None,
        inferred_missing_values=False)


class FastTelemetry(StressTelemetry):
    def receipt(self):
        result = super().receipt()
        result['fill_in'] = fill_in_metrics('\n'.join(self.messages))
        if self.passes:
            quality=self.passes[-1]['numerical_quality']
            result['fill_in']['native_barrier_iterations']=quality.get('BarIterCount')
            result['fill_in']['Work']=quality.get('Work')
        result['fill_in']['peak_RSS_bytes']=self.peak_rss
        return result
