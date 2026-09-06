"""Use inherited IEEE123 physical mapping with actual inputs; no AC restoration."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from dayahead.paper_analysis.storage import digest
from .contracts import ReplayError
from .physical_audit import engine_binding_observer, rho_recalculation


def replay(repo, day, case, context, power, exogenous, mess, identity, output):
    from dayahead.v28r2.electrical_context import source_root, with_realized_background
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    legacy = list(context.electrical.legacy_context)
    if legacy[0] is None:
        legacy[0] = {}
    base = SimpleNamespace(legacy_context=tuple(legacy), source_root=source_root(SOURCE_DATA_REPOSITORY),
        voltage=context.electrical.voltage,current=context.electrical.current,
        voltage_path=context.electrical.voltage_path,
        current_path=Path(context.electrical.voltage_path).with_name(f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"))
    actual = with_realized_background(SOURCE_DATA_REPOSITORY, base, timestamps_96=exogenous["timestamps"],
        demand_mw_96=exogenous["demand_mw"],pv_mw_96=exogenous["pv_mw"],aidc_plan_kw_96x12=power["PCC_P"])
    trajectory = FrozenTrajectory(day, "ACTUAL", case, power["PCC_P"], power["PCC_Q"],
        mess["p"],mess["q"],tuple(mess["ids"]),mess["locations"],identity)
    before = trajectory.immutable_sha256
    with engine_binding_observer(power,mess,output) as engine_audit:
        result = run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=actual,voltage=context.electrical.voltage,
                                  trajectory=trajectory,output=Path(output))
    rho_audit=rho_recalculation(result,output)
    if before != trajectory.immutable_sha256:
        raise ReplayError("ACTUAL_GRID_INPUT_MUTATED")
    audit = {"status": "PASS", "trajectory_identity": before, "pcc_P_binding_bit_equal": np.array_equal(trajectory.pcc_p_kw,power["PCC_P"]),
        "pcc_Q_binding_bit_equal": np.array_equal(trajectory.pcc_q_kvar,power["PCC_Q"]),
        "OpenDSS_namespace": result.namespace, "OpenDSS_slots": result.summary["convergence_count"],
        "Actual_AC_restoration_calls": 0, "native_control_rule": "INHERITED_APPLY_FROZEN_NATIVE_STATE_NO_NEW_CONTROL_POLICY",
        "actual_physical_violations_are_results_not_repaired": True,
        "engine_readback":engine_audit,"Actual_rho_recalculation":rho_audit,
        "AIDC_injection_mapping": "AIDC01..12 positive consumption -> Load.IDC_IDC01..12"}
    return result, audit
