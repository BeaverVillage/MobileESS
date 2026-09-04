#!/usr/bin/env python3
"""Fail once, before spawning April workers, when the local runtime is incomplete."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.source_manifest import verify_day_manifest  # noqa: E402
from dayahead.v28r2.backend_contract import DAY_WORKERS, GUROBI_THREADS  # noqa: E402
from dayahead.v28r2.source_preflight import APRIL_DAYS, day_root  # noqa: E402
from tools.final_campaign.run_v28r2_april import verify_launch_gates  # noqa: E402


REQUIRED_MODULES = (
    "numpy", "pandas", "pyarrow", "scipy", "sklearn", "lightgbm",
    "gurobipy", "opendssdirect", "psutil", "requests", "eccodes",
)


def check_runtime(repo: Path = REPO) -> dict[str, object]:
    versions: dict[str, str] = {}
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(name)
            versions[name] = str(getattr(module, "__version__", "AVAILABLE"))
        except Exception as error:
            missing.append(f"{name} ({type(error).__name__}: {error})")
    if missing:
        raise RuntimeError("V28R2_RUNTIME_DEPENDENCIES_MISSING: " + "; ".join(missing))

    import gurobipy as gp
    import opendssdirect as dss

    model = gp.Model("V28R2_WSL_PREFLIGHT")
    model.Params.OutputFlag = 0
    model.Params.Threads = GUROBI_THREADS
    model.dispose()
    verified_days = 0
    for day in APRIL_DAYS:
        path = day_root(repo, day) / "source_day_manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        verify_day_manifest(payload, base_dir=path.parent)
        verified_days += 1
    verify_launch_gates(repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_IMPLEMENTATION_READY_FLAGS.json")
    # Import the exact production graph and construct the first child contract.
    # This catches worktree/Git metadata and deferred-import failures once in the
    # parent instead of allowing thirty identical child failures.
    from dayahead.v28r2.production_handlers import ProductionHandlers, build_day_run_spec
    from dayahead.v28r2.lightgbm_channels import causal_optimizer_predictions
    from dayahead.v28r2.source_labels import load_optimizer_labels
    import numpy as np

    spec = build_day_run_spec(repo, APRIL_DAYS[0], "authority-preflight")
    spec.validate()
    production = ProductionHandlers(
        spec=spec, repo=repo, day_output=repo,
        state_path=repo / "DAY_STATE.json", mode="authority-preflight",
    )
    if len(production.handlers) != 30:
        raise RuntimeError("V28R2_PRODUCTION_HANDLER_COUNT")
    model_dir = repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_MODELS"
    p_quantiles, g_quantiles, w_quantiles = causal_optimizer_predictions(
        load_optimizer_labels(repo), APRIL_DAYS[-1], model_dir,
    )
    if (
        p_quantiles.shape != (3, 96)
        or g_quantiles.shape != (3, 96)
        or w_quantiles.shape != (3,)
        or not all(np.isfinite(values).all() for values in (p_quantiles, g_quantiles, w_quantiles))
    ):
        raise RuntimeError("V28R2_APRIL_OPTIMIZER_ROLLOUT_INVALID")
    return {
        "status": "PASS",
        "python": sys.version.split()[0],
        "dependencies": versions,
        "gurobi": ".".join(map(str, gp.gurobi.version())),
        "opendss": str(dss.Basic.Version()).splitlines()[0],
        "source_days_verified": verified_days,
        "production_contract_sha256": spec.sha256,
        "production_handlers_verified": 30,
        "optimizer_rollout_verified_through": APRIL_DAYS[-1],
        "day_workers": DAY_WORKERS,
        "gurobi_threads": GUROBI_THREADS,
    }


def main() -> int:
    try:
        result = check_runtime()
    except Exception as error:
        print(f"[실행 준비 FAIL] {error}", file=sys.stderr)
        return 2
    print(
        "[실행 준비 PASS] "
        f"Python {result['python']} | Gurobi {result['gurobi']} | "
        f"sources {result['source_days_verified']}/30 | "
        f"workers {result['day_workers']} | threads {result['gurobi_threads']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
