#!/usr/bin/env python3
"""Run an injected R26 controller for a causal issue range.

The project-specific adapter factory must return an ``R26FastController``.  The
driver intentionally has no implicit fake or fallback physics.  Use
``r26.smoke_driver`` for the explicitly non-authoritative dependency-free smoke.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable

from .experiment import aggregate_metrics


def _load_factory(spec: str) -> Callable[..., Any]:
    if ":" not in spec:
        raise ValueError("adapter must use module:function syntax")
    module_name, function_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, function_name)
    if not callable(factory):
        raise TypeError("adapter factory is not callable")
    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, help="module:function controller factory")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-issue", type=int, default=113)
    parser.add_argument("--count", type=int, default=54)
    args = parser.parse_args(argv)
    if args.count <= 0:
        parser.error("--count must be positive")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    controller = _load_factory(args.adapter)(config=config, output=args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    try:
        for issue in range(args.start_issue, args.start_issue + args.count):
            result = controller.run_issue(issue)
            record = {
                "issue": result.issue,
                "status": result.status,
                "committed": result.committed,
                "runtime_seconds": result.runtime_seconds,
                "num_integer_vars": result.num_integer_vars,
                "formulation": result.formulation,
                "planner_disposition": result.planner_disposition,
                "objective": result.dispatch_objective,
                "travel_energy_kwh": result.operational_metrics.get("travel_energy_kwh"),
                "soc_reserve_margin_kwh": result.operational_metrics.get("soc_reserve_margin_kwh"),
                "rack_support_margin": result.operational_metrics.get("rack_support_margin"),
                "ac_violation_count": (
                    int(result.operational_metrics.get("ac_violation_count", 0))
                    + (1 if result.status == "FAIL_CLOSED_FRESH_OPENDSS_GATE" else 0)
                ),
            }
            records.append(record)
            print(json.dumps(record, sort_keys=True), flush=True)
            if not result.committed:
                break
    finally:
        controller.planner.close(wait=False)
    summary = {
        "schema_version": "r26.run_summary.v1",
        "requested_issues": args.count,
        "completed_records": len(records),
        "authoritative_offline_3pct_certificate": False,
        "ac_aware_qcp_required": True,
        "fresh_nonlinear_opendss_required": True,
        "metrics": aggregate_metrics(records),
        "records": records,
    }
    (args.output / "R26_RUN_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if len(records) == args.count and all(row["committed"] for row in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
