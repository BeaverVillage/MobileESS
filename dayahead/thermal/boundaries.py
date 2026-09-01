"""NLR facility/cooling meter hierarchy and conservation audits."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_power_boundary(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Build non-overlapping facility, cooling-system, and other power [kW].

    NLR documentation states that ``cooling_kw``, ``hvac_kw``, ``pump_kw``,
    and ``plug_and_light_kw`` are mutually exclusive facility components. The
    reported PUE conservation identity is verified before using this boundary.
    """
    out = frame.copy()
    out["cooling_system_kw"] = out["cooling_kw"] + out["hvac_kw"] + out["pump_kw"]
    out["other_kw"] = out["plug_and_light_kw"]
    out["component_overhead_kw"] = out["cooling_system_kw"] + out["other_kw"]
    out["overhead_kw"] = out["component_overhead_kw"]
    out["facility_kw"] = out["it_power_kw"] + out["overhead_kw"]
    out["reported_pue_facility_kw"] = out["pue"] * out["it_power_kw"]
    residual = out["facility_kw"] - out["reported_pue_facility_kw"]
    # Source PUE is stored at 0.001 resolution. Its half-bin power uncertainty is
    # therefore 0.0005*P_IT; four component meters add a conservative 0.04 kW.
    tolerance_kw = 0.0005 * out["it_power_kw"] + 0.04
    pass_conservation = bool(np.all(np.abs(residual) <= tolerance_kw + 1e-12))
    boundary = {
        "artifact_id": "V24T_NLR_POWER_BOUNDARY_AUDIT",
        "classification": "BOUNDARY_B_NONOVERLAPPING_COMPONENT_SUM" if pass_conservation else "BOUNDARY_C_AMBIGUOUS_METER_HIERARCHY",
        "primary_target": "cooling_system_kw = cooling_kw + hvac_kw + pump_kw",
        "facility_target": "facility_kw = it_power_kw + exact non-overlapping component sum; reported pue*IT is an independently audited rounded check",
        "other_target": "other_kw = plug_and_light_kw",
        "meter_hierarchy": {
            "cooling_kw": "outdoor cooling fans, pipe trace heaters, dedicated tower filter pump",
            "hvac_kw": "fan walls, electrical-room fan coils, make-up air unit",
            "pump_kw": "energy-recovery/tower-water/boost pumps; excludes documented 2.67 kW tower filter attribution already in cooling_kw",
            "plug_and_light_kw": "lights, utility plugs, generator crank-case heater",
        },
        "non_overlapping_components": ["cooling_kw", "hvac_kw", "pump_kw", "plug_and_light_kw"],
        "double_count_count": 0,
        "pass": pass_conservation,
    }
    conservation = {
        "artifact_id": "V24T_NLR_POWER_CONSERVATION_AUDIT",
        "relation": "pue*it_power_kw approximately equals it_power_kw + cooling_kw + hvac_kw + pump_kw + plug_and_light_kw",
        "row_count": len(out),
        "max_abs_residual_kw": float(np.nanmax(np.abs(residual))),
        "mae_kw": float(np.nanmean(np.abs(residual))),
        "rmse_kw": float(np.sqrt(np.nanmean(residual**2))),
        "bias_kw": float(np.nanmean(residual)),
        "tolerance": "abs residual <= 0.0005*it_power_kw + 0.04 kW (reported PUE half-bin plus four 0.01-kW meters)",
        "within_tolerance_fraction": float(np.mean(np.abs(residual) <= tolerance_kw + 1e-12)),
        "pass": pass_conservation,
    }
    return out, boundary, conservation
