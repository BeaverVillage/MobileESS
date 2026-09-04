"""Isolated OpenDSS adapter that prepares frozen V16.3 coefficient NPZ files."""

from __future__ import annotations

from pathlib import Path

from dayahead.v28r2.electrical_context import ElectricalContext, _context_base
from dayahead.v28r2.formulation import V28R2FormulationData


def prepare_electrical_context(
    repo: Path, data: V28R2FormulationData, cache: Path,
) -> ElectricalContext:
    """Generate coefficient files, then reopen them through the solver loader."""

    # These frozen physical adapters are intentionally unreachable from the
    # solver modules.  They receive the already materialized V28R2 C1 plan.
    from dayahead.run_v16_3_correction import _generate_current_day
    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day

    source, legacy, voltage_path, _current_path = _context_base(repo, data, cache)
    reference, _vintage, background, binding, _path, _authority = legacy
    plan = tuple(tuple(map(float, row)) for row in reference["plan_kw_96x12"])
    _anchor_and_sensitivity_day(
        repo, source, background, plan, binding, data.day, voltage_path,
        build_sensitivity=True,
    )
    _generate_current_day(repo, source, cache, data.day, legacy)

    from dayahead.v28r2.electrical_context import build_electrical_context

    return build_electrical_context(repo, data, cache)
