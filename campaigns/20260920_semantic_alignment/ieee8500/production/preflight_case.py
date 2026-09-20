"""Fail-closed input, scale, policy-domain and native-solver preflight."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import numpy as np

HERE = Path(__file__).absolute().parent


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    start = time.perf_counter()
    assert str(HERE).isascii()
    from fleet_binding import install, IDS
    install()
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    from headroom_authority import install_power_binding
    install_power_binding()
    from frozen_binding import context
    from electrical_engine import Engine
    import gurobipy as gp

    authorization = read(HERE / "PRODUCTION_AUTHORIZATION.json")
    assert authorization["date"] == "2025-05-01"
    assert authorization["policies"] == ["B0", "B1", "B2", "B3"]
    assert (authorization["background_scale"], authorization["aidc_scale"], authorization["MESS_scale"]) == (.45, 2.1, 2.)
    assert len(IDS) == 6
    a = MessElectricalAuthority.from_repository()
    a.validate()
    assert (a.active_power_limit_kw, a.pcs_kva, a.capacity_kwh, a.energy_min_kwh,
            a.energy_max_kwh, a.initial_energy_kwh, a.terminal_energy_kwh) == \
           (600., 800., 2400., 880., 2160., 1520., 1520.)
    assert a.charge_efficiency == a.discharge_efficiency == .95
    assert a.pcs_polygon_faces == 16
    diff = read(HERE / "CODE_DIFF.json")
    assert all(sha(row["source"]) == row["source_sha256"] and
               sha(row["override"]) == row["override_sha256"] for row in diff)
    baseline = read(HERE / "B0_REPLAY/AC_VALIDATION.json")
    assert baseline["status"] == "PASS" and len(baseline["slots"]) == 96
    assert all(r["converged"] and r["controls_settled"] and r["feasible"] for r in baseline["slots"])
    e = Engine(HERE / "preflight/runtime")
    try:
        with np.load(HERE / "MAY01_B0_AIDC_POWER.npz") as z:
            assert max(float(np.max(np.abs(e.ap - z["pcc"]))),
                       float(np.max(np.abs(e.aq - z["qcc"])))) < 1e-12
            with np.load(HERE / "NORMALIZED_B0_AIDC_POWER.npz") as raw:
                arrays = {k: float(np.max(np.abs(z[k] - raw[k] * 4.2))) for k in raw.files}
            assert max(arrays.values()) < 1e-10
    finally:
        e.close()
    ctx = context()
    with np.load(HERE / "MAY01_B0_AIDC_POWER.npz") as z:
        pcc_error = float(np.max(np.abs(ctx.power["pcc"] - z["pcc"])))
        qcc_error = float(np.max(np.abs(ctx.power["qcc"] - z["qcc"])))
        it_error = float(np.max(np.abs(ctx.power["it"] * 4.2 - z["it"])))
        gpu_error = float(np.max(np.abs(ctx.power["gpu"] * 4.2 - z["gpu"])))
    assert max(pcc_error, qcc_error, it_error, gpu_error) < 1e-8
    assert len(ctx.options) == 1649 and sum(map(len, ctx.options.values())) == 7563689
    assert sum(ctx.capacity.site_capacity.values()) == 1312
    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 0)
        env.setParam("Threads", 4)
        env.start()
        with gp.Model("FINAL_MAY01_SOLVER_SMOKE", env=env) as model:
            x = model.addVar(lb=1)
            model.setObjective(x)
            model.optimize()
            assert model.Status == gp.GRB.OPTIMAL and abs(x.X - 1) < 1e-9
    result = dict(status="PASS", date="2025-05-01", slots=96, policies=authorization["policies"],
                  background_scale=.45, AIDC_scale=2.1, MESS_scale=2.,
                  AIDC_normalized_domain_jobs=len(ctx.options),
                  AIDC_legal_candidate_options=sum(map(len, ctx.options.values())),
                  AIDC_physical_C1_factor=4.2, AIDC_baseline_array_errors=arrays,
                  pcc_error_kw=pcc_error, qcc_error_kvar=qcc_error,
                  it_error_kw=it_error, gpu_equivalent_error=gpu_error,
                  MESS_authority=vars(a), MESS_fleet=len(IDS),
                  source_override_hashes_match=True, no_screening_policy_solution_import=True,
                  source_layout_SHA=sha(HERE / "LAYOUT.json"),
                  source_overlay_SHA=sha(HERE / "PCC_OVERLAY.dss"),
                  source_pcc_inventory_SHA=sha(HERE / "PCC_OVERLAY_INVENTORY.json"),
                  B0_exact_rho=baseline["metrics"]["max_phase_line_loading_pu"],
                  runtime_seconds=time.perf_counter() - start, workers=1, threads=4)
    save(HERE / "FINAL_CASE_PREFLIGHT.json", result)
    print("FINAL_CASE_PREFLIGHT_PASS", result["B0_exact_rho"], flush=True)


if __name__ == "__main__":
    main()
